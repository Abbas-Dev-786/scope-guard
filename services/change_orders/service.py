from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from services.agents.persistence import get_analysis_decision
from services.domain.auth import TrustedContext
from services.domain.canonical import canonical_sha256
from services.domain.errors import ConflictError, NotFoundError, ValidationError
from services.domain.models import (
    AnalysisDraftRevision,
    Approval,
    ApprovedRevenueFact,
    AuditEvent,
    ChangeOrder,
    ClientCapability,
    ClientContact,
    ClientSession,
    EvidenceBundle,
    EvidenceReference,
    ExternalAction,
    Notification,
    PaymentLinkAttempt,
    PaymentRequest,
    Project,
    ProposalRevision,
    RequestRecord,
    ScopeAmendment,
    ScopeVersion,
    ScopeVersionItem,
)
from services.workers.durable import enqueue_job, prepare_external_action


@dataclass(frozen=True, slots=True)
class CapabilityCredentials:
    capability: ClientCapability
    token: str
    session: ClientSession
    session_token: str
    csrf_token: str


@dataclass(frozen=True, slots=True)
class AcceptanceResult:
    change_order: ChangeOrder
    payment_request: PaymentRequest
    receipt: CapabilityCredentials


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _protect(value: str) -> str:
    """Encrypt the token envelope; lookup uses only its one-way hash."""
    from services.api.config import get_settings

    settings = get_settings()
    if not settings.capability_encryption_key and settings.environment != "development":
        raise ConflictError("Capability encryption is not configured")
    key_material = settings.capability_encryption_key or "scopeguard-development-only"
    key = hashlib.sha256(key_material.encode("utf-8")).digest()
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(key).encrypt(nonce, value.encode("utf-8"), b"scopeguard:client-capability")
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def _unprotect(value: str) -> str:
    from services.api.config import get_settings

    settings = get_settings()
    key_material = settings.capability_encryption_key or "scopeguard-development-only"
    try:
        envelope = base64.urlsafe_b64decode(value.encode("ascii"))
        return (
            AESGCM(hashlib.sha256(key_material.encode("utf-8")).digest())
            .decrypt(envelope[:12], envelope[12:], b"scopeguard:client-capability")
            .decode("utf-8")
        )
    except (ValueError, TypeError, UnicodeDecodeError) as exc:
        raise ValidationError("Capability envelope is invalid") from exc


def _queue_freelancer_notification(
    session: Session, context: TrustedContext, order: ChangeOrder, revision: ProposalRevision
) -> None:
    recipient = (context.email or "").strip().casefold()
    if not recipient:
        raise ValidationError("A verified freelancer notification address is required")
    payload: dict[str, object] = {
        "change_order_id": str(order.id),
        "revision_id": str(revision.id),
        "recipient": recipient,
        "subject": f"Approval required: {revision.title}",
        "token_ciphertext": revision.token_ciphertext,
        "approval_path": "/c",
    }
    action = prepare_external_action(
        session,
        tenant_id=order.tenant_id,
        project_id=order.project_id,
        action_key=f"change-order-notification:{order.id}:{revision.id}",
        provider="ses",
        operation="send_change_order",
        approved_payload=payload,
    )
    notification = session.scalar(
        select(Notification)
        .where(
            Notification.tenant_id == order.tenant_id,
            Notification.change_order_id == order.id,
            Notification.revision_id == revision.id,
            Notification.channel == "SES",
        )
        .with_for_update()
    )
    if notification is None:
        notification = Notification(
            tenant_id=order.tenant_id,
            change_order_id=order.id,
            revision_id=revision.id,
            channel="SES",
            verified_recipient=recipient,
            action_id=action.id,
        )
        session.add(notification)
    else:
        notification.action_id = action.id
    enqueue_job(
        session,
        tenant_id=order.tenant_id,
        project_id=order.project_id,
        kind="notification.send",
        payload_ref={"action_id": str(action.id), "notification_id": str(notification.id)},
        correlation_id=context.correlation_id,
    )


def _now() -> datetime:
    return datetime.now(UTC)


def _project(session: Session, context: TrustedContext, project_id: UUID) -> Project:
    project = session.scalar(
        select(Project).where(Project.id == project_id, Project.tenant_id == context.tenant_id)
    )
    if project is None:
        raise NotFoundError("Project was not found")
    return project


def _current_revision(session: Session, order: ChangeOrder) -> ProposalRevision:
    if order.current_revision_id is None:
        raise ConflictError("Change order has no current revision")
    revision = session.scalar(
        select(ProposalRevision).where(
            ProposalRevision.id == order.current_revision_id,
            ProposalRevision.change_order_id == order.id,
            ProposalRevision.tenant_id == order.tenant_id,
            ProposalRevision.status == "CURRENT",
        )
    )
    if revision is None:
        raise ConflictError("Change order revision is unavailable")
    return revision


def _proposal_payload(
    draft: dict[str, Any],
    *,
    approval_url: str,
    baseline_version_id: UUID,
    request_version: int,
    recipient_contact_id: UUID,
) -> dict[str, Any]:
    terms = draft.get("terms")
    if not isinstance(terms, dict):
        raise ValidationError("Proposal terms are missing")
    total = terms.get("total_minor")
    tax = terms.get("tax_minor", 0)
    if not isinstance(total, int) or not 0 < total <= 100_000_000:
        raise ValidationError("Proposal total is invalid")
    if not isinstance(tax, int) or not 0 <= tax <= total:
        raise ValidationError("Proposal tax is invalid")
    required = (
        "title",
        "requested_change",
        "deliverables",
        "client_explanation",
        "subject",
        "plain_text_body",
        "html_body",
        "recipient_email",
        "evidence_reference_ids",
    )
    if any(not draft.get(key) for key in required):
        raise ValidationError("Proposal content is incomplete")
    return {
        "schema_version": 1,
        "baseline_version_id": str(baseline_version_id),
        "request_version": request_version,
        "recipient_contact_id": str(recipient_contact_id),
        "recipient_email": str(draft["recipient_email"]).strip().casefold(),
        "title": str(draft["title"]),
        "requested_change": str(draft["requested_change"]),
        "deliverables": list(draft["deliverables"]),
        "exclusions": list(draft.get("exclusions", [])),
        "assumptions": list(draft.get("assumptions", [])),
        "client_explanation": str(draft["client_explanation"]),
        "subject": str(draft["subject"]),
        "plain_text_body": str(draft["plain_text_body"]),
        "html_body": str(draft["html_body"]),
        "attachment_hashes": list(draft.get("attachment_hashes", [])),
        "terms": terms,
        "evidence_reference_ids": [str(item) for item in draft["evidence_reference_ids"]],
        "client_approval_url": approval_url,
    }


