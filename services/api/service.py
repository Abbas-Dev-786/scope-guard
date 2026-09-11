from __future__ import annotations

import base64
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.api.schemas import (
    ClientCreate,
    ClientRead,
    ClientUpdate,
    ContactCreate,
    ContactRead,
    OnboardingCreate,
    OnboardingRead,
    Page,
    PreferenceRead,
    PreferenceUpdate,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    UserRead,
)
from services.domain.auth import TrustedContext
from services.domain.canonical import canonical_sha256
from services.domain.enums import ProjectStatus
from services.domain.errors import ConflictError, NotFoundError, ValidationError
from services.domain.models import (
    ApiIdempotency,
    AuditEvent,
    CalendarVersion,
    Client,
    ClientContact,
    PreferenceVersion,
    Project,
    User,
)
from services.domain.terms import CalendarRules

ResponseT = TypeVar("ResponseT", bound=BaseModel)


def _audit(
    session: Session,
    context: TrustedContext,
    action: str,
    resource_type: str,
    resource_id: UUID,
    before: dict[str, object] | None,
    after: dict[str, object] | None,
    revision: int | None = None,
    project_id: UUID | None = None,
) -> None:
    safe_content = {"before": before, "after": after}
    session.add(
        AuditEvent(
            tenant_id=context.tenant_id,
            project_id=project_id,
            actor=context.subject,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id),
            resource_revision=revision,
            correlation_id=context.correlation_id,
            before_state=before,
            after_state=after,
            content_digest=canonical_sha256(safe_content),
            safe_metadata={},
        )
    )


