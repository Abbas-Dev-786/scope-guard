from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal

from services.domain.errors import ConflictError, ValidationError


@dataclass(frozen=True, slots=True)
class ModelPrice:
    input_minor_per_1k: int
    output_minor_per_1k: int

    def __post_init__(self) -> None:
        if self.input_minor_per_1k < 0 or self.output_minor_per_1k < 0:
            raise ValidationError("Model prices cannot be negative")


@dataclass(frozen=True, slots=True)
class ReviewedModelPrices:
    version: str
    reviewed_at: datetime
    prices: dict[str, ModelPrice]
    max_age_days: int = 30

    def __post_init__(self) -> None:
        if not self.version or self.max_age_days <= 0:
            raise ValidationError("Reviewed model-price configuration is invalid")
        if self.reviewed_at.tzinfo is None:
            raise ValidationError("Reviewed model-price timestamp must be timezone-aware")

    def for_model(self, model_id: str, *, now: datetime | None = None) -> ModelPrice:
        observed = now or datetime.now(UTC)
        if observed - self.reviewed_at > timedelta(days=self.max_age_days):
            raise ConflictError("Model-price configuration is stale; analysis is paused")
        try:
            return self.prices[model_id]
        except KeyError as exc:
            raise ConflictError("Model price is unavailable; analysis is paused") from exc

    def cost_minor(self, model_id: str, *, input_tokens: int, output_tokens: int, now: datetime | None = None) -> int:
        if input_tokens < 0 or output_tokens < 0:
            raise ValidationError("Token counts cannot be negative")
        price = self.for_model(model_id, now=now)
        raw = (Decimal(input_tokens) * Decimal(price.input_minor_per_1k) + Decimal(output_tokens) * Decimal(price.output_minor_per_1k)) / Decimal(1000)
        return int(raw.to_integral_value(rounding=ROUND_CEILING))