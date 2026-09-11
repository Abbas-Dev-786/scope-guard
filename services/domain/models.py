from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from services.domain.enums import ProjectStatus, UserStatus

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    cognito_sub: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    verified_email: Mapped[str] = mapped_column(String(320), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=UserStatus.ACTIVE.value)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    row_version: Mapped[int] = mapped_column(BigInteger, default=1, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE','DISABLED','DELETION_PENDING')", name="ck_users_status"
        ),
    )


class PreferenceVersion(Base):
    __tablename__ = "preference_versions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    rate_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    minimum_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    increment_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    communication_style: Mapped[str] = mapped_column(
        String(32), nullable=False, default="professional"
    )
    reminder_policy: Mapped[dict[str, object]] = mapped_column(
        JSON_TYPE, nullable=False, default=dict
    )
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_preference_tenant_id"),
        UniqueConstraint("tenant_id", "version", name="uq_preference_tenant_version"),
        CheckConstraint("version > 0", name="ck_preference_version_positive"),
        CheckConstraint(
            "rate_minor > 0 AND minimum_minor > 0 AND increment_minor > 0",
            name="ck_preference_money_positive",
        ),
        CheckConstraint(
            "rate_minor <= 100000000 AND minimum_minor <= 100000000 AND increment_minor <= 100000000",
            name="ck_preference_money_limit",
        ),
    )


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    company: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    row_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)

    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_clients_tenant_id"),)


class ClientContact(Base):
    __tablename__ = "client_contacts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    normalized_email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "client_id"],
            ["clients.tenant_id", "clients.id"],
            ondelete="RESTRICT",
            name="fk_contact_client_owner",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_contacts_tenant_id"),
        UniqueConstraint(
            "tenant_id", "client_id", "normalized_email", name="uq_contact_email_per_client"
        ),
        Index("ix_contacts_tenant_client", "tenant_id", "client_id"),
    )


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default=ProjectStatus.PAUSED_UNCONFIRMED_SCOPE.value
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    base_contract_value_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    current_scope_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    preference_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    calendar_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    target_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    row_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_projects_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "client_id"],
            ["clients.tenant_id", "clients.id"],
            ondelete="RESTRICT",
            name="fk_project_client_owner",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "preference_version_id"],
            ["preference_versions.tenant_id", "preference_versions.id"],
            ondelete="RESTRICT",
            name="fk_project_preference_owner",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "id", "calendar_version_id"],
            ["calendar_versions.tenant_id", "calendar_versions.project_id", "calendar_versions.id"],
            name="fk_project_current_calendar_owner",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("currency = 'INR'", name="ck_projects_currency_inr"),
        CheckConstraint(
            "base_contract_value_minor >= 0 AND base_contract_value_minor <= 100000000",
            name="ck_projects_contract_value",
        ),
        CheckConstraint(
            "status IN ('DRAFT','PAUSED_UNCONFIRMED_SCOPE','ACTIVE','ARCHIVED','DELETION_PENDING')",
            name="ck_projects_status",
        ),
        Index("ix_projects_tenant_created", "tenant_id", "created_at", "id"),
    )


class CalendarVersion(Base):
    __tablename__ = "calendar_versions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    weekdays: Mapped[list[int]] = mapped_column(JSON_TYPE, nullable=False)
    holiday_dates: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False, default=list)
    confirmed_daily_capacity_hours: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "project_id", "id", name="uq_calendar_project_id"),
        UniqueConstraint("tenant_id", "project_id", "version", name="uq_calendar_project_version"),
        ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            ondelete="RESTRICT",
            name="fk_calendar_project_owner",
        ),
        CheckConstraint("version > 0", name="ck_calendar_version_positive"),
        CheckConstraint(
            "confirmed_daily_capacity_hours > 0 AND confirmed_daily_capacity_hours <= 24",
            name="ck_calendar_capacity",
        ),
    )


