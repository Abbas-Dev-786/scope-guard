from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.domain.canonical import canonical_sha256
from services.domain.models import (
    ActionAttempt,
    ConsumerReceipt,
    ExternalAction,
    Job,
    OutboxEvent,
    utc_now,
)
from services.workers.faults import CrashInjector, CrashPoint
from services.workers.observability import metrics

LEASE_SECONDS = 60
HEARTBEAT_SECONDS = 20
DEFAULT_MAX_ATTEMPTS = 3
LOCK_ORDER = {"project": 0, "order": 1, "payment": 2, "action": 3}


class LockOrderGuard:
    """Validate the canonical project -> order -> payment -> action lock order."""

    def __init__(self) -> None:
        self._held: list[str] = []

    def acquire(self, resource: str) -> None:
        if resource not in LOCK_ORDER:
            raise DurableExecutionError(f"Unknown lock resource: {resource}")
        if self._held and LOCK_ORDER[resource] < LOCK_ORDER[self._held[-1]]:
            raise DurableExecutionError(
                f"Lock order violation: {self._held[-1]} must be released before {resource}"
            )
        self._held.append(resource)

    def release(self, resource: str) -> None:
        if not self._held or self._held[-1] != resource:
            raise DurableExecutionError("Locks must be released in reverse acquisition order")
        self._held.pop()

    @property
    def held(self) -> tuple[str, ...]:
        return tuple(self._held)


class DurableExecutionError(ValueError):
    """Expected durable execution invariant failure."""


class StaleLeaseError(DurableExecutionError):
    """A worker attempted to mutate work it no longer owns."""


ACTION_TRANSITIONS: dict[str, frozenset[str]] = {
    "READY": frozenset({"DISPATCHING", "CANCELLED"}),
    "DISPATCHING": frozenset({"SUCCEEDED", "RETRY_WAIT", "UNKNOWN_OUTCOME", "REVIEW_REQUIRED"}),
    "RETRY_WAIT": frozenset({"DISPATCHING", "CANCELLED"}),
    "SUCCEEDED": frozenset({"RECEIPT_CONFIRMED"}),
    "UNKNOWN_OUTCOME": frozenset({"RECEIPT_CONFIRMED", "REVIEW_REQUIRED", "RETRY_WAIT"}),
    "REVIEW_REQUIRED": frozenset({"RECEIPT_CONFIRMED", "RETRY_WAIT", "CANCELLED"}),
    "RECEIPT_CONFIRMED": frozenset(),
    "CANCELLED": frozenset(),
}


def _now(value: datetime | None) -> datetime:
    return value or datetime.now(UTC)


def _safe_error(error: BaseException) -> str:
    return type(error).__name__[:120]


def _require_job_owner(job: Job, worker_id: str, fencing_generation: int) -> None:
    if (
        job.state != "RUNNING"
        or job.lease_owner != worker_id
        or job.fencing_generation != fencing_generation
    ):
        raise StaleLeaseError("Job lease or fencing generation is no longer valid")