def _new_revision(
    session: Session,
    *,
    order: ChangeOrder,
    project: Project,
    request: RequestRecord,
    contact: ClientContact,
    draft: dict[str, Any],
) -> tuple[ProposalRevision, str]:
    if project.current_scope_version_id is None:
        raise ConflictError("A confirmed scope baseline is required")
    baseline_id = project.current_scope_version_id
    token = secrets.token_urlsafe(32)
    approval_url = "/c"
    payload = _proposal_payload(
        draft,
        approval_url=approval_url,
        baseline_version_id=baseline_id,
        request_version=request.request_version,
        recipient_contact_id=contact.id,
    )
    artifact_hash = canonical_sha256(payload)
    previous = _current_revision(session, order) if order.current_revision_id else None
    if previous is not None:
        previous.status = "SUPERSEDED"
        session.query(ClientCapability).filter(
            ClientCapability.change_order_id == order.id,
            ClientCapability.revoked_at.is_(None),
        ).update({"revoked_at": _now(), "consumed_at": _now()}, synchronize_session=False)
    terms = payload["terms"]
    revision = ProposalRevision(
        tenant_id=order.tenant_id,
        project_id=project.id,
        change_order_id=order.id,
        revision_number=(previous.revision_number + 1 if previous else 1),
        baseline_version_id=baseline_id,
        request_version=request.request_version,
        preference_version_id=UUID(str(terms["preference_version_id"])),
        total_minor=int(terms["total_minor"]),
        tax_minor=int(terms.get("tax_minor", 0)),
        currency=str(terms.get("currency", "INR")),
        title=payload["title"],
        requested_change=payload["requested_change"],
        deliverables=payload["deliverables"],
        exclusions=payload["exclusions"],
        assumptions=payload["assumptions"],
        client_explanation=payload["client_explanation"],
        recipient_contact_id=contact.id,
        recipient_email=payload["recipient_email"],
        subject=payload["subject"],
        plain_text_body=payload["plain_text_body"],
        html_body=payload["html_body"],
        attachment_hashes=payload["attachment_hashes"],
        terms_json=terms,
        evidence_digest=canonical_sha256(payload["evidence_reference_ids"]),
        evidence_reference_ids=payload["evidence_reference_ids"],
        canonical_artifact_ref={
            "store": "proposal-artifacts",
            "format": "canonical-json",
            "schema_version": 1,
        },
        canonical_artifact_hash=artifact_hash,
        approval_url=approval_url,
        token_ciphertext=_protect(token),
    )
    session.add(revision)
    session.flush()
    order.current_revision_id = revision.id
    order.status = "AWAITING_FREELANCER_APPROVAL"
    order.row_version += 1
    capability = ClientCapability(
        tenant_id=order.tenant_id,
        project_id=project.id,
        change_order_id=order.id,
        revision_id=revision.id,
        client_id=project.client_id,
        token_hash=_hash(token),
        content_hash=artifact_hash,
        purpose="REVIEW",
    )
    session.add(capability)
    session.flush()
    return revision, token


def assemble_change_order(
    session: Session,
    context: TrustedContext,
    *,
    decision_id: UUID,
) -> ChangeOrder:
    decision = get_analysis_decision(session, context, decision_id)
    if decision.kind != "PROPOSAL_REVIEW":
        raise ValidationError("Only proposal decisions can become change orders")
    draft = session.scalar(
        select(AnalysisDraftRevision).where(
            AnalysisDraftRevision.decision_id == decision.id,
            AnalysisDraftRevision.status == "CURRENT",
        )
    )
    if draft is None:
        raise ConflictError("Proposal draft is unavailable")
    project = _project(session, context, decision.project_id)
    request = session.scalar(
        select(RequestRecord).where(
            RequestRecord.id == decision.request_id,
            RequestRecord.project_id == project.id,
            RequestRecord.tenant_id == context.tenant_id,
        )
    )
    if request is None or request.status not in {"OPEN", "PROPOSAL_OPEN"}:
        raise ConflictError("Request is not eligible for a proposal")
    if project.current_scope_version_id is None:
        raise ConflictError("A confirmed scope baseline is required")
    payload = draft.payload
    recipient = str(payload.get("recipient_email", "")).strip().casefold()
    contact = session.scalar(
        select(ClientContact).where(
            ClientContact.client_id == project.client_id,
            ClientContact.tenant_id == context.tenant_id,
            ClientContact.normalized_email == recipient,
        )
    )
    if contact is None:
        raise ValidationError("Proposal recipient is not an authorized client contact")
    order = session.scalar(
        select(ChangeOrder)
        .where(
            ChangeOrder.tenant_id == context.tenant_id,
            ChangeOrder.project_id == project.id,
            ChangeOrder.request_id == request.id,
            ChangeOrder.status.not_in({"CLIENT_APPROVED", "WITHDRAWN", "EXPIRED"}),
        )
        .with_for_update()
    )
    if order is None:
        next_number = session.scalar(
            select(func.coalesce(func.max(ChangeOrder.number), 0) + 1).where(
                ChangeOrder.tenant_id == context.tenant_id,
                ChangeOrder.project_id == project.id,
            )
        )
        order = ChangeOrder(
            tenant_id=context.tenant_id,
            project_id=project.id,
            request_id=request.id,
            number=int(next_number or 1),
        )
        session.add(order)
        session.flush()
    _new_revision(
        session, order=order, project=project, request=request, contact=contact, draft=payload
    )
    request.status = "PROPOSAL_OPEN"
    request.row_version += 1
    decision.status = "RESOLVED"
    decision.row_version += 1
    revision = _current_revision(session, order)
    _queue_freelancer_notification(session, context, order, revision)
    session.flush()
    return order


