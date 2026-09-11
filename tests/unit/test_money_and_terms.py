from datetime import UTC, datetime, time
from decimal import Decimal

import pytest

from services.domain.errors import UnsupportedTermsError, ValidationError
from services.domain.money import recommend_total_minor, validate_effort_range, validate_money
from services.domain.terms import CalendarRules, CommercialTerms, add_working_days, due_at


def test_demo_price_uses_exact_paise_and_minimum() -> None:
    assert recommend_total_minor("14", 100_000, 1_500_000, 50_000) == 1_500_000
    assert recommend_total_minor("15.01", 100_000, 1_500_000, 50_000) == 1_550_000


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "0", "1000.1", "words"])
def test_invalid_effort_never_reaches_minimum_fee(value: str) -> None:
    with pytest.raises(ValidationError):
        recommend_total_minor(value, 100_000, 1_500_000, 50_000)


def test_effort_range_is_ordered_bounded_and_not_overly_wide() -> None:
    assert validate_effort_range("8.5", "10", "12") == (
        Decimal("8.5"),
        Decimal("10"),
        Decimal("12"),
    )
    with pytest.raises(ValidationError):
        validate_effort_range("10", "9", "12")
    with pytest.raises(ValidationError):
        validate_effort_range("1", "2", "2.1")


def test_money_rejects_floats_booleans_currency_and_invalid_tax() -> None:
    for total, tax, currency in [
        (15_000.0, 0, "INR"),
        (True, 0, "INR"),
        (1_500_000, -1, "INR"),
        (1_500_000, 1_500_001, "INR"),
        (1_500_000, 0, "USD"),
    ]:
        with pytest.raises(ValidationError):
            validate_money(total, tax, currency)  # type: ignore[arg-type]


def test_supported_commercial_policy_is_explicit() -> None:
    supported = CommercialTerms(total_minor=1_500_000, tax_minor=0)
    assert supported.currency == "INR"
    assert supported.due_local_time == time(17, 0)
    with pytest.raises(UnsupportedTermsError):
        CommercialTerms(total_minor=1_500_000, tax_minor=0, full_payment_required=False)


def test_due_date_is_seven_calendar_days_at_frozen_project_time() -> None:
    approval = datetime(2026, 10, 30, 18, 30, tzinfo=UTC)
    assert due_at(approval, "America/New_York") == datetime(2026, 11, 6, 22, 0, tzinfo=UTC)


def test_working_days_skip_weekend_and_holiday() -> None:
    rules = CalendarRules(
        timezone_name="Asia/Kolkata",
        weekdays=(0, 1, 2, 3, 4),
        holiday_dates=(datetime(2026, 9, 7).date(),),
        confirmed_daily_capacity_hours=Decimal("7"),
    )
    friday = datetime(2026, 9, 4, 10, 0, tzinfo=UTC)
    assert add_working_days(friday, 2, rules) == datetime(2026, 9, 9, 10, 0, tzinfo=UTC)
