from __future__ import annotations

import hashlib
import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from services.contracts.extraction import ExtractionError, extract_document_bounded
from services.contracts.storage import ObjectStoreUnavailable, create_private_upload
from services.domain.auth import TrustedContext
from services.domain.canonical import canonical_sha256
from services.domain.errors import AuthorizationError, ConflictError, NotFoundError, ValidationError
from services.domain.models import (
    CommunicationEvent,
    ContractDocument,
    DocumentChunk,
    DocumentUploadGrant,
    ExternalEvent,
    IntegrationBinding,
    Project,
    RequestCommunication,
    RequestRecord,
    RoutingDecision,
    ScopeCandidate,
    ScopeItem,
    ScopeVersion,
    ScopeVersionItem,
    ThreadAssignment,
)


@dataclass(frozen=True, slots=True)
class UploadGrantResult:
    document: ContractDocument
    token: str
    expires_at: datetime
    upload_url: str | None = None
    upload_fields: dict[str, str] | None = None


@dataclass(frozen=True, slots=True)
class UploadSource:
    object_key: str
    expected_size_bytes: int
    expected_mime_type: str


def _require_project(session: Session, context: TrustedContext, project_id: UUID) -> Project:
    project = session.scalar(select(Project).where(Project.id == project_id, Project.tenant_id == context.tenant_id))
    if project is None:
        raise NotFoundError("Project was not found")
    return project


def create_upload_grant(
    session: Session,
    context: TrustedContext,
    *,
    project_id: UUID,
    object_key: str,
    mime_type: str,
    expected_size_bytes: int,
    expires_in_seconds: int = 900,
) -> UploadGrantResult:
    _require_project(session, context, project_id)
    if not object_key or object_key.startswith("/") or ".." in object_key.split("/"):
        raise ValidationError("Object key is invalid")
    filename = object_key.rsplit("/", 1)[-1]
    if not filename or filename in {".", ".."}:
        raise ValidationError("Object key must include a filename")
    if expected_size_bytes < 1 or expected_size_bytes > 10 * 1024 * 1024:
        raise ValidationError("Document size must be between 1 byte and 10 MiB")
    if expires_in_seconds < 60 or expires_in_seconds > 3600:
        raise ValidationError("Upload grant expiry must be between one minute and one hour")
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=expires_in_seconds)
    storage_key = f"contracts/{context.tenant_id}/{project_id}/{uuid4()}/{filename}"
    document = ContractDocument(
        tenant_id=context.tenant_id,
        project_id=project_id,
        object_key=storage_key,
        object_version=str(uuid4()),
        sha256="pending",
        size_bytes=expected_size_bytes,
        mime_type=mime_type,
        source_type="UPLOAD",
    )
    session.add(document)
    session.flush()
    session.add(
        DocumentUploadGrant(
            tenant_id=context.tenant_id,
            project_id=project_id,
            document_id=document.id,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expected_size_bytes=expected_size_bytes,
            expected_mime_type=mime_type,
            expires_at=expires_at,
        )
    )
    session.flush()
    try:
        presigned = create_private_upload(object_key=document.object_key, mime_type=mime_type, size_bytes=expected_size_bytes)
    except ObjectStoreUnavailable:
        presigned = None
    return UploadGrantResult(document=document, token=token, expires_at=expires_at, upload_url=presigned.url if presigned else None, upload_fields=presigned.fields if presigned else None)


def get_upload_source(
    session: Session,
    context: TrustedContext,
    *,
    document_id: UUID,
    upload_token: str,
) -> UploadSource:
    document = session.scalar(
        select(ContractDocument).where(
            ContractDocument.id == document_id, ContractDocument.tenant_id == context.tenant_id
        )
    )
    grant = session.scalar(
        select(DocumentUploadGrant).where(
            DocumentUploadGrant.document_id == document_id,
            DocumentUploadGrant.tenant_id == context.tenant_id,
            DocumentUploadGrant.token_hash == hashlib.sha256(upload_token.encode()).hexdigest(),
        )
    )
    if document is None or grant is None:
        raise NotFoundError("Document upload was not found")
    grant_expiry = grant.expires_at if grant.expires_at.tzinfo is not None else grant.expires_at.replace(tzinfo=UTC)
    if grant.consumed_at is not None or grant_expiry <= datetime.now(UTC):
        raise ConflictError("Document upload grant is expired or already consumed")
    if document.project_id != grant.project_id:
        raise AuthorizationError("Document ownership is invalid")
    return UploadSource(
        object_key=document.object_key,
        expected_size_bytes=grant.expected_size_bytes,
        expected_mime_type=grant.expected_mime_type,
    )


