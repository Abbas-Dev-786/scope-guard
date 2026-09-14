from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from services.domain.auth import TrustedContext
from services.domain.errors import NotFoundError
from services.domain.models import (
    Base,
    Job,
    PaymentLinkAttempt,
    PaymentObservation,
    PaymentRequest,
    PaymentWebhookIngress,
    ProposalRevision,
)
from services.payments import service as payment_service
from services.payments.service import (
    accept_payment_webhook,
    dispatch_payment_link,
    normalize_payment_webhook,
    observe_payment_event,
    payment_reference,
    prepare_payment_link,
    read_payment_request,
)
from services.workers.handlers import _action_for_job


@pytest.fixture
def payment_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[TrustedContext, sessionmaker[Session], UUID]:
    monkeypatch.setattr(
        payment_service,
        "get_settings",
        lambda: SimpleNamespace(razorpay_account_id="fixture-account", razorpay_environment="test"),
    )
    tenant_id = uuid4()
    project_id = uuid4()
    revision = ProposalRevision(
        tenant_id=tenant_id,
        project_id=project_id,
        change_order_id=uuid4(),
        revision_number=1,
        baseline_version_id=uuid4(),
        request_version=1,
        preference_version_id=uuid4(),
        total_minor=1_500_000,
        tax_minor=0,
        currency="INR",
        title="Stripe integration",
        requested_change="Add billing",
        deliverables=["Billing integration"],
        exclusions=[],
        assumptions=[],
        client_explanation="Additional work",
        recipient_contact_id=uuid4(),
        recipient_email="client@example.test",
        subject="Payment",
        plain_text_body="Please pay",
        html_body="<p>Please pay</p>",
        attachment_hashes=[],
        terms_json={"total_minor": 1_500_000},
        evidence_digest="a" * 64,
        evidence_reference_ids=[],
        canonical_artifact_ref={"version": 1},
        canonical_artifact_hash="b" * 64,
        approval_url="https://app.example.test/c#t=token",
        token_ciphertext="encrypted",
    )
    payment = PaymentRequest(
        tenant_id=tenant_id,
        project_id=project_id,
        accepted_revision_id=revision.id,
        total_minor=1_500_000,
        tax_minor=0,
        currency="INR",
        status="CREATION_PENDING",
    )
    engine = create_engine("sqlite+pysqlite:///" + str(tmp_path / "phase7.db"))
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as session:
        session.add(revision)
        session.flush()
        payment.accepted_revision_id = revision.id
        session.add(payment)
        session.flush()
        payment_id = payment.id
    return (
        TrustedContext(
            tenant_id=tenant_id,
            subject="phase7-owner",
            email="owner@example.test",
            email_verified=True,
            correlation_id=uuid4(),
        ),
        factory,
        payment_id,
    )


class FakeRazorpay:
    account_id = "fixture-account"
    environment = "test"

    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    def create_payment_link(self, payload: dict[str, object]) -> dict[str, object]:
        self.payloads.append(payload)
        return {
            "id": "plink_test_1",
            "short_url": "https://rzp.io/i/test1",
            "amount": payload["amount"],
            "currency": payload["currency"],
            "reference_id": payload["reference_id"],
            "status": "created",
        }

    def fetch_payment_link(self, provider_link_id: str) -> dict[str, object]:
        return {
            "id": provider_link_id,
            "amount": 1_500_000,
            "amount_paid": 0,
            "currency": "INR",
            "status": "created",
        }


def paid_payload(
    reference_id: str, *, amount: int = 1_500_000, status: str = "captured"
) -> dict[str, object]:
    return {
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {
                "entity": {
                    "id": "plink_test_1",
                    "reference_id": reference_id,
                    "amount": 1_500_000,
                    "amount_paid": amount,
                    "currency": "INR",
                    "status": "paid",
                }
            },
            "payment": {
                "entity": {
                    "id": "pay_test_1",
                    "order_id": "order_test_1",
                    "amount": amount,
                    "currency": "INR",
                    "status": status,
                    "captured": status == "captured",
                }
            },
        },
    }


