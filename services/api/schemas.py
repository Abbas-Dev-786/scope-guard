from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Generic, Literal, TypeVar
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from services.domain.enums import EventType, ProjectStatus

T = TypeVar("T")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ErrorBody(StrictModel):
    code: str
    message: str
    request_id: str
    details: dict[str, object] = Field(default_factory=dict)


class Page(StrictModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None


class UserRead(StrictModel):
    id: UUID
    verified_email: EmailStr
    timezone: str
    status: str
    row_version: int


class OnboardingCreate(StrictModel):
    timezone: str = Field(min_length=1, max_length=64)
    rate_minor: int = Field(gt=0, le=100_000_000)
    minimum_minor: int = Field(gt=0, le=100_000_000)
    increment_minor: int = Field(gt=0, le=100_000_000)
    communication_style: str = Field(min_length=1, max_length=32)
    reminder_policy: dict[str, object] = Field(default_factory=dict)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Timezone must be a valid IANA name") from exc
        return value


class PreferenceRead(StrictModel):
    id: UUID
    version: int
    rate_minor: int
    minimum_minor: int
    increment_minor: int
    communication_style: str
    reminder_policy: dict[str, object]
    confirmed_at: datetime


class OnboardingRead(StrictModel):
    user: UserRead
    preference: PreferenceRead


class PreferenceUpdate(StrictModel):
    expected_row_version: int = Field(gt=0)
    rate_minor: int = Field(gt=0, le=100_000_000)
    minimum_minor: int = Field(gt=0, le=100_000_000)
    increment_minor: int = Field(gt=0, le=100_000_000)
    communication_style: str = Field(min_length=1, max_length=32)
    reminder_policy: dict[str, object] = Field(default_factory=dict)


class ClientCreate(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    company: str | None = Field(default=None, max_length=200)


class ClientUpdate(StrictModel):
    expected_row_version: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=200)
    company: str | None = Field(default=None, max_length=200)


class ClientRead(StrictModel):
    id: UUID
    name: str
    company: str | None
    row_version: int
    created_at: datetime
    updated_at: datetime


class ContactCreate(StrictModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=200)
    role: str | None = Field(default=None, max_length=100)


class ContactRead(StrictModel):
    id: UUID
    client_id: UUID
    email: EmailStr
    display_name: str
    role: str | None
    created_at: datetime


class ProjectCreate(StrictModel):
    client_id: UUID
    name: str = Field(min_length=1, max_length=200)
    base_contract_value_minor: int = Field(default=0, ge=0, le=100_000_000)
    timezone: str = "Asia/Kolkata"
    weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4], min_length=1, max_length=7)
    holiday_dates: list[date] = Field(default_factory=list)
    confirmed_daily_capacity_hours: Decimal = Field(default=Decimal("7"), gt=0, le=24)
    target_date: date | None = None

    @field_validator("weekdays")
    @classmethod
    def valid_weekdays(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value) or any(day < 0 or day > 6 for day in value):
            raise ValueError("Weekdays must be distinct integers from 0 to 6")
        return sorted(value)


class ProjectUpdate(StrictModel):
    expected_row_version: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=200)
    target_date: date | None = None


class ProjectRead(StrictModel):
    id: UUID
    client_id: UUID
    name: str
    status: ProjectStatus
    currency: str
    base_contract_value_minor: int
    current_scope_version_id: UUID | None
    preference_version_id: UUID
    timezone: str
    calendar_version_id: UUID | None
    target_date: date | None
    row_version: int
    created_at: datetime
    updated_at: datetime


class EventEnvelope(StrictModel):
    schema_version: int = Field(ge=1)
    event_id: UUID
    event_type: EventType
    tenant_id: UUID
    project_id: UUID | None
    connection_id: UUID | None
    environment: str
    provider: str
    provider_account_id: str | None
    provider_event_id: str | None
    resource_type: str
    resource_id: str
    occurred_at: datetime
    received_at: datetime
    correlation_id: UUID
    causation_id: UUID | None
    payload_ref: str