def complete_upload(
    session: Session,
    context: TrustedContext,
    *,
    document_id: UUID,
    upload_token: str,
    content: bytes,
    declared_sha256: str,
    declared_mime_type: str,
) -> ContractDocument:
    document = session.scalar(
        select(ContractDocument).where(
            ContractDocument.id == document_id,
            ContractDocument.tenant_id == context.tenant_id,
        ).with_for_update()
    )
    grant = session.scalar(
        select(DocumentUploadGrant).where(
            DocumentUploadGrant.document_id == document_id,
            DocumentUploadGrant.tenant_id == context.tenant_id,
            DocumentUploadGrant.token_hash == hashlib.sha256(upload_token.encode()).hexdigest(),
        ).with_for_update()
    )
    if document is None or grant is None:
        raise NotFoundError("Document upload was not found")
    grant_expiry = grant.expires_at if grant.expires_at.tzinfo is not None else grant.expires_at.replace(tzinfo=UTC)
    if grant.consumed_at is not None or grant_expiry <= datetime.now(UTC):
        raise ConflictError("Document upload grant is expired or already consumed")
    if document.project_id != grant.project_id:
        raise AuthorizationError("Document ownership is invalid")
    if len(content) != grant.expected_size_bytes or declared_mime_type != grant.expected_mime_type:
        document.status = "REJECTED"
        document.rejection_reason = "upload_metadata_mismatch"
        session.flush()
        return document
    digest = hashlib.sha256(content).hexdigest()
    if digest != declared_sha256:
        document.status = "REJECTED"
        document.rejection_reason = "checksum_mismatch"
        session.flush()
        return document
    document.status = "EXTRACTING"
    session.flush()
    try:
        result = extract_document_bounded(content, mime_type=declared_mime_type, declared_size=len(content))
    except ExtractionError as exc:
        document.status = "REJECTED"
        document.rejection_reason = f"{exc.code}:{exc.message}"[:500]
        grant.consumed_at = datetime.now(UTC)
        session.flush()
        return document
    document.sha256 = result.sha256
    document.size_bytes = result.size_bytes
    document.extractor_version = result.extractor_version
    document.status = "AWAITING_SCOPE_REVIEW"
    document.completed_at = datetime.now(UTC)
    grant.consumed_at = datetime.now(UTC)
    session.add_all(
        DocumentChunk(
            tenant_id=context.tenant_id,
            project_id=document.project_id,
            document_id=document.id,
            chunk_index=chunk.index,
            page_number=chunk.page_number,
            section=chunk.section,
            start_offset=chunk.start_offset,
            end_offset=chunk.end_offset,
            source_text=chunk.text,
            content_hash=hashlib.sha256(chunk.text.encode()).hexdigest(),
        )
        for chunk in result.chunks
    )
    session.flush()
    return document


def persist_structure_candidates(
    session: Session,
    context: TrustedContext,
    *,
    document_id: UUID,
    candidates: Sequence[object],
    extractor_version: str,
) -> list[ScopeCandidate]:
    """Persist only candidates already validated against this document's exact chunks."""
    from services.contracts.structure import ValidatedScopeCandidate

    document = get_document(session, context, document_id)
    if document.status not in {"AWAITING_SCOPE_REVIEW", "CONFIRMED"}:
        raise ConflictError("Document is not ready for scope extraction")
    existing = {
        item.item_key: item
        for item in session.scalars(
            select(ScopeCandidate).where(
                ScopeCandidate.document_id == document_id,
                ScopeCandidate.tenant_id == context.tenant_id,
            )
        )
    }
    persisted: list[ScopeCandidate] = []
    for candidate in candidates:
        if not isinstance(candidate, ValidatedScopeCandidate):
            raise ValidationError("Scope provider returned an invalid candidate")
        current = existing.get(candidate.item_key)
        if current is not None:
            if current.source_chunk_id != candidate.source_chunk_id or current.extracted_text != candidate.text:
                raise ConflictError("A scope candidate key already has a different source span")
            persisted.append(current)
            continue
        item = ScopeCandidate(
            tenant_id=context.tenant_id,
            project_id=document.project_id,
            document_id=document_id,
            source_chunk_id=candidate.source_chunk_id,
            item_key=candidate.item_key,
            item_type=candidate.item_type,
            extracted_text=candidate.text,
            extractor_version=extractor_version,
        )
        session.add(item)
        session.flush()
        existing[item.item_key] = item
        persisted.append(item)
    return persisted


