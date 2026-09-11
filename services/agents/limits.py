from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

from services.domain.errors import ConflictError, ValidationError

MAX_PREPARATION_SECONDS = 180.0
MAX_NODE_SECONDS = 60.0
MAX_TOOL_SECONDS = 15.0
MAX_READ_CALLS = 20
MAX_INPUT_TOKENS = 40_000
MAX_OUTPUT_TOKENS = 8_000
MAX_JOB_ATTEMPTS = 3
MAX_REPAIRS = 1
MAX_DEPLOYMENT_TOKENS_PER_DAY = 1_000_000


@dataclass(frozen=True, slots=True)
class AnalysisUsage:
    read_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    attempts: int = 0
    repairs: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(slots=True)
class AnalysisLimits:
    deadline_seconds: float = MAX_PREPARATION_SECONDS
    max_read_calls: int = MAX_READ_CALLS
    max_input_tokens: int = MAX_INPUT_TOKENS
    max_output_tokens: int = MAX_OUTPUT_TOKENS
    max_attempts: int = MAX_JOB_ATTEMPTS
    max_repairs: int = MAX_REPAIRS
    started_at: float = 0.0
    read_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    attempts: int = 0
    repairs: int = 0

    def __post_init__(self) -> None:
        self.started_at = self.started_at or monotonic()
        if self.deadline_seconds <= 0 or self.deadline_seconds > MAX_PREPARATION_SECONDS:
            raise ValidationError("Preparation deadline must be at most 180 seconds")

    def check_deadline(self, *, now: float | None = None) -> None:
        elapsed = (now if now is not None else monotonic()) - self.started_at
        if elapsed > self.deadline_seconds:
            raise ConflictError("Analysis preparation deadline exhausted")

    def start_attempt(self) -> None:
        self.check_deadline()
        self.attempts += 1
        if self.attempts > self.max_attempts:
            raise ConflictError("Analysis attempt limit exhausted")

    def record_read(self, count: int = 1) -> None:
        if count < 0:
            raise ValidationError("Read count cannot be negative")
        self.read_calls += count
        if self.read_calls > self.max_read_calls:
            raise ConflictError("Analysis read-call budget exhausted")

    def record_usage(self, *, input_tokens: int, output_tokens: int) -> None:
        if input_tokens < 0 or output_tokens < 0:
            raise ValidationError("Token usage cannot be negative")
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        if self.input_tokens > self.max_input_tokens:
            raise ConflictError("Analysis input-token budget exhausted")
        if self.output_tokens > self.max_output_tokens:
            raise ConflictError("Analysis output-token budget exhausted")

    def record_repair(self) -> None:
        self.repairs += 1
        if self.repairs > self.max_repairs:
            raise ConflictError("Structured-output repair budget exhausted")

    def snapshot(self) -> AnalysisUsage:
        return AnalysisUsage(self.read_calls, self.input_tokens, self.output_tokens, self.attempts, self.repairs)


def validate_tool_timeout(seconds: float) -> None:
    if seconds <= 0 or seconds > MAX_TOOL_SECONDS:
        raise ValidationError("Tool timeout must be at most 15 seconds")


def validate_node_timeout(seconds: float) -> None:
    if seconds <= 0 or seconds > MAX_NODE_SECONDS:
        raise ValidationError("Node timeout must be at most 60 seconds")