from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from services.domain.models import Base, Job, OutboxEvent, User
from services.workers.durable import (
    DurableExecutionError,
    LockOrderGuard,
    StaleLeaseError,
    begin_action_dispatch,
    claim_jobs,
    complete_action,
    complete_job,
    confirm_action_receipt,
    enqueue_job,
    fail_job,
    mark_action_unknown,
    prepare_external_action,
    publish_outbox,
    record_consumer_receipt,
    retry_action,
)
from services.workers.recovery import run_recovery_sweep


@pytest.fixture
def factory(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'durable.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as session:
        session.add(
            User(
                id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
                cognito_sub="durable-owner",
                verified_email="durable@example.com",
                timezone="UTC",
            )
        )
    return factory


def test_job_claim_fencing_retry_and_outbox_are_durable(factory: sessionmaker[Session]) -> None:
    tenant_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
    correlation_id = uuid.uuid4()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    with factory.begin() as session:
        job = enqueue_job(
            session,
            tenant_id=tenant_id,
            kind="fixture.work",
            payload_ref={"input_digest": "abc"},
            correlation_id=correlation_id,
            available_at=start,
        )
        job_id = job.id

    with factory.begin() as session:
        claimed = claim_jobs(session, worker_id="worker-a", now=start, limit=1)
        assert len(claimed) == 1
        generation = claimed[0].fencing_generation
        assert claimed[0].attempt_count == 1
        with pytest.raises(StaleLeaseError):
            complete_job(
                session,
                job_id=job_id,
                worker_id="worker-b",
                fencing_generation=generation,
                now=start,
            )

    with factory.begin() as session:
        failed = fail_job(
            session,
            job_id=job_id,
            worker_id="worker-a",
            fencing_generation=generation,
            error=TimeoutError(),
            retryable=True,
            now=start + timedelta(seconds=1),
        )
        assert failed.state == "RETRY_WAIT"
        assert failed.last_error == "TimeoutError"

    with factory() as session:
        outbox = session.scalar(select(OutboxEvent))
        persisted = session.get(Job, job_id)
        assert outbox is not None
        assert outbox.published_at is None
        assert persisted is not None
        assert persisted.state == "RETRY_WAIT"


def test_outbox_failure_is_recorded_without_losing_the_entry(factory: sessionmaker[Session]) -> None:
    tenant_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
    with factory.begin() as session:
        enqueue_job(
            session,
            tenant_id=tenant_id,
            kind="fixture.publish",
            payload_ref={},
            correlation_id=uuid.uuid4(),
        )
    with factory() as session:
        published, failed = publish_outbox(
            session,
            publish=lambda _event: (_ for _ in ()).throw(ConnectionError("secret must not persist")),
        )
        assert (published, failed) == (0, 1)
        event = session.scalar(select(OutboxEvent))
        assert event is not None
        assert event.publish_attempts == 1
        assert event.last_error == "ConnectionError"
        assert event.published_at is None


def test_consumer_receipt_is_idempotent(factory: sessionmaker[Session]) -> None:
    event_id = uuid.uuid4()
    with factory.begin() as session:
        assert record_consumer_receipt(
            session,
            consumer_name="fixture-consumer",
            event_id=event_id,
            result_ref={"status": "done"},
        )
    with factory.begin() as session:
        assert not record_consumer_receipt(
            session,
            consumer_name="fixture-consumer",
            event_id=event_id,
            result_ref={"status": "different"},
        )


def test_unknown_external_action_never_retries_without_explicit_ack(
    factory: sessionmaker[Session],
) -> None:
    tenant_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
    with factory.begin() as session:
        action = prepare_external_action(
            session,
            tenant_id=tenant_id,
            action_key="fixture-send-1",
            provider="fixture",
            operation="send",
            approved_payload={"body_digest": "redacted"},
        )
        action_id = action.id
        begin_action_dispatch(session, action_id=action_id)

    with factory.begin() as session:
        mark_action_unknown(session, action_id=action_id, reason="response_lost")
        with pytest.raises(DurableExecutionError):
            retry_action(session, action_id=action_id, allow_duplicate_risk=False)
        retry_action(session, action_id=action_id, allow_duplicate_risk=True)
        attempt = begin_action_dispatch(session, action_id=action_id)
        complete_action(
            session,
            action_id=action_id,
            outcome_ref={"provider_reference": "fixture-1"},
            provider_request_id="request-1",
        )
        confirm_action_receipt(session, action_id=action_id, receipt_ref={"confirmed": True})
        assert attempt.attempt_number == 2
def test_lock_order_guard_rejects_inverted_acquisition() -> None:
    guard = LockOrderGuard()
    guard.acquire("project")
    guard.acquire("payment")
    with pytest.raises(DurableExecutionError):
        guard.acquire("order")
    guard.release("payment")
    guard.release("project")
    assert guard.held == ()
def test_recovery_sweep_releases_expired_lease(factory: sessionmaker[Session]) -> None:
    tenant_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
    start = datetime(2026, 1, 1, tzinfo=UTC)
    with factory.begin() as session:
        job = enqueue_job(
            session,
            tenant_id=tenant_id,
            kind="fixture.recovery",
            payload_ref={},
            correlation_id=uuid.uuid4(),
            available_at=start,
        )
        job_id = job.id
    with factory.begin() as session:
        claim_jobs(session, worker_id="crashed-worker", now=start)
    with factory() as session:
        result = run_recovery_sweep(
            session,
            publish=lambda _event: None,
            now=start + timedelta(seconds=61),
        )
        assert result.recovered_jobs == 1
        recovered = session.get(Job, job_id)
        assert recovered is not None
        assert recovered.state == "RETRY_WAIT"

def test_job_correlation_and_transaction_helper_are_atomic(factory: sessionmaker[Session]) -> None:
    from services.domain.models import AuditEvent
    from services.workers.transactions import AuditSpec, JobSpec, commit_durable_command

    tenant_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
    correlation_id = uuid.uuid4()
    with factory() as session:
        result = commit_durable_command(
            session,
            operation=lambda: "committed",
            audit=AuditSpec(
                tenant_id=tenant_id,
                actor="operator",
                action="fixture.commit",
                resource_type="fixture",
                resource_id="one",
                correlation_id=correlation_id,
            ),
            next_jobs=(JobSpec(
                tenant_id=tenant_id,
                kind="fixture.next",
                payload_ref={"safe": True},
                correlation_id=correlation_id,
            ),),
            lock_order=("project", "order", "payment", "action"),
        )
        assert result == "committed"
    with factory() as session:
        job = session.scalar(select(Job).where(Job.kind == "fixture.next"))
        assert job is not None
        assert job.correlation_id == correlation_id
        assert session.scalar(select(AuditEvent).where(AuditEvent.resource_id == "one")) is not None
        assert session.scalar(select(OutboxEvent).where(OutboxEvent.aggregate_id == str(job.id))) is not None


def test_consumer_transaction_returns_original_result(factory: sessionmaker[Session]) -> None:
    from services.workers.transactions import execute_consumer_once

    calls = 0
    event_id = uuid.uuid4()
    with factory() as session:
        first = execute_consumer_once(
            session,
            consumer_name="fixture-once",
            event_id=event_id,
            operation=lambda: {"result": "first"},
        )
        assert first == {"result": "first"}
    with factory() as session:
        def should_not_run() -> dict[str, object]:
            nonlocal calls
            calls += 1
            return {"result": "second"}

        second = execute_consumer_once(
            session,
            consumer_name="fixture-once",
            event_id=event_id,
            operation=should_not_run,
        )
        assert second == {"result": "first"}
    assert calls == 0


def test_capacity_is_tenant_limited_and_recovers(factory: sessionmaker[Session]) -> None:
    from services.domain.models import AnalysisCapacityReservation, User
    from services.workers.capacity import (
        CapacityExceededError,
        CapacityPolicy,
        active_capacity,
        recover_capacity_slots,
        release_analysis_slot,
        reserve_analysis_slot,
    )

    tenant_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
    other_tenant = uuid.uuid4()
    policy = CapacityPolicy(per_tenant=1, global_limit=2, lease_seconds=10)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with factory.begin() as session:
        session.add(User(id=other_tenant, cognito_sub="other", verified_email="other@example.com", timezone="UTC"))
        first = reserve_analysis_slot(session, tenant_id=tenant_id, reservation_key="a", worker_id="w1", policy=policy, now=now)
        with pytest.raises(CapacityExceededError):
            reserve_analysis_slot(session, tenant_id=tenant_id, reservation_key="b", worker_id="w2", policy=policy, now=now)
        other = reserve_analysis_slot(session, tenant_id=other_tenant, reservation_key="b", worker_id="w2", policy=policy, now=now)
        assert active_capacity(session, now=now) == 2
        release_analysis_slot(session, reservation_id=first.id, worker_id="w1", now=now)
        release_analysis_slot(session, reservation_id=other.id, worker_id="w2", now=now)
        assert active_capacity(session, now=now) == 0
        expired = reserve_analysis_slot(session, tenant_id=tenant_id, reservation_key="c", worker_id="w3", policy=policy, now=now)
        assert recover_capacity_slots(session, now=now + timedelta(seconds=11)) == 1
        assert session.get(AnalysisCapacityReservation, expired.id).released_at is not None


def test_connector_contracts_and_deterministic_guards(factory: sessionmaker[Session]) -> None:
    from services.connectors.contracts import (
        pre_dispatch_failure,
        provider_success,
        reconcile_action,
        uncertain_outcome,
    )
    from services.connectors.guards import guard_deterministic_action, read_only_agent_manifest
    from services.connectors.policy import require_capability
    from services.domain.errors import AuthorizationError

    tenant_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
    with factory.begin() as session:
        action = prepare_external_action(
            session,
            tenant_id=tenant_id,
            action_key="contract-failure",
            provider="gmail",
            operation="send",
            approved_payload={"body": "safe"},
        )
        begin_action_dispatch(session, action_id=action.id)
        reconcile_action(session, action_id=action.id, outcome=pre_dispatch_failure(provider="gmail", operation="send", error_code="timeout"))
        assert action.state == "RETRY_WAIT"
        action2 = prepare_external_action(
            session,
            tenant_id=tenant_id,
            action_key="contract-uncertain",
            provider="gmail",
            operation="send",
            approved_payload={"body": "safe2"},
        )
        begin_action_dispatch(session, action_id=action2.id)
        reconcile_action(session, action_id=action2.id, outcome=uncertain_outcome(provider="gmail", operation="send", evidence_ref={"search": "miss"}))
        assert action2.state == "UNKNOWN_OUTCOME"
        action3 = prepare_external_action(
            session,
            tenant_id=tenant_id,
            action_key="contract-success",
            provider="gmail",
            operation="send",
            approved_payload={"body": "safe3"},
        )
        guard_deterministic_action(action3, capability="messages.send", approved_payload={"body": "safe3"})
        begin_action_dispatch(session, action_id=action3.id)
        reconcile_action(session, action_id=action3.id, outcome=provider_success(provider="gmail", operation="send", provider_reference="msg-1"))
        assert action3.state == "SUCCEEDED"
    with pytest.raises(AuthorizationError):
        require_capability("gmail", "messages.send", actor="unknown")
    manifest = read_only_agent_manifest()
    assert all("deterministic_actions" not in config for config in manifest["providers"].values())


def test_recovery_finds_lost_wakeup_and_orphaned_action(factory: sessionmaker[Session]) -> None:
    from services.domain.models import ExternalAction
    from services.workers.recovery import discover_lost_wakeups, recover_orphaned_actions

    tenant_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with factory.begin() as session:
        job = Job(tenant_id=tenant_id, kind="lost", payload_ref={}, correlation_id=uuid.uuid4(), available_at=now)
        session.add(job)
        session.flush()
        action = prepare_external_action(session, tenant_id=tenant_id, action_key="orphan", provider="fixture", operation="send", approved_payload={})
        begin_action_dispatch(session, action_id=action.id)
        action.updated_at = now - timedelta(seconds=61)
        session.flush()
        job_id = job.id
        action_id = action.id
        assert discover_lost_wakeups(session, now=now) == 1
        assert recover_orphaned_actions(session, now=now) == 1
    with factory() as session:
        assert session.scalar(select(OutboxEvent).where(OutboxEvent.aggregate_id == str(job_id))) is not None
        assert session.get(ExternalAction, action_id).state == "UNKNOWN_OUTCOME"


def test_crash_hooks_leave_recoverable_durable_boundaries(factory: sessionmaker[Session]) -> None:
    from services.workers.faults import CrashInjector, CrashPoint, InjectedCrash

    tenant_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
    with factory() as session:
        with pytest.raises(InjectedCrash):
            enqueue_job(session, tenant_id=tenant_id, kind="crash", payload_ref={}, correlation_id=uuid.uuid4(), injector=CrashInjector(CrashPoint.TRANSACTION_PERSISTED))
        session.rollback()
    with factory() as session:
        enqueue_job(session, tenant_id=tenant_id, kind="publish-crash", payload_ref={}, correlation_id=uuid.uuid4())
        session.commit()
        with pytest.raises(InjectedCrash):
            publish_outbox(session, publish=lambda _event: None, injector=CrashInjector(CrashPoint.OUTBOX_ATTEMPT_COMMITTED))
        session.rollback()
        event = session.scalar(select(OutboxEvent).where(OutboxEvent.event_type == "job.queued", OutboxEvent.publish_attempts == 1))
        assert event is not None and event.published_at is None
    with factory() as session:
        action = prepare_external_action(session, tenant_id=tenant_id, action_key="dispatch-crash", provider="fixture", operation="send", approved_payload={})
        with pytest.raises(InjectedCrash):
            begin_action_dispatch(session, action_id=action.id, injector=CrashInjector(CrashPoint.ACTION_DISPATCH_PERSISTED))
        session.rollback()
        assert session.get(type(action), action.id) is None


def test_metrics_and_correlation_fields_are_redacted() -> None:
    from services.workers.observability import CorrelationContext, DurableMetrics

    metrics = DurableMetrics()
    metrics.increment("jobs_claimed")
    metrics.gauge("actions_unknown_outcome", 1)
    health = metrics.health()
    assert health["status"] == "degraded"
    safe = CorrelationContext(request_id=uuid.uuid4(), provider_observation_id="x" * 500).safe_fields()
    assert len(safe["provider_observation_id"]) == 120
    assert "payload" not in safe