def create_revision(
    session: Session,
    context: TrustedContext,
    *,
    change_order_id: UUID,
    edits: dict[str, Any],
) -> ProposalRevision:
    order = session.scalar(
        select(ChangeOrder)
        .where(ChangeOrder.id == change_order_id, ChangeOrder.tenant_id == context.tenant_id)
        .with_for_update()
    )
    if order is None:
        raise NotFoundError("Change order was not found")
    if order.status in {"CLIENT_APPROVED", "WITHDRAWN"}:
        raise ConflictError("Accepted or withdrawn change orders cannot be edited")
    current = _current_revision(session, order)
    project = _project(session, context, order.project_id)
    request = session.scalar(
        select(RequestRecord).where(
            RequestRecord.id == order.request_id, RequestRecord.tenant_id == context.tenant_id
        )
    )
    contact = session.get(ClientContact, current.recipient_contact_id)
    if request is None or contact is None:
        raise ConflictError("Revision dependencies are unavailable")
    payload = {
        "title": edits.get("title", current.title),
        "requested_change": edits.get("requested_change", current.requested_change),
        "deliverables": edits.get("deliverables", current.deliverables),
        "exclusions": edits.get("exclusions", current.exclusions),
        "assumptions": edits.get("assumptions", current.assumptions),
        "client_explanation": edits.get("client_explanation", current.client_explanation),
        "subject": edits.get("subject", current.subject),
        "plain_text_body": edits.get("plain_text_body", current.plain_text_body),
        "html_body": edits.get("html_body", current.html_body),
        "recipient_email": current.recipient_email,
        "evidence_reference_ids": current.evidence_reference_ids,
        "terms": current.terms_json,
    }
    revision, _ = _new_revision(
        session, order=order, project=project, request=request, contact=contact, draft=payload
    )
    return revision


def approve_freelancer(
    session: Session,
    context: TrustedContext,
    *,
    change_order_id: UUID,
    expected_row_version: int,
    revision_id: UUID,
    content_hash: str,
) -> tuple[ChangeOrder, ExternalAction]:
    project = _project(
        session,
        context,
        session.scalar(
            select(ChangeOrder.project_id).where(
                ChangeOrder.id == change_order_id, ChangeOrder.tenant_id == context.tenant_id
            )
        )
        or UUID(int=0),
    )
    order = session.scalar(
        select(ChangeOrder)
        .where(ChangeOrder.id == change_order_id, ChangeOrder.tenant_id == context.tenant_id)
        .with_for_update()
    )
    if order is None:
        raise NotFoundError("Change order was not found")
    project = _project(session, context, order.project_id)
    if order.row_version != expected_row_version:
        raise ConflictError(
            "Change order changed; refresh before approving",
            details={"current_row_version": order.row_version},
        )
    revision = _current_revision(session, order)
    if revision.id != revision_id or revision.canonical_artifact_hash != content_hash:
        raise ConflictError("The approved revision is stale")
    if order.status != "AWAITING_FREELANCER_APPROVAL":
        raise ConflictError("Change order is not awaiting freelancer approval")
    request = session.scalar(
        select(RequestRecord)
        .where(RequestRecord.id == order.request_id, RequestRecord.tenant_id == context.tenant_id)
        .with_for_update()
    )
    if request is None or request.request_version != revision.request_version:
        raise ConflictError("The proposal input changed; create a new revision")
    if project.current_scope_version_id != revision.baseline_version_id:
        raise ConflictError("The proposal baseline is stale")
    evidence_ids: list[UUID] = []
    for reference_id in revision.evidence_reference_ids:
        try:
            evidence_ids.append(UUID(str(reference_id)))
        except (TypeError, ValueError):
            continue
    evidence = (
        session.scalars(
            select(EvidenceReference).where(
                EvidenceReference.id.in_(evidence_ids),
                EvidenceReference.tenant_id == context.tenant_id,
                EvidenceReference.project_id == project.id,
            )
        ).all()
        if evidence_ids
        else []
    )
    bundle_ids = {item.bundle_id for item in evidence}
    stale_bundle = (
        session.scalar(
            select(EvidenceBundle).where(
                EvidenceBundle.id.in_(bundle_ids),
                EvidenceBundle.stale_at.is_not(None),
                EvidenceBundle.stale_at <= _now(),
            )
        )
        if bundle_ids
        else None
    )
    if stale_bundle is not None:
        raise ConflictError("Proposal evidence is stale; create a new revision")
    approval = Approval(
        tenant_id=context.tenant_id,
        project_id=order.project_id,
        change_order_id=order.id,
        revision_id=revision.id,
        actor_type="FREELANCER",
        actor_identifier=context.subject,
        content_hash=content_hash,
        decision="APPROVED",
        provenance={"model": "authenticated-owner", "exact_revision": str(revision.id)},
    )
    session.add(approval)
    cap = session.scalar(
        select(ClientCapability)
        .where(
            ClientCapability.revision_id == revision.id,
            ClientCapability.tenant_id == context.tenant_id,
            ClientCapability.revoked_at.is_(None),
        )
        .with_for_update()
    )
    if cap is None:
        raise ConflictError("Client capability is unavailable")
    now = _now()
    cap.activated_at = now
    cap.expires_at = now + timedelta(days=7)
    order.status = "SEND_PENDING"
    order.row_version += 1
    payload = {
        "change_order_id": str(order.id),
        "revision_id": str(revision.id),
        "recipient": revision.recipient_email,
        "subject": revision.subject,
        "plain_text_body": revision.plain_text_body,
        "html_body": revision.html_body,
        "attachment_hashes": revision.attachment_hashes,
        "content_hash": revision.canonical_artifact_hash,
        "marker": f"ScopeGuard/{order.id}/{revision.id}",
    }
    action = prepare_external_action(
        session,
        tenant_id=context.tenant_id,
        project_id=order.project_id,
        action_key=f"change-order-send:{order.id}:{revision.id}",
        provider="gmail",
        operation="send",
        approved_payload=dict(payload),
    )
    enqueue_job(
        session,
        tenant_id=context.tenant_id,
        project_id=order.project_id,
        kind="change_order.send",
        payload_ref={
            "action_id": str(action.id),
            "change_order_id": str(order.id),
            "revision_id": str(revision.id),
        },
        correlation_id=context.correlation_id,
    )
    session.flush()
    return order, action


def _session_scope(
    session: Session, session_token: str, csrf_token: str | None = None
) -> tuple[ClientSession, ClientCapability, ProposalRevision, ChangeOrder]:
    row = session.scalar(
        select(ClientSession)
        .where(ClientSession.session_hash == _hash(session_token))
        .with_for_update()
    )
    now = _now()
    if row is None or row.revoked_at is not None or _utc(row.expires_at) <= now:
        raise ValidationError("Invalid client session")
    if csrf_token is not None and _hash(csrf_token) != row.csrf_hash:
        raise ValidationError("Invalid client session")
    capability = session.get(ClientCapability, row.capability_id)
    if capability is None or capability.revoked_at is not None:
        raise ValidationError("Invalid client session")
    order = session.get(ChangeOrder, capability.change_order_id)
    revision = session.get(ProposalRevision, capability.revision_id)
    if order is None or revision is None:
        raise ValidationError("Invalid client session")
    return row, capability, revision, order


