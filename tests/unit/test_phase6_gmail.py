from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from services.domain.auth import TrustedContext
from services.domain.errors import ConflictError, ValidationError
from services.domain.models import Base, IntegrationConnection, Job, MailboxSync, User
from services.integrations import gmail
from services.integrations.gmail import (
    accept_gmail_push,
    complete_gmail_oauth,
    normalize_gmail_message,
    process_history_page,
    start_gmail_oauth,
)
from services.workers.durable import enqueue_job


@pytest.fixture
def integration_fixture(tmp_path) -> tuple[TrustedContext, sessionmaker[Session]]:
    tenant = uuid4()
    engine = create_engine("sqlite+pysqlite:///" + str(tmp_path / "phase6.db"))
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as session:
        session.add(
            User(
                id=tenant,
                cognito_sub="phase6-owner",
                verified_email="owner@example.test",
                timezone="UTC",
            )
        )
    return TrustedContext(
        tenant_id=tenant,
        subject="phase6-owner",
        email="owner@example.test",
        email_verified=True,
        correlation_id=uuid4(),
    ), factory


def test_gmail_oauth_state_is_single_use_and_account_bound(
    integration_fixture: tuple[TrustedContext, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, factory = integration_fixture
    monkeypatch.setattr(
        gmail,
        "get_settings",
        lambda: SimpleNamespace(
            capability_encryption_key="phase6-secret",
            environment="test",
            gmail_client_id="gmail-client",
            gmail_authorization_url="https://accounts.google.test/auth",
        ),
    )
    with factory.begin() as session:
        started = start_gmail_oauth(
            session, context, redirect_uri="https://app.test/callback", expected_account_id="acct-1"
        )
        scopes = set(parse_qs(urlsplit(started.authorization_url).query)["scope"][0].split())
        assert scopes == {
            "openid",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
        }
        connection = complete_gmail_oauth(
            session,
            context,
            state=started.state,
            code="code",
            provider_account_id="acct-1",
            account_email="owner@example.test",
            access_token="access",
            refresh_token="refresh",
            code_verifier=started.code_verifier,
        )
        assert connection.status == "CONNECTED"
        assert connection.credential_ciphertext is not None
        assert (
            session.scalar(select(MailboxSync).where(MailboxSync.connection_id == connection.id))
            is not None
        )
        with pytest.raises(ValidationError):
            complete_gmail_oauth(
                session,
                context,
                state=started.state,
                code="code",
                provider_account_id="acct-1",
                account_email="owner@example.test",
                access_token="access",
                code_verifier=started.code_verifier,
            )


def test_gmail_push_is_deduplicated_and_message_normalization_is_safe(
    integration_fixture: tuple[TrustedContext, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, factory = integration_fixture
    secret = "phase6-push-secret"
    monkeypatch.setattr(
        gmail,
        "get_settings",
        lambda: SimpleNamespace(
            capability_encryption_key=secret,
            gmail_push_verification_secret=secret,
            environment="test",
            gmail_client_id="client",
            gmail_authorization_url="https://accounts.google.test/auth",
        ),
    )
    with factory.begin() as session:
        connection = IntegrationConnection(
            tenant_id=context.tenant_id,
            provider_account_id="acct-1",
            account_email="owner@example.test",
            status="CONNECTED",
            watch_id="watch-1",
        )
        session.add(connection)
        session.flush()
        import hashlib
        import hmac

        verification = hmac.new(secret.encode(), b"acct-1:watch-1", hashlib.sha256).hexdigest()
        first = accept_gmail_push(
            session,
            provider_account_id="acct-1",
            watch_id="watch-1",
            history_id="100",
            delivery_id="delivery-1",
            payload_hash="a" * 64,
            occurred_at=datetime.now(UTC),
            verification_token=verification,
        )
        duplicate = accept_gmail_push(
            session,
            provider_account_id="acct-1",
            watch_id="watch-1",
            history_id="101",
            delivery_id="delivery-1",
            payload_hash="a" * 64,
            occurred_at=datetime.now(UTC),
            verification_token=verification,
        )
        assert duplicate.id == first.id
        with pytest.raises(ValidationError):
            accept_gmail_push(
                session,
                provider_account_id="acct-1",
                watch_id="watch-1",
                history_id="100",
                delivery_id="delivery-2",
                payload_hash="b" * 64,
                occurred_at=datetime.now(UTC),
                verification_token="wrong",
            )
    assert normalize_gmail_message({"id": "m1", "threadId": "t1", "labelIds": ["SENT"]}) is None
    assert (
        normalize_gmail_message(
            {
                "id": "m1",
                "threadId": "t1",
                "headers": [{"name": "Auto-Submitted", "value": "auto-generated"}],
            }
        )
        is None
    )
    assert (
        normalize_gmail_message(
            {"id": "m1", "threadId": "t1", "historyId": "100", "internalDate": "1700000000000"}
        ).provider_message_id
        == "m1"
    )


def test_history_page_advances_cursor_only_after_bounded_processing(
    integration_fixture: tuple[TrustedContext, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, factory = integration_fixture
    monkeypatch.setattr(
        gmail,
        "get_settings",
        lambda: SimpleNamespace(capability_encryption_key="secret", environment="test"),
    )
    with factory.begin() as session:
        connection = IntegrationConnection(
            tenant_id=context.tenant_id,
            provider_account_id="acct-1",
            account_email="owner@example.test",
            status="CONNECTED",
        )
        session.add(connection)
        session.flush()
        session.add(MailboxSync(tenant_id=context.tenant_id, connection_id=connection.id))
        session.flush()
        sync = process_history_page(
            session,
            context,
            connection_id=connection.id,
            history_id="100",
            next_history_id="101",
            messages=[
                {"id": "m1", "threadId": "t1", "historyId": "100", "internalDate": "1700000000000"}
            ],
        )
        assert sync.committed_history_id == "101"
        assert connection.committed_history_id == "101"
        with pytest.raises(ValidationError):
            process_history_page(
                session,
                context,
                connection_id=connection.id,
                history_id="101",
                next_history_id="102",
                messages=[{"id": str(index), "threadId": "t1"} for index in range(101)],
            )


def test_gmail_browser_callback_exchanges_code_and_binds_identity(
    integration_fixture: tuple[TrustedContext, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, factory = integration_fixture
    settings = SimpleNamespace(
        capability_encryption_key="phase6-secret",
        environment="test",
        gmail_client_id="gmail-client",
        gmail_client_secret="gmail-client-secret",
        gmail_authorization_url="https://accounts.google.test/auth",
        gmail_token_url="https://oauth2.google.test/token",
        gmail_userinfo_url="https://openidconnect.google.test/userinfo",
        gmail_redirect_uri="https://api.test/api/v1/integrations/gmail/callback",
    )
    monkeypatch.setattr(gmail, "get_settings", lambda: settings)
    token_request: dict[str, object] = {}

    class Response:
        status_code = 200

        def __init__(self, body: dict[str, object]) -> None:
            self.body = body

        def json(self) -> dict[str, object]:
            return self.body

    def fake_post(url: str, *, data: dict[str, str], timeout: float) -> Response:
        token_request.update(url=url, data=data, timeout=timeout)
        return Response({"access_token": "access", "refresh_token": "refresh"})

    def fake_get(url: str, *, headers: dict[str, str], timeout: float) -> Response:
        assert url == settings.gmail_userinfo_url
        assert headers == {"Authorization": "Bearer access"}
        assert timeout == 10.0
        return Response(
            {"sub": "google-sub-1", "email": "Owner@Example.test", "email_verified": True}
        )

    monkeypatch.setattr(gmail.httpx, "post", fake_post)
    monkeypatch.setattr(gmail.httpx, "get", fake_get)
    with factory.begin() as session:
        started = start_gmail_oauth(session, context)
        connection = gmail.complete_gmail_oauth_callback(
            session, state=started.state, code="google-code"
        )
        assert connection.provider_account_id == "google-sub-1"
        assert connection.account_email == "owner@example.test"
        assert json.loads(gmail._open(connection.credential_ciphertext or "")) == {
            "access_token": "access",
            "refresh_token": "refresh",
        }
        sync = session.scalar(select(MailboxSync).where(MailboxSync.connection_id == connection.id))
        job = session.scalar(select(Job).where(Job.kind == "gmail.initial_backfill"))
        assert sync is not None
        assert sync.status == "RUNNING"
        assert sync.coverage_start is not None
        assert job is not None
        assert job.payload_ref["connection_id"] == str(connection.id)
    assert token_request["url"] == settings.gmail_token_url
    assert isinstance(token_request["data"], dict)
    assert token_request["data"]["code"] == "google-code"
    assert token_request["data"]["code_verifier"] == started.code_verifier
    assert "gmail-client-secret" not in started.authorization_url


def test_gmail_history_adapter_fetches_added_messages_and_marks_404_gap(
    integration_fixture: tuple[TrustedContext, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, factory = integration_fixture
    settings = SimpleNamespace(
        capability_encryption_key="phase6-secret",
        environment="test",
        gmail_api_base_url="https://gmail.test/gmail/v1",
    )
    monkeypatch.setattr(gmail, "get_settings", lambda: settings)

    class Response:
        def __init__(self, status_code: int, body: dict[str, object]) -> None:
            self.status_code = status_code
            self.body = body

        def json(self) -> dict[str, object]:
            return self.body

    requests: list[tuple[str, str, dict[str, object] | None]] = []

    def fake_request(
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, object] | None = None,
        json: dict[str, object] | None = None,
        timeout: float,
    ) -> Response:
        requests.append((method, url, params))
        if url.endswith("/users/me/history"):
            return Response(
                200,
                {"historyId": "101", "history": [{"messagesAdded": [{"message": {"id": "m1"}}]}]},
            )
        return Response(
            200,
            {
                "id": "m1",
                "threadId": "t1",
                "labelIds": ["INBOX"],
                "internalDate": "1700000000000",
                "historyId": "101",
                "payload": {"headers": [{"name": "From", "value": "client@example.test"}]},
            },
        )

    monkeypatch.setattr(gmail.httpx, "request", fake_request)
    with factory.begin() as session:
        connection = IntegrationConnection(
            tenant_id=context.tenant_id,
            provider_account_id="acct-1",
            account_email="owner@example.test",
            status="CONNECTED",
            credential_ciphertext=gmail._seal(
                json.dumps({"access_token": "access", "refresh_token": "refresh"})
            ),
        )
        session.add(connection)
        session.flush()
        page = gmail.fetch_gmail_history_page(
            session, context, connection_id=connection.id, history_id="100"
        )
        assert len(page.messages) == 1
        assert page.messages[0]["id"] == "m1"
        assert requests[0][2]["startHistoryId"] == "100"
        assert requests[0][2]["historyTypes"] == "messageAdded"
        assert requests[1][2] == {"format": "full"}
        session.add(MailboxSync(tenant_id=context.tenant_id, connection_id=connection.id))
        session.flush()

        def fake_404(*args: object, **kwargs: object) -> Response:
            return Response(404, {})

        monkeypatch.setattr(gmail.httpx, "request", fake_404)
        with pytest.raises(gmail.GmailHistoryGap):
            gmail.sync_gmail_history_page(
                session, context, connection_id=connection.id, history_id="1"
            )
        session.flush()
        assert connection.status == "PAUSED"
        sync = session.scalar(select(MailboxSync).where(MailboxSync.connection_id == connection.id))
        assert sync is not None and sync.status == "GAP_DETECTED"


def test_oauth_account_switch_is_rejected(
    integration_fixture: tuple[TrustedContext, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, factory = integration_fixture
    monkeypatch.setattr(
        gmail,
        "get_settings",
        lambda: SimpleNamespace(
            capability_encryption_key="phase6-secret",
            environment="test",
            gmail_client_id="gmail-client",
            gmail_authorization_url="https://accounts.google.test/auth",
        ),
    )
    with factory.begin() as session:
        started = start_gmail_oauth(
            session,
            context,
            redirect_uri="https://app.test/callback",
            expected_account_id="authorized-account",
        )
        with pytest.raises(ConflictError):
            complete_gmail_oauth(
                session,
                context,
                state=started.state,
                code="code",
                provider_account_id="switched-account",
                account_email="attacker@example.test",
                access_token="access",
                refresh_token="refresh",
                code_verifier=started.code_verifier,
            )


def test_maintenance_recovers_dropped_push_and_expiring_watch(
    integration_fixture: tuple[TrustedContext, sessionmaker[Session]],
) -> None:
    context, factory = integration_fixture
    now = datetime.now(UTC)
    with factory.begin() as session:
        connection = IntegrationConnection(
            tenant_id=context.tenant_id,
            provider_account_id="acct-1",
            account_email="owner@example.test",
            status="CONNECTED",
            watch_id="watch-1",
            watch_expiry=now + timedelta(hours=1),
            committed_history_id="100",
        )
        session.add(connection)
        session.flush()
        session.add(
            MailboxSync(
                tenant_id=context.tenant_id,
                connection_id=connection.id,
                status="IDLE",
                mode="INCREMENTAL",
                committed_history_id="100",
            )
        )
        assert gmail.schedule_gmail_maintenance(session, now=now) == 2
        jobs = list(session.scalars(select(Job).where(Job.tenant_id == context.tenant_id)))
        assert {job.kind for job in jobs} == {"gmail.watch_renew", "gmail.history_sync"}
        assert gmail.schedule_gmail_maintenance(session, now=now) == 0


def test_disconnect_cancels_catchup_and_queues_watch_cleanup(
    integration_fixture: tuple[TrustedContext, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, factory = integration_fixture
    monkeypatch.setattr(
        gmail,
        "get_settings",
        lambda: SimpleNamespace(capability_encryption_key="phase6-secret", environment="test"),
    )
    with factory.begin() as session:
        connection = IntegrationConnection(
            tenant_id=context.tenant_id,
            provider_account_id="acct-1",
            account_email="owner@example.test",
            status="CONNECTED",
            watch_id="watch-1",
            watch_expiry=datetime.now(UTC) + timedelta(days=1),
            committed_history_id="100",
            credential_ciphertext=gmail._seal(
                json.dumps({"access_token": "access", "refresh_token": "refresh"})
            ),
        )
        session.add(connection)
        session.flush()
        sync = MailboxSync(
            tenant_id=context.tenant_id,
            connection_id=connection.id,
            status="IDLE",
            mode="INCREMENTAL",
            committed_history_id="100",
        )
        session.add(sync)
        session.flush()
        catchup = enqueue_job(
            session,
            tenant_id=context.tenant_id,
            kind="gmail.history_sync",
            payload_ref={"connection_id": str(connection.id), "history_id": "100"},
            correlation_id=context.correlation_id,
        )
        gmail.disconnect_gmail(session, context, connection_id=connection.id)
        assert connection.status == "DISCONNECTED"
        assert sync.status == "PAUSED"
        assert catchup.state == "CANCELLED"
        cleanup = session.scalar(
            select(Job).where(
                Job.kind == "gmail.watch_stop",
                Job.state == "QUEUED",
            )
        )
        assert cleanup is not None
        assert cleanup.payload_ref["connection_id"] == str(connection.id)


def test_rejected_refresh_moves_connection_to_reauthorization(
    integration_fixture: tuple[TrustedContext, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, factory = integration_fixture
    settings = SimpleNamespace(
        capability_encryption_key="phase6-secret",
        environment="test",
        gmail_client_id="gmail-client",
        gmail_client_secret="gmail-secret",
        gmail_token_url="https://oauth2.google.test/token",
    )
    monkeypatch.setattr(gmail, "get_settings", lambda: settings)

    class Response:
        status_code = 400

        def json(self) -> dict[str, object]:
            return {"error": "invalid_grant"}

    monkeypatch.setattr(gmail.httpx, "post", lambda *args, **kwargs: Response())
    with factory.begin() as session:
        connection = IntegrationConnection(
            tenant_id=context.tenant_id,
            provider_account_id="acct-1",
            account_email="owner@example.test",
            status="CONNECTED",
            credential_ciphertext=gmail._seal(
                json.dumps({"access_token": "expired", "refresh_token": "refresh"})
            ),
        )
        session.add(connection)
        session.flush()
        with pytest.raises(ConflictError):
            gmail.refresh_gmail_access_token(
                session,
                context,
                connection_id=connection.id,
            )
        assert connection.status == "REAUTH_REQUIRED"
        assert connection.last_error == "refresh_token_rejected"