class JobRead(StrictModel):
    id: UUID
    kind: str
    state: str
    payload_ref: dict[str, object]
    correlation_id: UUID
    available_at: datetime
    lease_until: datetime | None
    lease_owner: str | None
    fencing_generation: int
    attempt_count: int
    max_attempts: int
    deadline_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class ActionRead(StrictModel):
    id: UUID
    action_key: str
    provider: str
    operation: str
    state: str
    payload_digest: str
    receipt_ref: dict[str, object] | None
    uncertainty_reason: str | None
    created_at: datetime
    updated_at: datetime


class JobRetryRequest(StrictModel):
    reason: str = Field(min_length=1, max_length=200)


class ActionResolveRequest(StrictModel):
    resolution: Literal["retry", "confirm_receipt", "cancel"]
    duplicate_risk_acknowledged: bool = False
    receipt_ref: dict[str, object] | None = None


class OperationsHealthRead(StrictModel):
    status: Literal["ok", "degraded"]
    counters: dict[str, int]
    gauges: dict[str, int]
class DocumentUploadRequest(StrictModel):
    object_key: str = Field(min_length=1, max_length=512)
    mime_type: str = Field(min_length=1, max_length=120)
    expected_size_bytes: int = Field(gt=0, le=10 * 1024 * 1024)


class UploadGrantRead(StrictModel):
    document_id: UUID
    object_key: str
    object_version: str
    upload_token: str
    expires_at: datetime
    expected_size_bytes: int
    expected_mime_type: str
    upload_url: str | None = None
    upload_fields: dict[str, str] | None = None


class CompleteUploadRequest(StrictModel):
    upload_token: str = Field(min_length=20, max_length=256)
    content_base64: str | None = Field(default=None, min_length=1, max_length=14_000_000)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mime_type: str = Field(min_length=1, max_length=120)


class DocumentRead(StrictModel):
    id: UUID
    project_id: UUID
    object_key: str
    object_version: str
    sha256: str
    size_bytes: int
    mime_type: str
    status: str
    extractor_version: str | None
    rejection_reason: str | None
    created_at: datetime
    completed_at: datetime | None


class ScopeCandidateCorrection(StrictModel):
    candidate_id: UUID
    corrected_text: str = Field(min_length=1, max_length=4000)
    reason: str = Field(min_length=1, max_length=500)


class ScopeConfirmRequest(StrictModel):
    candidate_ids: list[UUID] = Field(min_length=1, max_length=500)


class ScopeItemRead(StrictModel):
    id: UUID
    item_type: str
    item_key: str
    text: str
    source_document_chunk_id: UUID | None


class ScopeRead(StrictModel):
    version: int
    content_hash: str
    confirmed_at: datetime
    items: list[ScopeItemRead]


class GmailOAuthStartRead(StrictModel):
    authorization_url: str
    state: str

class GmailOAuthCallbackRequest(StrictModel):
    state: str = Field(min_length=43, max_length=256)
    code: str = Field(min_length=1, max_length=4096)
    code_verifier: str = Field(min_length=1, max_length=256)
    provider_account_id: str = Field(min_length=1, max_length=255)
    account_email: EmailStr
    access_token: str = Field(min_length=1, max_length=4096)
    refresh_token: str | None = Field(default=None, max_length=4096)

class GmailPushRequest(StrictModel):
    provider_account_id: str = Field(min_length=1, max_length=255)
    watch_id: str = Field(min_length=1, max_length=255)
    history_id: str = Field(min_length=1, max_length=255)
    delivery_id: str = Field(min_length=1, max_length=255)
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    occurred_at: datetime
    verification_token: str = Field(min_length=1, max_length=256)

