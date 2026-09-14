"""Deterministic payment-intent, link, webhook, and reconciliation behavior."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from services.api.config import get_settings
from services.domain.auth import TrustedContext
from services.domain.canonical import canonical_sha256
from services.domain.enums import PaymentStatus
from services.domain.errors import ConflictError, NotFoundError, ValidationError
from services.domain.models import (
    ExternalAction,
    Job,
    PaymentAttempt,
    PaymentLinkAttempt,
    PaymentObservation,
    PaymentRequest,
    PaymentWebhookIngress,
    ProposalRevision,
    utc_now,
)
from services.integrations.razorpay import (
    RazorpayProvider,
    RazorpayProviderError,
    RazorpayProviderRetryable,
)
from services.workers.durable import (
    begin_action_dispatch,
    complete_action,
    enqueue_job,
    mark_action_review_required,
    mark_action_unknown,
    prepare_external_action,
)

REFERENCE_PREFIX = "sg-"
TEST_ENVIRONMENT = "test"


class PaymentProvider(Protocol):
    account_id: str
    environment: str

    def create_payment_link(self, payload: dict[str, object]) -> dict[str, object]: ...

    def fetch_payment_link(self, provider_link_id: str) -> dict[str, object]: ...

    def list_payment_links(self, *, reference_id: str) -> list[dict[str, object]]: ...

    def cancel_payment_link(self, provider_link_id: str) -> dict[str, object]: ...


class PaymentDispatchResult(Protocol):
    id: UUID


def payment_reference(payment_request_id: UUID, attempt_number: int = 1) -> str:
    """Return a stable provider reference within Razorpay's 40-character limit."""
    return (
        REFERENCE_PREFIX
        + hashlib.sha256(f"{payment_request_id}:{attempt_number}".encode("ascii")).hexdigest()[:36]
    )


def read_payment_request(
    session: Session,
    context: TrustedContext,
    *,
    payment_request_id: UUID,
    job_id: UUID | None = None,
) -> dict[str, object]:
    payment = _payment(session, context, payment_request_id)
    link = _active_link(session, payment)
    collected = 0
    if link is not None:
        collected = sum(
            session.scalars(
                select(PaymentAttempt.amount_minor).where(
                    PaymentAttempt.link_attempt_id == link.id,
                    PaymentAttempt.captured.is_(True),
                )
            )
        )
    return {
        "id": payment.id,
        "project_id": payment.project_id,
        "accepted_revision_id": payment.accepted_revision_id,
        "total_minor": payment.total_minor,
        "tax_minor": payment.tax_minor,
        "currency": payment.currency,
        "status": payment.status,
        "due_at": payment.due_at,
        "expire_at": payment.expire_at,
        "paid_at": payment.paid_at,
        "row_version": payment.row_version,
        "provider_link_id": link.provider_link_id if link else None,
        "payment_link_url": link.short_url if link else None,
        "payment_link_status": link.provider_status if link else None,
        "collected_minor": collected,
        "job_id": job_id,
    }


def _payment(
    session: Session, context: TrustedContext, payment_request_id: UUID, *, lock: bool = False
) -> PaymentRequest:
    query = select(PaymentRequest).where(
        PaymentRequest.id == payment_request_id,
        PaymentRequest.tenant_id == context.tenant_id,
    )
    if lock:
        query = query.with_for_update()
    payment = session.scalar(query)
    if payment is None:
        raise NotFoundError("Payment request was not found")
    return payment


def _revision(session: Session, payment: PaymentRequest) -> ProposalRevision:
    revision = session.scalar(
        select(ProposalRevision).where(
            ProposalRevision.id == payment.accepted_revision_id,
            ProposalRevision.tenant_id == payment.tenant_id,
        )
    )
    if revision is None:
        raise ConflictError("Accepted proposal revision is unavailable")
    return revision


