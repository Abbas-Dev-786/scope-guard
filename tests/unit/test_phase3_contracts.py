from __future__ import annotations

import hashlib
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from services.contracts.extraction import (
    ExtractionError,
    extract_document,
    extract_document_bounded,
)
from services.contracts.service import (
    add_scope_candidate,
    complete_upload,
    confirm_scope,
    create_upload_grant,
    ingest_external_event,
    route_external_event,
)
from services.domain.auth import TrustedContext
from services.domain.models import (
    Base,
    Client,
    ContractDocument,
    DocumentChunk,
    IntegrationBinding,
    PreferenceVersion,
    Project,
    RoutingDecision,
    ScopeVersion,
    User,
)

TENANT = uuid.UUID("11111111-1111-4111-8111-111111111111")


@pytest.fixture
def context_and_factory(tmp_path: Path) -> tuple[TrustedContext, sessionmaker[Session]]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'phase3.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as session:
        session.add(User(id=TENANT, cognito_sub="phase3-owner", verified_email="phase3@example.com", timezone="UTC"))
        session.add(PreferenceVersion(tenant_id=TENANT, version=1, rate_minor=1000, minimum_minor=1000, increment_minor=1000))
        client = Client(tenant_id=TENANT, name="Acme")
        session.add(client)
        session.flush()
        session.add(Project(tenant_id=TENANT, client_id=client.id, name="Alpha", preference_version_id=session.scalar(select(PreferenceVersion.id)), timezone="UTC"))
    context = TrustedContext(tenant_id=TENANT, subject="phase3-owner", email="phase3@example.com", email_verified=True, correlation_id=uuid.uuid4())
    return context, factory


def test_extraction_rejects_unsafe_inputs_and_chunks_text() -> None:
    result = extract_document(b"Heading\n\nIncluded work", mime_type="text/markdown")
    assert result.sha256 == hashlib.sha256(b"Heading\n\nIncluded work").hexdigest()
    assert len(result.chunks) == 2
    with pytest.raises(ExtractionError, match="Scanned-only"):
        extract_document(b"%PDF-1.7\n/Type /Page", mime_type="application/pdf")
    with pytest.raises(ExtractionError, match="Unsupported"):
        extract_document(b"data", mime_type="application/octet-stream")


def test_extraction_timeout_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    def slow_extract(*args: object, **kwargs: object) -> object:
        time.sleep(0.05)
        return None

    import services.contracts.extraction as extraction

    monkeypatch.setattr(extraction, "extract_document", slow_extract)
    with pytest.raises(ExtractionError, match="time limit"):
        extract_document_bounded(b"data", mime_type="text/plain", timeout_seconds=0.001)


def test_upload_scope_confirmation_is_versioned_and_immutable(context_and_factory: tuple[TrustedContext, sessionmaker[Session]]) -> None:
    context, factory = context_and_factory
    with factory.begin() as session:
        project_id = session.scalar(select(Project.id).where(Project.tenant_id == TENANT))
        content = b"Included implementation\n\nExcluded hosting"
        grant = create_upload_grant(session, context, project_id=project_id, object_key="contracts/sow.md", mime_type="text/markdown", expected_size_bytes=len(content))
        document_id = grant.document.id
        assert str(project_id) in grant.document.object_key
        completed = complete_upload(session, context, document_id=document_id, upload_token=grant.token, content=content, declared_sha256=hashlib.sha256(content).hexdigest(), declared_mime_type="text/markdown")
        assert completed.status == "AWAITING_SCOPE_REVIEW"
        chunk = session.scalar(select(DocumentChunk).where(DocumentChunk.document_id == document_id))
        candidate = add_scope_candidate(session, context, document_id=document_id, source_chunk_id=chunk.id, item_key="included", item_type="INCLUDED", extracted_text=chunk.source_text, extractor_version="fixture")
        version = confirm_scope(session, context, project_id=project_id, candidate_ids=[candidate.id])
        assert version.version == 1
        assert session.get(ContractDocument, document_id).status == "CONFIRMED"
        assert session.get(Project, project_id).status == "ACTIVE"
        assert session.scalar(select(ScopeVersion).where(ScopeVersion.id == version.id)) is not None


def test_routing_preserves_ambiguity_and_deduplicates_explicit_mapping(context_and_factory: tuple[TrustedContext, sessionmaker[Session]]) -> None:
    context, factory = context_and_factory
    with factory.begin() as session:
        projects = list(session.scalars(select(Project).where(Project.tenant_id == TENANT)))
        project_one = projects[0]
        project_two = Project(tenant_id=TENANT, client_id=project_one.client_id, name="Beta", preference_version_id=project_one.preference_version_id, timezone="UTC")
        session.add(project_two)
        session.flush()
        event = ingest_external_event(session, context, provider="fixture", environment="test", provider_event_id="delivery-1", payload_hash="a" * 64, occurred_at=datetime.now(UTC))
        session.add_all([
            IntegrationBinding(tenant_id=TENANT, project_id=project_one.id, provider="fixture", resource_type="thread", resource_id="thread-1"),
            IntegrationBinding(tenant_id=TENANT, project_id=project_two.id, provider="fixture", resource_type="thread", resource_id="thread-1"),
        ])
        session.flush()
        decision = route_external_event(session, context, external_event_id=event.id, resource_type="thread", resource_id="thread-1", source_version="v1", content_ref="fixture://message-1", occurred_at=datetime.now(UTC))
        assert isinstance(decision, RoutingDecision)
        assert decision.status == "OPEN"
        communication = route_external_event(session, context, external_event_id=event.id, resource_type="thread", resource_id="thread-1", source_version="v1", content_ref="fixture://message-1", occurred_at=datetime.now(UTC), explicit_project_id=project_one.id)
        assert communication.project_id == project_one.id
        duplicate = route_external_event(session, context, external_event_id=event.id, resource_type="thread", resource_id="thread-1", source_version="v1", content_ref="fixture://message-1", occurred_at=datetime.now(UTC), explicit_project_id=project_one.id)
        assert duplicate.id == communication.id


