from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from sqlalchemy.orm import Session

from services.workers.durable import (
    DurableExecutionError,
    complete_action,
    mark_action_retry,
    mark_action_unknown,
)


class ProviderOutcomeKind(StrEnum):
    PRE_DISPATCH_FAILURE = "PRE_DISPATCH_FAILURE"
    SUCCESS = "SUCCESS"
    UNCERTAIN = "UNCERTAIN"


@dataclass(frozen=True, slots=True)
class ProviderOutcome:
    kind: ProviderOutcomeKind
    provider: str
    operation: str
    provider_reference: str | None = None
    evidence_ref: Mapping[str, object] | None = None
    error_code: str | None = None

    def __post_init__(self) -> None:
        if self.kind is ProviderOutcomeKind.SUCCESS and not self.provider_reference:
            raise ValueError("Successful provider outcomes require a provider reference")
        if self.kind is ProviderOutcomeKind.PRE_DISPATCH_FAILURE and not self.error_code:
            raise ValueError("Pre-dispatch failures require an error code")
        if self.kind is ProviderOutcomeKind.UNCERTAIN and not self.evidence_ref:
            raise ValueError("Uncertain outcomes require reconciliation evidence")


def pre_dispatch_failure(
    *, provider: str, operation: str, error_code: str
) -> ProviderOutcome:
    return ProviderOutcome(
        ProviderOutcomeKind.PRE_DISPATCH_FAILURE,
        provider,
        operation,
        error_code=error_code,
    )


def provider_success(
    *,
    provider: str,
    operation: str,
    provider_reference: str,
    evidence_ref: Mapping[str, object] | None = None,
) -> ProviderOutcome:
    return ProviderOutcome(
        ProviderOutcomeKind.SUCCESS,
        provider,
        operation,
        provider_reference=provider_reference,
        evidence_ref=evidence_ref,
    )


def uncertain_outcome(
    *,
    provider: str,
    operation: str,
    evidence_ref: Mapping[str, object],
) -> ProviderOutcome:
    return ProviderOutcome(
        ProviderOutcomeKind.UNCERTAIN,
        provider,
        operation,
        evidence_ref=evidence_ref,
    )


def reconcile_action(
    session: Session,
    *,
    action_id: UUID,
    outcome: ProviderOutcome,
) -> None:
    if outcome.kind is ProviderOutcomeKind.PRE_DISPATCH_FAILURE:
        mark_action_retry(session, action_id=action_id, error_code=outcome.error_code or "provider_failure")
        return
    if outcome.kind is ProviderOutcomeKind.SUCCESS:
        complete_action(
            session,
            action_id=action_id,
            outcome_ref={
                "provider": outcome.provider,
                "operation": outcome.operation,
                "provider_reference": outcome.provider_reference,
                "evidence": dict(outcome.evidence_ref or {}),
            },
            provider_request_id=outcome.provider_reference,
        )
        return
    if outcome.kind is ProviderOutcomeKind.UNCERTAIN:
        mark_action_unknown(
            session,
            action_id=action_id,
            reason="provider_response_uncertain_requires_reconciliation",
        )
        return
    raise DurableExecutionError("Unsupported provider outcome")