def _transition(
    payment: PaymentRequest, target: PaymentStatus, *, reason: str | None = None
) -> None:
    current = PaymentStatus(payment.status)
    if current is target:
        return
    if current is PaymentStatus.REVERSED:
        return
    if current is PaymentStatus.PAID and target is not PaymentStatus.REVERSED:
        return
    if target is PaymentStatus.REVIEW_REQUIRED:
        if current not in {
            PaymentStatus.CREATION_PENDING,
            PaymentStatus.PENDING,
            PaymentStatus.REVIEW_REQUIRED,
        }:
            raise ConflictError(f"Payment cannot enter review from {current.value}")
    else:
        transitions = {
            (PaymentStatus.CREATION_PENDING, PaymentStatus.PENDING),
            (PaymentStatus.PENDING, PaymentStatus.PAID),
            (PaymentStatus.REVIEW_REQUIRED, PaymentStatus.PAID),
            (PaymentStatus.PENDING, PaymentStatus.EXPIRED),
            (PaymentStatus.PENDING, PaymentStatus.CANCELLED),
            (PaymentStatus.EXPIRED, PaymentStatus.PENDING),
            (PaymentStatus.CANCELLED, PaymentStatus.PENDING),
            (PaymentStatus.EXPIRED, PaymentStatus.PAID),
            (PaymentStatus.PAID, PaymentStatus.REVERSED),
        }
        if (current, target) not in transitions:
            raise ConflictError(f"Payment cannot transition from {current.value} to {target.value}")
    payment.status = target.value
    payment.row_version += 1
    if target is PaymentStatus.PAID:
        payment.paid_at = payment.paid_at or utc_now()
    if reason:
        del reason


def _active_link(session: Session, payment: PaymentRequest) -> PaymentLinkAttempt | None:
    return session.scalar(
        select(PaymentLinkAttempt)
        .where(
            PaymentLinkAttempt.payment_request_id == payment.id,
            PaymentLinkAttempt.tenant_id == payment.tenant_id,
            PaymentLinkAttempt.status == "CREATED",
        )
        .order_by(PaymentLinkAttempt.attempt_number.desc())
        .limit(1)
    )


def _action_for_payment(session: Session, payment: PaymentRequest) -> ExternalAction | None:
    return session.scalar(
        select(ExternalAction).where(
            ExternalAction.tenant_id == payment.tenant_id,
            ExternalAction.action_key == f"payment-link-create:{payment.id}",
        )
    )


def prepare_payment_link(
    session: Session, context: TrustedContext, *, payment_request_id: UUID
) -> tuple[ExternalAction, object | None]:
    payment = _payment(session, context, payment_request_id, lock=True)
    if payment.status not in {PaymentStatus.CREATION_PENDING.value, PaymentStatus.PENDING.value}:
        raise ConflictError("Payment request is not eligible for link creation")
    existing_link = _active_link(session, payment)
    if existing_link is not None:
        action = (
            session.get(ExternalAction, existing_link.action_id)
            if existing_link.action_id
            else None
        )
        if action is not None:
            return action, None
    attempt_number = (
        session.scalar(
            select(func.max(PaymentLinkAttempt.attempt_number)).where(
                PaymentLinkAttempt.payment_request_id == payment.id
            )
        )
        or 0
    ) + 1
    if attempt_number > 3:
        raise ConflictError("Payment link replacement limit has been reached")
    revision = _revision(session, payment)
    settings = get_settings()
    account_id = str(settings.razorpay_account_id or "fixture-account").strip()
    if str(settings.razorpay_environment or TEST_ENVIRONMENT).strip().lower() != TEST_ENVIRONMENT:
        raise ConflictError("Only Razorpay Test Mode payment links are allowed")
    if payment.due_at is None:
        payment.due_at = utc_now() + timedelta(days=7)
    if payment.expire_at is None:
        payment.expire_at = payment.due_at + timedelta(days=7)
    reference = payment_reference(payment.id, attempt_number)
    payload: dict[str, object] = {
        "amount": payment.total_minor,
        "currency": payment.currency,
        "accept_partial": False,
        "reference_id": reference,
        "description": f"ScopeGuard payment request {reference}",
        "customer": {"email": revision.recipient_email},
        "notify": {"email": False, "sms": False},
        "reminder_enable": False,
        "expire_by": int(payment.expire_at.timestamp()),
    }
    action = prepare_external_action(
        session,
        tenant_id=payment.tenant_id,
        project_id=payment.project_id,
        action_key=f"payment-link-create:{payment.id}:{attempt_number}",
        provider="razorpay",
        operation="payment_links.create",
        approved_payload={
            **payload,
            "provider_account_id": account_id,
            "provider_environment": TEST_ENVIRONMENT,
        },
    )
    attempt = session.scalar(
        select(PaymentLinkAttempt).where(
            PaymentLinkAttempt.payment_request_id == payment.id,
            PaymentLinkAttempt.attempt_number == attempt_number,
        )
    )
    if attempt is None:
        attempt = PaymentLinkAttempt(
            tenant_id=payment.tenant_id,
            project_id=payment.project_id,
            payment_request_id=payment.id,
            attempt_number=attempt_number,
            provider_account_id=account_id,
            provider_environment=TEST_ENVIRONMENT,
            reference_id=reference,
            amount_minor=payment.total_minor,
            currency=payment.currency,
            action_id=action.id,
        )
        session.add(attempt)
        session.flush()
    if payment.status == PaymentStatus.CREATION_PENDING.value:
        payment.updated_at = utc_now()
    job = enqueue_job(
        session,
        tenant_id=payment.tenant_id,
        project_id=payment.project_id,
        kind="payment.create",
        payload_ref={"payment_request_id": str(payment.id), "action_id": str(action.id)},
        correlation_id=context.correlation_id,
    )
    return action, job