def test_payment_link_freezes_exact_terms_and_worker_dispatch(
    payment_fixture: tuple[TrustedContext, sessionmaker[Session], UUID],
) -> None:
    context, factory, payment_id = payment_fixture
    fake = FakeRazorpay()
    with factory.begin() as session:
        action, job = prepare_payment_link(session, context, payment_request_id=payment_id)
        assert job is not None
        assert action.provider == "razorpay"
        dispatch_payment_link(session, action_id=action.id, provider=fake)
        payment = session.get(PaymentRequest, payment_id)
        attempt = session.scalar(
            select(PaymentLinkAttempt).where(PaymentLinkAttempt.payment_request_id == payment_id)
        )
        assert payment is not None and payment.status == "PENDING"
        assert attempt is not None and attempt.provider_link_id == "plink_test_1"
    payload = fake.payloads[0]
    assert payload["amount"] == 1_500_000
    assert payload["currency"] == "INR"
    assert payload["accept_partial"] is False
    assert payload["notify"] == {"email": False, "sms": False}
    assert payload["reminder_enable"] is False
    assert len(str(payload["reference_id"])) <= 40


def test_webhook_mismatch_is_quarantined_and_duplicate_delivery_is_idempotent(
    payment_fixture: tuple[TrustedContext, sessionmaker[Session], UUID],
) -> None:
    context, factory, payment_id = payment_fixture
    fake = FakeRazorpay()
    with factory.begin() as session:
        action, _ = prepare_payment_link(session, context, payment_request_id=payment_id)
        dispatch_payment_link(session, action_id=action.id, provider=fake)
        reference = payment_reference(payment_id)
        payload = paid_payload(reference, amount=1_400_000)
        first = observe_payment_event(
            session,
            provider_account_id="fixture-account",
            provider_environment="test",
            provider_event_id="evt-1",
            event_type="payment_link.paid",
            payload=payload,
            signature_verified=True,
        )
        duplicate = observe_payment_event(
            session,
            provider_account_id="fixture-account",
            provider_environment="test",
            provider_event_id="evt-1",
            event_type="payment_link.paid",
            payload=payload,
            signature_verified=True,
        )
        assert first.id == duplicate.id
        assert (
            session.scalar(select(PaymentRequest).where(PaymentRequest.id == payment_id)).status
            == "REVIEW_REQUIRED"
        )
        assert len(list(session.scalars(select(PaymentObservation)))) == 1


def test_verified_capture_is_monotonic_after_later_expiry(
    payment_fixture: tuple[TrustedContext, sessionmaker[Session], UUID],
) -> None:
    context, factory, payment_id = payment_fixture
    fake = FakeRazorpay()
    with factory.begin() as session:
        action, _ = prepare_payment_link(session, context, payment_request_id=payment_id)
        dispatch_payment_link(session, action_id=action.id, provider=fake)
        reference = payment_reference(payment_id)
        first = observe_payment_event(
            session,
            provider_account_id="fixture-account",
            provider_environment="test",
            provider_event_id="evt-paid",
            event_type="payment_link.paid",
            payload=paid_payload(reference),
            signature_verified=True,
        )
        expired = {
            "event": "payment_link.expired",
            "payload": {
                "payment_link": {
                    "entity": {
                        "id": "plink_test_1",
                        "reference_id": reference,
                        "amount": 1_500_000,
                        "currency": "INR",
                        "status": "expired",
                    }
                }
            },
        }
        observe_payment_event(
            session,
            provider_account_id="fixture-account",
            provider_environment="test",
            provider_event_id="evt-expired",
            event_type="payment_link.expired",
            payload=expired,
            signature_verified=True,
        )
        payment = session.get(PaymentRequest, payment_id)
        assert first.id != uuid4()
        assert payment is not None and payment.status == "PAID"