class ApiIdempotency(Base):
    __tablename__ = "api_idempotency"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    actor_scope: Mapped[str] = mapped_column(String(255), nullable=False)
    route: Mapped[str] = mapped_column(String(255), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    response_ref: Mapped[dict[str, object]] = mapped_column(JSON_TYPE, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    __table_args__ = (
        UniqueConstraint("actor_scope", "route", "key", name="uq_api_idempotency_scope_route_key"),
        Index("ix_api_idempotency_expiry", "expires_at"),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_revision: Mapped[int | None] = mapped_column(BigInteger)
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    causation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    before_state: Mapped[dict[str, object] | None] = mapped_column(JSON_TYPE)
    after_state: Mapped[dict[str, object] | None] = mapped_column(JSON_TYPE)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    safe_metadata: Mapped[dict[str, object]] = mapped_column(
        JSON_TYPE, nullable=False, default=dict
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            ondelete="RESTRICT",
            name="fk_audit_project_owner",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_audit_tenant_id"),
        Index("ix_audit_tenant_project_time", "tenant_id", "project_id", "occurred_at"),
    )

class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(120), nullable=False)
    payload_ref: Mapped[dict[str, object]] = mapped_column(JSON_TYPE, nullable=False)
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, default=uuid.uuid4)
    causation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="QUEUED")
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    fencing_generation: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            ondelete="RESTRICT",
            name="fk_jobs_project_owner",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_jobs_tenant_id"),
        CheckConstraint(
            "state IN ('QUEUED','RUNNING','RETRY_WAIT','SUCCEEDED','FAILED_REQUIRES_REVIEW','CANCELLED')",
            name="ck_jobs_state",
        ),
        CheckConstraint("fencing_generation >= 0", name="ck_jobs_fence_nonnegative"),
        CheckConstraint("attempt_count >= 0 AND attempt_count <= max_attempts", name="ck_jobs_attempts"),
        CheckConstraint("max_attempts BETWEEN 1 AND 3", name="ck_jobs_max_attempts"),
        Index("ix_jobs_runnable", "state", "available_at", "lease_until"),
        Index("ix_jobs_tenant_state", "tenant_id", "state"),
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON_TYPE, nullable=False)
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    causation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publish_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_outbox_tenant_id"),
        Index("ix_outbox_unpublished", "published_at", "created_at"),
        Index("ix_outbox_aggregate", "tenant_id", "aggregate_type", "aggregate_id"),
    )


class ConsumerReceipt(Base):
    __tablename__ = "consumer_receipts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    consumer_name: Mapped[str] = mapped_column(String(120), nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    result_ref: Mapped[dict[str, object]] = mapped_column(JSON_TYPE, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    __table_args__ = (
        UniqueConstraint("consumer_name", "event_id", name="uq_consumer_event"),
        Index("ix_consumer_receipts_event", "event_id"),
    )


class WorkflowInstance(Base):
    __tablename__ = "workflow_instances"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    workflow_key: Mapped[str] = mapped_column(String(160), nullable=False)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="RUNNING")
    budget_minor: Mapped[int | None] = mapped_column(BigInteger)
    reserved_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    current_job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    scope_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    preference_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    current_phase: Mapped[str | None] = mapped_column(String(80))
    policy_version: Mapped[str | None] = mapped_column(String(120))
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    row_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            ondelete="RESTRICT",
            name="fk_workflows_project_owner",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "current_job_id"],
            ["jobs.tenant_id", "jobs.id"],
            ondelete="RESTRICT",
            name="fk_workflows_job_owner",
        ),
        UniqueConstraint("tenant_id", "workflow_key", name="uq_workflows_key"),
        CheckConstraint(
            "state IN ('RUNNING','SUCCEEDED','FAILED','REVIEW_REQUIRED','CANCELLED')",
            name="ck_workflows_state",
        ),
        CheckConstraint("budget_minor IS NULL OR budget_minor >= 0", name="ck_workflows_budget"),
        CheckConstraint("reserved_minor >= 0", name="ck_workflows_reserved"),
    )


class ExternalAction(Base):
    __tablename__ = "external_actions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    action_key: Mapped[str] = mapped_column(String(160), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    operation: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="READY")
    approved_payload: Mapped[dict[str, object]] = mapped_column(JSON_TYPE, nullable=False)
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    receipt_ref: Mapped[dict[str, object] | None] = mapped_column(JSON_TYPE)
    uncertainty_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            ondelete="RESTRICT",
            name="fk_actions_project_owner",
        ),
        UniqueConstraint("tenant_id", "action_key", name="uq_actions_key"),
        CheckConstraint(
            "state IN ('READY','DISPATCHING','RETRY_WAIT','SUCCEEDED','RECEIPT_CONFIRMED',"
            "'UNKNOWN_OUTCOME','REVIEW_REQUIRED','CANCELLED')",
            name="ck_actions_state",
        ),
        Index("ix_actions_state", "state", "updated_at"),
    )