def exchange_capability(session: Session, *, token: str) -> CapabilityCredentials:
    if len(token) < 43:
        raise ValidationError("Invalid client capability")
    capability = session.scalar(
        select(ClientCapability)
        .where(ClientCapability.token_hash == _hash(token))
        .with_for_update()
    )
    now = _now()
    if (
        capability is None
        or capability.purpose != "REVIEW"
        or capability.activated_at is None
        or capability.revoked_at is not None
        or capability.expires_at is None
        or _utc(capability.expires_at) <= now
    ):
        raise ValidationError("Invalid client capability")
    if capability.consumed_at is not None:
        order = session.get(ChangeOrder, capability.change_order_id)
        if order is None or order.status != "CLIENT_APPROVED":
            raise ValidationError("Invalid client capability")
        receipt = session.scalar(
            select(ClientCapability)
            .where(
                ClientCapability.change_order_id == order.id,
                ClientCapability.revision_id == capability.revision_id,
                ClientCapability.client_id == capability.client_id,
                ClientCapability.purpose == "RECEIPT",
                ClientCapability.revoked_at.is_(None),
            )
            .order_by(ClientCapability.created_at.desc())
        )
        if receipt is None or receipt.expires_at is None or _utc(receipt.expires_at) <= now:
            raise ValidationError("Invalid client capability")
        session_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        client_session = ClientSession(
            capability_id=receipt.id,
            session_hash=_hash(session_token),
            csrf_hash=_hash(csrf_token),
            purpose="RECEIPT",
            expires_at=now + timedelta(hours=24),
        )
        session.add(client_session)
        session.flush()
        return CapabilityCredentials(receipt, "", client_session, session_token, csrf_token)
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    client_session = ClientSession(
        capability_id=capability.id,
        session_hash=_hash(session_token),
        csrf_hash=_hash(csrf_token),
        purpose="REVIEW",
        expires_at=now + timedelta(hours=24),
    )
    session.add(client_session)
    session.flush()
    return CapabilityCredentials(capability, token, client_session, session_token, csrf_token)


def read_client_review(session: Session, *, session_token: str) -> dict[str, Any]:
    _, _unused_capability, revision, order = _session_scope(session, session_token)
    if (
        _unused_capability.purpose != "REVIEW"
        or _unused_capability.consumed_at is not None
        or order.status not in {"AWAITING_CLIENT_APPROVAL", "SEND_PENDING"}
    ):
        raise ConflictError("Client review is unavailable")
    return {
        "change_order_id": str(order.id),
        "revision_id": str(revision.id),
        "revision_number": revision.revision_number,
        "status": order.status,
        "row_version": order.row_version,
        "content_hash": revision.canonical_artifact_hash,
        "title": revision.title,
        "requested_change": revision.requested_change,
        "deliverables": revision.deliverables,
        "exclusions": revision.exclusions,
        "assumptions": revision.assumptions,
        "client_explanation": revision.client_explanation,
        "recipient_email": revision.recipient_email,
        "subject": revision.subject,
        "plain_text_body": revision.plain_text_body,
        "html_body": revision.html_body,
        "terms": revision.terms_json,
    }


def accept_client(
    session: Session,
    *,
    session_token: str,
    csrf_token: str,
    change_order_id: UUID,
    expected_row_version: int,
    revision_id: UUID,
    content_hash: str,
    client_idempotency_key: str,
) -> AcceptanceResult:
    _session_row, capability, revision, order = _session_scope(session, session_token, csrf_token)
    if (
        order.id != change_order_id
        or capability.revision_id != revision_id
        or revision.canonical_artifact_hash != content_hash
    ):
        raise ConflictError("Client offer is stale")
    if not client_idempotency_key:
        raise ValidationError("Client idempotency key is required")
    project = session.scalar(
        select(Project)
        .where(Project.id == order.project_id, Project.tenant_id == capability.tenant_id)
        .with_for_update()
    )
    locked_order = session.scalar(
        select(ChangeOrder)
        .where(ChangeOrder.id == order.id, ChangeOrder.tenant_id == capability.tenant_id)
        .with_for_update()
    )
    if locked_order is None:
        raise ConflictError("Client offer changed; reload before accepting")
    order = locked_order
    if project is None:
        raise ConflictError("Client project is unavailable")
    if capability.consumed_at is not None:
        prior = session.scalar(
            select(Approval).where(
                Approval.revision_id == revision.id,
                Approval.actor_type == "CLIENT",
                Approval.provenance["idempotency_key"].as_string() == client_idempotency_key,
            )
        )
        existing = session.scalar(
            select(PaymentRequest).where(PaymentRequest.accepted_revision_id == revision.id)
        )
        if prior is not None and existing is not None:
            return AcceptanceResult(
                order,
                existing,
                _receipt_credentials_for_existing(session, capability, revision, now=_now()),
            )
        raise ConflictError("Client capability has already been consumed")
    if order.row_version != expected_row_version:
        raise ConflictError("Client offer changed; reload before accepting")
    action = session.scalar(
        select(ExternalAction)
        .where(
            ExternalAction.action_key == f"change-order-send:{order.id}:{revision.id}",
            ExternalAction.tenant_id == capability.tenant_id,
        )
        .with_for_update()
    )
    eligible = order.status == "AWAITING_CLIENT_APPROVAL" or (
        order.status == "SEND_PENDING"
        and action is not None
        and action.state in {"DISPATCHING", "UNKNOWN_OUTCOME"}
    )
    if not eligible:
        raise ConflictError("Client offer is not eligible for acceptance")
    if project.current_scope_version_id != revision.baseline_version_id:
        raise ConflictError("Offer baseline is stale; freelancer revalidation is required")
    existing = session.scalar(
        select(PaymentRequest).where(PaymentRequest.accepted_revision_id == revision.id)
    )
    if existing is not None:
        return AcceptanceResult(
            order, existing, _receipt_credentials(session, capability, revision, now=_now())
        )
    approval = Approval(
        tenant_id=capability.tenant_id,
        project_id=order.project_id,
        change_order_id=order.id,
        revision_id=revision.id,
        actor_type="CLIENT",
        actor_identifier=f"client:{capability.client_id}",
        content_hash=content_hash,
        decision="APPROVED",
        provenance={"model": "bearer-capability", "idempotency_key": client_idempotency_key},
    )
    session.add(approval)
    now = _now()
    capability.consumed_at = now
    capability.expires_at = now + timedelta(days=30)
    if action is not None and action.state in {"DISPATCHING", "UNKNOWN_OUTCOME"}:
        action.state = "RECEIPT_CONFIRMED"
        action.receipt_ref = {"provenance": "client-receipt", "revision_id": str(revision.id)}
    order.status = "CLIENT_APPROVED"
    order.row_version += 1
    request = session.get(RequestRecord, order.request_id)
    if request is not None:
        request.status = "RESOLVED"
        request.row_version += 1
    previous_scope = session.get(ScopeVersion, project.current_scope_version_id)
    if previous_scope is None:
        raise ConflictError("Scope baseline is unavailable")
    next_version = (
        session.scalar(
            select(func.max(ScopeVersion.version)).where(
                ScopeVersion.project_id == project.id,
                ScopeVersion.tenant_id == capability.tenant_id,
            )
        )
        or previous_scope.version
    ) + 1
    resulting = ScopeVersion(
        tenant_id=capability.tenant_id,
        project_id=project.id,
        version=next_version,
        parent_version_id=previous_scope.id,
        source_revision_id=revision.id,
        confirmation_actor=f"client:{capability.client_id}",
        content_hash=canonical_sha256(
            {"parent": previous_scope.content_hash, "revision": revision.canonical_artifact_hash}
        ),
    )
    session.add(resulting)
    session.flush()
    links = session.scalars(
        select(ScopeVersionItem).where(ScopeVersionItem.scope_version_id == previous_scope.id)
    ).all()
    for link in links:
        session.add(
            ScopeVersionItem(
                tenant_id=capability.tenant_id,
                project_id=project.id,
                scope_version_id=resulting.id,
                scope_item_id=link.scope_item_id,
            )
        )
    project.current_scope_version_id = resulting.id
    amendment = ScopeAmendment(
        tenant_id=capability.tenant_id,
        project_id=project.id,
        accepted_revision_id=revision.id,
        previous_scope_version_id=previous_scope.id,
        resulting_scope_version_id=resulting.id,
        operations_json=[
            {
                "operation": "ADD_CHANGE_ORDER",
                "change_order_id": str(order.id),
                "revision_id": str(revision.id),
            }
        ],
    )
    session.add(amendment)
    payment = PaymentRequest(
        tenant_id=capability.tenant_id,
        project_id=project.id,
        accepted_revision_id=revision.id,
        total_minor=revision.total_minor,
        tax_minor=revision.tax_minor,
        currency=revision.currency,
        status="CREATION_PENDING",
    )
    session.add(payment)
    session.add(
        ApprovedRevenueFact(
            tenant_id=capability.tenant_id,
            project_id=project.id,
            change_order_id=order.id,
            revision_id=revision.id,
            amount_minor=revision.total_minor,
            tax_minor=revision.tax_minor,
            currency=revision.currency,
        )
    )
    session.flush()
    from services.payments.service import prepare_payment_link

    payment_context = TrustedContext(
        tenant_id=capability.tenant_id,
        subject=f"client:{capability.client_id}",
        email=revision.recipient_email,
        email_verified=True,
        correlation_id=uuid4(),
    )
    prepare_payment_link(session, payment_context, payment_request_id=payment.id)
    receipt = _receipt_credentials(session, capability, revision, now=now)
    session.flush()
    return AcceptanceResult(order, payment, receipt)