def _payment_link_attempt(session: Session, action: ExternalAction) -> PaymentLinkAttempt:
    attempt = session.scalar(
        select(PaymentLinkAttempt)
        .where(PaymentLinkAttempt.action_id == action.id)
        .with_for_update()
    )
    if attempt is None:
        raise ConflictError("Payment link attempt is missing")
    return attempt


def _validate_link_response(
    attempt: PaymentLinkAttempt, response: Mapping[str, object]
) -> tuple[str, str, str, str | None]:
    provider_id = str(response.get("id") or "").strip()
    short_url = str(response.get("short_url") or "").strip()
    currency = str(response.get("currency") or "").strip().upper()
    amount = response.get("amount")
    reference = str(response.get("reference_id") or "").strip()
    order_id = str(response.get("order_id") or "").strip() or None
    if not provider_id or not short_url:
        raise RazorpayProviderError("razorpay_link_identity_missing")
    if (
        amount != attempt.amount_minor
        or currency != attempt.currency
        or reference != attempt.reference_id
    ):
        raise RazorpayProviderError("razorpay_link_terms_mismatch")
    return provider_id, short_url, str(response.get("status") or "created"), order_id


def dispatch_payment_link(
    session: Session, *, action_id: UUID, provider: PaymentProvider | None = None
) -> str:
    action = session.get(ExternalAction, action_id, with_for_update=True)
    if (
        action is None
        or action.provider != "razorpay"
        or action.operation != "payment_links.create"
    ):
        raise NotFoundError("Payment link action was not found")
    attempt = _payment_link_attempt(session, action)
    payment = session.get(PaymentRequest, attempt.payment_request_id, with_for_update=True)
    if payment is None:
        raise NotFoundError("Payment request was not found")
    if action.state == "SUCCEEDED" and attempt.provider_link_id:
        return attempt.provider_link_id
    if payment.status not in {PaymentStatus.CREATION_PENDING.value, PaymentStatus.PENDING.value}:
        raise ConflictError("Payment request is no longer eligible for link dispatch")
    provider_client = provider if provider is not None else RazorpayProvider.from_settings()
    if (
        provider_client.environment != TEST_ENVIRONMENT
        or provider_client.account_id != attempt.provider_account_id
    ):
        raise ConflictError("Razorpay provider identity does not match the frozen payment intent")
    begin_action_dispatch(session, action_id=action.id)
    try:
        response = provider_client.create_payment_link(dict(action.approved_payload))
        provider_id, short_url, provider_status, provider_order_id = _validate_link_response(
            attempt, response
        )
    except RazorpayProviderRetryable as exc:
        attempt.status = "UNKNOWN_OUTCOME"
        _transition(payment, PaymentStatus.REVIEW_REQUIRED, reason="provider_request_uncertain")
        mark_action_unknown(session, action_id=action.id, reason=str(exc))
        raise
    except RazorpayProviderError as exc:
        attempt.status = "REVIEW_REQUIRED"
        _transition(payment, PaymentStatus.REVIEW_REQUIRED, reason=str(exc))
        mark_action_review_required(session, action_id=action.id, reason=str(exc))
        raise
    except Exception as exc:
        attempt.status = "UNKNOWN_OUTCOME"
        _transition(payment, PaymentStatus.REVIEW_REQUIRED, reason="provider_request_uncertain")
        mark_action_unknown(session, action_id=action.id, reason=type(exc).__name__)
        raise
    attempt.status = "CREATED"
    attempt.provider_link_id = provider_id
    attempt.provider_order_id = provider_order_id
    attempt.short_url = short_url
    attempt.provider_status = provider_status
    attempt.provider_payload = dict(response)
    _transition(payment, PaymentStatus.PENDING)
    complete_action(
        session,
        action_id=action.id,
        provider_request_id=provider_id,
        outcome_ref={
            "provider": "razorpay",
            "operation": "payment_links.create",
            "provider_link_id": provider_id,
        },
    )
    return provider_id