def test_mapping_resolution_replays_original_event_and_evidence_is_snapshot_bound(context_and_factory: tuple[TrustedContext, sessionmaker[Session]]) -> None:
    from services.contracts.evidence import (
        add_evidence_reference,
        create_evidence_bundle,
        search_contract_chunks,
    )
    from services.contracts.service import resolve_routing_decision
    from services.domain.models import EvidenceReference, RoutingDecision

    context, factory = context_and_factory
    with factory.begin() as session:
        project = session.scalar(select(Project).where(Project.tenant_id == TENANT))
        event = ingest_external_event(session, context, provider="fixture", environment="test", provider_event_id="delivery-resolve", payload_hash="b" * 64, occurred_at=datetime.now(UTC))
        decision = route_external_event(session, context, external_event_id=event.id, resource_type="message", resource_id="msg-1", source_version="v1", content_ref="fixture://msg-1", occurred_at=datetime.now(UTC), sender="client@example.com", thread_id="thread-unmapped")
        assert isinstance(decision, RoutingDecision)
        communication = resolve_routing_decision(session, context, decision_id=decision.id, project_id=project.id, actor="operator")
        assert communication.project_id == project.id
        assert communication.sender == "client@example.com"
        from services.domain.models import ThreadAssignment
        assignment = session.scalar(select(ThreadAssignment).where(ThreadAssignment.thread_id == "thread-unmapped"))
        assert assignment is not None and assignment.project_id == project.id
        bundle = create_evidence_bundle(session, context, project_id=project.id, request_id=None, searched_sources=[{"source": "contract", "coverage": "COMPLETE"}], completeness="COMPLETE")
        add_evidence_reference(session, context, bundle_id=bundle.id, source_type="document_chunk", source_id="chunk-1", source_version="v1", exact_excerpt_ref="object://excerpt", content_hash="c" * 64, locator={"page": 1}, access_scope="tenant", relation="SUPPORTS")
        assert session.scalar(select(EvidenceReference).where(EvidenceReference.bundle_id == bundle.id)) is not None
        assert search_contract_chunks(session, context, project_id=project.id, query="never-matching-term") == []


def test_request_clarify_merge_and_split_preserve_provenance(context_and_factory: tuple[TrustedContext, sessionmaker[Session]]) -> None:
    from services.contracts.requests import clarify_request, create_request, merge_requests

    context, factory = context_and_factory
    with factory.begin() as session:
        project = session.scalar(select(Project).where(Project.tenant_id == TENANT))
        first = create_request(session, context, project_id=project.id, summary="Initial request")
        second = create_request(session, context, project_id=project.id, summary="Duplicate request")
        clarify_request(session, context, request_id=first.id, correction="Corrected request")
        merged = merge_requests(session, context, target_request_id=first.id, source_request_id=second.id, reason="Same business request")
        assert merged.id == first.id
        assert session.get(type(second), second.id).status == "MERGED"
        assert session.get(type(first), first.id).request_version == 3


def test_structured_scope_output_must_match_authorized_chunk(context_and_factory: tuple[TrustedContext, sessionmaker[Session]]) -> None:
    from services.contracts.structure import validate_or_pending, validate_structure_output
    from services.domain.errors import ValidationError

    _context, factory = context_and_factory
    with factory.begin() as session:
        project = session.scalar(select(Project).where(Project.tenant_id == TENANT))
        chunk = DocumentChunk(tenant_id=TENANT, project_id=project.id, document_id=uuid.uuid4(), chunk_index=0, start_offset=0, end_offset=8, source_text="Included", content_hash="d" * 64)
        session.add(chunk)
        session.flush()
        valid = validate_structure_output([{"item_key": "one", "item_type": "INCLUDED", "text": "Included", "source_chunk_id": chunk.id, "start_offset": 0, "end_offset": 8}], [chunk])
        assert valid[0].item_key == "one"
        pending = validate_or_pending(None, [chunk])
        assert pending.status == "PENDING"
        assert pending.reason == "model_unavailable"
        with pytest.raises(ValidationError):
            validate_structure_output([{"item_key": "bad", "item_type": "INCLUDED", "text": "Invented", "source_chunk_id": chunk.id, "start_offset": 0, "end_offset": 8}], [chunk])
