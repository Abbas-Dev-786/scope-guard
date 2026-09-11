from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from services.api.app import app
from services.api.auth import get_current_context
from services.api.database import get_session
from services.domain.auth import TrustedContext
from services.domain.models import Base, Client, PreferenceVersion, Project, User


@pytest.fixture
def database(tmp_path: Path) -> tuple[sessionmaker[Session], User, User]:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'scopeguard.db'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    first = User(
        id=uuid.uuid4(),
        cognito_sub="owner-a",
        verified_email="owner-a@example.com",
        timezone="Asia/Kolkata",
    )
    second = User(
        id=uuid.uuid4(), cognito_sub="owner-b", verified_email="owner-b@example.com", timezone="UTC"
    )
    with factory.begin() as session:
        session.add_all([first, second])
        session.flush()
        session.add_all(
            [
                PreferenceVersion(
                    id=uuid.uuid4(),
                    tenant_id=first.id,
                    version=1,
                    rate_minor=100_000,
                    minimum_minor=1_500_000,
                    increment_minor=50_000,
                    communication_style="professional",
                    reminder_policy={"approval_required": True},
                ),
                PreferenceVersion(
                    id=uuid.uuid4(),
                    tenant_id=second.id,
                    version=1,
                    rate_minor=120_000,
                    minimum_minor=1_200_000,
                    increment_minor=10_000,
                    communication_style="concise",
                    reminder_policy={"approval_required": True},
                ),
            ]
        )
    return factory, first, second


@pytest.fixture
def client(
    database: tuple[sessionmaker[Session], User, User],
) -> Iterator[tuple[TestClient, User, User]]:
    factory, first, second = database

    def session_override() -> Iterator[Session]:
        with factory() as session:
            yield session

    def context_override() -> TrustedContext:
        return TrustedContext(first.id, first.cognito_sub, first.verified_email, True, uuid.uuid4())

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_current_context] = context_override
    with TestClient(app) as http:
        yield http, first, second
    app.dependency_overrides.clear()


def _headers(key: str) -> dict[str, str]:
    return {"Idempotency-Key": key}


def test_client_project_flow_is_idempotent_and_paused(
    client: tuple[TestClient, User, User],
) -> None:
    http, first, _second = client
    assert http.get("/api/v1/me").json()["id"] == str(first.id)
    payload = {"name": "Acme", "company": "Acme SaaS"}
    created = http.post("/api/v1/clients", json=payload, headers=_headers("create-acme"))
    assert created.status_code == 201
    replay = http.post("/api/v1/clients", json=payload, headers=_headers("create-acme"))
    assert replay.status_code == 201
    assert replay.json()["id"] == created.json()["id"]
    conflict = http.post("/api/v1/clients", json={"name": "Other"}, headers=_headers("create-acme"))
    assert conflict.status_code == 409

    project = http.post(
        "/api/v1/projects",
        headers=_headers("create-project"),
        json={
            "client_id": created.json()["id"],
            "name": "Acme SaaS Platform",
            "base_contract_value_minor": 30_000_000,
            "timezone": "Asia/Kolkata",
            "weekdays": [0, 1, 2, 3, 4],
            "holiday_dates": [],
            "confirmed_daily_capacity_hours": "7",
        },
    )
    assert project.status_code == 201, project.text
    assert project.json()["status"] == "PAUSED_UNCONFIRMED_SCOPE"
    assert project.json()["currency"] == "INR"
    assert project.json()["calendar_version_id"]


def test_stale_updates_fail_without_mutation(client: tuple[TestClient, User, User]) -> None:
    http, _first, _second = client
    created = http.post("/api/v1/clients", json={"name": "Acme"}, headers=_headers("c1")).json()
    updated = http.patch(
        f"/api/v1/clients/{created['id']}",
        json={"expected_row_version": 1, "name": "Acme Ltd", "company": None},
        headers=_headers("u1"),
    )
    assert updated.status_code == 200
    stale = http.patch(
        f"/api/v1/clients/{created['id']}",
        json={"expected_row_version": 1, "name": "Stale", "company": None},
        headers=_headers("u2"),
    )
    assert stale.status_code == 409
    assert http.get(f"/api/v1/clients/{created['id']}").json()["name"] == "Acme Ltd"


def test_other_tenant_resource_is_indistinguishable_from_missing(
    client: tuple[TestClient, User, User], database: tuple[sessionmaker[Session], User, User]
) -> None:
    http, _first, second = client
    factory, _first_db, _second_db = database
    with factory.begin() as session:
        foreign = Client(tenant_id=second.id, name="Private B")
        session.add(foreign)
        session.flush()
        foreign_id = foreign.id
    response = http.get(f"/api/v1/clients/{foreign_id}")
    assert response.status_code == 404
    assert response.json()["code"] == "resource_not_found"


def test_database_rejects_cross_tenant_project_relationship(
    database: tuple[sessionmaker[Session], User, User],
) -> None:
    factory, first, second = database
    with factory.begin() as session:
        client_b = Client(tenant_id=second.id, name="Private B")
        session.add(client_b)
        session.flush()
        preference_a = session.scalar(
            select(PreferenceVersion).where(PreferenceVersion.tenant_id == first.id)
        )
        project = Project(
            tenant_id=first.id,
            client_id=client_b.id,
            name="Leak",
            preference_version_id=preference_a.id,
            timezone="UTC",
        )
        session.add(project)
        with pytest.raises(IntegrityError):
            session.flush()


def test_untrusted_tenant_field_and_missing_idempotency_are_rejected(
    client: tuple[TestClient, User, User],
) -> None:
    http, _first, second = client
    injected = http.post(
        "/api/v1/clients",
        json={"name": "Leak", "tenant_id": str(second.id)},
        headers=_headers("bad-body"),
    )
    assert injected.status_code == 422
    missing = http.post("/api/v1/clients", json={"name": "No key"})
    assert missing.status_code == 422
    assert "request_id" in missing.json()

def test_two_tenant_two_project_baseline_is_list_isolated(
    client: tuple[TestClient, User, User], database: tuple[sessionmaker[Session], User, User]
) -> None:
    http, _first, second = client
    factory, _first_db, _second_db = database
    first_client = http.post(
        "/api/v1/clients", json={"name": "Owner A client"}, headers=_headers("baseline-client-a")
    ).json()
    project_a = http.post(
        "/api/v1/projects",
        headers=_headers("baseline-project-a"),
        json={"client_id": first_client["id"], "name": "Owner A project"},
    )
    assert project_a.status_code == 201, project_a.text
    with factory.begin() as session:
        preference_b = session.scalar(
            select(PreferenceVersion).where(PreferenceVersion.tenant_id == second.id)
        )
        client_b = Client(tenant_id=second.id, name="Owner B client")
        session.add(client_b)
        session.flush()
        project_b = Project(
            tenant_id=second.id,
            client_id=client_b.id,
            name="Owner B project",
            preference_version_id=preference_b.id,
            timezone="UTC",
        )
        session.add(project_b)
        session.flush()
        project_b_id = project_b.id
    listed = http.get("/api/v1/projects")
    assert listed.status_code == 200
    assert [item["name"] for item in listed.json()["items"]] == ["Owner A project"]
    assert http.get(f"/api/v1/projects/{project_b_id}").status_code == 404
