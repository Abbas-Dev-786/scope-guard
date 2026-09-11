from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.domain.canonical import canonical_sha256
from services.domain.models import AuditEvent, ConsumerReceipt
from services.workers.durable import LockOrderGuard, enqueue_job, record_consumer_receipt

ResultT = TypeVar("ResultT")


@dataclass(frozen=True, slots=True)
class AuditSpec:
    tenant_id: UUID
    actor: str
    action: str
    resource_type: str
    resource_id: str
    correlation_id: UUID
    project_id: UUID | None = None
    before_state: dict[str, object] | None = None
    after_state: dict[str, object] | None = None
    resource_revision: int | None = None
    causation_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class JobSpec:
    tenant_id: UUID
    kind: str
    payload_ref: dict[str, object]
    correlation_id: UUID
    project_id: UUID | None = None
    causation_id: UUID | None = None


def _audit_event(spec: AuditSpec) -> AuditEvent:
    content = {"before": spec.before_state, "after": spec.after_state}
    return AuditEvent(
        tenant_id=spec.tenant_id,
        project_id=spec.project_id,
        actor=spec.actor,
        action=spec.action,
        resource_type=spec.resource_type,
        resource_id=spec.resource_id,
        resource_revision=spec.resource_revision,
        correlation_id=spec.correlation_id,
        causation_id=spec.causation_id,
        before_state=spec.before_state,
        after_state=spec.after_state,
        content_digest=canonical_sha256(content),
        safe_metadata={},
    )


def commit_durable_command(
    session: Session,
    *,
    operation: Callable[[], ResultT],
    audit: AuditSpec | None = None,
    next_jobs: Iterable[JobSpec] = (),
    lock_order: Iterable[str] = (),
) -> ResultT:
    """Commit domain state, audit, jobs and outbox as one local transaction."""
    guard = LockOrderGuard()
    for resource in lock_order:
        guard.acquire(resource)
    try:
        result = operation()
        if audit is not None:
            session.add(_audit_event(audit))
        for spec in next_jobs:
            enqueue_job(
                session,
                tenant_id=spec.tenant_id,
                kind=spec.kind,
                payload_ref=spec.payload_ref,
                correlation_id=spec.correlation_id,
                project_id=spec.project_id,
                causation_id=spec.causation_id,
            )
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise


def execute_consumer_once(
    session: Session,
    *,
    consumer_name: str,
    event_id: UUID,
    operation: Callable[[], dict[str, object]],
) -> dict[str, object]:
    """Return the original logical result on duplicate delivery."""
    existing = session.scalar(
        select(ConsumerReceipt).where(
            ConsumerReceipt.consumer_name == consumer_name,
            ConsumerReceipt.event_id == event_id,
        )
    )
    if existing is not None:
        return dict(existing.result_ref)
    try:
        result = operation()
        if not record_consumer_receipt(
            session,
            consumer_name=consumer_name,
            event_id=event_id,
            result_ref=result,
        ):
            session.rollback()
            existing = session.scalar(
                select(ConsumerReceipt).where(
                    ConsumerReceipt.consumer_name == consumer_name,
                    ConsumerReceipt.event_id == event_id,
                )
            )
            if existing is None:
                raise RuntimeError("Consumer receipt disappeared during duplicate handling")
            return dict(existing.result_ref)
        session.commit()
        return result
    except IntegrityError:
        session.rollback()
        existing = session.scalar(
            select(ConsumerReceipt).where(
                ConsumerReceipt.consumer_name == consumer_name,
                ConsumerReceipt.event_id == event_id,
            )
        )
        if existing is None:
            raise
        return dict(existing.result_ref)