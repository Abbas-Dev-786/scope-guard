from __future__ import annotations

from decimal import ROUND_CEILING, Decimal, InvalidOperation

from services.domain.errors import ValidationError

MAX_CHANGE_MINOR = 100_000_000
MAX_HOURS = Decimal("1000")


def parse_hours(value: str) -> Decimal:
    if not isinstance(value, str):
        raise ValidationError("Hours must be a decimal string")
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError("Hours must be a valid decimal string") from exc
    if not parsed.is_finite() or not Decimal("0") < parsed <= MAX_HOURS:
        raise ValidationError("Hours are outside the supported range")
    return parsed


def validate_effort_range(
    low_hours: str, recommended_hours: str, high_hours: str
) -> tuple[Decimal, Decimal, Decimal]:
    low, recommended, high = map(parse_hours, (low_hours, recommended_hours, high_hours))
    if not low <= recommended <= high:
        raise ValidationError("Effort range must satisfy low <= recommended <= high")
    if high > low * Decimal("2"):
        raise ValidationError("Effort uncertainty requires clarification")
    return low, recommended, high


def recommend_total_minor(
    hours: str, rate_minor: int, minimum_minor: int, increment_minor: int
) -> int:
    effort = parse_hours(hours)
    values = (rate_minor, minimum_minor, increment_minor)
    if any(type(value) is not int or value <= 0 for value in values):
        raise ValidationError("Pricing parameters must be positive integer paise")
    raw = max(effort * Decimal(rate_minor), Decimal(minimum_minor))
    steps = (raw / Decimal(increment_minor)).to_integral_value(rounding=ROUND_CEILING)
    result = int(steps) * increment_minor
    if result > MAX_CHANGE_MINOR:
        raise ValidationError("Proposal exceeds the MVP change-order limit")
    return result


def validate_money(
    total_minor: int, tax_minor: int, currency: str = "INR", *, allow_zero: bool = False
) -> None:
    if currency != "INR":
        raise ValidationError("Only INR is supported")
    if type(total_minor) is not int or total_minor < 0 or total_minor > MAX_CHANGE_MINOR:
        raise ValidationError("Total must be integer paise within MVP bounds")
    if not allow_zero and total_minor == 0:
        raise ValidationError("A payment-bearing change order must have a positive total")
    if type(tax_minor) is not int or tax_minor < 0 or tax_minor > total_minor:
        raise ValidationError("Tax must be explicit integer paise between zero and total")