def _entity(payload: Mapping[str, object], name: str) -> dict[str, object]:
    parent = payload.get("payload")
    if not isinstance(parent, Mapping):
        return {}
    value = parent.get(name)
    if not isinstance(value, Mapping):
        return {}
    entity = value.get("entity")
    return dict(entity) if isinstance(entity, Mapping) else {}


def accept_payment_webhook(
    session: Session,
    *,
    provider_account_id: str,
    provider_environment: str,
    provider_event_id: str,
    event_type: str,
    payload: dict[str, object],
    signature_verified: bool,
    observed_at: datetime | None = None,
) -> tuple[PaymentWebhookIngress, Job | None]:
    """Persist an authenticated raw webhook before any business normalization."""
    if provider_environment != TEST_ENVIRONMENT:
        raise ValidationError("Only Razorpay Test Mode webhooks are accepted")
    if not signature_verified:
        raise ValidationError("Razorpay webhook signature is invalid")
    account_id = provider_account_id.strip()
    kind = event_type.strip()
    if not account_id or not kind:
        raise ValidationError("Razorpay webhook identity is incomplete")
    event_id = provider_event_id.strip() or canonical_sha256(payload)
    existing = session.scalar(
        select(PaymentWebhookIngress).where(
            PaymentWebhookIngress.provider_account_id == account_id,
            PaymentWebhookIngress.provider_environment == provider_environment,
            PaymentWebhookIngress.provider_event_id == event_id,
        )
    )
    if existing is not None:
        return existing, None

    ingress = PaymentWebhookIngress(
        provider_account_id=account_id,
        provider_environment=provider_environment,
        provider_event_id=event_id,
        event_type=kind,
        signature_verified=True,
        raw_payload=payload,
        received_at=observed_at or utc_now(),
    )
    session.add(ingress)
    session.flush()

    link = _entity(payload, "payment_link")
    link_id = str(link.get("id") or "").strip()
    reference_id = str(link.get("reference_id") or "").strip()
    attempt = None
    if link_id:
        attempt = session.scalar(
            select(PaymentLinkAttempt).where(
                PaymentLinkAttempt.provider_link_id == link_id,
                PaymentLinkAttempt.provider_account_id == account_id,
                PaymentLinkAttempt.provider_environment == provider_environment,
            )
        )
    if attempt is None and reference_id:
        attempt = session.scalar(
            select(PaymentLinkAttempt)
            .where(
                PaymentLinkAttempt.reference_id == reference_id,
                PaymentLinkAttempt.provider_account_id == account_id,
                PaymentLinkAttempt.provider_environment == provider_environment,
            )
            .order_by(PaymentLinkAttempt.attempt_number.desc())
            .limit(1)
        )

    job = None
    if attempt is not None:
        job = enqueue_job(
            session,
            tenant_id=attempt.tenant_id,
            project_id=attempt.project_id,
            kind="payment.webhook.normalize",
            payload_ref={"ingress_id": str(ingress.id)},
            correlation_id=uuid4(),
        )
    return ingress, job


def normalize_payment_webhook(
    session: Session,
    *,
    ingress_id: UUID,
    expected_tenant_id: UUID | None = None,
) -> PaymentObservation:
    ingress = session.get(PaymentWebhookIngress, ingress_id, with_for_update=True)
    if ingress is None:
        raise NotFoundError("Payment webhook ingress was not found")
    if expected_tenant_id is not None:
        link = _entity(ingress.raw_payload, "payment_link")
        link_id = str(link.get("id") or "").strip()
        reference_id = str(link.get("reference_id") or "").strip()
        statement = select(PaymentLinkAttempt).where(
            PaymentLinkAttempt.provider_account_id == ingress.provider_account_id,
            PaymentLinkAttempt.provider_environment == ingress.provider_environment,
        )
        if link_id:
            statement = statement.where(PaymentLinkAttempt.provider_link_id == link_id)
        elif reference_id:
            statement = statement.where(PaymentLinkAttempt.reference_id == reference_id)
        else:
            raise NotFoundError("Payment webhook target was not found")
        target = session.scalar(
            statement.order_by(PaymentLinkAttempt.attempt_number.desc()).limit(1)
        )
        if target is None or target.tenant_id != expected_tenant_id:
            raise NotFoundError("Payment webhook target was not found")
    if ingress.normalization_state == "NORMALIZED" and ingress.observation_id is not None:
        observation = session.get(PaymentObservation, ingress.observation_id)
        if observation is None:
            raise ConflictError("Normalized payment webhook observation is missing")
        if expected_tenant_id is not None and observation.tenant_id != expected_tenant_id:
            raise NotFoundError("Payment webhook target was not found")
        return observation
    try:
        observation = observe_payment_event(
            session,
            provider_account_id=ingress.provider_account_id,
            provider_environment=ingress.provider_environment,
            provider_event_id=ingress.provider_event_id,
            event_type=ingress.event_type,
            payload=ingress.raw_payload,
            signature_verified=ingress.signature_verified,
            observed_at=ingress.received_at,
        )
    except Exception as exc:
        ingress.normalization_state = "REVIEW_REQUIRED"
        ingress.last_error = type(exc).__name__[:120]
        session.flush()
        raise
    ingress.normalization_state = "NORMALIZED"
    ingress.observation_id = observation.id
    ingress.normalized_at = utc_now()
    ingress.last_error = None
    session.flush()
    return observation


