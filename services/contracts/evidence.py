from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.domain.auth import TrustedContext
from services.domain.canonical import canonical_sha256
from services.domain.errors import NotFoundError, ValidationError
from services.domain.models import (
    DocumentChunk,
    EvidenceBundle,
    EvidenceReference,
    Project,
)


@dataclass(frozen=True, slots=True)
class ChunkSearchResult:
    chunk_id: UUID
    document_id: UUID
    source_version: str
    excerpt: str
    locator: dict[str, object]
    content_hash: str


def search_contract_chunks(
    session: Session,
    context: TrustedContext,
    *,
    project_id: UUID,
    query: str,
    limit: int = 20,
) -> list[ChunkSearchResult]:
    project = session.scalar(select(Project).where(Project.id == project_id, Project.tenant_id == context.tenant_id))
    if project is None:
        raise NotFoundError("Project was not found")
    if not query.strip():
        raise ValidationError("Evidence search requires a query")
    if limit < 1 or limit > 100:
        raise ValidationError("Evidence search limit must be between 1 and 100")
    terms = [term.lower() for term in query.split() if term.strip()]
    rows = session.scalars(select(DocumentChunk).where(DocumentChunk.tenant_id == context.tenant_id, DocumentChunk.project_id == project_id).order_by(DocumentChunk.created_at, DocumentChunk.chunk_index)).all()
    results: list[ChunkSearchResult] = []
    for row in rows:
        lowered = row.source_text.lower()
        if all(term in lowered for term in terms):
            results.append(ChunkSearchResult(chunk_id=row.id, document_id=row.document_id, source_version=str(row.document_id), excerpt=row.source_text[:2000], locator={"page": row.page_number, "section": row.section, "start": row.start_offset, "end": row.end_offset}, content_hash=row.content_hash))
            if len(results) >= limit:
                break
    return results


def create_evidence_bundle(
    session: Session,
    context: TrustedContext,
    *,
    project_id: UUID,
    request_id: UUID | None,
    searched_sources: list[dict[str, object]],
    completeness: str,
    cutoff: datetime | None = None,
) -> EvidenceBundle:
    if completeness not in {"COMPLETE", "PARTIAL", "UNAVAILABLE"}:
        raise ValidationError("Evidence completeness is invalid")
    if not session.scalar(select(Project.id).where(Project.id == project_id, Project.tenant_id == context.tenant_id)):
        raise NotFoundError("Project was not found")
    now = cutoff or datetime.now(UTC)
    bundle = EvidenceBundle(tenant_id=context.tenant_id, project_id=project_id, request_id=request_id, snapshot_digest=canonical_sha256(searched_sources), searched_sources=searched_sources, cutoff=now, completeness=completeness)
    session.add(bundle)
    session.flush()
    return bundle


def add_evidence_reference(
    session: Session,
    context: TrustedContext,
    *,
    bundle_id: UUID,
    source_type: str,
    source_id: str,
    source_version: str,
    exact_excerpt_ref: str,
    content_hash: str,
    locator: dict[str, object],
    access_scope: str,
    relation: str,
    fetched_at: datetime | None = None,
) -> EvidenceReference:
    bundle = session.scalar(select(EvidenceBundle).where(EvidenceBundle.id == bundle_id, EvidenceBundle.tenant_id == context.tenant_id))
    if bundle is None:
        raise NotFoundError("Evidence bundle was not found")
    if relation not in {"SUPPORTS", "CONTRADICTS", "CONTEXT"}:
        raise ValidationError("Evidence relation is invalid")
    reference = EvidenceReference(tenant_id=context.tenant_id, project_id=bundle.project_id, bundle_id=bundle.id, source_type=source_type, source_id=source_id, source_version=source_version, exact_excerpt_ref=exact_excerpt_ref, content_hash=content_hash, locator=locator, fetched_at=fetched_at or datetime.now(UTC), access_scope=access_scope, relation=relation)
    session.add(reference)
    session.flush()
    return reference