def execute_idempotent(
    session: Session,
    context: TrustedContext,
    route: str,
    key: str,
    request: BaseModel | dict[str, object],
    response_type: type[ResponseT],
    operation: Callable[[], ResponseT],
    *,
    actor_scope: str | None = None,
) -> ResponseT:
    if not key or len(key) > 128:
        raise ValidationError("A valid Idempotency-Key header is required")
    payload = request.model_dump(mode="json") if isinstance(request, BaseModel) else request
    digest = canonical_sha256(payload)
    actor_scope = actor_scope or f"tenant:{context.tenant_id}:subject:{context.subject}"
    existing = session.scalar(
        select(ApiIdempotency).where(
            ApiIdempotency.actor_scope == actor_scope,
            ApiIdempotency.route == route,
            ApiIdempotency.key == key,
        )
    )
    if existing:
        if existing.request_digest != digest:
            raise ConflictError("Idempotency key was already used for different content")
        return response_type.model_validate(existing.response_ref)
    try:
        result = operation()
        session.flush()
        session.add(
            ApiIdempotency(
                actor_scope=actor_scope,
                route=route,
                key=key,
                request_digest=digest,
                response_ref=result.model_dump(mode="json"),
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        concurrent = session.scalar(
            select(ApiIdempotency).where(
                ApiIdempotency.actor_scope == actor_scope,
                ApiIdempotency.route == route,
                ApiIdempotency.key == key,
            )
        )
        if concurrent and concurrent.request_digest == digest:
            return response_type.model_validate(concurrent.response_ref)
        raise ConflictError("Concurrent mutation conflicted; refresh and retry") from None
    return result


def _encode_cursor(created_at: datetime, resource_id: UUID) -> str:
    raw = json.dumps([created_at.isoformat(), str(resource_id)], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        timestamp, resource_id = json.loads(raw)
        return datetime.fromisoformat(timestamp), UUID(resource_id)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValidationError("Cursor is invalid") from exc


def _apply_cursor(
    query: Select[Any], model: type[Client] | type[Project], cursor: str | None
) -> Select[Any]:
    if cursor:
        created_at, resource_id = _decode_cursor(cursor)
        query = query.where(
            or_(
                model.created_at > created_at,
                and_(model.created_at == created_at, model.id > resource_id),
            )
        )
    return query.order_by(model.created_at, model.id)


def current_preference(session: Session, tenant_id: UUID) -> PreferenceVersion:
    preference = session.scalar(
        select(PreferenceVersion)
        .where(PreferenceVersion.tenant_id == tenant_id)
        .order_by(PreferenceVersion.version.desc())
        .limit(1)
    )
    if preference is None:
        raise ConflictError("Complete pricing preferences before creating a project")
    return preference


def onboard_owner(
    session: Session, context: TrustedContext, request: OnboardingCreate
) -> OnboardingRead:
    existing = session.scalar(select(User).where(User.cognito_sub == context.subject))
    if existing is not None:
        preference = current_preference(session, existing.id)
        return OnboardingRead(
            user=UserRead.model_validate(existing),
            preference=PreferenceRead.model_validate(preference),
        )
    user = User(
        id=context.tenant_id,
        cognito_sub=context.subject,
        verified_email=context.email.strip().casefold(),
        timezone=request.timezone,
    )
    session.add(user)
    session.flush()
    preference = PreferenceVersion(
        tenant_id=user.id,
        version=1,
        rate_minor=request.rate_minor,
        minimum_minor=request.minimum_minor,
        increment_minor=request.increment_minor,
        communication_style=request.communication_style,
        reminder_policy=request.reminder_policy,
    )
    session.add(preference)
    session.flush()
    result = OnboardingRead(
        user=UserRead.model_validate(user),
        preference=PreferenceRead.model_validate(preference),
    )
    _audit(
        session,
        context,
        "tenant.onboarded",
        "user",
        user.id,
        None,
        result.model_dump(mode="json"),
        user.row_version,
    )
    return result


def read_preference(session: Session, context: TrustedContext) -> PreferenceRead:
    return PreferenceRead.model_validate(current_preference(session, context.tenant_id))


def update_preference(
    session: Session, context: TrustedContext, request: PreferenceUpdate
) -> PreferenceRead:
    user = session.scalar(select(User).where(User.id == context.tenant_id).with_for_update())
    if user is None:
        raise NotFoundError("Account was not found")
    if user.row_version != request.expected_row_version:
        raise ConflictError(
            "Preferences changed; refresh before saving",
            details={"current_row_version": user.row_version},
        )
    latest = current_preference(session, context.tenant_id)
    new_preference = PreferenceVersion(
        tenant_id=context.tenant_id,
        version=latest.version + 1,
        rate_minor=request.rate_minor,
        minimum_minor=request.minimum_minor,
        increment_minor=request.increment_minor,
        communication_style=request.communication_style,
        reminder_policy=request.reminder_policy,
    )
    user.row_version += 1
    session.add(new_preference)
    session.flush()
    result = PreferenceRead.model_validate(new_preference)
    _audit(
        session,
        context,
        "preferences.updated",
        "preference_version",
        new_preference.id,
        None,
        result.model_dump(mode="json"),
        new_preference.version,
    )
    return result


def create_client(session: Session, context: TrustedContext, request: ClientCreate) -> ClientRead:
    client = Client(
        tenant_id=context.tenant_id,
        name=request.name.strip(),
        company=request.company.strip() if request.company else None,
    )
    session.add(client)
    session.flush()
    result = ClientRead.model_validate(client)
    _audit(
        session,
        context,
        "client.created",
        "client",
        client.id,
        None,
        result.model_dump(mode="json"),
        client.row_version,
    )
    return result


def list_clients(
    session: Session, context: TrustedContext, limit: int, cursor: str | None
) -> Page[ClientRead]:
    query = _apply_cursor(
        select(Client).where(Client.tenant_id == context.tenant_id), Client, cursor
    ).limit(limit + 1)
    rows = list(session.scalars(query))
    next_cursor = (
        _encode_cursor(rows[limit - 1].created_at, rows[limit - 1].id)
        if len(rows) > limit
        else None
    )
    return Page[ClientRead](
        items=[ClientRead.model_validate(row) for row in rows[:limit]], next_cursor=next_cursor
    )


def get_client(session: Session, context: TrustedContext, client_id: UUID) -> Client:
    client = session.scalar(
        select(Client).where(Client.id == client_id, Client.tenant_id == context.tenant_id)
    )
    if client is None:
        raise NotFoundError("Client was not found")
    return client


def update_client(
    session: Session, context: TrustedContext, client_id: UUID, request: ClientUpdate
) -> ClientRead:
    client = session.scalar(
        select(Client)
        .where(Client.id == client_id, Client.tenant_id == context.tenant_id)
        .with_for_update()
    )
    if client is None:
        raise NotFoundError("Client was not found")
    if client.row_version != request.expected_row_version:
        raise ConflictError(
            "Client changed; refresh before saving",
            details={"current_row_version": client.row_version},
        )
    before = ClientRead.model_validate(client).model_dump(mode="json")
    client.name = request.name.strip()
    client.company = request.company.strip() if request.company else None
    client.row_version += 1
    client.updated_at = datetime.now(UTC)
    result = ClientRead.model_validate(client)
    _audit(
        session,
        context,
        "client.updated",
        "client",
        client.id,
        before,
        result.model_dump(mode="json"),
        client.row_version,
    )
    return result


def create_contact(
    session: Session, context: TrustedContext, client_id: UUID, request: ContactCreate
) -> ContactRead:
    get_client(session, context, client_id)
    contact = ClientContact(
        tenant_id=context.tenant_id,
        client_id=client_id,
        normalized_email=str(request.email).strip().casefold(),
        display_name=request.display_name.strip(),
        role=request.role.strip() if request.role else None,
    )
    session.add(contact)
    session.flush()
    result = ContactRead(
        id=contact.id,
        client_id=contact.client_id,
        email=contact.normalized_email,
        display_name=contact.display_name,
        role=contact.role,
        created_at=contact.created_at,
    )
    _audit(
        session,
        context,
        "contact.created",
        "client_contact",
        contact.id,
        None,
        result.model_dump(mode="json"),
    )
    return result


def list_contacts(session: Session, context: TrustedContext, client_id: UUID) -> list[ContactRead]:
    get_client(session, context, client_id)
    rows = session.scalars(
        select(ClientContact)
        .where(ClientContact.tenant_id == context.tenant_id, ClientContact.client_id == client_id)
        .order_by(ClientContact.created_at, ClientContact.id)
    )
    return [
        ContactRead(
            id=row.id,
            client_id=row.client_id,
            email=row.normalized_email,
            display_name=row.display_name,
            role=row.role,
            created_at=row.created_at,
        )
        for row in rows
    ]


def create_project(
    session: Session, context: TrustedContext, request: ProjectCreate
) -> ProjectRead:
    get_client(session, context, request.client_id)
    preference = current_preference(session, context.tenant_id)
    rules = CalendarRules(
        timezone_name=request.timezone,
        weekdays=tuple(request.weekdays),
        holiday_dates=tuple(request.holiday_dates),
        confirmed_daily_capacity_hours=request.confirmed_daily_capacity_hours,
    )
    project = Project(
        tenant_id=context.tenant_id,
        client_id=request.client_id,
        name=request.name.strip(),
        status=ProjectStatus.PAUSED_UNCONFIRMED_SCOPE.value,
        currency="INR",
        base_contract_value_minor=request.base_contract_value_minor,
        preference_version_id=preference.id,
        timezone=rules.timezone_name,
        target_date=request.target_date,
    )
    session.add(project)
    session.flush()
    calendar = CalendarVersion(
        tenant_id=context.tenant_id,
        project_id=project.id,
        version=1,
        weekdays=list(rules.weekdays),
        holiday_dates=[item.isoformat() for item in rules.holiday_dates],
        confirmed_daily_capacity_hours=rules.confirmed_daily_capacity_hours,
    )
    session.add(calendar)
    session.flush()
    project.calendar_version_id = calendar.id
    result = ProjectRead.model_validate(project)
    _audit(
        session,
        context,
        "project.created",
        "project",
        project.id,
        None,
        result.model_dump(mode="json"),
        project.row_version,
        project.id,
    )
    return result


def list_projects(
    session: Session, context: TrustedContext, limit: int, cursor: str | None
) -> Page[ProjectRead]:
    query = _apply_cursor(
        select(Project).where(Project.tenant_id == context.tenant_id), Project, cursor
    ).limit(limit + 1)
    rows = list(session.scalars(query))
    next_cursor = (
        _encode_cursor(rows[limit - 1].created_at, rows[limit - 1].id)
        if len(rows) > limit
        else None
    )
    return Page[ProjectRead](
        items=[ProjectRead.model_validate(row) for row in rows[:limit]], next_cursor=next_cursor
    )


def get_project(
    session: Session, context: TrustedContext, project_id: UUID, *, lock: bool = False
) -> Project:
    query = select(Project).where(Project.id == project_id, Project.tenant_id == context.tenant_id)
    project = session.scalar(query.with_for_update() if lock else query)
    if project is None:
        raise NotFoundError("Project was not found")
    return project


def update_project(
    session: Session, context: TrustedContext, project_id: UUID, request: ProjectUpdate
) -> ProjectRead:
    project = get_project(session, context, project_id, lock=True)
    if project.row_version != request.expected_row_version:
        raise ConflictError(
            "Project changed; refresh before saving",
            details={"current_row_version": project.row_version},
        )
    before = ProjectRead.model_validate(project).model_dump(mode="json")
    project.name = request.name.strip()
    project.target_date = request.target_date
    project.row_version += 1
    project.updated_at = datetime.now(UTC)
    result = ProjectRead.model_validate(project)
    _audit(
        session,
        context,
        "project.updated",
        "project",
        project.id,
        before,
        result.model_dump(mode="json"),
        project.row_version,
        project.id,
    )
    return result


def delete_project(
    session: Session, context: TrustedContext, project_id: UUID, expected_row_version: int
) -> ProjectRead:
    project = get_project(session, context, project_id, lock=True)
    if project.row_version != expected_row_version:
        raise ConflictError(
            "Project changed; refresh before deleting",
            details={"current_row_version": project.row_version},
        )
    before = ProjectRead.model_validate(project).model_dump(mode="json")
    project.status = ProjectStatus.DELETION_PENDING.value
    project.row_version += 1
    project.updated_at = datetime.now(UTC)
    result = ProjectRead.model_validate(project)
    _audit(
        session,
        context,
        "project.deletion_requested",
        "project",
        project.id,
        before,
        result.model_dump(mode="json"),
        project.row_version,
        project.id,
    )
    return result


def count_owned(session: Session, model: type[Client] | type[Project], tenant_id: UUID) -> int:
    return (
        session.scalar(select(func.count()).select_from(model).where(model.tenant_id == tenant_id))
        or 0
    )
