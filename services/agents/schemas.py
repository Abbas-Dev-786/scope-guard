from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from services.domain.money import validate_effort_range


class AgentSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


Classification = Literal[
    "IN_SCOPE",
    "POTENTIAL_SCOPE_CHANGE",
    "AMBIGUOUS",
    "PREVIOUSLY_APPROVED",
    "NOT_A_SCOPE_REQUEST",
]
Coverage = Literal["COMPLETE", "PARTIAL", "UNAVAILABLE", "REQUIRES_CLARIFICATION"]
Uncertainty = Literal["LOW", "MEDIUM", "HIGH"]


class ScopeRoleOutput(AgentSchema):
    classification: Classification
    request_summary: str = Field(min_length=1, max_length=4000)
    reason: str = Field(min_length=1, max_length=4000)
    matched_scope_item_ids: list[UUID] = Field(default_factory=list, max_length=100)
    matched_amendment_ids: list[UUID] = Field(default_factory=list, max_length=100)
    pending_request_ids: list[UUID] = Field(default_factory=list, max_length=100)
    required_evidence_queries: list[str] = Field(default_factory=list, max_length=20)
    uncertainty: Uncertainty


class EvidenceReferenceOutput(AgentSchema):
    reference_id: UUID
    relation: Literal["SUPPORTS", "CONTRADICTS", "CONTEXT"]
    claim: str = Field(min_length=1, max_length=1000)


class EvidenceRoleOutput(AgentSchema):
    final_classification: Classification
    supporting_references: list[EvidenceReferenceOutput] = Field(default_factory=list, max_length=100)
    contradictory_references: list[EvidenceReferenceOutput] = Field(default_factory=list, max_length=100)
    searched_sources: list[dict[str, object]] = Field(default_factory=list, max_length=100)
    completeness: Coverage
    unavailable_sources: list[str] = Field(default_factory=list, max_length=50)
    unresolved_questions: list[str] = Field(default_factory=list, max_length=50)
    temporal_coverage: str = Field(min_length=1, max_length=500)


class ImpactTask(AgentSchema):
    task_key: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=1000)
    low_hours: str
    recommended_hours: str
    high_hours: str
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    dependencies: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_hours(self) -> ImpactTask:
        validate_effort_range(self.low_hours, self.recommended_hours, self.high_hours)
        return self


class ImpactRoleOutput(AgentSchema):
    tasks: list[ImpactTask] = Field(min_length=1, max_length=100)
    low_hours: str
    recommended_hours: str
    high_hours: str
    assumptions: list[str] = Field(default_factory=list, max_length=50)
    dependencies: list[str] = Field(default_factory=list, max_length=50)
    missing_information: list[str] = Field(default_factory=list, max_length=50)
    uncertainty: Uncertainty
    cold_start: bool = True

    @model_validator(mode="after")
    def validate_hours(self) -> ImpactRoleOutput:
        validate_effort_range(self.low_hours, self.recommended_hours, self.high_hours)
        if self.cold_start and not any("history" in item.lower() for item in self.assumptions):
            raise ValueError("Cold-start estimates must disclose missing historical duration")
        return self


class ChangeOrderRoleOutput(AgentSchema):
    title: str = Field(min_length=1, max_length=240)
    requested_change: str = Field(min_length=1, max_length=4000)
    deliverables: list[str] = Field(min_length=1, max_length=50)
    exclusions: list[str] = Field(default_factory=list, max_length=50)
    assumptions: list[str] = Field(default_factory=list, max_length=50)
    client_explanation: str = Field(min_length=1, max_length=5000)


class CommunicationRoleOutput(AgentSchema):
    subject: str = Field(min_length=1, max_length=240)
    plain_text_body: str = Field(min_length=1, max_length=12000)
    html_body: str = Field(min_length=1, max_length=24000)
    recipient_email: str = Field(min_length=3, max_length=320)

    @field_validator("html_body")
    @classmethod
    def reject_active_html(cls, value: str) -> str:
        lowered = value.lower()
        if any(token in lowered for token in ("<script", "javascript:", "<iframe", "onerror=")):
            raise ValueError("Active HTML is not allowed")
        return value


class TermsSnapshot(AgentSchema):
    total_minor: int = Field(gt=0, le=100_000_000)
    tax_minor: int = Field(ge=0)
    currency: Literal["INR"] = "INR"
    preference_version_id: UUID
    calendar_version_id: UUID | None
    recommended_hours: str
    schedule_impact_days: int = Field(ge=0, le=1000)
    full_payment_required: Literal[True] = True
    due_days: Literal[7] = 7
    link_expiry_days: Literal[30] = 30
    pay_before_work: Literal[True] = True
    conditions: list[str] = Field(min_length=1, max_length=50)

    @field_validator("tax_minor")
    @classmethod
    def tax_within_total(cls, value: int, info: object) -> int:
        total = info.data.get("total_minor") if hasattr(info, "data") else None
        if isinstance(total, int) and value > total:
            raise ValueError("Tax cannot exceed total")
        return value


class ProposalPayload(AgentSchema):
    title: str = Field(min_length=1, max_length=240)
    requested_change: str = Field(min_length=1, max_length=4000)
    deliverables: list[str] = Field(min_length=1, max_length=50)
    exclusions: list[str] = Field(default_factory=list, max_length=50)
    assumptions: list[str] = Field(default_factory=list, max_length=50)
    client_explanation: str = Field(min_length=1, max_length=5000)
    subject: str = Field(min_length=1, max_length=240)
    plain_text_body: str = Field(min_length=1, max_length=12000)
    html_body: str = Field(min_length=1, max_length=24000)
    recipient_email: str = Field(min_length=3, max_length=320)
    evidence_reference_ids: list[UUID] = Field(min_length=1, max_length=100)
    terms: TermsSnapshot


class GateDecision(AgentSchema):
    route: Literal["PROPOSAL", "COVERED", "CLARIFICATION", "NO_ACTION"]
    classification: Classification
    reason: str = Field(min_length=1, max_length=4000)
    required_questions: list[str] = Field(default_factory=list, max_length=50)
    evidence_reference_ids: list[UUID] = Field(default_factory=list, max_length=100)


class TraceStage(AgentSchema):
    role: str
    status: Literal["SUCCEEDED", "CLARIFICATION", "FAILED", "SKIPPED"]
    duration_ms: int = Field(ge=0)
    evidence_count: int = Field(ge=0)
    retry_count: int = Field(ge=0, le=3)
    safe_summary: str = Field(max_length=1000)


class DecisionSummary(AgentSchema):
    id: UUID
    kind: str
    status: str
    title: str
    summary: str
    classification: Classification | None = None
    uncertainty: Uncertainty | None = None
    evidence_coverage: Coverage | None = None
    terms: TermsSnapshot | None = None