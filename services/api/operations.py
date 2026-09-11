from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.api.schemas import ActionRead, JobRead
from services.domain.auth import TrustedContext
from services.domain.errors import ConflictError, NotFoundError
from services.domain.models import ExternalAction, Job
from services.workers.durable import (
    cancel_action,
    confirm_action_receipt,
    retry_action,
)


def list_jobs(
    session: Session,
    context: TrustedContext,
    *,
    state: str | None = None,
    limit: int = 50,
) -> list[JobRead]:
    query = (
        select(Job)
        .where(Job.tenant_id == context.tenant_id)
        .order_by(Job.created_at.desc(), Job.id.desc())
        .limit(limit)
    )
    if state is not None:
        query = query.where(Job.state == state)
    return [JobRead.model_validate(job) for job in session.scalars(query)]


def get_action(session: Session, context: TrustedContext, action_id: UUID) -> ExternalAction:
    action = session.scalar(
        select(ExternalAction).where(
            ExternalAction.id == action_id,
            ExternalAction.tenant_id == context.tenant_id,
        )
    )
    if action is None:
        raise NotFoundError("Action was not found")
    return action


def retry_failed_job(
    session: Session,
    context: TrustedContext,
    job_id: UUID,
    reason: str,
) -> JobRead:
    job = session.scalar(
        select(Job)
        .where(Job.id == job_id, Job.tenant_id == context.tenant_id)
        .with_for_update()
    )
    if job is None:
        raise NotFoundError("Job was not found")
    if job.state not in {"FAILED_REQUIRES_REVIEW", "RETRY_WAIT"}:
        raise ConflictError("Only failed or retry-wait jobs can be retried")
    job.state = "RETRY_WAIT"
    job.available_at = datetime.now(UTC)
    job.last_error = f"operator_retry:{reason}"[:500]
    job.lease_owner = None
    job.lease_until = None
    session.flush()
    return JobRead.model_validate(job)


def resolve_action(
    session: Session,
    context: TrustedContext,
    action_id: UUID,
    *,
    resolution: str,
    duplicate_risk_acknowledged: bool,
    receipt_ref: dict[str, object] | None,
) -> ActionRead:
    action = get_action(session, context, action_id)
    if resolution == "retry":
        retry_action(
            session,
            action_id=action_id,
            allow_duplicate_risk=duplicate_risk_acknowledged,
        )
    elif resolution == "confirm_receipt":
        if receipt_ref is None:
            raise ConflictError("Receipt evidence is required")
        confirm_action_receipt(session, action_id=action_id, receipt_ref=receipt_ref)
    elif resolution == "cancel":
        cancel_action(session, action_id=action_id)
    else:
        raise ConflictError("Unsupported action resolution")
    session.flush()
    return ActionRead.model_validate(action)