class IntegrationConnectionRead(StrictModel):
    id: UUID
    provider: str
    provider_account_id: str
    account_email: EmailStr
    status: str
    committed_history_id: str | None
    watch_expiry: datetime | None
    last_success_at: datetime | None
    coverage_cutoff: datetime | None
    last_error: str | None
    sync_status: str
    gap_detected_at: datetime | None
    gap_reason: str | None
    watch_expiry_warning: bool
    stale_sync_warning: bool

class RoutingEventRequest(StrictModel):
    provider: str = Field(min_length=1, max_length=80)
    environment: str = Field(min_length=1, max_length=32)
    provider_event_id: str = Field(min_length=1, max_length=255)
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    occurred_at: datetime
    resource_type: str = Field(min_length=1, max_length=80)
    resource_id: str = Field(min_length=1, max_length=255)
    source_version: str = Field(min_length=1, max_length=255)
    content_ref: str = Field(min_length=1, max_length=512)
    explicit_project_id: UUID | None = None
    alias: str | None = Field(default=None, max_length=160)
    sender: str | None = Field(default=None, max_length=320)
    thread_id: str | None = Field(default=None, max_length=255)


class RoutingDecisionRead(StrictModel):
    id: UUID
    external_event_id: UUID
    status: str
    precedence: str
    candidate_projects: list[str]
    evidence: list[dict[str, object]]
    selected_project_id: UUID | None


class CommunicationRead(StrictModel):
    id: UUID
    project_id: UUID | None
    resource_type: str
    resource_id: str
    source_version: str
    thread_id: str | None
    occurred_at: datetime

class ScopeCandidateRead(StrictModel):
    candidate_id: UUID
    status: str
    corrected_text: str | None


class RoutingResultRead(StrictModel):
    kind: Literal["communication", "decision"]
    id: UUID
    status: str
    project_id: UUID | None = None
    candidate_projects: list[str] = Field(default_factory=list)
    resource_type: str | None = None
    resource_id: str | None = None
    source_version: str | None = None

class RequestCreate(StrictModel):
    project_id: UUID
    summary: str = Field(min_length=1, max_length=4000)
    communication_ids: list[UUID] = Field(default_factory=list, max_length=100)


class RequestRead(StrictModel):
    id: UUID
    project_id: UUID
    summary: str
    status: str
    request_version: int
    merged_into_id: UUID | None
    rejection_reason: str | None
    row_version: int
    created_at: datetime
    updated_at: datetime


class RequestClarify(StrictModel):
    correction: str = Field(min_length=1, max_length=4000)


class RequestMerge(StrictModel):
    source_request_id: UUID
    reason: str = Field(min_length=1, max_length=500)


class RoutingResolveRequest(StrictModel):
    project_id: UUID

class DocumentDownloadRead(StrictModel):
    document_id: UUID
    object_key: str
    object_version: str
    sha256: str
    access_scope: str
    download_url: str | None = None

class DocumentCandidateRead(StrictModel):
    id: UUID
    item_key: str
    item_type: str
    extracted_text: str
    corrected_text: str | None
    status: str
    source_chunk_id: UUID
    correction_reason: str | None


class StructureExtractionRead(StrictModel):
    status: Literal["PENDING", "READY"]
    reason: str | None
    candidates: list[DocumentCandidateRead]

class AnalysisDecisionRead(StrictModel):
    id: UUID
    project_id: UUID
    request_id: UUID | None
    workflow_id: UUID
    kind: str
    status: str
    title: str
    summary: str
    safe_details: dict[str, object]
    terms_snapshot: dict[str, object] | None
    trace_summary: dict[str, object]
    row_version: int
    created_at: datetime
    updated_at: datetime


class AnalysisDecisionDetailRead(AnalysisDecisionRead):
    draft_revision_id: UUID | None = None
    draft_revision: dict[str, object] | None = None


class AnalysisEvidenceRead(StrictModel):
    id: UUID
    bundle_id: UUID
    source_type: str
    source_id: str
    source_version: str
    exact_excerpt_ref: str
    content_hash: str
    locator: dict[str, object]
    fetched_at: datetime
    access_scope: str
    relation: str