class ActionAttempt(Base):
    __tablename__ = "action_attempts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    action_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("external_actions.id", ondelete="RESTRICT"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(255))
    dispatched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome_ref: Mapped[dict[str, object] | None] = mapped_column(JSON_TYPE)
    error_code: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (
        UniqueConstraint("action_id", "attempt_number", name="uq_action_attempt_number"),
        CheckConstraint("attempt_number BETWEEN 1 AND 3", name="ck_action_attempt_number"),
        Index("ix_action_attempts_action", "action_id", "attempt_number"),
    )
class AnalysisCapacityReservation(Base):
    __tablename__ = "analysis_capacity_reservations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reservation_key: Mapped[str] = mapped_column(String(160), nullable=False)
    worker_id: Mapped[str] = mapped_column(String(255), nullable=False)
    lease_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "reservation_key", name="uq_analysis_reservation_key"),
        Index("ix_analysis_capacity_active", "released_at", "lease_until"),
        Index("ix_analysis_capacity_tenant", "tenant_id", "released_at"),
    )
class ContractDocument(Base):
    __tablename__ = "contract_documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    object_version: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="UPLOADED")
    extractor_version: Mapped[str | None] = mapped_column(String(120))
    rejection_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_contract_documents_tenant_id"),
        UniqueConstraint("tenant_id", "project_id", "object_key", "object_version", name="uq_contract_document_object_version"),
        CheckConstraint("status IN ('UPLOADED','EXTRACTING','AWAITING_SCOPE_REVIEW','CONFIRMED','REJECTED','FAILED_REQUIRES_REVIEW')", name="ck_contract_document_status"),
        CheckConstraint("size_bytes >= 0 AND size_bytes <= 10485760", name="ck_contract_document_size"),
        Index("ix_contract_documents_project_created", "tenant_id", "project_id", "created_at"),
    )


class DocumentUploadGrant(Base):
    __tablename__ = "document_upload_grants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("contract_documents.id", ondelete="RESTRICT"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expected_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("contract_documents.id", ondelete="RESTRICT"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(255))
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),
        CheckConstraint("start_offset >= 0 AND end_offset >= start_offset", name="ck_document_chunk_offsets"),
        Index("ix_document_chunks_project", "tenant_id", "project_id", "document_id", "chunk_index"),
    )


class ScopeCandidate(Base):
    __tablename__ = "scope_candidates"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("contract_documents.id", ondelete="RESTRICT"), nullable=False)
    source_chunk_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("document_chunks.id", ondelete="RESTRICT"), nullable=False)
    item_key: Mapped[str] = mapped_column(String(160), nullable=False)
    item_type: Mapped[str] = mapped_column(String(40), nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    corrected_text: Mapped[str | None] = mapped_column(Text)
    extractor_version: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="CANDIDATE")
    correction_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        UniqueConstraint("tenant_id", "document_id", "item_key", name="uq_scope_candidate_key"),
        CheckConstraint("status IN ('CANDIDATE','CORRECTED','CONFIRMED','REJECTED')", name="ck_scope_candidate_status"),
    )


class ScopeVersion(Base):
    __tablename__ = "scope_versions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    source_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    confirmation_actor: Mapped[str] = mapped_column(String(255), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("tenant_id", "project_id", "version", name="uq_scope_version_number"),
        UniqueConstraint("tenant_id", "id", name="uq_scope_version_tenant_id"),
    )


class ScopeItem(Base):
    __tablename__ = "scope_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    source_document_chunk_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("document_chunks.id", ondelete="RESTRICT"))
    source_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    item_type: Mapped[str] = mapped_column(String(40), nullable=False)
    item_key: Mapped[str] = mapped_column(String(160), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    supersedes_item_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "item_key", "created_at", name="uq_scope_item_identity"),)


