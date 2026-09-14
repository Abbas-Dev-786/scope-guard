from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.domain.models import ExternalAction, Job, OutboxEvent
from services.workers.durable import mark_action_unknown, publish_outbox, recover_expired_jobs

RECOVERY_STALE_SECONDS = 60


@dataclass(frozen=True)
class RecoverySweepResult:
    recovered_jobs: int
    recovery_wakeups: int
    orphaned_actions: int
    published_events: int
    failed_publications: int
    gmail_maintenance_jobs: int = 0
    payment_maintenance_jobs: int = 0
    payment_webhooks_normalized: int = 0


def discover_lost_wakeups(session: Session, *, now: datetime | None = None) -> int:
    current = now or datetime.now(UTC)
    stale_before = current - timedelta(seconds=RECOVERY_STALE_SECONDS)
    jobs = session.scalars(
        select(Job).where(
            Job.state.in_(("QUEUED", "RETRY_WAIT")),
            Job.available_at <= current,
        )
    ).all()
    created = 0
    for job in jobs:
        pending = session.scalar(
            select(OutboxEvent.id)
            .where(
                OutboxEvent.aggregate_type == "job",
                OutboxEvent.aggregate_id == str(job.id),
                OutboxEvent.published_at.is_(None),
            )
            .limit(1)
        )
        recent = session.scalar(
            select(OutboxEvent.id)
            .where(
                OutboxEvent.aggregate_type == "job",
                OutboxEvent.aggregate_id == str(job.id),
                OutboxEvent.created_at >= stale_before,
            )
            .limit(1)
        )
        if pending is None and recent is None:
            session.add(
                OutboxEvent(
                    tenant_id=job.tenant_id,
                    aggregate_type="job",
                    aggregate_id=str(job.id),
                    event_type="job.recovery_wakeup",
                    payload={"job_id": str(job.id), "kind": job.kind},
                    correlation_id=job.correlation_id,
                    causation_id=job.causation_id,
                )
            )
            created += 1
    session.flush()
    return created


def recover_orphaned_actions(session: Session, *, now: datetime | None = None) -> int:
    current = now or datetime.now(UTC)
    stale_before = current - timedelta(seconds=RECOVERY_STALE_SECONDS)
    actions = session.scalars(
        select(ExternalAction).where(
            ExternalAction.state == "DISPATCHING",
            ExternalAction.updated_at <= stale_before,
        )
    ).all()
    for action in actions:
        mark_action_unknown(
            session,
            action_id=action.id,
            reason="dispatch_lease_expired_requires_reconciliation",
        )
    return len(actions)


def run_recovery_sweep(
    session: Session,
    *,
    publish: Callable[[OutboxEvent], None],
    now: datetime | None = None,
) -> RecoverySweepResult:
    """Run the one-minute recovery work from a dedicated worker session."""
    from services.integrations.gmail import schedule_gmail_maintenance
    from services.payments.service import (
        normalize_pending_payment_webhooks,
        replay_unmatched_payment_observations,
        schedule_payment_maintenance,
    )

    recovered = recover_expired_jobs(session, now=now)
    maintenance = schedule_gmail_maintenance(session, now=now)
    payment_maintenance = schedule_payment_maintenance(session, now=now)
    payment_webhooks_normalized = normalize_pending_payment_webhooks(session)
    replay_unmatched_payment_observations(session, now=now)
    wakeups = discover_lost_wakeups(session, now=now)
    orphaned = recover_orphaned_actions(session, now=now)
    session.commit()
    published, failed = publish_outbox(session, publish=publish, now=now)
    return RecoverySweepResult(
        recovered,
        wakeups,
        orphaned,
        published,
        failed,
        maintenance,
        payment_maintenance,
        payment_webhooks_normalized,
    )