def _receipt_credentials(
    session: Session, source: ClientCapability, revision: ProposalRevision, *, now: datetime
) -> CapabilityCredentials:
    token = secrets.token_urlsafe(32)
    cap = ClientCapability(
        tenant_id=source.tenant_id,
        project_id=source.project_id,
        change_order_id=source.change_order_id,
        revision_id=revision.id,
        client_id=source.client_id,
        token_hash=_hash(token),
        content_hash=revision.canonical_artifact_hash,
        purpose="RECEIPT",
        activated_at=now,
        expires_at=now + timedelta(days=30),
    )
    session.add(cap)
    session.flush()
    session_token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    client_session = ClientSession(
        capability_id=cap.id,
        session_hash=_hash(session_token),
        csrf_hash=_hash(csrf),
        purpose="RECEIPT",
        expires_at=now + timedelta(hours=24),
    )
    session.add(client_session)
    session.flush()
    return CapabilityCredentials(cap, token, client_session, session_token, csrf)


def verify_receipt_session(session: Session, *, session_token: str) -> dict[str, Any]:
    _, capability, revision, order = _session_scope(session, session_token)
    if capability.purpose != "RECEIPT" or order.status != "CLIENT_APPROVED":
        raise ValidationError("Receipt is unavailable")
    payment = session.scalar(
        select(PaymentRequest).where(PaymentRequest.accepted_revision_id == revision.id)
    )
    link = None
    if payment is not None:
        link = session.scalar(
            select(PaymentLinkAttempt)
            .where(
                PaymentLinkAttempt.payment_request_id == payment.id,
                PaymentLinkAttempt.status == "CREATED",
            )
            .order_by(PaymentLinkAttempt.attempt_number.desc())
            .limit(1)
        )
    return {
        "change_order_id": str(order.id),
        "revision_id": str(revision.id),
        "status": order.status,
        "payment_status": payment.status if payment else "CREATION_PENDING",
        "payment_request_id": str(payment.id) if payment else None,
        "payment_link_url": link.short_url if link else None,
        "payment_link_status": link.provider_status if link else None,
    }


def read_change_order(
    session: Session, context: TrustedContext, *, change_order_id: UUID
) -> ChangeOrder:
    order = session.scalar(
        select(ChangeOrder).where(
            ChangeOrder.id == change_order_id,
            ChangeOrder.tenant_id == context.tenant_id,
        )
    )
    if order is None:
        raise NotFoundError("Change order was not found")
    return order


def begin_gmail_send(session: Session, *, action_id: UUID) -> dict[str, Any]:
    from services.workers.durable import begin_action_dispatch

    action = session.scalar(
        select(ExternalAction).where(ExternalAction.id == action_id).with_for_update()
    )
    if action is None or action.provider != "gmail" or action.operation != "send":
        raise NotFoundError("Gmail send action was not found")
    try:
        order_id = UUID(str(action.approved_payload["change_order_id"]))
    except (TypeError, ValueError) as exc:
        raise ValidationError("Gmail action has an invalid change order") from exc
    order = session.scalar(
        select(ChangeOrder)
        .where(ChangeOrder.id == order_id, ChangeOrder.tenant_id == action.tenant_id)
        .with_for_update()
    )
    if order is None or order.status != "SEND_PENDING":
        raise ConflictError("Gmail send is no longer pending")
    begin_action_dispatch(session, action_id=action.id)
    return dict(action.approved_payload)