class WorkflowTraceRead(StrictModel):
    workflow_id: UUID
    state: str
    current_phase: str | None
    policy_version: str | None
    stages: list[dict[str, object]]

class ProposalRevisionRead(StrictModel):
    id: UUID
    change_order_id: UUID
    revision_number: int
    baseline_version_id: UUID
    request_version: int
    total_minor: int
    tax_minor: int
    currency: str
    title: str
    requested_change: str
    deliverables: list[str]
    exclusions: list[str]
    assumptions: list[str]
    client_explanation: str
    recipient_email: EmailStr
    subject: str
    plain_text_body: str
    html_body: str
    attachment_hashes: list[str]
    terms_json: dict[str, object]
    evidence_digest: str
    evidence_reference_ids: list[str]
    canonical_artifact_hash: str
    approval_url: str
    status: str
    created_at: datetime


class ChangeOrderRead(StrictModel):
    id: UUID
    project_id: UUID
    request_id: UUID
    number: int
    current_revision_id: UUID | None
    status: str
    row_version: int
    created_at: datetime
    updated_at: datetime
    revision: ProposalRevisionRead | None = None


class ProposalRevisionEdit(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    requested_change: str | None = Field(default=None, min_length=1, max_length=4000)
    deliverables: list[str] | None = Field(default=None, min_length=1, max_length=50)
    exclusions: list[str] | None = Field(default=None, max_length=50)
    assumptions: list[str] | None = Field(default=None, max_length=50)
    client_explanation: str | None = Field(default=None, min_length=1, max_length=5000)
    subject: str | None = Field(default=None, min_length=1, max_length=240)
    plain_text_body: str | None = Field(default=None, min_length=1, max_length=12000)
    html_body: str | None = Field(default=None, min_length=1, max_length=24000)


class FreelancerApprovalRequest(StrictModel):
    expected_row_version: int = Field(gt=0)
    revision_id: UUID
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class FreelancerDecisionRequest(StrictModel):
    comment: str | None = Field(default=None, max_length=2000)

class WithdrawalRequest(StrictModel):
    reason: str | None = Field(default=None, max_length=500)

class ClientDecisionRequest(StrictModel):
    expected_row_version: int = Field(gt=0)
    revision_id: UUID
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    comment: str | None = Field(default=None, max_length=2000)

class CapabilityExchangeRequest(StrictModel):
    token: str = Field(min_length=43, max_length=256)


class ClientReviewRead(StrictModel):
    change_order_id: UUID
    revision_id: UUID
    revision_number: int
    status: str
    title: str
    requested_change: str
    deliverables: list[str]
    exclusions: list[str]
    assumptions: list[str]
    client_explanation: str
    recipient_email: EmailStr
    subject: str
    plain_text_body: str
    html_body: str
    terms: dict[str, object]


class ClientAcceptanceRequest(StrictModel):
    expected_row_version: int = Field(gt=0)
    revision_id: UUID
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class PaymentLinkReplaceRequest(StrictModel):
    expected_row_version: int = Field(gt=0)


class PaymentRequestRead(StrictModel):
    id: UUID
    project_id: UUID
    accepted_revision_id: UUID
    total_minor: int
    tax_minor: int
    currency: str
    status: str
    due_at: datetime | None
    expire_at: datetime | None
    paid_at: datetime | None
    row_version: int
    provider_link_id: str | None = None
    payment_link_url: str | None = None
    payment_link_status: str | None = None
    collected_minor: int = 0
    job_id: UUID | None = None

class ClientReceiptRead(StrictModel):
    change_order_id: UUID
    revision_id: UUID
    status: str
    payment_status: str
    payment_request_id: UUID | None
    payment_link_url: str | None = None
    payment_link_status: str | None = None
    receipt_session_token: str | None = None
    receipt_csrf_token: str | None = None