def add_scope_candidate(
    session: Session,
    context: TrustedContext,
    *,
    document_id: UUID,
    source_chunk_id: UUID,
    item_key: str,
    item_type: str,
    extracted_text: str,
    extractor_version: str,
) -> ScopeCandidate:
    document = session.scalar(select(ContractDocument).where(ContractDocument.id == document_id, ContractDocument.tenant_id == context.tenant_id))
    chunk = session.scalar(select(DocumentChunk).where(DocumentChunk.id == source_chunk_id, DocumentChunk.tenant_id == context.tenant_id, DocumentChunk.document_id == document_id))
    if document is None or chunk is None:
        raise NotFoundError("Document source was not found")
    if not item_key or not extracted_text.strip():
        raise ValidationError("Scope candidates require a key and source text")
    candidate = ScopeCandidate(
        tenant_id=context.tenant_id,
        project_id=document.project_id,
        document_id=document_id,
        source_chunk_id=source_chunk_id,
        item_key=item_key,
        item_type=item_type,
        extracted_text=extracted_text,
        extractor_version=extractor_version,
    )
    session.add(candidate)
    session.flush()
    return candidate


def correct_scope_candidate(
    session: Session,
    context: TrustedContext,
    *,
    candidate_id: UUID,
    corrected_text: str,
    reason: str,
) -> ScopeCandidate:
    candidate = session.scalar(select(ScopeCandidate).where(ScopeCandidate.id == candidate_id, ScopeCandidate.tenant_id == context.tenant_id).with_for_update())
    if candidate is None:
        raise NotFoundError("Scope candidate was not found")
    if not corrected_text.strip() or not reason.strip():
        raise ValidationError("Corrections require text and a reason")
    candidate.corrected_text = corrected_text
    candidate.correction_reason = reason[:500]
    candidate.status = "CORRECTED"
    session.flush()
    return candidate


def confirm_scope(
    session: Session,
    context: TrustedContext,
    *,
    project_id: UUID,
    candidate_ids: list[UUID],
) -> ScopeVersion:
    project = _require_project(session, context, project_id)
    if not candidate_ids:
        raise ValidationError("At least one scope candidate is required")
    candidates = list(session.scalars(select(ScopeCandidate).where(ScopeCandidate.tenant_id == context.tenant_id, ScopeCandidate.project_id == project_id, ScopeCandidate.id.in_(candidate_ids)).with_for_update()))
    if len(candidates) != len(set(candidate_ids)):
        raise AuthorizationError("One or more scope candidates do not belong to this project")
    if any(candidate.status == "REJECTED" for candidate in candidates):
        raise ConflictError("Rejected scope candidates cannot be confirmed")
    next_version = int(session.scalar(select(func.max(ScopeVersion.version)).where(ScopeVersion.tenant_id == context.tenant_id, ScopeVersion.project_id == project_id)) or 0) + 1
    item_payloads: list[dict[str, object]] = []
    items: list[ScopeItem] = []
    for candidate in sorted(candidates, key=lambda item: item.item_key):
        item = ScopeItem(
            tenant_id=context.tenant_id,
            project_id=project_id,
            source_document_chunk_id=candidate.source_chunk_id,
            source_revision_id=candidate.id,
            item_type=candidate.item_type,
            item_key=candidate.item_key,
            text=candidate.corrected_text or candidate.extracted_text,
        )
        items.append(item)
        item_payloads.append({"key": item.item_key, "type": item.item_type, "text": item.text, "source": str(candidate.source_chunk_id)})
    content_hash = canonical_sha256(item_payloads)
    version = ScopeVersion(
        tenant_id=context.tenant_id,
        project_id=project_id,
        version=next_version,
        parent_version_id=project.current_scope_version_id,
        confirmation_actor=context.subject,
        content_hash=content_hash,
    )
    session.add(version)
    session.flush()
    session.add_all(items)
    session.flush()
    session.add_all(ScopeVersionItem(tenant_id=context.tenant_id, project_id=project_id, scope_version_id=version.id, scope_item_id=item.id) for item in items)
    for candidate in candidates:
        candidate.status = "CONFIRMED"
    for document in session.scalars(select(ContractDocument).where(ContractDocument.id.in_({candidate.document_id for candidate in candidates}))).all():
        document.status = "CONFIRMED"
    project.current_scope_version_id = version.id
    project.status = "ACTIVE"
    session.flush()
    return version


