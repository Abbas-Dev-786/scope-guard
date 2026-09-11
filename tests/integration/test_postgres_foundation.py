from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from services.api.config import get_settings
from services.domain.models import (
    AuditEvent,
    CalendarVersion,
    Client,
    PreferenceVersion,
    Project,
    User,
)

pytestmark = pytest.mark.postgres


@contextmanager
def postgres_session() -> Iterator[Session]:
    if os.getenv("RUN_POSTGRES_TESTS") != "1":
        pytest.skip("Set RUN_POSTGRES_TESTS=1 with the isolated PostgreSQL service running")
    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def test_migration_head_and_composite_ownership() -> None:
    with postgres_session() as session:
        assert (
            session.scalar(select(text("version_num")).select_from(text("alembic_version")))
            == "0009_phase4_decisions_evaluation"
        )
        tenant_a = User(
            id=uuid.uuid4(),
            cognito_sub=f"pg-a-{uuid.uuid4()}",
            verified_email="pg-a@example.com",
            timezone="UTC",
        )
        tenant_b = User(
            id=uuid.uuid4(),
            cognito_sub=f"pg-b-{uuid.uuid4()}",
            verified_email="pg-b@example.com",
            timezone="UTC",
        )
        session.add_all([tenant_a, tenant_b])
        session.flush()
        preference_a = PreferenceVersion(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            version=1,
            rate_minor=100_000,
            minimum_minor=1_500_000,
            increment_minor=50_000,
            communication_style="professional",
            reminder_policy={},
        )
        client_b = Client(id=uuid.uuid4(), tenant_id=tenant_b.id, name="Private B")
        session.add_all([preference_a, client_b])
        session.flush()
        with session.begin_nested():
            session.add(
                Project(
                    id=uuid.uuid4(),
                    tenant_id=tenant_a.id,
                    client_id=client_b.id,
                    name="Cross tenant",
                    preference_version_id=preference_a.id,
                    timezone="UTC",
                )
            )
            with pytest.raises(IntegrityError):
                session.flush()
        session.rollback()


def test_project_calendar_cycle_is_scoped_and_deferred() -> None:
    with postgres_session() as session:
        tenant = User(
            id=uuid.uuid4(),
            cognito_sub=f"pg-cycle-{uuid.uuid4()}",
            verified_email="cycle@example.com",
            timezone="Asia/Kolkata",
        )
        session.add(tenant)
        session.flush()
        preference = PreferenceVersion(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            version=1,
            rate_minor=100_000,
            minimum_minor=1_500_000,
            increment_minor=50_000,
            communication_style="professional",
            reminder_policy={},
        )
        client = Client(id=uuid.uuid4(), tenant_id=tenant.id, name="Acme")
        session.add_all([preference, client])
        session.flush()
        project_id, calendar_id = uuid.uuid4(), uuid.uuid4()
        project = Project(
            id=project_id,
            tenant_id=tenant.id,
            client_id=client.id,
            name="Acme SaaS",
            preference_version_id=preference.id,
            timezone="Asia/Kolkata",
        )
        calendar = CalendarVersion(
            id=calendar_id,
            tenant_id=tenant.id,
            project_id=project_id,
            version=1,
            weekdays=[0, 1, 2, 3, 4],
            holiday_dates=[],
            confirmed_daily_capacity_hours=Decimal("7"),
        )
        session.add(project)
        session.flush()
        session.add(calendar)
        session.flush()
        project.calendar_version_id = calendar.id
        session.flush()
        assert project.calendar_version_id == calendar.id
        session.rollback()


def test_postgres_money_constraint_rejects_out_of_bounds_contract() -> None:
    with postgres_session() as session:
        tenant = User(
            id=uuid.uuid4(),
            cognito_sub=f"pg-money-{uuid.uuid4()}",
            verified_email="money@example.com",
            timezone="UTC",
        )
        session.add(tenant)
        session.flush()
        preference = PreferenceVersion(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            version=1,
            rate_minor=100_000,
            minimum_minor=1_500_000,
            increment_minor=50_000,
            communication_style="professional",
            reminder_policy={},
        )
        client = Client(id=uuid.uuid4(), tenant_id=tenant.id, name="Acme")
        session.add_all([preference, client])
        session.flush()
        session.add(
            Project(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                client_id=client.id,
                name="Too large",
                preference_version_id=preference.id,
                base_contract_value_minor=100_000_001,
                timezone="UTC",
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

def test_audit_records_are_immutable() -> None:
    with postgres_session() as session:
        tenant = User(
            id=uuid.uuid4(),
            cognito_sub=f"pg-audit-{uuid.uuid4()}",
            verified_email="audit@example.com",
            timezone="UTC",
        )
        session.add(tenant)
        session.flush()
        event = AuditEvent(
            tenant_id=tenant.id,
            actor="test",
            action="created",
            resource_type="fixture",
            resource_id="fixture-1",
            correlation_id=uuid.uuid4(),
            content_digest="0" * 64,
            safe_metadata={},
        )
        session.add(event)
        session.flush()
        event_id = event.id
        session.commit()
        with pytest.raises(DBAPIError):
            session.execute(
                text("UPDATE audit_events SET action = 'changed' WHERE id = :event_id"),
                {"event_id": event_id},
            )
        session.rollback()
        with pytest.raises(DBAPIError):
            session.execute(
                text("DELETE FROM audit_events WHERE id = :event_id"),
                {"event_id": event_id},
            )
        session.rollback()