def record_gmail_send_success(
    session: Session,
    *,
    action_id: UUID,
    provider_message_id: str,
    recipient: str,
    plain_text_body: str,
    content_hash: str,
) -> ExternalAction:
    from services.domain.models import ActionAttempt
    from services.workers.durable import complete_action

    action = session.scalar(
        select(ExternalAction).where(ExternalAction.id == action_id).with_for_update()
    )
    if action is None:
        raise NotFoundError("Gmail send action was not found")
    expected = action.approved_payload
    if (
        expected.get("recipient") != recipient
        or expected.get("plain_text_body") != plain_text_body
        or expected.get("content_hash") != content_hash
    ):
        raise ValidationError("Provider content does not match the approved artifact")
    if action.state == "RECEIPT_CONFIRMED":
        attempt = session.scalar(
            select(ActionAttempt)
            .where(ActionAttempt.action_id == action.id)
            .order_by(ActionAttempt.attempt_number.desc())
            .limit(1)
        )
        if attempt is not None:
            attempt.provider_request_id = provider_message_id
            attempt.outcome_ref = {
                "provider_message_id": provider_message_id,
                "late_callback": True,
            }
        action.receipt_ref = {
            **(action.receipt_ref or {}),
            "provider_message_id": provider_message_id,
        }
        session.flush()
        return action
    if action.state not in {"DISPATCHING", "UNKNOWN_OUTCOME"}:
        raise ConflictError("Gmail send action is not awaiting a provider result")
    if action.state == "UNKNOWN_OUTCOME":
        action.state = "SUCCEEDED"
        attempt = session.scalar(
            select(ActionAttempt)
            .where(ActionAttempt.action_id == action.id)
            .order_by(ActionAttempt.attempt_number.desc())
            .limit(1)
        )
        if attempt is not None:
            attempt.state = "SUCCEEDED"
            attempt.provider_request_id = provider_message_id
            attempt.completed_at = _now()
            attempt.outcome_ref = {"provider_message_id": provider_message_id}
    else:
        complete_action(
            session,
            action_id=action.id,
            provider_request_id=provider_message_id,
            outcome_ref={"provider_message_id": provider_message_id},
        )
    order = session.scalar(
        select(ChangeOrder)
        .where(
            ChangeOrder.id == UUID(str(expected["change_order_id"])),
            ChangeOrder.tenant_id == action.tenant_id,
        )
        .with_for_update()
    )
    if order is not None and order.status == "SEND_PENDING":
        order.status = "AWAITING_CLIENT_APPROVAL"
        order.row_version += 1
    session.flush()
    return action


def record_gmail_send_unknown(session: Session, *, action_id: UUID, reason: str) -> ExternalAction:
    from services.workers.durable import mark_action_unknown

    action = session.get(ExternalAction, action_id, with_for_update=True)
    if action is None:
        raise NotFoundError("Gmail send action was not found")
    if action.state == "UNKNOWN_OUTCOME":
        return action
    if action.state != "DISPATCHING":
        raise ConflictError("Gmail send action is not awaiting a provider result")
    return mark_action_unknown(session, action_id=action_id, reason=reason)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _receipt_credentials_for_existing(
    session: Session,
    source: ClientCapability,
    revision: ProposalRevision,
    *,
    now: datetime,
) -> CapabilityCredentials:
    receipt = session.scalar(
        select(ClientCapability)
        .where(
            ClientCapability.change_order_id == source.change_order_id,
            ClientCapability.revision_id == revision.id,
            ClientCapability.client_id == source.client_id,
            ClientCapability.purpose == "RECEIPT",
            ClientCapability.revoked_at.is_(None),
        )
        .order_by(ClientCapability.created_at.desc())
    )
    if receipt is None:
        return _receipt_credentials(session, source, revision, now=now)
    session_token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    client_session = ClientSession(
        capability_id=receipt.id,
        session_hash=_hash(session_token),
        csrf_hash=_hash(csrf),
        purpose="RECEIPT",
        expires_at=now + timedelta(hours=24),
    )
    session.add(client_session)
    session.flush()
    return CapabilityCredentials(receipt, "", client_session, session_token, csrf)


def _audit_change_order(
    session: Session,
    order: ChangeOrder,
    *,
    actor: str,
    action: str,
    before: str,
    after: str,
    correlation_id: UUID,
    metadata: dict[str, object] | None = None,
) -> None:
    session.add(
        AuditEvent(
            tenant_id=order.tenant_id,
            project_id=order.project_id,
            actor=actor,
            action=action,
            resource_type="change_order",
            resource_id=str(order.id),
            resource_revision=order.row_version,
            correlation_id=correlation_id,
            before_state={"status": before},
            after_state={"status": after},
            content_digest=canonical_sha256(
                {
                    "change_order_id": str(order.id),
                    "before": before,
                    "after": after,
                    "row_version": order.row_version,
                }
            ),
            safe_metadata=metadata or {},
        )
    )


def _revoke_capabilities(session: Session, order_id: UUID, *, now: datetime) -> None:
    session.query(ClientCapability).filter(
        ClientCapability.change_order_id == order_id, ClientCapability.revoked_at.is_(None)
    ).update({"revoked_at": now}, synchronize_session=False)


def _cancel_pending_send(session: Session, order: ChangeOrder) -> None:
    from services.workers.durable import cancel_action

    action = session.scalar(
        select(ExternalAction)
        .where(
            ExternalAction.action_key.like(f"change-order-send:{order.id}:%"),
            ExternalAction.tenant_id == order.tenant_id,
        )
        .order_by(ExternalAction.created_at.desc())
        .with_for_update()
    )
    if action is not None and action.state in {"READY", "RETRY_WAIT"}:
        cancel_action(session, action_id=action.id)


