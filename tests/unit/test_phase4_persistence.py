from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from services.agents.limits import AnalysisLimits
from services.agents.live import (
    LiveAnalysisInput,
    _reserve_live_budgets,
    _settle_live_budgets,
)
from services.agents.persistence import (
    create_workflow,
    finish_agent_run,
    reconcile_analysis_budget,
    record_scope_assessment,
    reserve_analysis_budget,
    start_agent_run,
)
from services.domain.auth import TrustedContext
from services.domain.errors import ConflictError
from services.domain.models import (
    AnalysisBudgetReservation,
    AnalysisBudgetWindow,
    Base,
    Client,
    Job,
    PreferenceVersion,
    Project,
    User,
)

TENANT = uuid.UUID("44444444-4444-4444-8444-444444444444")


@pytest.fixture
def phase4_factory(tmp_path: Path) -> tuple[TrustedContext, sessionmaker[Session], uuid.UUID]:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'phase4.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as session:
        session.add(
            User(
                id=TENANT,
                cognito_sub="phase4-owner",
                verified_email="phase4@example.com",
                timezone="UTC",
            )
        )
        preference = PreferenceVersion(
            tenant_id=TENANT, version=1, rate_minor=1000, minimum_minor=1000, increment_minor=1000
        )
        session.add(preference)
        client = Client(tenant_id=TENANT, name="Acme")
        session.add(client)
        session.flush()
        project = Project(
            tenant_id=TENANT,
            client_id=client.id,
            name="Analysis",
            preference_version_id=preference.id,
            timezone="UTC",
        )
        session.add(project)
        session.flush()
    return (
        TrustedContext(
            tenant_id=TENANT,
            subject="phase4-owner",
            email="phase4@example.com",
            email_verified=True,
            correlation_id=uuid.uuid4(),
        ),
        factory,
        project.id,
    )


def test_workflow_agent_run_assessment_are_reproducible(
    phase4_factory: tuple[TrustedContext, sessionmaker[Session], uuid.UUID],
) -> None:
    context, factory, project_id = phase4_factory
    with factory.begin() as session:
        workflow = create_workflow(
            session,
            context,
            workflow_key="fixture-analysis",
            project_id=project_id,
            input_snapshot={"request": "csv export", "scope_version": 1},
        )
        assert (
            create_workflow(
                session,
                context,
                workflow_key="fixture-analysis",
                project_id=project_id,
                input_snapshot={"request": "csv export", "scope_version": 1},
            ).id
            == workflow.id
        )
        run = start_agent_run(
            session,
            context,
            workflow_id=workflow.id,
            node_name="scope",
            attempt=1,
            model_id="fixture-model",
            prompt_version="prompt-v1",
            schema_version="schema-v1",
            tool_policy_version="tools-v1",
            input_snapshot={"request": "csv export"},
        )
        finished = finish_agent_run(
            session,
            context,
            run_id=run.id,
            output={"classification": "POTENTIAL_SCOPE_CHANGE"},
            usage={"input_tokens": 10, "output_tokens": 4},
        )
        assert finished.status == "SUCCEEDED"
        assessment = record_scope_assessment(
            session,
            context,
            project_id=project_id,
            workflow_id=workflow.id,
            classification="POTENTIAL_SCOPE_CHANGE",
            reason="New deliverable is outside the baseline.",
            coverage_status="COMPLETE",
            input_snapshot={"request": "csv export"},
            uncertainty="LOW",
        )
        assert assessment.input_digest
        with pytest.raises(ConflictError):
            create_workflow(
                session,
                context,
                workflow_key="fixture-analysis",
                project_id=project_id,
                input_snapshot={"request": "different"},
            )