def ingest_external_event(
    session: Session,
    context: TrustedContext,
    *,
    provider: str,
    environment: str,
    provider_event_id: str,
    payload_hash: str,
    occurred_at: datetime,
    connection_id: UUID | None = None,
) -> ExternalEvent:
    existing = session.scalar(select(ExternalEvent).where(ExternalEvent.tenant_id == context.tenant_id, ExternalEvent.connection_id == connection_id, ExternalEvent.provider_event_id == provider_event_id))
    if existing is not None:
        if existing.payload_hash != payload_hash:
            raise ConflictError("Provider delivery ID was reused with different content")
        return existing
    event = ExternalEvent(tenant_id=context.tenant_id, connection_id=connection_id, provider=provider, environment=environment, provider_event_id=provider_event_id, payload_hash=payload_hash, occurred_at=occurred_at, correlation_id=context.correlation_id)
    session.add(event)
    session.flush()
    return event


def route_external_event(
    session: Session,
    context: TrustedContext,
    *,
    external_event_id: UUID,
    resource_type: str,
    resource_id: str,
    source_version: str,
    content_ref: str,
    occurred_at: datetime,
    explicit_project_id: UUID | None = None,
    alias: str | None = None,
    sender: str | None = None,
    thread_id: str | None = None,
) -> CommunicationEvent | RoutingDecision:
    event = session.scalar(select(ExternalEvent).where(ExternalEvent.id == external_event_id, ExternalEvent.tenant_id == context.tenant_id))
    if event is None:
        raise NotFoundError("External event was not found")
    event.resource_type = resource_type
    event.resource_id = resource_id
    event.source_version = source_version
    event.content_ref = content_ref
    existing = session.scalar(select(CommunicationEvent).where(CommunicationEvent.tenant_id == context.tenant_id, CommunicationEvent.connection_id == event.connection_id, CommunicationEvent.resource_type == resource_type, CommunicationEvent.resource_id == resource_id, CommunicationEvent.source_version == source_version))
    if existing is not None:
        return existing
    project_ids: list[UUID] = []
    precedence = "UNMAPPED"
    if explicit_project_id is not None:
        _require_project(session, context, explicit_project_id)
        project_ids = [explicit_project_id]
        precedence = "EXPLICIT"
    elif thread_id:
        project_ids = list(session.scalars(select(ThreadAssignment.project_id).where(ThreadAssignment.tenant_id == context.tenant_id, ThreadAssignment.connection_id == event.connection_id, ThreadAssignment.thread_id == thread_id)))
        precedence = "THREAD_ASSIGNMENT"
    elif alias:
        project_ids = list(session.scalars(select(IntegrationBinding.project_id).where(IntegrationBinding.tenant_id == context.tenant_id, IntegrationBinding.alias == alias, IntegrationBinding.status == "ACTIVE").distinct()))
        precedence = "ALIAS"
    else:
        project_ids = list(session.scalars(select(IntegrationBinding.project_id).where(IntegrationBinding.tenant_id == context.tenant_id, IntegrationBinding.provider == event.provider, IntegrationBinding.resource_type == resource_type, IntegrationBinding.resource_id == resource_id, IntegrationBinding.status == "ACTIVE").distinct()))
        precedence = "BINDING"
    if len(project_ids) != 1:
        decision = RoutingDecision(tenant_id=context.tenant_id, external_event_id=external_event_id, precedence=precedence, candidate_projects=[str(item) for item in project_ids], evidence=[{"resource_type": resource_type, "resource_id": resource_id, "source_version": source_version}], status="OPEN")
        session.add(decision)
        session.flush()
        return decision
    project = session.get(Project, project_ids[0])
    if project is None:
        raise NotFoundError("Routed project was not found")
    if project.status == "PAUSED_UNCONFIRMED_SCOPE":
        event.processing_status = "BLOCKED_BY_SCOPE"
    communication = CommunicationEvent(tenant_id=context.tenant_id, project_id=project_ids[0], connection_id=event.connection_id, external_event_id=event.id, resource_type=resource_type, resource_id=resource_id, source_version=source_version, sender=sender, thread_id=thread_id, occurred_at=occurred_at, content_ref=content_ref, direction="INBOUND")
    session.add(communication)
    session.flush()
    if event.processing_status != "BLOCKED_BY_SCOPE":
        event.processing_status = "MAPPED"
    return communication