class ScopeVersionItem(Base):
    __tablename__ = "scope_version_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    scope_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("scope_versions.id", ondelete="RESTRICT"), nullable=False)
    scope_item_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("scope_items.id", ondelete="RESTRICT"), nullable=False)

    __table_args__ = (UniqueConstraint("scope_version_id", "scope_item_id", name="uq_scope_version_item"),)


class ScopeAmendment(Base):
    __tablename__ = "scope_amendments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    accepted_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, unique=True)
    previous_scope_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("scope_versions.id", ondelete="RESTRICT"), nullable=False)
    resulting_scope_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("scope_versions.id", ondelete="RESTRICT"), nullable=False, unique=True)
    operations_json: Mapped[list[dict[str, object]]] = mapped_column(JSON_TYPE, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class IntegrationBinding(Base):
    __tablename__ = "integration_bindings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    connection_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    alias: Mapped[str | None] = mapped_column(String(160))
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("tenant_id", "project_id", "provider", "resource_type", "resource_id", name="uq_integration_binding"),
        Index("ix_integration_binding_lookup", "tenant_id", "provider", "resource_type", "resource_id", "status"),
    )


class ExternalEvent(Base):
    __tablename__ = "external_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    connection_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_account_id: Mapped[str | None] = mapped_column(String(255))
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_object_ref: Mapped[str | None] = mapped_column(String(512))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(40), nullable=False, default="RECEIVED")
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(80))
    resource_id: Mapped[str | None] = mapped_column(String(255))
    source_version: Mapped[str | None] = mapped_column(String(255))
    content_ref: Mapped[str | None] = mapped_column(String(512))

    __table_args__ = (UniqueConstraint("tenant_id", "connection_id", "provider_event_id", name="uq_external_event_delivery"),)


class CommunicationEvent(Base):
    __tablename__ = "communication_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="RESTRICT"))
    connection_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    external_event_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("external_events.id", ondelete="RESTRICT"), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_version: Mapped[str] = mapped_column(String(255), nullable=False)
    sender: Mapped[str | None] = mapped_column(String(320))
    thread_id: Mapped[str | None] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    direction: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (UniqueConstraint("tenant_id", "connection_id", "resource_type", "resource_id", "source_version", name="uq_communication_source_version"),)


class RequestRecord(Base):
    __tablename__ = "request_records"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="OPEN")
    request_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    rejection_reason: Mapped[str | None] = mapped_column(String(500))
    row_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        CheckConstraint("status IN ('OPEN','CLARIFICATION_REQUIRED','COVERED','PROPOSAL_OPEN','WAIVED','DECLINED','MERGED','RESOLVED')", name="ck_request_record_status"),
        Index("ix_request_records_project_status", "tenant_id", "project_id", "status", "created_at"),
    )


class RequestCommunication(Base):
    __tablename__ = "request_communications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("request_records.id", ondelete="RESTRICT"), nullable=False)
    communication_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("communication_events.id", ondelete="RESTRICT"), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(40), nullable=False, default="SUPPORTS")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (UniqueConstraint("request_id", "communication_id", name="uq_request_communication"),)


class EvidenceBundle(Base):
    __tablename__ = "evidence_bundles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("request_records.id", ondelete="RESTRICT"))
    snapshot_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    searched_sources: Mapped[list[dict[str, object]]] = mapped_column(JSON_TYPE, nullable=False)
    cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completeness: Mapped[str] = mapped_column(String(32), nullable=False)
    stale_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class EvidenceReference(Base):
    __tablename__ = "evidence_references"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    bundle_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("evidence_bundles.id", ondelete="RESTRICT"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_version: Mapped[str] = mapped_column(String(255), nullable=False)
    exact_excerpt_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    locator: Mapped[dict[str, object]] = mapped_column(JSON_TYPE, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    access_scope: Mapped[str] = mapped_column(String(255), nullable=False)
    relation: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (CheckConstraint("relation IN ('SUPPORTS','CONTRADICTS','CONTEXT')", name="ck_evidence_reference_relation"),)


class RoutingDecision(Base):
    __tablename__ = "routing_decisions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    external_event_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("external_events.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN")
    precedence: Mapped[str] = mapped_column(String(40), nullable=False)
    candidate_projects: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False)
    evidence: Mapped[list[dict[str, object]]] = mapped_column(JSON_TYPE, nullable=False)
    selected_project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    resolved_by: Mapped[str | None] = mapped_column(String(255))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (CheckConstraint("status IN ('OPEN','RESOLVED','DISMISSED')", name="ck_routing_decision_status"),)

class ThreadAssignment(Base):
    __tablename__ = "thread_assignments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    connection_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    thread_id: Mapped[str] = mapped_column(String(255), nullable=False)
    assigned_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "connection_id", "thread_id", name="uq_thread_assignment"),)



