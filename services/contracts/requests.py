from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.contracts.service import _require_project
from services.domain.auth import TrustedContext
from services.domain.errors import AuthorizationError, ConflictError, NotFoundError, ValidationError
from services.domain.models import CommunicationEvent, RequestCommunication, RequestRecord


def create_request(session: Session, context: TrustedContext, *, project_id: UUID, summary: str, communication_ids: list[UUID] | None = None) -> RequestRecord:
    project = _require_project(session, context, project_id)
    if not summary.strip():
        raise ValidationError("Request summary is required")
    request = RequestRecord(tenant_id=context.tenant_id, project_id=project.id, summary=summary[:4000])
    session.add(request)
    session.flush()
    for communication_id in communication_ids or []:
        communication = session.scalar(select(CommunicationEvent).where(CommunicationEvent.id == communication_id, CommunicationEvent.tenant_id == context.tenant_id))
        if communication is None or communication.project_id != project_id:
            raise AuthorizationError("Communication does not belong to this project")
        session.add(RequestCommunication(tenant_id=context.tenant_id, project_id=project_id, request_id=request.id, communication_id=communication_id))
    session.flush()
    return request


def get_request(session: Session, context: TrustedContext, request_id: UUID) -> RequestRecord:
    request = session.scalar(select(RequestRecord).where(RequestRecord.id == request_id, RequestRecord.tenant_id == context.tenant_id))
    if request is None:
        raise NotFoundError("Request was not found")
    return request


def clarify_request(session: Session, context: TrustedContext, *, request_id: UUID, correction: str) -> RequestRecord:
    request = get_request(session, context, request_id)
    if request.status not in {"OPEN", "CLARIFICATION_REQUIRED", "PROPOSAL_OPEN"}:
        raise ConflictError("This request cannot be clarified in its current state")
    if not correction.strip():
        raise ValidationError("Clarification requires a correction or evidence note")
    request.summary = correction[:4000]
    request.status = "OPEN"
    request.request_version += 1
    request.row_version += 1
    session.flush()
    return request


def merge_requests(session: Session, context: TrustedContext, *, target_request_id: UUID, source_request_id: UUID, reason: str) -> RequestRecord:
    target = get_request(session, context, target_request_id)
    source = get_request(session, context, source_request_id)
    if target.id == source.id or target.project_id != source.project_id:
        raise ConflictError("Requests must be distinct and belong to the same project")
    if not reason.strip() or source.status in {"RESOLVED", "MERGED"}:
        raise ConflictError("Only unresolved requests with a merge reason can be merged")
    associations = list(session.scalars(select(RequestCommunication).where(RequestCommunication.request_id == source.id)))
    for association in associations:
        existing = session.scalar(select(RequestCommunication).where(RequestCommunication.request_id == target.id, RequestCommunication.communication_id == association.communication_id))
        if existing is None:
            session.add(RequestCommunication(tenant_id=context.tenant_id, project_id=target.project_id, request_id=target.id, communication_id=association.communication_id, relationship_type="MERGED_PROVENANCE"))
    source.status = "MERGED"
    source.merged_into_id = target.id
    source.rejection_reason = reason[:500]
    source.row_version += 1
    target.request_version += 1
    target.row_version += 1
    session.flush()
    return target


def split_request(
    session: Session,
    context: TrustedContext,
    *,
    request_id: UUID,
    parts: list[tuple[str, list[UUID]]],
    reason: str,
) -> list[RequestRecord]:
    source = get_request(session, context, request_id)
    if source.status in {"RESOLVED", "MERGED"}:
        raise ConflictError("Resolved requests cannot be split")
    if not reason.strip() or len(parts) < 2:
        raise ValidationError("A split requires at least two parts and a reason")
    communications = {item.communication_id for item in session.scalars(select(RequestCommunication).where(RequestCommunication.request_id == source.id))}
    created: list[RequestRecord] = []
    assigned: set[UUID] = set()
    for summary, communication_ids in parts:
        if not summary.strip() or any(item not in communications for item in communication_ids) or assigned.intersection(communication_ids):
            raise AuthorizationError("Split parts must use distinct communications from the source request")
        request = RequestRecord(tenant_id=context.tenant_id, project_id=source.project_id, summary=summary[:4000])
        session.add(request)
        session.flush()
        session.add_all(RequestCommunication(tenant_id=context.tenant_id, project_id=source.project_id, request_id=request.id, communication_id=item, relationship_type="SPLIT_PROVENANCE") for item in communication_ids)
        assigned.update(communication_ids)
        created.append(request)
    source.status = "MERGED"
    source.rejection_reason = reason[:500]
    source.row_version += 1
    session.flush()
    return created