def resolve_routing_decision(
    session: Session,
    context: TrustedContext,
    *,
    decision_id: UUID,
    project_id: UUID,
    actor: str,
) -> CommunicationEvent | RoutingDecision:
    decision = session.scalar(select(RoutingDecision).where(RoutingDecision.id == decision_id, RoutingDecision.tenant_id == context.tenant_id).with_for_update())
    if decision is None:
        raise NotFoundError("Routing decision was not found")
    if decision.status != "OPEN" or str(project_id) not in decision.candidate_projects:
        raise ConflictError("Routing decision is stale or the project is not a candidate")
    _require_project(session, context, project_id)
    decision.status = "RESOLVED"
    decision.selected_project_id = project_id
    decision.resolved_by = actor
    decision.resolved_at = datetime.now(UTC)
    event = session.get(ExternalEvent, decision.external_event_id)
    if event is None or not event.resource_type or not event.resource_id or not event.source_version or not event.content_ref:
        raise ConflictError("Original event identity is incomplete and cannot be replayed")
    result = route_external_event(session, context, external_event_id=event.id, resource_type=event.resource_type, resource_id=event.resource_id, source_version=event.source_version, content_ref=event.content_ref, occurred_at=event.occurred_at, explicit_project_id=project_id)
    session.flush()
    return result


def replay_external_event(
    session: Session,
    context: TrustedContext,
    *,
    external_event_id: UUID,
    project_id: UUID,
) -> CommunicationEvent | RoutingDecision:
    event = session.scalar(select(ExternalEvent).where(ExternalEvent.id == external_event_id, ExternalEvent.tenant_id == context.tenant_id))
    if event is None:
        raise NotFoundError("External event was not found")
    if not event.resource_type or not event.resource_id or not event.source_version or not event.content_ref:
        raise ConflictError("Original event identity is incomplete and cannot be replayed")
    return route_external_event(session, context, external_event_id=event.id, resource_type=event.resource_type, resource_id=event.resource_id, source_version=event.source_version, content_ref=event.content_ref, occurred_at=event.occurred_at, explicit_project_id=project_id)


def associate_request(
    session: Session,
    context: TrustedContext,
    *,
    request_id: UUID,
    communication_id: UUID,
    relationship_type: str = "SUPPORTS",
) -> RequestCommunication:
    request = session.scalar(select(RequestRecord).where(RequestRecord.id == request_id, RequestRecord.tenant_id == context.tenant_id).with_for_update())
    communication = session.scalar(select(CommunicationEvent).where(CommunicationEvent.id == communication_id, CommunicationEvent.tenant_id == context.tenant_id))
    if request is None or communication is None or request.project_id != communication.project_id:
        raise AuthorizationError("Request and communication must share a tenant and project")
    association = RequestCommunication(tenant_id=context.tenant_id, project_id=request.project_id, request_id=request_id, communication_id=communication_id, relationship_type=relationship_type)
    session.add(association)
    session.flush()
    return association


def list_documents(session: Session, context: TrustedContext, project_id: UUID) -> list[ContractDocument]:
    _require_project(session, context, project_id)
    return list(session.scalars(select(ContractDocument).where(ContractDocument.tenant_id == context.tenant_id, ContractDocument.project_id == project_id).order_by(ContractDocument.created_at.desc())))


def list_candidates(session: Session, context: TrustedContext, document_id: UUID) -> list[ScopeCandidate]:
    document = get_document(session, context, document_id)
    return list(session.scalars(select(ScopeCandidate).where(ScopeCandidate.document_id == document.id, ScopeCandidate.tenant_id == context.tenant_id).order_by(ScopeCandidate.created_at, ScopeCandidate.item_key)))


def list_routing_decisions(session: Session, context: TrustedContext) -> list[RoutingDecision]:
    return list(session.scalars(select(RoutingDecision).where(RoutingDecision.tenant_id == context.tenant_id).order_by(RoutingDecision.created_at.desc())))


def get_document(session: Session, context: TrustedContext, document_id: UUID) -> ContractDocument:
    document = session.scalar(select(ContractDocument).where(ContractDocument.id == document_id, ContractDocument.tenant_id == context.tenant_id))
    if document is None:
        raise NotFoundError("Document was not found")
    return document


def read_confirmed_scope(session: Session, context: TrustedContext, project_id: UUID) -> ScopeVersion:
    project = _require_project(session, context, project_id)
    if project.current_scope_version_id is None:
        raise NotFoundError("Project has no confirmed scope")
    version = session.get(ScopeVersion, project.current_scope_version_id)
    if version is None or version.tenant_id != context.tenant_id or version.project_id != project_id:
        raise NotFoundError("Project scope was not found")
    return version


