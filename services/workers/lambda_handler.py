"""Scheduled Lambda entrypoint for durable provider jobs and recovery."""

from __future__ import annotations

import json
import os
from typing import Any
from uuid import UUID

import boto3  # type: ignore[import-untyped]

from services.api.database import SessionLocal
from services.domain.models import OutboxEvent
from services.workers.durable import claim_jobs
from services.workers.handlers import execute_claimed_job
from services.workers.recovery import run_recovery_sweep

MAX_JOBS_PER_INVOCATION = 25
CLAIM_BATCH_SIZE = 5


def _publish_outbox_event(event: OutboxEvent) -> None:
    event_bus_name = os.environ.get("SCOPEGUARD_EVENT_BUS_NAME", "").strip()
    if not event_bus_name:
        return
    response = boto3.client(
        "events",
        region_name=os.environ.get("SCOPEGUARD_AWS_REGION", "us-east-1"),
    ).put_events(
        Entries=[
            {
                "Source": "scopeguard",
                "DetailType": event.event_type,
                "Detail": json.dumps(
                    {
                        "event_id": str(event.id),
                        "tenant_id": str(event.tenant_id),
                        "aggregate_type": event.aggregate_type,
                        "aggregate_id": event.aggregate_id,
                        "payload": event.payload,
                    },
                    default=str,
                    separators=(",", ":"),
                ),
                "EventBusName": event_bus_name,
            }
        ]
    )
    if int(response.get("FailedEntryCount", 0)) != 0:
        raise RuntimeError("EventBridge rejected an outbox event")


def handler(event: dict[str, Any], context: Any) -> dict[str, int]:
    del event
    worker_id = f"lambda:{getattr(context, 'aws_request_id', 'manual')}"
    with SessionLocal() as session:
        recovery = run_recovery_sweep(session, publish=_publish_outbox_event)

    processed = 0
    failed = 0
    while processed + failed < MAX_JOBS_PER_INVOCATION:
        limit = min(CLAIM_BATCH_SIZE, MAX_JOBS_PER_INVOCATION - processed - failed)
        with SessionLocal() as session:
            claimed = claim_jobs(session, worker_id=worker_id, limit=limit)
            leases = [
                (UUID(str(job.id)), int(job.fencing_generation), str(job.kind))
                for job in claimed
            ]
            session.commit()
        if not leases:
            break
        for job_id, generation, kind in leases:
            if kind == "analysis.prepare":
                from services.agents.live import execute_live_analysis_job

                try:
                    execute_live_analysis_job(
                        job_id=job_id,
                        worker_id=worker_id,
                        fencing_generation=generation,
                    )
                except Exception:
                    failed += 1
                else:
                    processed += 1
                continue
            with SessionLocal() as session:
                try:
                    execute_claimed_job(
                        session,
                        job_id=job_id,
                        worker_id=worker_id,
                        fencing_generation=generation,
                    )
                except Exception:
                    failed += 1
                    session.commit()
                else:
                    processed += 1
                    session.commit()

    return {
        "processed_jobs": processed,
        "failed_jobs": failed,
        "recovered_jobs": recovery.recovered_jobs,
        "gmail_maintenance_jobs": recovery.gmail_maintenance_jobs,
        "payment_maintenance_jobs": recovery.payment_maintenance_jobs,
        "published_events": recovery.published_events,
        "failed_publications": recovery.failed_publications,
    }