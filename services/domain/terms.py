from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from services.domain.errors import UnsupportedTermsError, ValidationError
from services.domain.money import validate_money


class CalendarRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    timezone_name: str
    weekdays: tuple[int, ...] = (0, 1, 2, 3, 4)
    holiday_dates: tuple[date, ...] = ()
    confirmed_daily_capacity_hours: Decimal = Field(gt=0, le=24)

    @field_validator("timezone_name")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Unknown IANA timezone") from exc
        return value

    @field_validator("weekdays")
    @classmethod
    def valid_weekdays(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if not value or len(set(value)) != len(value) or any(day < 0 or day > 6 for day in value):
            raise ValueError("Weekdays must be distinct integers from 0 to 6")
        return tuple(sorted(value))


class CommercialTerms(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    total_minor: int
    tax_minor: int
    currency: str = "INR"
    full_payment_required: bool = True
    due_days: int = 7
    due_local_time: time = time(17, 0)
    link_expiry_days: int = 30
    pay_before_work: bool = True

    @model_validator(mode="after")
    def supported_policy(self) -> CommercialTerms:
        validate_money(self.total_minor, self.tax_minor, self.currency)
        if not self.full_payment_required or not self.pay_before_work:
            raise UnsupportedTermsError("MVP requires verified full payment before work")
        if self.due_days != 7 or self.due_local_time != time(17, 0) or self.link_expiry_days != 30:
            raise UnsupportedTermsError("Contract collection terms require manual handling")
        return self


def due_at(client_approved_at: datetime, timezone_name: str) -> datetime:
    if client_approved_at.tzinfo is None:
        raise ValidationError("Approval timestamp must be timezone-aware")
    try:
        project_zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValidationError("Unknown IANA timezone") from exc
    approval_local = client_approved_at.astimezone(project_zone)
    due_date = approval_local.date() + timedelta(days=7)
    local_due = datetime.combine(due_date, time(17, 0), tzinfo=project_zone)
    return local_due.astimezone(UTC)


def add_working_days(started_at: datetime, days: int, rules: CalendarRules) -> datetime:
    if started_at.tzinfo is None or days < 0:
        raise ValidationError("A timezone-aware start and non-negative working days are required")
    if days == 0:
        return started_at.astimezone(UTC)
    zone = ZoneInfo(rules.timezone_name)
    local = started_at.astimezone(zone)
    current = local.date()
    remaining = days
    while remaining:
        current += timedelta(days=1)
        if current.weekday() in rules.weekdays and current not in rules.holiday_dates:
            remaining -= 1
    return datetime.combine(current, local.timetz(), tzinfo=zone).astimezone(UTC)