def test_authenticated_webhook_is_persisted_before_async_normalization(
    payment_fixture: tuple[TrustedContext, sessionmaker[Session], UUID],
) -> None:
    context, factory, payment_id = payment_fixture
    fake = FakeRazorpay()
    with factory.begin() as session:
        action, _ = prepare_payment_link(session, context, payment_request_id=payment_id)
        dispatch_payment_link(session, action_id=action.id, provider=fake)
        payload = paid_payload(payment_reference(payment_id))
        ingress, job = accept_payment_webhook(
            session,
            provider_account_id="fixture-account",
            provider_environment="test",
            provider_event_id="evt-async",
            event_type="payment_link.paid",
            payload=payload,
            signature_verified=True,
        )
        duplicate, duplicate_job = accept_payment_webhook(
            session,
            provider_account_id="fixture-account",
            provider_environment="test",
            provider_event_id="evt-async",
            event_type="payment_link.paid",
            payload=payload,
            signature_verified=True,
        )
        assert duplicate.id == ingress.id
        assert duplicate_job is None
        assert job is not None and job.kind == "payment.webhook.normalize"
        assert ingress.normalization_state == "PENDING"
        assert session.get(PaymentRequest, payment_id).status == "PENDING"
        observation = normalize_payment_webhook(session, ingress_id=ingress.id)
        assert observation.payment_request_id == payment_id
        assert ingress.normalization_state == "NORMALIZED"
        assert ingress.observation_id == observation.id
        assert session.get(PaymentRequest, payment_id).status == "PAID"
        assert session.scalar(select(PaymentWebhookIngress.id)) == ingress.id


def test_webhook_signature_uses_raw_body(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.integrations import razorpay

    secret = "webhook-secret"
    monkeypatch.setattr(
        razorpay, "get_settings", lambda: SimpleNamespace(razorpay_webhook_secret=secret)
    )
    provider = razorpay.RazorpayProvider(
        key_id="", key_secret="", api_base_url="", account_id="acct-test"
    )
    body = b'{"event":"payment_link.paid"}'
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert provider.verify_webhook_signature(body, signature)
    assert not provider.verify_webhook_signature(body + b" ", signature)


def test_payment_read_projection_is_tenant_scoped(
    payment_fixture: tuple[TrustedContext, sessionmaker[Session], UUID],
) -> None:
    context, factory, payment_id = payment_fixture
    with factory() as session:
        projection = read_payment_request(session, context, payment_request_id=payment_id)
        assert projection["id"] == payment_id
        assert projection["status"] == "CREATION_PENDING"


def test_worker_targets_cannot_cross_tenant_boundaries(
    payment_fixture: tuple[TrustedContext, sessionmaker[Session], UUID],
) -> None:
    context, factory, payment_id = payment_fixture
    fake = FakeRazorpay()
    with factory.begin() as session:
        action, _ = prepare_payment_link(session, context, payment_request_id=payment_id)
        dispatch_payment_link(session, action_id=action.id, provider=fake)
        ingress, _ = accept_payment_webhook(
            session,
            provider_account_id="fixture-account",
            provider_environment="test",
            provider_event_id="evt-tenant-boundary",
            event_type="payment_link.paid",
            payload=paid_payload(payment_reference(payment_id)),
            signature_verified=True,
        )
        foreign_tenant = uuid4()
        foreign_job = Job(
            tenant_id=foreign_tenant,
            kind="payment.create",
            payload_ref={"action_id": str(action.id)},
            state="RUNNING",
        )
        session.add(foreign_job)
        session.flush()
        with pytest.raises(ValueError, match="External action for job was not found"):
            _action_for_job(
                session,
                foreign_job,
                action_id=action.id,
                provider="razorpay",
                operation="create_payment_link",
            )
        with pytest.raises(NotFoundError, match="Payment webhook target was not found"):
            normalize_payment_webhook(
                session,
                ingress_id=ingress.id,
                expected_tenant_id=foreign_tenant,
            )
        assert session.get(PaymentRequest, payment_id).status == "PENDING"
        normalized = normalize_payment_webhook(
            session,
            ingress_id=ingress.id,
            expected_tenant_id=context.tenant_id,
        )
        assert normalized.tenant_id == context.tenant_id
        assert session.get(PaymentRequest, payment_id).status == "PAID"