class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    workflow_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("workflow_instances.id", ondelete="RESTRICT"), nullable=False)
    node_name: Mapped[str] = mapped_column(String(120), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(120), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(120), nullable=False)
    tool_policy_version: Mapped[str] = mapped_column(String(120), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_ref: Mapped[dict[str, object]] = mapped_column(JSON_TYPE, nullable=False)
    output_ref: Mapped[dict[str, object] | None] = mapped_column(JSON_TYPE)
    output_hash: Mapped[str | None] = mapped_column(String(64))
    usage: Mapped[dict[str, object] | None] = mapped_column(JSON_TYPE)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RUNNING")
    error_code: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("workflow_id", "node_name", "attempt", name="uq_agent_run_node_attempt"),
        CheckConstraint("attempt BETWEEN 1 AND 3", name="ck_agent_run_attempt"),
        CheckConstraint("status IN ('RUNNING','SUCCEEDED','REPAIRING','FAILED','REVIEW_REQUIRED')", name="ck_agent_run_status"),
        Index("ix_agent_runs_workflow", "tenant_id", "workflow_id", "node_name", "attempt"),
    )


class ScopeAssessment(Base):
    __tablename__ = "scope_assessments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("request_records.id", ondelete="RESTRICT"))
    workflow_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("workflow_instances.id", ondelete="RESTRICT"), nullable=False)
    classification: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_bundle_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("evidence_bundles.id", ondelete="RESTRICT"))
    scope_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("scope_versions.id", ondelete="RESTRICT"))
    request_version: Mapped[int | None] = mapped_column(Integer)
    coverage_status: Mapped[str] = mapped_column(String(32), nullable=False)
    matched_scope_item_ids: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False, default=list)
    matched_amendment_ids: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False, default=list)
    pending_request_ids: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False, default=list)
    required_evidence_queries: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False, default=list)
    uncertainty: Mapped[str | None] = mapped_column(String(32))
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        CheckConstraint("classification IN ('IN_SCOPE','POTENTIAL_SCOPE_CHANGE','AMBIGUOUS','PREVIOUSLY_APPROVED','NOT_A_SCOPE_REQUEST')", name="ck_scope_assessment_classification"),
        CheckConstraint("coverage_status IN ('COMPLETE','PARTIAL','UNAVAILABLE','REQUIRES_CLARIFICATION')", name="ck_scope_assessment_coverage"),
        CheckConstraint("uncertainty IS NULL OR uncertainty IN ('LOW','MEDIUM','HIGH')", name="ck_scope_assessment_uncertainty"),
        Index("ix_scope_assessments_request", "tenant_id", "project_id", "request_id", "created_at"),
    )


class AnalysisBudgetWindow(Base):
    __tablename__ = "analysis_budget_windows"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    scope_key: Mapped[str] = mapped_column(String(160), nullable=False)
    window_start: Mapped[date] = mapped_column(Date, nullable=False)
    token_limit: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tokens_reserved: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    tokens_used: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost_limit_minor: Mapped[int | None] = mapped_column(BigInteger)
    cost_reserved_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost_used_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        UniqueConstraint("scope_key", "window_start", name="uq_analysis_budget_window"),
        CheckConstraint("token_limit > 0 AND tokens_reserved >= 0 AND tokens_used >= 0", name="ck_analysis_budget_tokens"),
        CheckConstraint("cost_limit_minor IS NULL OR cost_limit_minor >= 0", name="ck_analysis_budget_cost_limit"),
        CheckConstraint("cost_reserved_minor >= 0 AND cost_used_minor >= 0", name="ck_analysis_budget_costs"),
    )