def freelancer_decide(
    session: Session,
    context: TrustedContext,
    *,
    change_order_id: UUID,
    decision: str,
    comment: str | None = None,
) -> ChangeOrder:
    if decision not in {"REJECTED", "WAIVED"}:
        raise ValidationError("Unsupported freelancer decision")
    order = session.scalar(
        select(ChangeOrder)
        .where(ChangeOrder.id == change_order_id, ChangeOrder.tenant_id == context.tenant_id)
        .with_for_update()
    )
    if order is None:
        raise NotFoundError("Change order was not found")
    if order.status != "AWAITING_FREELANCER_APPROVAL":
        raise ConflictError("Change order is not awaiting freelancer decision")
    revision = _current_revision(session, order)
    now = _now()
    target = "REJECTED_BY_FREELANCER" if decision == "REJECTED" else "WITHDRAWN"
    session.add(
        Approval(
            tenant_id=order.tenant_id,
            project_id=order.project_id,
            change_order_id=order.id,
            revision_id=revision.id,
            actor_type="FREELANCER",
            actor_identifier=context.subject,
            content_hash=revision.canonical_artifact_hash,
            decision=decision,
            comment=comment,
            provenance={"model": "authenticated-owner"},
        )
    )
    before = order.status
    order.status = target
    order.row_version += 1
    request = session.get(RequestRecord, order.request_id, with_for_update=True)
    if request is not None:
        request.status = "DECLINED" if decision == "REJECTED" else "WAIVED"
        request.rejection_reason = comment
        request.row_version += 1
    _revoke_capabilities(session, order.id, now=now)
    _audit_change_order(
        session,
        order,
        actor=context.subject,
        action=f"freelancer_{decision.lower()}",
        before=before,
        after=target,
        correlation_id=context.correlation_id,
        metadata={"comment_present": bool(comment)},
    )
    session.flush()
    return order


def withdraw_change_order(
    session: Session, context: TrustedContext, *, change_order_id: UUID, reason: str | None = None
) -> ChangeOrder:
    order = session.scalar(
        select(ChangeOrder)
        .where(ChangeOrder.id == change_order_id, ChangeOrder.tenant_id == context.tenant_id)
        .with_for_update()
    )
    if order is None:
        raise NotFoundError("Change order was not found")
    if order.status in {
        "CLIENT_APPROVED",
        "WITHDRAWN",
        "EXPIRED",
        "REJECTED_BY_CLIENT",
        "REJECTED_BY_FREELANCER",
    }:
        raise ConflictError("Change order cannot be withdrawn")
    action = session.scalar(
        select(ExternalAction)
        .where(
            ExternalAction.action_key.like(f"change-order-send:{order.id}:%"),
            ExternalAction.tenant_id == order.tenant_id,
        )
        .order_by(ExternalAction.created_at.desc())
        .with_for_update()
    )
    if action is not None and action.state in {"DISPATCHING", "UNKNOWN_OUTCOME"}:
        raise ConflictError("Send outcome must be reconciled before withdrawal")
    before = order.status
    order.status = "WITHDRAWN"
    order.row_version += 1
    request = session.get(RequestRecord, order.request_id, with_for_update=True)
    if request is not None:
        request.status = "DECLINED"
        request.rejection_reason = reason
        request.row_version += 1
    _cancel_pending_send(session, order)
    _revoke_capabilities(session, order.id, now=_now())
    _audit_change_order(
        session,
        order,
        actor=context.subject,
        action="withdraw",
        before=before,
        after=order.status,
        correlation_id=context.correlation_id,
        metadata={"reason_present": bool(reason)},
    )
    session.flush()
    return order


def client_decide(
    session: Session,
    *,
    session_token: str,
    csrf_token: str,
    change_order_id: UUID,
    expected_row_version: int,
    revision_id: UUID,
    content_hash: str,
    decision: str,
    comment: str | None = None,
) -> ChangeOrder:
    if decision not in {"REQUEST_CHANGES", "REJECTED"}:
        raise ValidationError("Unsupported client decision")
    _session_row, capability, revision, order = _session_scope(session, session_token, csrf_token)
    if (
        capability.purpose != "REVIEW"
        or capability.consumed_at is not None
        or order.id != change_order_id
        or revision.id != revision_id
        or revision.canonical_artifact_hash != content_hash
    ):
        raise ConflictError("Client offer is stale or unavailable")
    project = session.scalar(
        select(Project)
        .where(Project.id == order.project_id, Project.tenant_id == capability.tenant_id)
        .with_for_update()
    )
    locked_order = session.scalar(
        select(ChangeOrder)
        .where(ChangeOrder.id == order.id, ChangeOrder.tenant_id == capability.tenant_id)
        .with_for_update()
    )
    if project is None or locked_order is None:
        raise ConflictError("Client offer is unavailable")
    order = locked_order
    if order.row_version != expected_row_version:
        raise ConflictError("Client offer changed; reload before deciding")
    if order.status != "AWAITING_CLIENT_APPROVAL":
        raise ConflictError("Client offer is not awaiting a decision")
    now = _now()
    capability.consumed_at = now
    target = "REVISION_REQUESTED" if decision == "REQUEST_CHANGES" else "REJECTED_BY_CLIENT"
    session.add(
        Approval(
            tenant_id=capability.tenant_id,
            project_id=order.project_id,
            change_order_id=order.id,
            revision_id=revision.id,
            actor_type="CLIENT",
            actor_identifier=f"client:{capability.client_id}",
            content_hash=content_hash,
            decision=decision,
            comment=comment,
            provenance={"model": "bearer-capability"},
        )
    )
    before = order.status
    order.status = target
    order.row_version += 1
    request = session.get(RequestRecord, order.request_id, with_for_update=True)
    if request is not None:
        request.status = "PROPOSAL_OPEN" if decision == "REQUEST_CHANGES" else "DECLINED"
        request.rejection_reason = comment
        request.row_version += 1
        if decision == "REQUEST_CHANGES":
            enqueue_job(
                session,
                tenant_id=capability.tenant_id,
                project_id=project.id,
                kind="change_order.freelancer_review",
                payload_ref={"change_order_id": str(order.id), "revision_id": str(revision.id)},
                correlation_id=uuid4(),
            )
    _revoke_capabilities(session, order.id, now=now)
    _audit_change_order(
        session,
        order,
        actor=f"client:{capability.client_id}",
        action="client_request_changes" if decision == "REQUEST_CHANGES" else "client_reject",
        before=before,
        after=target,
        correlation_id=uuid4(),
        metadata={"comment_present": bool(comment)},
    )
    session.flush()
    return order


def refresh_client_session(session: Session, *, session_token: str) -> CapabilityCredentials:
    row, capability, _revision, _order = _session_scope(session, session_token)
    row.revoked_at = _now()
    new_session_token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    new_row = ClientSession(
        capability_id=capability.id,
        session_hash=_hash(new_session_token),
        csrf_hash=_hash(csrf),
        purpose=row.purpose,
        expires_at=_now() + timedelta(hours=24),
    )
    session.add(new_row)
    session.flush()
    return CapabilityCredentials(capability, "", new_row, new_session_token, csrf)