def test_budget_reservation_is_cumulative_and_reconciled(
    phase4_factory: tuple[TrustedContext, sessionmaker[Session], uuid.UUID],
) -> None:
    context, factory, project_id = phase4_factory
    with factory.begin() as session:
        workflow = create_workflow(
            session,
            context,
            workflow_key="budget-analysis",
            project_id=project_id,
            input_snapshot={"request": "budget"},
        )
        first = reserve_analysis_budget(
            session,
            context,
            workflow_id=workflow.id,
            reservation_key="budget-1",
            token_amount=80,
            token_limit=100,
        )
        reconcile_analysis_budget(
            session, context, reservation_id=first.reservation.id, token_used=70
        )
        second = reserve_analysis_budget(
            session,
            context,
            workflow_id=workflow.id,
            reservation_key="budget-2",
            token_amount=30,
            token_limit=100,
        )
        assert second.reservation.token_reserved == 30
        with pytest.raises(ConflictError):
            reserve_analysis_budget(
                session,
                context,
                workflow_id=workflow.id,
                reservation_key="budget-3",
                token_amount=1,
                token_limit=100,
            )


def test_live_analysis_reserves_and_settles_tenant_and_deployment_budgets(
    phase4_factory: tuple[TrustedContext, sessionmaker[Session], uuid.UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, factory, project_id = phase4_factory
    settings = SimpleNamespace(
        max_model_cost_minor_per_day=1_000,
        model_price_version="fixture-prices-v1",
        model_price_reviewed_at=datetime.now(UTC),
        model_price_max_age_days=30,
        model_input_price_minor_per_1k=2,
        model_output_price_minor_per_1k=4,
        bedrock_model_id="fixture-model",
        tenant_token_limit_per_day=250_000,
        deployment_token_limit_per_day=1_000_000,
    )
    from services.api import config as api_config

    monkeypatch.setattr(api_config, "get_settings", lambda: settings)
    request_id = uuid.uuid4()
    inputs = LiveAnalysisInput(
        context=context,
        project_id=project_id,
        request_id=request_id,
        request_version=1,
        input_snapshot={
            "request_id": str(request_id),
            "request_version": 1,
            "scope_version_id": str(uuid.uuid4()),
            "request_summary": "Add export",
        },
        scope_items=(),
        evidence_references=(),
        recipient_email="client@example.test",
    )
    with factory.begin() as session:
        job = Job(
            tenant_id=context.tenant_id,
            project_id=project_id,
            kind="analysis.prepare",
            payload_ref={"request_id": str(request_id)},
            correlation_id=context.correlation_id,
            state="RUNNING",
            attempt_count=1,
        )
        session.add(job)
        session.flush()
        budget = _reserve_live_budgets(session, inputs, job)
        assert budget.reserved_tokens == 48_000
        assert budget.reserved_cost_minor == 112
        windows = list(session.query(AnalysisBudgetWindow).all())
        assert {window.scope_key for window in windows} == {
            "deployment",
            f"tenant:{context.tenant_id}",
        }
        limits = AnalysisLimits()
        limits.record_usage(input_tokens=1_000, output_tokens=100)
        _settle_live_budgets(session, inputs, budget, limits, conservative=False)
        reservations = list(session.query(AnalysisBudgetReservation).all())
        assert len(reservations) == 2
        assert all(item.status == "RECONCILED" for item in reservations)
        assert all(item.token_used == 1_100 for item in reservations)
        assert all(item.cost_used_minor == 3 for item in reservations)


def test_live_analysis_rejects_missing_reviewed_prices(
    phase4_factory: tuple[TrustedContext, sessionmaker[Session], uuid.UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, factory, project_id = phase4_factory
    from services.api import config as api_config

    monkeypatch.setattr(
        api_config,
        "get_settings",
        lambda: SimpleNamespace(
            max_model_cost_minor_per_day=0,
            model_price_version="",
            model_price_reviewed_at=None,
            model_input_price_minor_per_1k=0,
            model_output_price_minor_per_1k=0,
        ),
    )
    inputs = LiveAnalysisInput(
        context=context,
        project_id=project_id,
        request_id=uuid.uuid4(),
        request_version=1,
        input_snapshot={"scope_version_id": str(uuid.uuid4())},
        scope_items=(),
        evidence_references=(),
        recipient_email="client@example.test",
    )
    with factory.begin() as session:
        job = Job(
            tenant_id=context.tenant_id,
            project_id=project_id,
            kind="analysis.prepare",
            payload_ref={},
            state="RUNNING",
            attempt_count=1,
        )
        session.add(job)
        session.flush()
        with pytest.raises(ConflictError, match="Reviewed model prices"):
            _reserve_live_budgets(session, inputs, job)
