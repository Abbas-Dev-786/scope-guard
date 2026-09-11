from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from services.agents.costs import ModelPrice, ReviewedModelPrices
from services.agents.evaluation import (
    build_evaluation_dataset,
    dataset_digest,
    run_three_held_out_evaluations,
    split_evaluation_dataset,
)
from services.agents.gates import apply_evidence_gate, freeze_terms
from services.agents.limits import AnalysisLimits
from services.agents.persistence import (
    get_workflow_trace,
    list_analysis_decisions,
)
from services.agents.roles import RoleGraph, read_only_role_manifest, validate_tool_inventory
from services.agents.schemas import (
    EvidenceReferenceOutput,
    EvidenceRoleOutput,
    ImpactRoleOutput,
    ScopeRoleOutput,
)
from services.agents.validation import StructuredOutputError, parse_with_one_repair
from services.agents.workflow import prepare_analysis
from services.domain.auth import TrustedContext
from services.domain.errors import AuthorizationError, ConflictError
from services.domain.models import (
    Base,
    CalendarVersion,
    Client,
    ClientContact,
    EvidenceBundle,
    EvidenceReference,
    PreferenceVersion,
    Project,
    RequestRecord,
    User,
)

TENANT = uuid.UUID("55555555-5555-4555-8555-555555555555")


def test_strict_output_allows_only_one_repair() -> None:
    payload = {"classification": "POTENTIAL_SCOPE_CHANGE", "request_summary": "Add SSO", "reason": "New", "uncertainty": "LOW", "unexpected": True}
    repaired = {key: value for key, value in payload.items() if key != "unexpected"}
    parsed = parse_with_one_repair(ScopeRoleOutput, payload, repair=lambda _: repaired)
    assert parsed.repaired is True
    with pytest.raises(StructuredOutputError):
        parse_with_one_repair(ScopeRoleOutput, payload, repair=lambda _: payload)


def test_evidence_gate_overturns_change_and_blocks_conflict() -> None:
    reference = uuid.uuid4()
    preliminary = ScopeRoleOutput(classification="POTENTIAL_SCOPE_CHANGE", request_summary="SSO", reason="New", uncertainty="LOW", matched_amendment_ids=[uuid.uuid4()])
    covered = EvidenceRoleOutput(final_classification="PREVIOUSLY_APPROVED", supporting_references=[EvidenceReferenceOutput(reference_id=reference, relation="SUPPORTS", claim="Accepted amendment")], completeness="COMPLETE", temporal_coverage="current")
    assert apply_evidence_gate(preliminary, covered, accepted_amendment_ids=set(preliminary.matched_amendment_ids)).route == "COVERED"
    conflict = covered.model_copy(update={"contradictory_references": [EvidenceReferenceOutput(reference_id=uuid.uuid4(), relation="CONTRADICTS", claim="Conflicting promise")]})
    assert apply_evidence_gate(preliminary, conflict).route == "CLARIFICATION"


def test_limits_are_cumulative_and_bounded() -> None:
    limits = AnalysisLimits(deadline_seconds=10, max_read_calls=2, max_input_tokens=4, max_output_tokens=4, max_attempts=1, max_repairs=1)
    limits.start_attempt()
    limits.record_read(2)
    limits.record_usage(input_tokens=4, output_tokens=4)
    limits.record_repair()
    with pytest.raises(ConflictError):
        limits.record_read()
    with pytest.raises(ConflictError):
        limits.record_repair()


def test_roles_are_read_only_and_manifest_fails_closed() -> None:
    manifest = read_only_role_manifest()
    assert manifest["default_policy"] == "deny"
    with pytest.raises(AuthorizationError):
        validate_tool_inventory("gmail", {"messages.send": {"read_only": True}})
    graph = RoleGraph()
    stages = graph.run_pipeline({}, {name: lambda _payload, _limits: {"ok": True} for name in ("scope", "evidence", "impact", "change_order", "communication")})
    assert [stage.role for stage in stages] == ["scope", "evidence", "impact", "change_order", "communication"]


def test_dataset_has_frozen_split_and_three_passing_runs() -> None:
    cases = build_evaluation_dataset()
    development, held_out = split_evaluation_dataset(cases)
    assert len(cases) == 120 and len(development) == len(held_out) == 60
    assert len({item.project_id for item in development}.intersection(item.project_id for item in held_out)) == 0
    assert sum(item.label == "POTENTIAL_SCOPE_CHANGE" for item in held_out) >= 20
    assert sum(item.label != "POTENTIAL_SCOPE_CHANGE" for item in held_out) >= 20
    assert dataset_digest(cases) == dataset_digest(build_evaluation_dataset())
    reports = run_three_held_out_evaluations(lambda case: case.label)
    assert all(report.passed for report in reports)


@pytest.fixture
def terms_factory(tmp_path: Path) -> tuple[TrustedContext, sessionmaker[Session], uuid.UUID]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'terms.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as session:
        session.add(User(id=TENANT, cognito_sub="phase4-analysis", verified_email="analysis@example.com", timezone="Asia/Kolkata"))
        pref = PreferenceVersion(tenant_id=TENANT, version=1, rate_minor=100_000, minimum_minor=1_500_000, increment_minor=50_000)
        session.add(pref)
        client = Client(tenant_id=TENANT, name="Acme")
        session.add(client)
        session.flush()
        project = Project(tenant_id=TENANT, client_id=client.id, name="OIDC", preference_version_id=pref.id, timezone="Asia/Kolkata")
        session.add(project)
        session.flush()
        calendar = CalendarVersion(tenant_id=TENANT, project_id=project.id, version=1, weekdays=[0, 1, 2, 3, 4], holiday_dates=[], confirmed_daily_capacity_hours=7)
        session.add(calendar)
        session.flush()
        project.calendar_version_id = calendar.id
    return TrustedContext(tenant_id=TENANT, subject="phase4-analysis", email="analysis@example.com", email_verified=True, correlation_id=uuid.uuid4()), factory, project.id