def enqueue_job(
    session: Session,
    *,
    tenant_id: UUID,
    kind: str,
    payload_ref: dict[str, object],
    correlation_id: UUID,
    project_id: UUID | None = None,
    available_at: datetime | None = None,
    deadline_at: datetime | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    causation_id: UUID | None = None,
    injector: CrashInjector | None = None,
) -> Job:
    if not 1 <= max_attempts <= DEFAULT_MAX_ATTEMPTS:
        raise DurableExecutionError("max_attempts must be between one and three")
    job = Job(
        tenant_id=tenant_id,
        project_id=project_id,
        kind=kind,
        payload_ref=payload_ref,
        available_at=available_at or utc_now(),
        deadline_at=deadline_at,
        max_attempts=max_attempts,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    session.add(job)
    session.flush()
    session.add(
        OutboxEvent(
            tenant_id=tenant_id,
            aggregate_type="job",
            aggregate_id=str(job.id),
            event_type="job.queued",
            payload={"job_id": str(job.id), "kind": kind},
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
    )
    session.flush()
    if injector is not None:
        injector.trip(CrashPoint.TRANSACTION_PERSISTED)
    return job


def claim_jobs(
    session: Session,
    *,
    worker_id: str,
    limit: int = 1,
    now: datetime | None = None,
    injector: CrashInjector | None = None,
) -> list[Job]:
    if limit < 1:
        raise DurableExecutionError("claim limit must be positive")
    current = _now(now)
    query: Select[tuple[Job]] = (
        select(Job)
        .where(
            Job.state.in_(("QUEUED", "RETRY_WAIT")),
            Job.available_at <= current,
            (Job.lease_until.is_(None) | (Job.lease_until <= current)),
        )
        .order_by(Job.available_at, Job.created_at, Job.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    claimed: list[Job] = []
    for job in session.scalars(query):
        if job.deadline_at is not None and job.deadline_at <= current:
            job.state = "FAILED_REQUIRES_REVIEW"
            job.last_error = "deadline_exceeded"
            continue
        job.state = "RUNNING"
        job.lease_owner = worker_id
        job.lease_until = current + timedelta(seconds=LEASE_SECONDS)
        job.fencing_generation += 1
        job.attempt_count += 1
        job.last_error = None
        claimed.append(job)
    session.flush()
    metrics.increment("jobs_claimed", len(claimed))
    if injector is not None:
        injector.trip(CrashPoint.JOB_CLAIMED)
    return claimed


def heartbeat_job(
    session: Session,
    *,
    job_id: UUID,
    worker_id: str,
    fencing_generation: int,
    now: datetime | None = None,
) -> Job:
    job = session.get(Job, job_id, with_for_update=True)
    if job is None:
        raise DurableExecutionError("Job does not exist")
    _require_job_owner(job, worker_id, fencing_generation)
    current = _now(now)
    if job.lease_until is None or job.lease_until < current:
        raise StaleLeaseError("Job lease has expired")
    job.lease_until = current + timedelta(seconds=LEASE_SECONDS)
    session.flush()
    return job


def complete_job(
    session: Session,
    *,
    job_id: UUID,
    worker_id: str,
    fencing_generation: int,
    now: datetime | None = None,
) -> Job:
    job = session.get(Job, job_id, with_for_update=True)
    if job is None:
        raise DurableExecutionError("Job does not exist")
    _require_job_owner(job, worker_id, fencing_generation)
    if job.deadline_at is not None and job.deadline_at < _now(now):
        raise DurableExecutionError("Expired work cannot be marked successful")
    job.state = "SUCCEEDED"
    job.lease_owner = None
    job.lease_until = None
    job.updated_at = _now(now)
    session.flush()
    metrics.increment("jobs_succeeded")
    return job


def fail_job(
    session: Session,
    *,
    job_id: UUID,
    worker_id: str,
    fencing_generation: int,
    error: BaseException,
    retryable: bool,
    now: datetime | None = None,
) -> Job:
    job = session.get(Job, job_id, with_for_update=True)
    if job is None:
        raise DurableExecutionError("Job does not exist")
    _require_job_owner(job, worker_id, fencing_generation)
    current = _now(now)
    job.last_error = _safe_error(error)
    can_retry = retryable and job.attempt_count < job.max_attempts
    if job.deadline_at is not None and current >= job.deadline_at:
        can_retry = False
    if can_retry:
        delay = min(2 ** max(job.attempt_count - 1, 0), 60)
        job.state = "RETRY_WAIT"
        job.available_at = current + timedelta(seconds=delay)
    else:
        job.state = "FAILED_REQUIRES_REVIEW"
    job.lease_owner = None
    job.lease_until = None
    job.updated_at = current
    session.flush()
    metrics.increment("jobs_failed_requires_review" if job.state == "FAILED_REQUIRES_REVIEW" else "jobs_retry_wait")
    return job


def recover_expired_jobs(session: Session, *, now: datetime | None = None) -> int:
    current = _now(now)
    expired = session.scalars(
        select(Job)
        .where(Job.state == "RUNNING", Job.lease_until.is_not(None), Job.lease_until < current)
        .with_for_update(skip_locked=True)
    ).all()
    recovered = 0
    for job in expired:
        job.lease_owner = None
        job.lease_until = None
        if job.attempt_count < job.max_attempts and (
            job.deadline_at is None or current < job.deadline_at
        ):
            job.state = "RETRY_WAIT"
            job.available_at = current
        else:
            job.state = "FAILED_REQUIRES_REVIEW"
            job.last_error = "lease_expired_attempt_budget_exhausted"
        recovered += 1
    session.flush()
    return recovered


def publish_outbox(
    session: Session,
    *,
    publish: Callable[[OutboxEvent], None],
    limit: int = 100,
    now: datetime | None = None,
    injector: CrashInjector | None = None,
) -> tuple[int, int]:
    """Publish entries using a dedicated session; no transaction spans a network call."""
    if limit < 1:
        raise DurableExecutionError("publish limit must be positive")
    current = _now(now)
    entries = session.scalars(
        select(OutboxEvent)
        .where(OutboxEvent.published_at.is_(None))
        .order_by(OutboxEvent.created_at, OutboxEvent.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()
    published = 0
    failed = 0
    for event in entries:
        event.publish_attempts += 1
        session.flush()
        session.commit()
        if injector is not None:
            injector.trip(CrashPoint.OUTBOX_ATTEMPT_COMMITTED)
        try:
            if injector is not None:
                injector.trip(CrashPoint.OUTBOX_PUBLISHING)
            publish(event)
        except Exception as exc:
            failed += 1
            event.last_error = _safe_error(exc)
            session.merge(event)
            session.commit()
        else:
            published += 1
            if injector is not None:
                injector.trip(CrashPoint.OUTBOX_RESULT_SAVE)
            event.published_at = current
            event.last_error = None
            session.merge(event)
            session.commit()
    return published, failed


def record_consumer_receipt(
    session: Session,
    *,
    consumer_name: str,
    event_id: UUID,
    result_ref: dict[str, object],
) -> bool:
    existing = session.scalar(
        select(ConsumerReceipt).where(
            ConsumerReceipt.consumer_name == consumer_name,
            ConsumerReceipt.event_id == event_id,
        )
    )
    if existing is not None:
        return False
    try:
        session.add(
            ConsumerReceipt(
                consumer_name=consumer_name,
                event_id=event_id,
                result_ref=result_ref,
            )
        )
        session.flush()
    except IntegrityError:
        session.rollback()
        return False
    return True


def prepare_external_action(
    session: Session,
    *,
    tenant_id: UUID,
    action_key: str,
    provider: str,
    operation: str,
    approved_payload: dict[str, object],
    project_id: UUID | None = None,
) -> ExternalAction:
    digest = canonical_sha256(approved_payload)
    existing = session.scalar(
        select(ExternalAction).where(
            ExternalAction.tenant_id == tenant_id,
            ExternalAction.action_key == action_key,
        )
    )
    if existing is not None:
        if existing.payload_digest != digest:
            raise DurableExecutionError("Action key was reused with different approved content")
        return existing
    action = ExternalAction(
        tenant_id=tenant_id,
        project_id=project_id,
        action_key=action_key,
        provider=provider,
        operation=operation,
        approved_payload=approved_payload,
        payload_digest=digest,
        idempotency_key=str(uuid4()),
    )
    session.add(action)
    session.flush()
    return action


def _transition_action(action: ExternalAction, target: str) -> None:
    if target not in ACTION_TRANSITIONS.get(action.state, frozenset()):
        raise DurableExecutionError(f"Illegal action transition: {action.state} -> {target}")
    action.state = target


def begin_action_dispatch(session: Session, *, action_id: UUID, injector: CrashInjector | None = None) -> ActionAttempt:
    action = session.get(ExternalAction, action_id, with_for_update=True)
    if action is None:
        raise DurableExecutionError("Action does not exist")
    _transition_action(action, "DISPATCHING")
    attempt_number = (
        session.scalar(
            select(ActionAttempt.attempt_number)
            .where(ActionAttempt.action_id == action.id)
            .order_by(ActionAttempt.attempt_number.desc())
            .limit(1)
        )
        or 0
    ) + 1
    if attempt_number > DEFAULT_MAX_ATTEMPTS:
        raise DurableExecutionError("Action attempt budget exhausted")
    attempt = ActionAttempt(
        action_id=action.id,
        attempt_number=attempt_number,
        state="DISPATCHING",
    )
    session.add(attempt)
    session.flush()
    if injector is not None:
        injector.trip(CrashPoint.ACTION_DISPATCH_PERSISTED)
    return attempt


def complete_action(
    session: Session,
    *,
    action_id: UUID,
    outcome_ref: dict[str, object],
    provider_request_id: str | None = None,
    injector: CrashInjector | None = None,
) -> ExternalAction:
    action = session.get(ExternalAction, action_id, with_for_update=True)
    if action is None:
        raise DurableExecutionError("Action does not exist")
    if injector is not None:
        injector.trip(CrashPoint.ACTION_PROVIDER_SUCCEEDED)
    _transition_action(action, "SUCCEEDED")
    attempt = session.scalar(
        select(ActionAttempt)
        .where(ActionAttempt.action_id == action.id)
        .order_by(ActionAttempt.attempt_number.desc())
        .limit(1)
    )
    if attempt is None:
        raise DurableExecutionError("Action has no dispatch attempt")
    attempt.state = "SUCCEEDED"
    attempt.provider_request_id = provider_request_id
    attempt.completed_at = utc_now()
    attempt.outcome_ref = outcome_ref
    session.flush()
    if injector is not None:
        injector.trip(CrashPoint.ACTION_RESULT_SAVED)
    return action


def mark_action_review_required(
    session: Session,
    *,
    action_id: UUID,
    reason: str,
) -> ExternalAction:
    """Record a definite provider rejection without treating it as an uncertain send."""
    action = session.get(ExternalAction, action_id, with_for_update=True)
    if action is None:
        raise DurableExecutionError("Action does not exist")
    _transition_action(action, "REVIEW_REQUIRED")
    action.uncertainty_reason = reason[:500]
    attempt = session.scalar(
        select(ActionAttempt)
        .where(ActionAttempt.action_id == action.id)
        .order_by(ActionAttempt.attempt_number.desc())
        .limit(1)
    )
    if attempt is not None:
        attempt.state = "REVIEW_REQUIRED"
        attempt.completed_at = utc_now()
        attempt.error_code = "PROVIDER_REJECTED"
        attempt.error_message = reason[:500]
    session.flush()
    return action

def mark_action_unknown(
    session: Session,
    *,
    action_id: UUID,
    reason: str,
) -> ExternalAction:
    action = session.get(ExternalAction, action_id, with_for_update=True)
    if action is None:
        raise DurableExecutionError("Action does not exist")
    _transition_action(action, "UNKNOWN_OUTCOME")
    action.uncertainty_reason = reason[:500]
    attempt = session.scalar(
        select(ActionAttempt)
        .where(ActionAttempt.action_id == action.id)
        .order_by(ActionAttempt.attempt_number.desc())
        .limit(1)
    )
    if attempt is not None:
        attempt.state = "UNKNOWN_OUTCOME"
        attempt.completed_at = utc_now()
        attempt.error_code = "UNKNOWN_OUTCOME"
    session.flush()
    return action



def mark_action_retry(
    session: Session,
    *,
    action_id: UUID,
    error_code: str,
) -> ExternalAction:
    action = session.get(ExternalAction, action_id, with_for_update=True)
    if action is None:
        raise DurableExecutionError("Action does not exist")
    _transition_action(action, "RETRY_WAIT")
    attempt = session.scalar(
        select(ActionAttempt)
        .where(ActionAttempt.action_id == action.id)
        .order_by(ActionAttempt.attempt_number.desc())
        .limit(1)
    )
    if attempt is not None:
        attempt.state = "RETRY_WAIT"
        attempt.completed_at = utc_now()
        attempt.error_code = error_code[:120]
    session.flush()
    return action
def retry_action(
    session: Session,
    *,
    action_id: UUID,
    allow_duplicate_risk: bool,
) -> ExternalAction:
    action = session.get(ExternalAction, action_id, with_for_update=True)
    if action is None:
        raise DurableExecutionError("Action does not exist")
    if action.state not in {"UNKNOWN_OUTCOME", "REVIEW_REQUIRED"}:
        raise DurableExecutionError("Only uncertain or review-required actions may be retried")
    if action.state in {"UNKNOWN_OUTCOME", "REVIEW_REQUIRED"} and not allow_duplicate_risk:
        raise DurableExecutionError("Explicit duplicate-risk acknowledgement is required")
    _transition_action(action, "RETRY_WAIT")
    session.flush()
    return action


def confirm_action_receipt(
    session: Session,
    *,
    action_id: UUID,
    receipt_ref: dict[str, object],
) -> ExternalAction:
    action = session.get(ExternalAction, action_id, with_for_update=True)
    if action is None:
        raise DurableExecutionError("Action does not exist")
    _transition_action(action, "RECEIPT_CONFIRMED")
    action.receipt_ref = receipt_ref
    session.flush()
    return action


def cancel_action(session: Session, *, action_id: UUID) -> ExternalAction:
    action = session.get(ExternalAction, action_id, with_for_update=True)
    if action is None:
        raise DurableExecutionError("Action does not exist")
    _transition_action(action, "CANCELLED")
    session.flush()
    return action