from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_CEILING, Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.domain.auth import TrustedContext
from services.domain.errors import NotFoundError, ValidationError
from services.domain.models import CalendarVersion, PreferenceVersion, Project
from services.domain.money import recommend_total_minor, validate_effort_range
from services.domain.terms import CalendarRules

from .schemas import (
    EvidenceRoleOutput,
    GateDecision,
    ImpactRoleOutput,
    ScopeRoleOutput,
    TermsSnapshot,
)
from .validation import require_project_context


@dataclass(frozen=True, slots=True)
class ScheduleResult:
    schedule_impact_days: int | None
    conditions: tuple[str, ...]


def apply_evidence_gate(
    preliminary: ScopeRoleOutput,
    evidence: EvidenceRoleOutput | None,
    *,
    accepted_amendment_ids: set[UUID] | None = None,
    required_baseline_complete: bool = True,
) -> GateDecision:
    """Conservatively route analysis; evidence can overturn a preliminary change finding."""
    accepted = accepted_amendment_ids or set()
    if preliminary.classification == "NOT_A_SCOPE_REQUEST":
        return GateDecision(route="NO_ACTION", classification=preliminary.classification, reason=preliminary.reason)
    if evidence is None:
        return GateDecision(route="CLARIFICATION", classification="AMBIGUOUS", reason="Evidence verification was not completed", required_questions=["Provide the governing scope and request evidence"])
    refs = [item.reference_id for item in evidence.supporting_references + evidence.contradictory_references]
    if not required_baseline_complete or evidence.completeness in {"PARTIAL", "UNAVAILABLE", "REQUIRES_CLARIFICATION"}:
        return GateDecision(route="CLARIFICATION", classification="AMBIGUOUS", reason="Required evidence coverage is incomplete", required_questions=evidence.unresolved_questions or ["Provide the missing baseline or request evidence"], evidence_reference_ids=refs)
    if evidence.contradictory_references:
        return GateDecision(route="CLARIFICATION", classification="AMBIGUOUS", reason="Evidence contains conflicting promises or scope statements", required_questions=evidence.unresolved_questions or ["Resolve the conflicting commitments"], evidence_reference_ids=refs)
    amendment_matches = accepted.intersection(set(preliminary.matched_amendment_ids))
    if evidence.final_classification == "PREVIOUSLY_APPROVED" and not amendment_matches:
        return GateDecision(route="CLARIFICATION", classification="AMBIGUOUS", reason="Prior approval was not linked to an accepted amendment", required_questions=["Provide the accepted amendment reference"], evidence_reference_ids=refs)
    if amendment_matches:
        return GateDecision(route="COVERED", classification="PREVIOUSLY_APPROVED", reason="An accepted amendment covers the requested work", evidence_reference_ids=refs)
    if evidence.final_classification == "IN_SCOPE" or preliminary.classification == "IN_SCOPE":
        return GateDecision(route="COVERED", classification="IN_SCOPE", reason="The confirmed baseline covers the request", evidence_reference_ids=refs)
    if evidence.final_classification in {"AMBIGUOUS", "NOT_A_SCOPE_REQUEST"}:
        return GateDecision(route="CLARIFICATION" if evidence.final_classification == "AMBIGUOUS" else "NO_ACTION", classification=evidence.final_classification, reason="Evidence does not support a billable additional-work proposal", required_questions=evidence.unresolved_questions, evidence_reference_ids=refs)
    if evidence.final_classification == "POTENTIAL_SCOPE_CHANGE" and evidence.supporting_references:
        return GateDecision(route="PROPOSAL", classification="POTENTIAL_SCOPE_CHANGE", reason="Authorized evidence supports additional work", evidence_reference_ids=refs)
    return GateDecision(route="CLARIFICATION", classification="AMBIGUOUS", reason="Evidence did not establish a supported route", required_questions=["Clarify the request against the confirmed scope"], evidence_reference_ids=refs)


def _calendar(session: Session, context: TrustedContext, project: Project) -> CalendarRules | None:
    if project.calendar_version_id is None:
        return None
    row = session.scalar(select(CalendarVersion).where(CalendarVersion.id == project.calendar_version_id, CalendarVersion.tenant_id == context.tenant_id, CalendarVersion.project_id == project.id))
    if row is None:
        raise NotFoundError("Project calendar version was not found")
    holidays = tuple(date.fromisoformat(value) for value in row.holiday_dates)
    return CalendarRules(timezone_name=project.timezone, weekdays=tuple(row.weekdays), holiday_dates=holidays, confirmed_daily_capacity_hours=Decimal(str(row.confirmed_daily_capacity_hours)))


def schedule_effort(*, recommended_hours: str, calendar: CalendarRules | None) -> ScheduleResult:
    hours = Decimal(recommended_hours)
    if calendar is None:
        return ScheduleResult(None, ("Schedule is conditional because no confirmed calendar capacity is available",))
    days = int((hours / calendar.confirmed_daily_capacity_hours).to_integral_value(rounding=ROUND_CEILING))
    return ScheduleResult(max(days, 1), (f"Uses confirmed capacity of {calendar.confirmed_daily_capacity_hours} hours per working day",))


def freeze_terms(
    session: Session,
    context: TrustedContext,
    *,
    project_id: UUID,
    impact: ImpactRoleOutput,
    tax_minor: int = 0,
) -> TermsSnapshot:
    """Compute money and schedule only from frozen database versions, never model values."""
    project = require_project_context(session, context, project_id)
    preference = session.scalar(select(PreferenceVersion).where(PreferenceVersion.id == project.preference_version_id, PreferenceVersion.tenant_id == context.tenant_id))
    if preference is None:
        raise NotFoundError("Project preference version was not found")
    low, recommended, high = validate_effort_range(impact.low_hours, impact.recommended_hours, impact.high_hours)
    if high > low * Decimal("2"):
        raise ValidationError("Effort range is too uncertain for automatic pricing")
    total = recommend_total_minor(str(recommended), preference.rate_minor, preference.minimum_minor, preference.increment_minor)
    if tax_minor < 0 or tax_minor > total:
        raise ValidationError("Tax must be explicit and within the calculated total")
    schedule = schedule_effort(recommended_hours=str(recommended), calendar=_calendar(session, context, project))
    conditions = ["Full payment is required before work begins", "Client prerequisites must be satisfied"]
    conditions.extend(schedule.conditions)
    if impact.cold_start:
        conditions.append("Cold-start estimate: no verified historical task duration was supplied")
    return TermsSnapshot(total_minor=total, tax_minor=tax_minor, preference_version_id=preference.id, calendar_version_id=project.calendar_version_id, recommended_hours=str(recommended), schedule_impact_days=schedule.schedule_impact_days or 0, conditions=conditions)