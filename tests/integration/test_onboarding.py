from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from services.api.app import app
from services.api.auth import VerifiedPrincipal, get_verified_principal
from services.api.database import get_session
from services.domain.models import AuditEvent, Base, PreferenceVersion, User


@pytest.fixture
def onboarding_client(tmp_path: Path) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'onboarding.db'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def session_override() -> Iterator[Session]:
        with factory() as session:
            yield session

    def identity_override() -> VerifiedPrincipal:
        return VerifiedPrincipal("new-owner", "New.Owner@Example.com", True)

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_verified_principal] = identity_override
    with TestClient(app) as http:
        yield http, factory
    app.dependency_overrides.clear()


def _payload(rate_minor: int = 100_000) -> dict[str, object]:
    return {
        "timezone": "Asia/Kolkata",
        "rate_minor": rate_minor,
        "minimum_minor": 1_500_000,
        "increment_minor": 50_000,
        "communication_style": "professional",
        "reminder_policy": {"approval_required": True},
    }


def test_verified_identity_onboards_once_and_replays_exact_request(
    onboarding_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    http, factory = onboarding_client
    headers = {"Idempotency-Key": "onboard-once"}
    created = http.post("/api/v1/onboarding", json=_payload(), headers=headers)
    replay = http.post("/api/v1/onboarding", json=_payload(), headers=headers)
    conflict = http.post("/api/v1/onboarding", json=_payload(120_000), headers=headers)

    assert created.status_code == 201, created.text
    assert replay.status_code == 201
    assert replay.json() == created.json()
    assert conflict.status_code == 409
    assert created.json()["user"]["verified_email"] == "new.owner@example.com"
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(User)) == 1
        assert session.scalar(select(func.count()).select_from(PreferenceVersion)) == 1
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1


def test_onboarding_requires_verified_email(
    onboarding_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    http, _factory = onboarding_client
    app.dependency_overrides[get_verified_principal] = lambda: VerifiedPrincipal(
        "unverified", "unverified@example.com", False
    )
    response = http.post(
        "/api/v1/onboarding",
        json=_payload(),
        headers={"Idempotency-Key": "unverified"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"