class AnalysisBudgetReservation(Base):
    __tablename__ = "analysis_budget_reservations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    workflow_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("workflow_instances.id", ondelete="RESTRICT"), nullable=False)
    window_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("analysis_budget_windows.id", ondelete="RESTRICT"), nullable=False)
    reservation_key: Mapped[str] = mapped_column(String(160), nullable=False)
    token_reserved: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cost_reserved_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    token_used: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost_used_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RESERVED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        UniqueConstraint("tenant_id", "reservation_key", name="uq_analysis_budget_reservation"),
        CheckConstraint("token_reserved > 0 AND token_used >= 0", name="ck_analysis_reservation_tokens"),
        CheckConstraint("cost_reserved_minor >= 0 AND cost_used_minor >= 0", name="ck_analysis_reservation_costs"),
        CheckConstraint("status IN ('RESERVED','RECONCILED','RELEASED')", name="ck_analysis_reservation_status"),
    )

class AnalysisDecision(Base):
    """Sanitized decision inbox item produced by a bounded analysis workflow."""

    __tablename__ = "analysis_decisions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("request_records.id", ondelete="RESTRICT"))
    workflow_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("workflow_instances.id", ondelete="RESTRICT"), nullable=False)
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("scope_assessments.id", ondelete="RESTRICT"))
    evidence_bundle_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("evidence_bundles.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="OPEN")
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    safe_details: Mapped[dict[str, object]] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    terms_snapshot: Mapped[dict[str, object] | None] = mapped_column(JSON_TYPE)
    trace_summary: Mapped[dict[str, object]] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    row_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        CheckConstraint("kind IN ('PROPOSAL_REVIEW','CLARIFICATION','PROJECT_MAPPING','INTEGRATION_HEALTH','ACTION_UNCERTAINTY')", name="ck_analysis_decision_kind"),
        CheckConstraint("status IN ('OPEN','RESOLVED','DISMISSED','STALE')", name="ck_analysis_decision_status"),
        Index("ix_analysis_decisions_inbox", "tenant_id", "status", "created_at"),
        Index("ix_analysis_decisions_project", "tenant_id", "project_id", "created_at"),
    )


class AnalysisDraftRevision(Base):
    """Immutable, sanitized draft/revision payload; edits create a new row."""

    __tablename__ = "analysis_draft_revisions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("request_records.id", ondelete="RESTRICT"))
    workflow_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("workflow_instances.id", ondelete="RESTRICT"), nullable=False)
    decision_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("analysis_decisions.id", ondelete="RESTRICT"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON_TYPE, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="CURRENT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("decision_id", "revision"),
        CheckConstraint("revision > 0", name="ck_analysis_draft_revision_positive"),
        CheckConstraint("status IN ('CURRENT','SUPERSEDED','REVOKED')", name="ck_analysis_draft_status"),
        Index("ix_analysis_drafts_tenant", "tenant_id", "project_id", "created_at"),
    )


class AnalysisEvaluationRun(Base):
    """Pinned evaluation report with safe aggregate metrics and no model chain-of-thought."""

    __tablename__ = "analysis_evaluation_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    dataset_version: Mapped[str] = mapped_column(String(120), nullable=False)
    split: Mapped[str] = mapped_column(String(20), nullable=False)
    run_number: Mapped[int] = mapped_column(Integer, nullable=False)
    model_version: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(120), nullable=False)
    tool_policy_version: Mapped[str] = mapped_column(String(120), nullable=False)
    metrics: Mapped[dict[str, object]] = mapped_column(JSON_TYPE, nullable=False)
    passed: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("dataset_version", "split", "run_number", "model_version", "prompt_version", "tool_policy_version"),
        CheckConstraint("run_number BETWEEN 1 AND 3", name="ck_analysis_evaluation_run_number"),
        CheckConstraint("split IN ('development','held_out')", name="ck_analysis_evaluation_split"),
    )