def normalize_pending_payment_webhooks(session: Session, *, limit: int = 100) -> int:
    ingress_ids = list(
        session.scalars(
            select(PaymentWebhookIngress.id)
            .where(PaymentWebhookIngress.normalization_state == "PENDING")
            .order_by(PaymentWebhookIngress.received_at, PaymentWebhookIngress.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    normalized = 0
    for ingress_id in ingress_ids:
        try:
            with session.begin_nested():
                normalize_payment_webhook(session, ingress_id=ingress_id)
        except Exception:
            continue
        normalized += 1
    return normalized


def observe_payment_event(
    session: Session,
    *,
    provider_account_id: str,
    provider_environment: str,
    provider_event_id: str,
    event_type: str,
    payload: dict[str, object],
    signature_verified: bool,
    observed_at: datetime | None = None,
) -> PaymentObservation:
    if provider_environment != TEST_ENVIRONMENT:
        raise ValidationError("Only Razorpay Test Mode observations are accepted")
    if not signature_verified:
        raise ValidationError("Razorpay webhook signature is invalid")
    event_id = (
        provider_event_id.strip()
        or hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    )
    existing = session.scalar(
        select(PaymentObservation).where(
            PaymentObservation.provider_account_id == provider_account_id,
            PaymentObservation.provider_environment == provider_environment,
            PaymentObservation.provider_event_id == event_id,
        )
    )
    if existing is not None:
        return existing
    link = _entity(payload, "payment_link")
    payment_entity = _entity(payload, "payment")
    link_id = str(link.get("id") or "").strip() or None
    payment_id = str(payment_entity.get("id") or "").strip() or None
    order = _entity(payload, "order")
    order_id = str(payment_entity.get("order_id") or order.get("id") or "").strip() or None
    reference = str(link.get("reference_id") or "").strip() or None
    raw_amount = payment_entity.get("amount", link.get("amount_paid", link.get("amount")))
    amount = (
        int(raw_amount)
        if isinstance(raw_amount, int) and not isinstance(raw_amount, bool)
        else None
    )
    currency = (
        str(payment_entity.get("currency") or link.get("currency") or "").strip().upper() or None
    )
    observed_status = str(payment_entity.get("status") or link.get("status") or event_type).strip()
    attempt = None
    if link_id:
        attempt = session.scalar(
            select(PaymentLinkAttempt).where(PaymentLinkAttempt.provider_link_id == link_id)
        )
    request = (
        session.get(PaymentRequest, attempt.payment_request_id) if attempt is not None else None
    )
    capture_event = event_type.lower() in {
        "payment_link.paid",
        "payment.captured",
        "payment.authorized",
    }
    mismatch = (
        attempt is None
        or attempt.provider_account_id != provider_account_id
        or attempt.provider_environment != provider_environment
        or reference != attempt.reference_id
        or amount != attempt.amount_minor
        or currency != attempt.currency
        or (capture_event and not order_id)
        or (
            attempt is not None
            and attempt.provider_order_id is not None
            and order_id != attempt.provider_order_id
        )
    )
    payment_attempt = None
    if payment_id:
        payment_attempt = session.scalar(
            select(PaymentAttempt).where(PaymentAttempt.provider_payment_id == payment_id)
        )
    if payment_attempt is None and payment_id:
        payment_attempt = PaymentAttempt(
            tenant_id=request.tenant_id if request else None,
            project_id=request.project_id if request else None,
            link_attempt_id=attempt.id if attempt else None,
            provider_payment_id=payment_id,
            provider_order_id=order_id,
            amount_minor=amount or 0,
            currency=currency or "INR",
            status=observed_status,
            captured=observed_status.lower() in {"captured", "paid"},
            provider_payload=payment_entity or None,
        )
        if amount is not None and 0 < amount <= 100000000:
            session.add(payment_attempt)
            session.flush()
        else:
            payment_attempt = None
    observation = PaymentObservation(
        tenant_id=request.tenant_id if request else None,
        project_id=request.project_id if request else None,
        payment_request_id=request.id if request else None,
        link_attempt_id=attempt.id if attempt else None,
        payment_attempt_id=payment_attempt.id if payment_attempt else None,
        provider_account_id=provider_account_id,
        provider_environment=provider_environment,
        provider_event_id=event_id,
        event_type=event_type,
        provider_link_id=link_id,
        provider_payment_id=payment_id,
        provider_order_id=order_id,
        reference_id=reference,
        amount_minor=amount,
        currency=currency,
        observed_status=observed_status,
        signature_verified=True,
        raw_payload=payload,
        observed_at=observed_at or utc_now(),
        association_state="ASSOCIATED"
        if request is not None and attempt is not None
        else "UNMATCHED",
        next_retry_at=None
        if request is not None and attempt is not None
        else (observed_at or utc_now()) + timedelta(hours=24),
        associated_at=observed_at or utc_now()
        if request is not None and attempt is not None
        else None,
    )
    session.add(observation)
    session.flush()
    if request is None or attempt is None:
        return observation
    if mismatch:
        attempt.status = "REVIEW_REQUIRED"
        _transition(request, PaymentStatus.REVIEW_REQUIRED, reason="provider_observation_mismatch")
        return observation
    lower_event = event_type.lower()
    if capture_event and not mismatch and attempt.provider_order_id is None:
        attempt.provider_order_id = order_id
    if lower_event in {"payment_link.paid", "payment.captured", "payment.authorized"} and (
        payment_attempt is None or not payment_attempt.captured
    ):
        attempt.status = "REVIEW_REQUIRED"
        _transition(request, PaymentStatus.REVIEW_REQUIRED, reason="capture_not_verified")
    elif lower_event in {"payment_link.paid", "payment.captured"}:
        _transition(request, PaymentStatus.PAID)
    elif lower_event in {"payment_link.expired", "payment.expired"}:
        attempt.status = "EXPIRED"
        if request.status == PaymentStatus.PENDING.value:
            _transition(request, PaymentStatus.EXPIRED)
    elif lower_event in {"payment_link.cancelled", "payment_link.canceled"}:
        attempt.status = "CANCELLED"
        if request.status == PaymentStatus.PENDING.value:
            _transition(request, PaymentStatus.CANCELLED)
    return observation


def replay_unmatched_payment_observations(
    session: Session, *, now: datetime | None = None, limit: int = 100
) -> int:
    """Associate durable orphan observations after a link or local save becomes visible."""
    current = now or utc_now()
    observations = session.scalars(
        select(PaymentObservation)
        .where(PaymentObservation.association_state == "UNMATCHED")
        .order_by(PaymentObservation.observed_at, PaymentObservation.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()
    associated = 0
    for observation in observations:
        attempt = None
        if observation.provider_link_id:
            attempt = session.scalar(
                select(PaymentLinkAttempt).where(
                    PaymentLinkAttempt.provider_link_id == observation.provider_link_id,
                    PaymentLinkAttempt.provider_account_id == observation.provider_account_id,
                    PaymentLinkAttempt.provider_environment == observation.provider_environment,
                )
            )
        if attempt is None and observation.reference_id:
            attempt = session.scalar(
                select(PaymentLinkAttempt)
                .where(
                    PaymentLinkAttempt.reference_id == observation.reference_id,
                    PaymentLinkAttempt.provider_account_id == observation.provider_account_id,
                    PaymentLinkAttempt.provider_environment == observation.provider_environment,
                )
                .order_by(PaymentLinkAttempt.attempt_number.desc())
            )
        request = session.get(PaymentRequest, attempt.payment_request_id) if attempt else None
        exact = bool(
            attempt is not None
            and request is not None
            and observation.reference_id == attempt.reference_id
            and observation.amount_minor == attempt.amount_minor
            and observation.currency == attempt.currency
        )
        if exact:
            assert attempt is not None
            assert request is not None
            observation.tenant_id = request.tenant_id
            observation.project_id = request.project_id
            observation.payment_request_id = request.id
            observation.link_attempt_id = attempt.id
            if observation.provider_payment_id:
                payment_attempt = session.scalar(
                    select(PaymentAttempt).where(
                        PaymentAttempt.provider_payment_id == observation.provider_payment_id
                    )
                )
                if (
                    payment_attempt is None
                    and observation.amount_minor is not None
                    and observation.currency
                ):
                    payment_attempt = PaymentAttempt(
                        tenant_id=request.tenant_id,
                        project_id=request.project_id,
                        link_attempt_id=attempt.id,
                        provider_payment_id=observation.provider_payment_id,
                        provider_order_id=observation.provider_order_id,
                        amount_minor=observation.amount_minor,
                        currency=observation.currency,
                        status=observation.observed_status,
                        captured=observation.observed_status.lower() in {"captured", "paid"},
                        provider_payload=observation.raw_payload,
                    )
                    session.add(payment_attempt)
                    session.flush()
                if payment_attempt is not None:
                    payment_attempt.link_attempt_id = attempt.id
                    observation.payment_attempt_id = payment_attempt.id
            observation.association_state = "ASSOCIATED"
            observation.associated_at = current
            observation.next_retry_at = None
            capture = observation.event_type.lower() in {"payment_link.paid", "payment.captured"}
            if (
                capture
                and observation.payment_attempt_id is not None
                and observation.amount_minor == request.total_minor
            ):
                if attempt.provider_order_id is None:
                    attempt.provider_order_id = observation.provider_order_id
                if (
                    observation.provider_order_id
                    and attempt.provider_order_id == observation.provider_order_id
                ):
                    attempt.status = "CREATED"
                    _transition(request, PaymentStatus.PAID)
            elif capture:
                attempt.status = "REVIEW_REQUIRED"
                _transition(
                    request, PaymentStatus.REVIEW_REQUIRED, reason="unmatched_capture_mismatch"
                )
            associated += 1
        elif observation.next_retry_at is not None and current >= observation.next_retry_at:
            observation.association_state = "MANUAL_REVIEW"
            observation.next_retry_at = None
    session.flush()
    return associated


def reconcile_payment_request(
    session: Session,
    context: TrustedContext,
    *,
    payment_request_id: UUID,
    provider: PaymentProvider | None = None,
) -> PaymentObservation:
    payment = _payment(session, context, payment_request_id, lock=True)
    attempt = session.scalar(
        select(PaymentLinkAttempt)
        .where(PaymentLinkAttempt.payment_request_id == payment.id)
        .order_by(PaymentLinkAttempt.attempt_number.desc())
        .limit(1)
        .with_for_update()
    )
    provider_client = provider if provider is not None else RazorpayProvider.from_settings()
    if provider_client.environment != TEST_ENVIRONMENT:
        raise ConflictError("Only Razorpay Test Mode reconciliation is allowed")
    if attempt is None:
        raise ConflictError("No persisted payment-link attempt is available for reconciliation")
    if provider_client.account_id != attempt.provider_account_id:
        raise ConflictError("Razorpay provider identity does not match the frozen payment intent")
    if not attempt.provider_link_id:
        lookup = getattr(provider_client, "list_payment_links", None)
        candidates = lookup(reference_id=attempt.reference_id) if callable(lookup) else []
        matches = [
            item
            for item in candidates
            if str(item.get("reference_id") or "").strip() == attempt.reference_id
            and item.get("amount") == attempt.amount_minor
            and str(item.get("currency") or "").upper() == attempt.currency
        ]
        if matches:
            response = matches[-1]
            attempt.provider_link_id = str(response.get("id") or "").strip() or None
            attempt.short_url = str(response.get("short_url") or "").strip() or None
            attempt.provider_status = str(response.get("status") or "created")
            attempt.provider_order_id = str(response.get("order_id") or "").strip() or None
            attempt.provider_payload = dict(response)
            if not attempt.provider_link_id:
                raise ConflictError("Provider returned a payment link without an identity")
        else:
            attempt.status = "UNKNOWN_OUTCOME"
            _transition(
                payment,
                PaymentStatus.REVIEW_REQUIRED,
                reason="provider_link_not_found_is_not_proof_of_absence",
            )
            raise ConflictError("Provider link was not found; outcome remains UNKNOWN_OUTCOME")
    response = provider_client.fetch_payment_link(attempt.provider_link_id)
    payments = response.get("payments")
    payment_entity = (
        payments[0]
        if isinstance(payments, list) and payments and isinstance(payments[0], dict)
        else None
    )
    payload_entity: dict[str, object] = {"payment_link": response}
    if payment_entity is not None:
        payload_entity["payment"] = payment_entity
    if response.get("order_id"):
        payload_entity["order"] = {"id": response.get("order_id")}
    status_value = str(response.get("status") or "").lower()
    raw_amount_paid = response.get("amount_paid")
    amount_paid = (
        raw_amount_paid
        if isinstance(raw_amount_paid, int) and not isinstance(raw_amount_paid, bool)
        else 0
    )
    event = (
        "payment_link.paid"
        if status_value == "paid" or amount_paid == payment.total_minor
        else "payment_link.expired"
        if status_value == "expired"
        else "payment_link.cancelled"
        if status_value in {"cancelled", "canceled"}
        else "payment_link.reconciled"
    )
    return observe_payment_event(
        session,
        provider_account_id=attempt.provider_account_id,
        provider_environment=attempt.provider_environment,
        provider_event_id=f"reconcile:{attempt.provider_link_id}:{canonical_sha256(response)}",
        event_type=event,
        payload={"event": event, "payload": payload_entity},
        signature_verified=True,
    )


def schedule_payment_maintenance(
    session: Session, *, now: datetime | None = None, limit: int = 100
) -> int:
    """Queue bounded pending and recent-paid reconciliation work."""
    current = now or utc_now()
    payments = session.scalars(
        select(PaymentRequest)
        .where(
            PaymentRequest.status.in_(
                (
                    PaymentStatus.PENDING.value,
                    PaymentStatus.REVIEW_REQUIRED.value,
                    PaymentStatus.PAID.value,
                )
            )
        )
        .order_by(PaymentRequest.updated_at, PaymentRequest.id)
        .limit(limit)
    ).all()
    created = 0
    for payment in payments:
        attempt = session.scalar(
            select(PaymentLinkAttempt)
            .where(
                PaymentLinkAttempt.payment_request_id == payment.id,
                PaymentLinkAttempt.provider_link_id.is_not(None),
            )
            .order_by(PaymentLinkAttempt.attempt_number.desc())
        )
        if attempt is None:
            continue
        interval = (
            timedelta(days=1)
            if payment.status == PaymentStatus.PAID.value
            else timedelta(minutes=15)
        )
        if payment.status == PaymentStatus.PAID.value and (
            payment.paid_at is None or payment.paid_at < current - timedelta(days=30)
        ):
            continue
        last_observation = session.scalar(
            select(PaymentObservation.created_at)
            .where(PaymentObservation.payment_request_id == payment.id)
            .order_by(PaymentObservation.created_at.desc())
            .limit(1)
        )
        if last_observation is not None and last_observation > current - interval:
            continue
        pending = session.scalars(
            select(Job).where(
                Job.tenant_id == payment.tenant_id,
                Job.kind == "payment.reconcile",
                Job.state.in_(("QUEUED", "RUNNING", "RETRY_WAIT")),
            )
        ).all()
        if any(
            str(job.payload_ref.get("payment_request_id") or "") == str(payment.id)
            for job in pending
        ):
            continue
        enqueue_job(
            session,
            tenant_id=payment.tenant_id,
            project_id=payment.project_id,
            kind="payment.reconcile",
            payload_ref={
                "payment_request_id": str(payment.id),
                "mode": "daily" if payment.status == PaymentStatus.PAID.value else "pending",
            },
            correlation_id=uuid4(),
        )
        created += 1
    session.flush()
    return created


def replace_payment_link(
    session: Session,
    context: TrustedContext,
    *,
    payment_request_id: UUID,
    expected_row_version: int,
) -> tuple[ExternalAction, object | None]:
    """Prepare a bounded replacement only after authoritative old-link closure."""
    payment = _payment(session, context, payment_request_id, lock=True)
    if payment.row_version != expected_row_version:
        raise ConflictError("Payment request changed; reload before replacing the link")
    if payment.status in {PaymentStatus.PAID.value, PaymentStatus.REVERSED.value}:
        raise ConflictError("A collected payment cannot be replaced")
    latest = session.scalar(
        select(PaymentLinkAttempt)
        .where(PaymentLinkAttempt.payment_request_id == payment.id)
        .order_by(PaymentLinkAttempt.attempt_number.desc())
        .limit(1)
    )
    if latest is None or latest.status not in {"EXPIRED", "CANCELLED"}:
        raise ConflictError(
            "Reconcile the prior link to authoritative expiry or cancellation before replacement"
        )
    if payment.status in {PaymentStatus.EXPIRED.value, PaymentStatus.CANCELLED.value}:
        _transition(payment, PaymentStatus.PENDING)
    return prepare_payment_link(session, context, payment_request_id=payment.id)