def expire_stale_offers(session: Session, *, now: datetime | None = None) -> int:
    current = now or _now()
    count = 0
    orders = session.scalars(
        select(ChangeOrder).where(
            ChangeOrder.status.in_(("SEND_PENDING", "AWAITING_CLIENT_APPROVAL"))
        )
    ).all()
    for order in orders:
        cap = session.scalar(
            select(ClientCapability)
            .where(
                ClientCapability.change_order_id == order.id,
                ClientCapability.purpose == "REVIEW",
                ClientCapability.revoked_at.is_(None),
            )
            .order_by(ClientCapability.created_at.desc())
            .with_for_update()
        )
        if cap is None or cap.expires_at is None or _utc(cap.expires_at) > current:
            continue
        before = order.status
        order.status = "EXPIRED"
        order.row_version += 1
        cap.revoked_at = current
        _cancel_pending_send(session, order)
        _audit_change_order(
            session,
            order,
            actor="system",
            action="offer_expired",
            before=before,
            after=order.status,
            correlation_id=uuid4(),
        )
        count += 1
    pending = session.scalars(select(ChangeOrder).where(ChangeOrder.status == "SEND_PENDING")).all()
    for order in pending:
        action = session.scalar(
            select(ExternalAction)
            .where(
                ExternalAction.action_key.like(f"change-order-send:{order.id}:%"),
                ExternalAction.tenant_id == order.tenant_id,
            )
            .order_by(ExternalAction.created_at.desc())
        )
        if action is None or action.state not in {"READY", "RETRY_WAIT"}:
            continue
        approval = session.scalar(
            select(Approval)
            .where(
                Approval.change_order_id == order.id,
                Approval.actor_type == "FREELANCER",
                Approval.decision == "APPROVED",
            )
            .order_by(Approval.created_at.desc())
        )
        if approval is not None and _utc(approval.created_at) + timedelta(hours=24) <= current:
            before = order.status
            order.status = "EXPIRED"
            order.row_version += 1
            _cancel_pending_send(session, order)
            _revoke_capabilities(session, order.id, now=current)
            _audit_change_order(
                session,
                order,
                actor="system",
                action="unsent_offer_expired",
                before=before,
                after=order.status,
                correlation_id=uuid4(),
            )
            count += 1
    session.flush()
    return count


def materialize_client_approval_url(revision: ProposalRevision) -> str:
    """Return the one-time capability URL for an authenticated proposal response."""
    from services.api.config import get_settings

    base_url = str(get_settings().client_review_base_url or "http://localhost:3000").rstrip("/")
    return f"{base_url}/c#t={_unprotect(revision.token_ciphertext)}"

def materialize_ses_notification(session: Session, *, action_id: UUID) -> dict[str, object]:
    action = session.get(ExternalAction, action_id)
    if action is None or action.provider != "ses" or action.operation != "send_change_order":
        raise NotFoundError("SES notification action was not found")
    payload = action.approved_payload
    token_ciphertext = payload.get("token_ciphertext")
    if not isinstance(token_ciphertext, str):
        raise ValidationError("SES notification capability is unavailable")
    result = dict(payload)
    from services.api.config import get_settings

    base_url = str(get_settings().client_review_base_url or "http://localhost:3000").rstrip("/")
    result["approval_url"] = f"{base_url}/c#t={_unprotect(token_ciphertext)}"
    return result


def record_ses_notification_success(
    session: Session, *, action_id: UUID, provider_message_id: str
) -> Notification:
    from services.workers.durable import complete_action

    action = session.scalar(
        select(ExternalAction).where(ExternalAction.id == action_id).with_for_update()
    )
    if action is None or action.provider != "ses":
        raise NotFoundError("SES notification action was not found")
    if action.state == "DISPATCHING":
        complete_action(
            session,
            action_id=action.id,
            provider_request_id=provider_message_id,
            outcome_ref={"provider_message_id": provider_message_id},
        )
    elif action.state == "UNKNOWN_OUTCOME":
        action.state = "SUCCEEDED"
        action.receipt_ref = {"provider_message_id": provider_message_id}
    elif action.state != "SUCCEEDED":
        raise ConflictError("SES notification is not awaiting a provider result")
    notification = session.scalar(
        select(Notification).where(Notification.action_id == action.id).with_for_update()
    )
    if notification is None:
        raise NotFoundError("Notification was not found")
    notification.state = "SENT"
    session.flush()
    return notification


def record_ses_notification_unknown(
    session: Session, *, action_id: UUID, reason: str
) -> Notification:
    from services.workers.durable import mark_action_unknown

    action = session.scalar(
        select(ExternalAction).where(ExternalAction.id == action_id).with_for_update()
    )
    if action is None or action.provider != "ses":
        raise NotFoundError("SES notification action was not found")
    if action.state == "DISPATCHING":
        mark_action_unknown(session, action_id=action.id, reason=reason)
    elif action.state != "UNKNOWN_OUTCOME":
        raise ConflictError("SES notification is not awaiting a provider result")
    notification = session.scalar(
        select(Notification).where(Notification.action_id == action.id).with_for_update()
    )
    if notification is None:
        raise NotFoundError("Notification was not found")
    notification.state = "UNKNOWN_OUTCOME"
    session.flush()
    return notification


def reconcile_gmail_unknown(
    session: Session, *, action_id: UUID, matches: list[dict[str, str]]
) -> ExternalAction:
    action = session.scalar(
        select(ExternalAction).where(ExternalAction.id == action_id).with_for_update()
    )
    if action is None or action.provider != "gmail" or action.operation != "send":
        raise NotFoundError("Gmail send action was not found")
    if action.state != "UNKNOWN_OUTCOME":
        raise ConflictError("Gmail action is not awaiting reconciliation")
    expected = action.approved_payload
    exact = [
        item
        for item in matches
        if item.get("recipient") == expected.get("recipient")
        and item.get("plain_text_body") == expected.get("plain_text_body")
        and item.get("content_hash") == expected.get("content_hash")
        and item.get("marker") == expected.get("marker")
        and item.get("provider_message_id")
    ]
    if len(exact) == 1:
        return record_gmail_send_success(
            session,
            action_id=action.id,
            provider_message_id=exact[0]["provider_message_id"],
            recipient=str(expected["recipient"]),
            plain_text_body=str(expected["plain_text_body"]),
            content_hash=str(expected["content_hash"]),
        )
    if len(exact) > 1:
        from services.workers.durable import _transition_action

        _transition_action(action, "REVIEW_REQUIRED")
        action.uncertainty_reason = "multiple_exact_provider_matches"
    session.flush()
    return action