class ChangeOrder(Base):
    __tablename__ = "change_orders"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("request_records.id", ondelete="RESTRICT"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("proposal_revisions.id", name="fk_change_order_current_revision", use_alter=True, deferrable=True, initially="DEFERRED"))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="DRAFT")
    row_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_change_orders_tenant_id"),
        UniqueConstraint("tenant_id", "project_id", "number", name="uq_change_order_number"),
        CheckConstraint("status IN ('DRAFT','AWAITING_FREELANCER_APPROVAL','SEND_PENDING','AWAITING_CLIENT_APPROVAL','REVISION_REQUESTED','CLIENT_APPROVED','REJECTED_BY_FREELANCER','REJECTED_BY_CLIENT','WITHDRAWN','EXPIRED')", name="ck_change_order_status"),
        CheckConstraint("number > 0", name="ck_change_order_number_positive"),
        CheckConstraint("row_version >= 1", name="ck_change_order_row_version"),
        Index("ix_change_orders_project_status", "tenant_id", "project_id", "status", "created_at"),
    )


class ProposalRevision(Base):
    __tablename__ = "proposal_revisions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    change_order_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("change_orders.id", ondelete="RESTRICT"), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("scope_versions.id", ondelete="RESTRICT"), nullable=False)
    request_version: Mapped[int] = mapped_column(Integer, nullable=False)
    preference_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("preference_versions.id", ondelete="RESTRICT"), nullable=False)
    total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    requested_change: Mapped[str] = mapped_column(Text, nullable=False)
    deliverables: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False)
    exclusions: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False, default=list)
    assumptions: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False, default=list)
    client_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    recipient_contact_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("client_contacts.id", ondelete="RESTRICT"), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(240), nullable=False)
    plain_text_body: Mapped[str] = mapped_column(Text, nullable=False)
    html_body: Mapped[str] = mapped_column(Text, nullable=False)
    attachment_hashes: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False, default=list)
    terms_json: Mapped[dict[str, object]] = mapped_column(JSON_TYPE, nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_reference_ids: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False, default=list)
    canonical_artifact_ref: Mapped[dict[str, object]] = mapped_column(JSON_TYPE, nullable=False)
    canonical_artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    token_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="CURRENT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_proposal_revisions_tenant_id"),
        UniqueConstraint("change_order_id", "revision_number", name="uq_proposal_revision_number"),
        CheckConstraint("revision_number > 0", name="ck_proposal_revision_positive"),
        CheckConstraint("total_minor > 0 AND total_minor <= 100000000", name="ck_proposal_total_bounds"),
        CheckConstraint("tax_minor >= 0 AND tax_minor <= total_minor", name="ck_proposal_tax_bounds"),
        CheckConstraint("currency = 'INR'", name="ck_proposal_currency_inr"),
        CheckConstraint("status IN ('CURRENT','SUPERSEDED','REVOKED')", name="ck_proposal_revision_status"),
        Index("ix_proposal_revisions_current", "tenant_id", "change_order_id", "status"),
    )


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    change_order_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("change_orders.id", ondelete="RESTRICT"), nullable=False)
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("proposal_revisions.id", ondelete="RESTRICT"), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    provenance: Mapped[dict[str, object]] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    comment: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("revision_id", "actor_type", "decision", name="uq_approval_revision_actor_decision"),
        CheckConstraint("actor_type IN ('FREELANCER','CLIENT')", name="ck_approval_actor_type"),
        CheckConstraint("decision IN ('APPROVED','REJECTED','REQUEST_CHANGES','WAIVED')", name="ck_approval_decision"),
    )


class ClientCapability(Base):
    __tablename__ = "client_capabilities"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    change_order_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("change_orders.id", ondelete="RESTRICT"), nullable=False)
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("proposal_revisions.id", ondelete="RESTRICT"), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False, default="REVIEW")
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        CheckConstraint("purpose IN ('REVIEW','RECEIPT')", name="ck_client_capability_purpose"),
        Index("ix_client_capabilities_scope", "tenant_id", "change_order_id", "revision_id"),
    )


class ClientSession(Base):
    __tablename__ = "client_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    capability_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("client_capabilities.id", ondelete="RESTRICT"), nullable=False)
    session_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (CheckConstraint("purpose IN ('REVIEW','RECEIPT')", name="ck_client_session_purpose"),)


