from __future__ import annotations

from enum import StrEnum


class CrashPoint(StrEnum):
    TRANSACTION_PERSISTED = "transaction_persisted"
    OUTBOX_ATTEMPT_COMMITTED = "outbox_attempt_committed"
    OUTBOX_PUBLISHING = "outbox_publishing"
    OUTBOX_RESULT_SAVE = "outbox_result_save"
    JOB_CLAIMED = "job_claimed"
    ACTION_DISPATCH_PERSISTED = "action_dispatch_persisted"
    ACTION_PROVIDER_SUCCEEDED = "action_provider_succeeded"
    ACTION_RESULT_SAVED = "action_result_saved"


class InjectedCrash(RuntimeError):
    """Deterministic fault used only by tests and controlled failure exercises."""


class CrashInjector:
    def __init__(self, *points: CrashPoint) -> None:
        self._points = set(points)

    def trip(self, point: CrashPoint) -> None:
        if point in self._points:
            raise InjectedCrash(point.value)