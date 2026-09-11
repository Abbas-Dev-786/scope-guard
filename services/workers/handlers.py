
"""Durable job handlers for provider-backed work."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.domain.auth import TrustedContext
from services.domain.models import IntegrationConnection, Job
from services.integrations.gmail import (
    GmailProviderRetryable,
    _context,
    run_gmail_initial_backfill_page,
    start_gmail_watch,
    sync_gmail_history_page,
)
from services.integrations.ses import SesProviderRetryable
from services.workers.durable import complete_job, enqueue_job, fail_job


def _gmail_context(session: Session, connection_id: UUID, tenant_id: UUID) -> TrustedContext:
    connection = session.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.id == connection_id,
            IntegrationConnection.tenant_id == tenant_id,
        )
    )
    if connection is None:
        raise ValueError("Gmail connection for job was not found")
    return _context(connection)


def _run_payload_job(session: Session, job: Job) -> None:
    payload = job.payload_ref
    if job.kind == "change_order.send":
        from services.integrations.gmail import dispatch_gmail_send

        dispatch_gmail_send(session, action_id=UUID(str(payload["action_id"])))
        return
    if job.kind == "notification.send":
        from services.integrations.ses import dispatch_ses_notification

        dispatch_ses_notification(session, action_id=UUID(str(payload["action_id"])))
        return
    if job.kind == "gmail.history_sync":
        connection_id = UUID(str(payload["connection_id"]))
        context = _gmail_context(session, connection_id, job.tenant_id)
        connection = session.get(IntegrationConnection, connection_id)
        history_id = str(payload.get("history_id") or (connection.committed_history_id if connection else "") or "")
        if not history_id:
            raise ValueError("Gmail history sync has no starting cursor")
        page = sync_gmail_history_page(
            session,
            context,
            connection_id=connection_id,
            history_id=history_id,
            page_token=str(payload["page_token"]) if payload.get("page_token") else None,
        )
        if page.next_page_token:
            enqueue_job(
                session,
                tenant_id=job.tenant_id,
                project_id=job.project_id,
                kind=job.kind,
                payload_ref={**payload, "page_token": page.next_page_token},
                correlation_id=job.correlation_id,
                causation_id=job.id,
            )
        return
    if job.kind == "gmail.initial_backfill":
        connection_id = UUID(str(payload["connection_id"]))
        context = _gmail_context(session, connection_id, job.tenant_id)
        run_gmail_initial_backfill_page(
            session,
            context,
            connection_id=connection_id,
            page_token=str(payload["page_token"]) if payload.get("page_token") else None,
        )
        return
    if job.kind == "gmail.watch_stop":
        from services.integrations.gmail import stop_gmail_watch
        connection_id = UUID(str(payload["connection_id"]))
        context = _gmail_context(session, connection_id, job.tenant_id)
        stop_gmail_watch(session, context, connection_id=connection_id)
        return
    if job.kind == "gmail.watch_renew":
        connection_id = UUID(str(payload["connection_id"]))
        context = _gmail_context(session, connection_id, job.tenant_id)
        start_gmail_watch(session, context, connection_id=connection_id)
        return
    raise ValueError(f"Unsupported provider job kind: {job.kind}")


def execute_claimed_job(
    session: Session,
    *,
    job_id: UUID,
    worker_id: str,
    fencing_generation: int,
) -> Job:
    """Execute one claimed provider job and keep retries in the durable job layer."""
    job = session.get(Job, job_id, with_for_update=True)
    if job is None or job.state != "RUNNING" or job.lease_owner != worker_id or job.fencing_generation != fencing_generation:
        raise ValueError("Job lease or fencing generation is stale")
    try:
        _run_payload_job(session, job)
    except (GmailProviderRetryable, SesProviderRetryable) as exc:
        fail_job(
            session,
            job_id=job.id,
            worker_id=worker_id,
            fencing_generation=fencing_generation,
            error=exc,
            retryable=True,
        )
        raise
    except Exception as exc:
        fail_job(
            session,
            job_id=job.id,
            worker_id=worker_id,
            fencing_generation=fencing_generation,
            error=exc,
            retryable=False,
        )
        raise
    return complete_job(
        session,
        job_id=job.id,
        worker_id=worker_id,
        fencing_generation=fencing_generation,
    )