class PaymentRequest(Base):
    __tablename__ = "payment_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    accepted_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("proposal_revisions.id", ondelete="RESTRICT"), nullable=False, unique=True)
    total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="NOT_REQUESTED")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    row_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        CheckConstraint("total_minor > 0 AND total_minor <= 100000000", name="ck_payment_request_total_bounds"),
        CheckConstraint("tax_minor >= 0 AND tax_minor <= total_minor", name="ck_payment_request_tax_bounds"),
        CheckConstraint("currency = 'INR'", name="ck_payment_request_currency_inr"),
        CheckConstraint("status IN ('NOT_REQUESTED','CREATION_PENDING','PENDING','REVIEW_REQUIRED','PAID','EXPIRED','CANCELLED','REVERSED')", name="ck_payment_request_status"),
    )


class ApprovedRevenueFact(Base):
    __tablename__ = "approved_revenue_facts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    change_order_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("change_orders.id", ondelete="RESTRICT"), nullable=False)
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("proposal_revisions.id", ondelete="RESTRICT"), nullable=False, unique=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    fact_type: Mapped[str] = mapped_column(String(32), nullable=False, default="APPROVED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        CheckConstraint("amount_minor > 0 AND amount_minor <= 100000000", name="ck_revenue_amount_bounds"),
        CheckConstraint("tax_minor >= 0 AND tax_minor <= amount_minor", name="ck_revenue_tax_bounds"),
        CheckConstraint("currency = 'INR'", name="ck_revenue_currency_inr"),
    )


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    change_order_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("change_orders.id", ondelete="RESTRICT"))
    revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("proposal_revisions.id", ondelete="RESTRICT"))
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="SES")
    verified_recipient: Mapped[str] = mapped_column(String(320), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    action_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("external_actions.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("tenant_id", "change_order_id", "revision_id", "channel", name="uq_notification_revision_channel"),
        CheckConstraint("channel IN ('SES')", name="ck_notification_channel"),
        CheckConstraint("state IN ('PENDING','SENT','UNKNOWN_OUTCOME','FAILED','CANCELLED')", name="ck_notification_state"),
    )


class IntegrationConnection(Base):
    __tablename__ = "integration_connections"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False, default="gmail")
    provider_account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    account_email: Mapped[str] = mapped_column(String(320), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="CONNECTING")
    credential_ciphertext: Mapped[str | None] = mapped_column(Text)
    credential_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    watch_id: Mapped[str | None] = mapped_column(String(255))
    watch_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    committed_history_id: Mapped[str | None] = mapped_column(String(255))
    coverage_cutoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    row_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", "provider_account_id", name="uq_integration_connection_account"),
        CheckConstraint("provider IN ('gmail')", name="ck_integration_connection_provider"),
        CheckConstraint("status IN ('CONNECTING','CONNECTED','REAUTH_REQUIRED','DISCONNECTED','PAUSED')", name="ck_integration_connection_status"),
        CheckConstraint("credential_version >= 1", name="ck_integration_connection_credential_version"),
        CheckConstraint("row_version >= 1", name="ck_integration_connection_row_version"),
        Index("ix_integration_connections_health", "tenant_id", "provider", "status", "updated_at"),
    )


class OAuthSession(Base):
    __tablename__ = "oauth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False, default="gmail")
    state_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    code_verifier_ciphertext: Mapped[str | None] = mapped_column(Text)
    redirect_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    expected_account_id: Mapped[str | None] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        CheckConstraint("provider IN ('gmail')", name="ck_oauth_session_provider"),
        Index("ix_oauth_sessions_expiry", "expires_at"),
    )


class MailboxSync(Base):
    __tablename__ = "mailbox_syncs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    connection_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("integration_connections.id", ondelete="RESTRICT"), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="IDLE")
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="INITIAL_BACKFILL")
    committed_history_id: Mapped[str | None] = mapped_column(String(255))
    coverage_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    coverage_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    gap_detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    gap_reason: Mapped[str | None] = mapped_column(String(500))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    row_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        CheckConstraint("status IN ('IDLE','RUNNING','REAUTH_REQUIRED','GAP_DETECTED','PAUSED')", name="ck_mailbox_sync_status"),
        CheckConstraint("mode IN ('INITIAL_BACKFILL','INCREMENTAL')", name="ck_mailbox_sync_mode"),
        CheckConstraint("row_version >= 1", name="ck_mailbox_sync_row_version"),
        Index("ix_mailbox_sync_health", "tenant_id", "status", "last_success_at"),
    )
