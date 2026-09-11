from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from threading import Lock
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CorrelationContext:
    request_id: UUID
    workflow_id: UUID | None = None
    job_id: UUID | None = None
    action_id: UUID | None = None
    provider_observation_id: str | None = None

    def safe_fields(self) -> dict[str, str]:
        fields = {"request_id": str(self.request_id)}
        if self.workflow_id is not None:
            fields["workflow_id"] = str(self.workflow_id)
        if self.job_id is not None:
            fields["job_id"] = str(self.job_id)
        if self.action_id is not None:
            fields["action_id"] = str(self.action_id)
        if self.provider_observation_id is not None:
            fields["provider_observation_id"] = self.provider_observation_id[:120]
        return fields


class DurableMetrics:
    """Process-local metrics with bounded labels and no payload/body values."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: Counter[str] = Counter()
        self._gauges: dict[str, int] = {}

    def increment(self, name: str, amount: int = 1) -> None:
        if amount < 0:
            raise ValueError("Counters cannot decrement")
        with self._lock:
            self._counters[name[:120]] += amount

    def gauge(self, name: str, value: int) -> None:
        with self._lock:
            self._gauges[name[:120]] = value

    def snapshot(self) -> dict[str, dict[str, int]]:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
            }

    def health(self) -> dict[str, object]:
        snapshot = self.snapshot()
        return {
            "status": "degraded"
            if snapshot["gauges"].get("jobs_failed_requires_review", 0) > 0
            or snapshot["gauges"].get("actions_unknown_outcome", 0) > 0
            else "ok",
            **snapshot,
        }


metrics = DurableMetrics()