def test_frozen_terms_use_database_versions_and_expected_fixture_price(terms_factory: tuple[TrustedContext, sessionmaker[Session], uuid.UUID]) -> None:
    context, factory, project_id = terms_factory
    impact = ImpactRoleOutput(tasks=[{"task_key": "oidc", "description": "Implement OIDC", "low_hours": "10", "recommended_hours": "14", "high_hours": "18", "assumptions": ["No verified history is available"], "dependencies": ["Client metadata"]}], low_hours="10", recommended_hours="14", high_hours="18", assumptions=["No verified history is available"], dependencies=["Client metadata"], uncertainty="MEDIUM", cold_start=True)
    with factory.begin() as session:
        terms = freeze_terms(session, context, project_id=project_id, impact=impact)
    assert terms.total_minor == 1_500_000
    assert terms.tax_minor == 0
    assert terms.schedule_impact_days == 2
    assert any("Full payment" in condition for condition in terms.conditions)

def test_prepare_analysis_persists_safe_proposal_and_trace(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'workflow.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as session:
        session.add(User(id=TENANT, cognito_sub="workflow-owner", verified_email="workflow@example.com", timezone="Asia/Kolkata"))
        pref = PreferenceVersion(tenant_id=TENANT, version=1, rate_minor=100_000, minimum_minor=1_500_000, increment_minor=50_000)
        session.add(pref)
        client = Client(tenant_id=TENANT, name="Acme")
        session.add(client)
        session.flush()
        session.add(ClientContact(tenant_id=TENANT, client_id=client.id, normalized_email="client@example.com", display_name="Client"))
        project = Project(tenant_id=TENANT, client_id=client.id, name="Workflow", preference_version_id=pref.id, timezone="Asia/Kolkata")
        session.add(project)
        session.flush()
        request = RequestRecord(tenant_id=TENANT, project_id=project.id, summary="Add OIDC")
        session.add(request)
        session.flush()
        bundle = EvidenceBundle(tenant_id=TENANT, project_id=project.id, request_id=request.id, snapshot_digest="a" * 64, searched_sources=[], cutoff=__import__("datetime").datetime.now(__import__("datetime").UTC), completeness="COMPLETE")
        session.add(bundle)
        session.flush()
        reference = EvidenceReference(tenant_id=TENANT, project_id=project.id, bundle_id=bundle.id, source_type="contract", source_id="doc", source_version="v1", exact_excerpt_ref="chunk:1", content_hash="b" * 64, locator={}, fetched_at=bundle.cutoff, access_scope="project", relation="SUPPORTS")
        session.add(reference)
        session.flush()
        context = TrustedContext(tenant_id=TENANT, subject="workflow-owner", email="workflow@example.com", email_verified=True, correlation_id=uuid.uuid4())
        preliminary = ScopeRoleOutput(classification="POTENTIAL_SCOPE_CHANGE", request_summary="Add OIDC", reason="New integration", uncertainty="MEDIUM")
        evidence = EvidenceRoleOutput(final_classification="POTENTIAL_SCOPE_CHANGE", supporting_references=[EvidenceReferenceOutput(reference_id=reference.id, relation="SUPPORTS", claim="OIDC is new")], completeness="COMPLETE", temporal_coverage="current")
        impact = ImpactRoleOutput(tasks=[{"task_key": "oidc", "description": "Implement OIDC", "low_hours": "10", "recommended_hours": "14", "high_hours": "18", "assumptions": ["No verified history is available"], "dependencies": ["Client metadata"]}], low_hours="10", recommended_hours="14", high_hours="18", assumptions=["No verified history is available"], dependencies=["Client metadata"], uncertainty="MEDIUM", cold_start=True)
        from services.agents.schemas import ChangeOrderRoleOutput, CommunicationRoleOutput
        result = prepare_analysis(session, context, project_id=project.id, request_id=request.id, input_snapshot={"summary": request.summary}, preliminary=preliminary, evidence=evidence, impact=impact, change_order=ChangeOrderRoleOutput(title="OIDC integration", requested_change="Add OIDC", deliverables=["OIDC login"], client_explanation="This is additional work."), communication=CommunicationRoleOutput(subject="OIDC change", plain_text_body="Please approve.", html_body="<p>Please approve.</p>", recipient_email="client@example.com"))
        assert result.gate.route == "PROPOSAL"
        assert result.draft_revision_id is not None
        assert len(list_analysis_decisions(session, context)) == 1
        trace = get_workflow_trace(session, context, result.workflow_id)
        assert trace["workflow_id"] == str(result.workflow_id)

def test_missing_or_stale_model_price_pauses_work() -> None:
    from datetime import UTC, datetime, timedelta

    from services.domain.errors import ConflictError

    fresh = ReviewedModelPrices(version="prices-v1", reviewed_at=datetime.now(UTC), prices={"fixture": ModelPrice(2, 4)})
    assert fresh.cost_minor("fixture", input_tokens=1000, output_tokens=1000) == 6
    with pytest.raises(ConflictError):
        fresh.cost_minor("unknown", input_tokens=1, output_tokens=1)
    stale = ReviewedModelPrices(version="prices-v1", reviewed_at=datetime.now(UTC) - timedelta(days=31), prices={"fixture": ModelPrice(2, 4)})
    with pytest.raises(ConflictError):
        stale.cost_minor("fixture", input_tokens=1, output_tokens=1)