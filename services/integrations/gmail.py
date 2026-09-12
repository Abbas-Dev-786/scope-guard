"""Durable Gmail connection, push-ingress, and mailbox synchronization boundaries."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from uuid import UUID, uuid4

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.api.config import get_settings
from services.contracts.service import ingest_external_event, route_external_event
from services.domain.auth import TrustedContext
from services.domain.errors import ConflictError, NotFoundError, ValidationError
from services.domain.models import (
    CommunicationEvent,
    ExternalAction,
    ExternalEvent,
    IntegrationBinding,
    IntegrationConnection,
    Job,
    MailboxSync,
    OAuthSession,
    utc_now,
)
from services.workers.durable import cancel_action, enqueue_job

MAX_PUSH_ID_LENGTH = 255
MAX_HISTORY_PAGE = 100
HISTORY_RETENTION_DAYS = 90
WATCH_DAYS = 7


@dataclass(frozen=True, slots=True)
class GmailOAuthStart:
    state: str
    code_verifier: str
    authorization_url: str


@dataclass(frozen=True, slots=True)
class NormalizedGmailMessage:
    provider_message_id: str
    thread_id: str
    source_version: str
    sender: str | None
    occurred_at: datetime
    content_ref: str
    labels: tuple[str, ...]
    subject: str | None
    snippet: str


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _pkce_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _key() -> bytes:
    settings = get_settings()
    material = settings.capability_encryption_key or "scopeguard-development-only"
    if not settings.capability_encryption_key and settings.environment != "development":
        raise ConflictError("Gmail credential encryption is not configured")
    return hashlib.sha256(material.encode("utf-8")).digest()


def _seal(value: str) -> str:
    nonce = secrets.token_bytes(12)
    encrypted = AESGCM(_key()).encrypt(nonce, value.encode("utf-8"), b"scopeguard:gmail-credential")
    return base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")


def _open(value: str) -> str:
    try:
        envelope = base64.urlsafe_b64decode(value.encode("ascii"))
        return AESGCM(_key()).decrypt(envelope[:12], envelope[12:], b"scopeguard:gmail-credential").decode("utf-8")
    except (ValueError, TypeError, UnicodeDecodeError) as exc:
        raise ValidationError("Gmail credential envelope is invalid") from exc


def _history_is_newer(candidate: str, current: str | None) -> bool:
    if current is None:
        return True
    try:
        return int(candidate) > int(current)
    except ValueError:
        return candidate != current


def _context(connection: IntegrationConnection, *, correlation_id: UUID | None = None) -> TrustedContext:
    return TrustedContext(
        tenant_id=connection.tenant_id,
        subject=f"gmail:{connection.provider_account_id}",
        email=connection.account_email,
        email_verified=True,
        correlation_id=correlation_id or uuid4(),
    )


def _require_google_setting(name: str, message: str) -> str:
    value = str(getattr(get_settings(), name, "") or "").strip()
    if not value:
        raise ConflictError(message)
    return value


def start_gmail_oauth(
    session: Session,
    context: TrustedContext,
    *,
    redirect_uri: str | None = None,
    expected_account_id: str | None = None,
) -> GmailOAuthStart:
    if not context.email_verified:
        raise ValidationError("A verified owner is required to connect Gmail")
    settings = get_settings()
    client_id = str(getattr(settings, "gmail_client_id", "") or "").strip()
    if not client_id:
        if settings.environment == "development":
            client_id = "scopeguard-development-gmail-client"
        else:
            raise ConflictError("Gmail OAuth client is not configured")
    callback_uri = str(redirect_uri or getattr(settings, "gmail_redirect_uri", "") or "").strip()
    if not callback_uri:
        raise ConflictError("Gmail OAuth redirect URI is not configured")
    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(48)
    row = OAuthSession(
        tenant_id=context.tenant_id,
        provider="gmail",
        state_hash=_hash(state),
        code_verifier_ciphertext=_seal(code_verifier),
        redirect_uri=callback_uri,
        expected_account_id=expected_account_id,
        expires_at=utc_now() + timedelta(minutes=10),
    )
    session.add(row)
    session.flush()
    authorization_url = f"{settings.gmail_authorization_url}?" + urlencode(
        {
            "client_id": client_id,
            "redirect_uri": callback_uri,
            "response_type": "code",
            "scope": (
                "openid https://www.googleapis.com/auth/userinfo.email "
                "https://www.googleapis.com/auth/gmail.readonly "
                "https://www.googleapis.com/auth/gmail.send"
            ),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
            "code_challenge": _pkce_challenge(code_verifier),
            "code_challenge_method": "S256",
        }
    )
    return GmailOAuthStart(state=state, code_verifier=code_verifier, authorization_url=authorization_url)


def _load_oauth_session(session: Session, *, state: str, tenant_id: UUID | None = None) -> OAuthSession:
    statement = select(OAuthSession).where(
        OAuthSession.provider == "gmail",
        OAuthSession.state_hash == _hash(state),
    )
    if tenant_id is not None:
        statement = statement.where(OAuthSession.tenant_id == tenant_id)
    oauth = session.scalar(statement.with_for_update())
    if oauth is None or oauth.consumed_at is not None or _utc(oauth.expires_at) <= utc_now():
        raise ValidationError("Gmail OAuth state is invalid or expired")
    return oauth


def _finish_gmail_oauth(
    session: Session,
    *,
    tenant_id: UUID,
    oauth: OAuthSession,
    provider_account_id: str,
    account_email: str,
    access_token: str,
    refresh_token: str | None,
) -> IntegrationConnection:
    provider_account_id = provider_account_id.strip()
    account_email = account_email.strip().casefold()
    if not provider_account_id or not account_email or not access_token:
        raise ValidationError("Gmail callback identity or credentials are incomplete")
    if oauth.expected_account_id and oauth.expected_account_id != provider_account_id:
        raise ConflictError("Gmail account does not match the authorized account")
    oauth.consumed_at = utc_now()
    connection = session.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.tenant_id == tenant_id,
            IntegrationConnection.provider == "gmail",
            IntegrationConnection.provider_account_id == provider_account_id,
        ).with_for_update()
    )
    if connection is None:
        connection = IntegrationConnection(
            tenant_id=tenant_id,
            provider="gmail",
            provider_account_id=provider_account_id,
            account_email=account_email,
        )
        session.add(connection)
        session.flush()
    elif connection.account_email != account_email and connection.status == "CONNECTED":
        raise ConflictError("Gmail account identity changed")
    if not refresh_token and connection.credential_ciphertext:
        try:
            refresh_token = str(json.loads(_open(connection.credential_ciphertext)).get("refresh_token") or "")
        except (TypeError, ValueError, ValidationError):
            refresh_token = ""
    connection.account_email = account_email
    connection.status = "CONNECTED"
    connection.credential_ciphertext = _seal(json.dumps({"access_token": access_token, "refresh_token": refresh_token or ""}))
    connection.credential_version += 1
    connection.last_error = None
    connection.row_version += 1
    sync = session.scalar(select(MailboxSync).where(MailboxSync.connection_id == connection.id).with_for_update())
    initial_backfill = sync is None or connection.committed_history_id is None
    if sync is None:
        sync = MailboxSync(tenant_id=tenant_id, connection_id=connection.id)
        session.add(sync)
    else:
        sync.status = "IDLE"
        sync.row_version += 1
    session.flush()
    schedule_gmail_sync(
        session,
        _context(connection),
        connection_id=connection.id,
        initial_backfill=initial_backfill,
    )
    return connection


def complete_gmail_oauth(
    session: Session,
    context: TrustedContext,
    *,
    state: str,
    code: str,
    provider_account_id: str,
    account_email: str,
    access_token: str,
    refresh_token: str | None = None,
    code_verifier: str,
) -> IntegrationConnection:
    if not state or not code or not provider_account_id or not account_email:
        raise ValidationError("Gmail callback is incomplete")
    oauth = _load_oauth_session(session, state=state, tenant_id=context.tenant_id)
    if oauth.code_verifier_ciphertext is None or not hmac.compare_digest(_open(oauth.code_verifier_ciphertext), code_verifier):
        raise ValidationError("Gmail PKCE verifier is invalid")
    return _finish_gmail_oauth(
        session,
        tenant_id=context.tenant_id,
        oauth=oauth,
        provider_account_id=provider_account_id,
        account_email=account_email,
        access_token=access_token,
        refresh_token=refresh_token,
    )


def _google_token_exchange(*, code: str, code_verifier: str, redirect_uri: str) -> tuple[str, str | None]:
    client_id = _require_google_setting("gmail_client_id", "Gmail OAuth client is not configured")
    client_secret = _require_google_setting("gmail_client_secret", "Gmail OAuth client secret is not configured")
    token_url = str(getattr(get_settings(), "gmail_token_url", "https://oauth2.googleapis.com/token"))
    try:
        response = httpx.post(
            token_url,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
            timeout=10.0,
        )
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ValidationError("Gmail OAuth token exchange failed") from exc
    if response.status_code >= 400 or not isinstance(body, dict):
        raise ValidationError("Gmail OAuth token exchange failed")
    access_token = str(body.get("access_token") or "")
    if not access_token:
        raise ValidationError("Gmail OAuth response did not include an access token")
    refresh_token = str(body.get("refresh_token") or "") or None
    return access_token, refresh_token


def _google_identity(access_token: str) -> tuple[str, str]:
    userinfo_url = str(getattr(get_settings(), "gmail_userinfo_url", "https://openidconnect.googleapis.com/v1/userinfo"))
    try:
        response = httpx.get(userinfo_url, headers={"Authorization": f"Bearer {access_token}"}, timeout=10.0)
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ValidationError("Gmail account identity lookup failed") from exc
    if response.status_code >= 400 or not isinstance(body, dict):
        raise ValidationError("Gmail account identity lookup failed")
    if body.get("email_verified") is False:
        raise ValidationError("Gmail account email is not verified")
    account_id = str(body.get("sub") or "").strip()
    email = str(body.get("email") or "").strip().casefold()
    if not account_id or not email:
        raise ValidationError("Gmail account identity is incomplete")
    return account_id, email


def complete_gmail_oauth_callback(session: Session, *, state: str, code: str) -> IntegrationConnection:
    if not state or not code:
        raise ValidationError("Gmail callback is incomplete")
    oauth = _load_oauth_session(session, state=state)
    if oauth.code_verifier_ciphertext is None:
        raise ValidationError("Gmail PKCE verifier is missing")
    code_verifier = _open(oauth.code_verifier_ciphertext)
    access_token, refresh_token = _google_token_exchange(code=code, code_verifier=code_verifier, redirect_uri=oauth.redirect_uri)
    provider_account_id, account_email = _google_identity(access_token)
    return _finish_gmail_oauth(
        session,
        tenant_id=oauth.tenant_id,
        oauth=oauth,
        provider_account_id=provider_account_id,
        account_email=account_email,
        access_token=access_token,
        refresh_token=refresh_token,
    )

def get_connection(session: Session, context: TrustedContext, connection_id: UUID) -> IntegrationConnection:
    connection = session.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.id == connection_id,
            IntegrationConnection.tenant_id == context.tenant_id,
        )
    )
    if connection is None:
        raise NotFoundError("Gmail connection was not found")
    return connection


def disconnect_gmail(session: Session, context: TrustedContext, *, connection_id: UUID) -> IntegrationConnection:
    connection = session.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.id == connection_id,
            IntegrationConnection.tenant_id == context.tenant_id,
        ).with_for_update()
    )
    if connection is None:
        raise NotFoundError("Gmail connection was not found")
    has_watch_to_stop = bool(connection.watch_id and connection.credential_ciphertext)
    connection.status = "DISCONNECTED"
    if not has_watch_to_stop:
        connection.credential_ciphertext = None
        connection.credential_version += 1
    connection.row_version += 1
    sync = session.scalar(select(MailboxSync).where(MailboxSync.connection_id == connection.id).with_for_update())
    if sync is not None:
        sync.status = "PAUSED"
        sync.row_version += 1
    project_ids = set(session.scalars(select(IntegrationBinding.project_id).where(IntegrationBinding.connection_id == connection.id, IntegrationBinding.tenant_id == context.tenant_id)).all())
    actions = session.scalars(
        select(ExternalAction).where(
            ExternalAction.tenant_id == context.tenant_id,
            ExternalAction.provider == "gmail",
            ExternalAction.state.in_(( "READY", "RETRY_WAIT")),
        ).with_for_update()
    ).all()
    for action in actions:
        if action.project_id not in project_ids:
            continue
        cancel_action(session, action_id=action.id)
    sync_jobs = session.scalars(
        select(Job).where(Job.tenant_id == context.tenant_id, Job.kind.like("gmail.%"), Job.state.in_(("QUEUED", "RETRY_WAIT")))
    ).all()
    for job in sync_jobs:
        if str(job.payload_ref.get("connection_id") or "") == str(connection.id):
            job.state = "CANCELLED"
            job.last_error = "gmail_connection_disconnected"
    if has_watch_to_stop and not any(
        job.kind == "gmail.watch_stop"
        and job.state in {"QUEUED", "RUNNING", "RETRY_WAIT"}
        and str(job.payload_ref.get("connection_id") or "") == str(connection.id)
        for job in sync_jobs
    ):
        enqueue_job(
            session,
            tenant_id=connection.tenant_id,
            project_id=None,
            kind="gmail.watch_stop",
            payload_ref={"connection_id": str(connection.id)},
            correlation_id=context.correlation_id,
        )
    session.flush()
    return connection

def read_gmail_health(session: Session, context: TrustedContext) -> list[dict[str, object]]:
    rows = session.scalars(
        select(IntegrationConnection).where(
            IntegrationConnection.tenant_id == context.tenant_id,
            IntegrationConnection.provider == "gmail",
        ).order_by(IntegrationConnection.created_at.desc())
    ).all()
    now = utc_now()
    result: list[dict[str, object]] = []
    for connection in rows:
        sync = session.scalar(select(MailboxSync).where(MailboxSync.connection_id == connection.id))
        watch_warning = connection.watch_expiry is not None and _utc(connection.watch_expiry) <= now + timedelta(hours=24)
        stale_warning = connection.last_success_at is None or _utc(connection.last_success_at) <= now - timedelta(minutes=30)
        result.append({
            "id": connection.id,
            "provider": connection.provider,
            "provider_account_id": connection.provider_account_id,
            "account_email": connection.account_email,
            "status": connection.status,
            "committed_history_id": connection.committed_history_id,
            "watch_expiry": connection.watch_expiry,
            "last_success_at": connection.last_success_at,
            "coverage_cutoff": connection.coverage_cutoff,
            "last_error": connection.last_error,
            "sync_status": sync.status if sync else "IDLE",
            "gap_detected_at": sync.gap_detected_at if sync else None,
            "gap_reason": sync.gap_reason if sync else None,
            "watch_expiry_warning": watch_warning,
            "stale_sync_warning": stale_warning,
        })
    return result


def normalize_gmail_message(payload: dict[str, Any]) -> NormalizedGmailMessage | None:
    message_id = str(payload.get("id", "")).strip()
    thread_id = str(payload.get("threadId", "")).strip()
    if not message_id or not thread_id:
        raise ValidationError("Gmail message identity is incomplete")
    labels = tuple(sorted({str(label).upper() for label in payload.get("labelIds", [])}))
    headers = {str(item.get("name", "")).lower(): str(item.get("value", "")) for item in payload.get("headers", []) if isinstance(item, dict)}
    if {"DRAFT", "SENT"} & set(labels):
        return None
    if headers.get("auto-submitted", "").lower() not in {"", "no"}:
        return None
    sender = headers.get("from")
    subject = headers.get("subject") or None
    snippet = " ".join(str(payload.get("snippet") or "").split())[:2000]
    occurred_value = payload.get("internalDate")
    try:
        occurred_at = datetime.fromtimestamp(int(occurred_value) / 1000, tz=UTC) if occurred_value else utc_now()
    except (TypeError, ValueError, OSError) as exc:
        raise ValidationError("Gmail message timestamp is invalid") from exc
    source_version = str(payload.get("historyId") or payload.get("etag") or "unknown")
    content_ref = str(payload.get("contentRef") or f"gmail://messages/{message_id}")
    return NormalizedGmailMessage(message_id, thread_id, source_version, sender, occurred_at, content_ref, labels, subject, snippet)


def accept_gmail_push(
    session: Session,
    *,
    provider_account_id: str,
    watch_id: str,
    history_id: str,
    delivery_id: str,
    payload_hash: str,
    occurred_at: datetime,
    verification_token: str,
) -> ExternalEvent:
    if any(len(value) == 0 or len(value) > MAX_PUSH_ID_LENGTH for value in (provider_account_id, watch_id, history_id, delivery_id)):
        raise ValidationError("Gmail push identity is invalid")
    settings = get_settings()
    expected_secret = getattr(settings, "gmail_push_verification_secret", "") or (settings.capability_encryption_key if settings.environment == "development" else "")
    expected = hmac.new(expected_secret.encode(), f"{provider_account_id}:{watch_id}".encode(), hashlib.sha256).hexdigest() if expected_secret else ""
    if not expected_secret or not hmac.compare_digest(expected, verification_token):
        raise ValidationError("Gmail push identity could not be verified")
    connection = session.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.provider == "gmail",
            IntegrationConnection.provider_account_id == provider_account_id,
            IntegrationConnection.watch_id == watch_id,
            IntegrationConnection.status == "CONNECTED",
        ).with_for_update()
    )
    if connection is None:
        raise NotFoundError("Gmail push connection is not active")
    context = _context(connection)
    event = ingest_external_event(
        session, context, provider="gmail", environment=settings.environment,
        provider_event_id=delivery_id, payload_hash=payload_hash,
        occurred_at=occurred_at, connection_id=connection.id,
    )
    enqueue_job(
        session, tenant_id=connection.tenant_id, project_id=None, kind="gmail.history_sync",
        payload_ref={"connection_id": str(connection.id), "history_id": history_id, "external_event_id": str(event.id)},
        correlation_id=event.correlation_id,
    )
    session.flush()
    return event


def process_history_page(
    session: Session,
    context: TrustedContext,
    *,
    connection_id: UUID,
    history_id: str,
    next_history_id: str | None,
    messages: list[dict[str, Any]],
    mode: str = "INCREMENTAL",
    now: datetime | None = None,
) -> MailboxSync:
    connection = session.scalar(select(IntegrationConnection).where(IntegrationConnection.id == connection_id, IntegrationConnection.tenant_id == context.tenant_id).with_for_update())
    if connection is None or connection.status != "CONNECTED":
        raise ConflictError("Gmail connection is not eligible for sync")
    if len(messages) > MAX_HISTORY_PAGE:
        raise ValidationError("Gmail history page exceeds the processing bound")
    sync = session.scalar(select(MailboxSync).where(MailboxSync.connection_id == connection.id).with_for_update())
    if sync is None:
        raise ConflictError("Mailbox sync checkpoint is unavailable")
    sync.status = "RUNNING"
    for raw in messages:
        normalized = normalize_gmail_message(raw)
        if normalized is None:
            continue
        event = ingest_external_event(
            session, context, provider="gmail", environment=get_settings().environment,
            provider_event_id=normalized.provider_message_id,
            payload_hash=_hash(str(raw)),
            occurred_at=normalized.occurred_at, connection_id=connection.id,
        )
        request_summary = "\n\n".join(
            item for item in (normalized.subject, normalized.snippet) if item
        )[:4000] or f"Gmail message {normalized.provider_message_id}"
        result = route_external_event(
            session, context, external_event_id=event.id,
            resource_type="message", resource_id=normalized.provider_message_id,
            source_version=normalized.source_version, content_ref=normalized.content_ref,
            occurred_at=normalized.occurred_at, sender=normalized.sender, thread_id=normalized.thread_id,
            request_summary=request_summary,
        )
        if mode == "INCREMENTAL" and isinstance(result, CommunicationEvent):
            from services.contracts.requests import create_request_from_communication

            create_request_from_communication(
                session,
                context,
                communication=result,
                summary=request_summary,
            )
    current = now or utc_now()
    if next_history_id is not None and _history_is_newer(next_history_id, connection.committed_history_id):
        connection.committed_history_id = next_history_id
        sync.committed_history_id = next_history_id
    sync.status = "IDLE"
    sync.mode = mode
    sync.last_success_at = current
    connection.last_success_at = current
    connection.last_error = None
    connection.row_version += 1
    sync.row_version += 1
    session.flush()
    return sync


def mark_history_gap(
    session: Session,
    context: TrustedContext,
    *,
    connection_id: UUID,
    reason: str,
    now: datetime | None = None,
) -> MailboxSync:
    connection = session.scalar(select(IntegrationConnection).where(IntegrationConnection.id == connection_id, IntegrationConnection.tenant_id == context.tenant_id).with_for_update())
    sync = session.scalar(select(MailboxSync).where(MailboxSync.connection_id == connection_id, MailboxSync.tenant_id == context.tenant_id).with_for_update())
    if connection is None or sync is None:
        raise NotFoundError("Mailbox sync was not found")
    current = now or utc_now()
    sync.status = "GAP_DETECTED"
    sync.gap_detected_at = current
    sync.gap_reason = reason[:500]
    sync.row_version += 1
    connection.status = "PAUSED"
    connection.last_error = reason[:500]
    connection.row_version += 1
    enqueue_job(session, tenant_id=context.tenant_id, kind="gmail.initial_backfill", payload_ref={"connection_id": str(connection.id), "reason": reason}, correlation_id=context.correlation_id)
    session.flush()
    return sync


def renew_gmail_watch(session: Session, context: TrustedContext, *, connection_id: UUID, watch_id: str, expires_at: datetime) -> IntegrationConnection:
    connection = session.scalar(select(IntegrationConnection).where(IntegrationConnection.id == connection_id, IntegrationConnection.tenant_id == context.tenant_id).with_for_update())
    if connection is None or connection.status != "CONNECTED":
        raise ConflictError("Gmail connection is not eligible for watch renewal")
    if _utc(expires_at) <= utc_now():
        raise ValidationError("Gmail watch expiry must be in the future")
    connection.watch_id = watch_id
    connection.watch_expiry = expires_at
    connection.row_version += 1
    session.flush()
    return connection


def schedule_gmail_sync(session: Session, context: TrustedContext, *, connection_id: UUID, initial_backfill: bool = False) -> MailboxSync:
    connection = session.scalar(select(IntegrationConnection).where(IntegrationConnection.id == connection_id, IntegrationConnection.tenant_id == context.tenant_id).with_for_update())
    if connection is None or connection.status != "CONNECTED":
        raise ConflictError("Gmail connection is not eligible for synchronization")
    sync = session.scalar(select(MailboxSync).where(MailboxSync.connection_id == connection.id).with_for_update())
    if sync is None:
        raise ConflictError("Mailbox sync checkpoint is unavailable")
    now = utc_now()
    sync.status = "RUNNING"
    sync.mode = "INITIAL_BACKFILL" if initial_backfill else "INCREMENTAL"
    if initial_backfill:
        sync.coverage_start = now - timedelta(days=HISTORY_RETENTION_DAYS)
        sync.coverage_end = now
        connection.coverage_cutoff = sync.coverage_start
    sync.row_version += 1
    enqueue_job(session, tenant_id=context.tenant_id, kind="gmail.initial_backfill" if initial_backfill else "gmail.history_sync", payload_ref={"connection_id": str(connection.id), "mode": sync.mode}, correlation_id=context.correlation_id)
    session.flush()
    return sync


class GmailHistoryGap(ConflictError):
    """Gmail no longer retains the requested history cursor."""


class GmailProviderRetryable(RuntimeError):
    """A bounded provider read/write can be retried safely."""


@dataclass(frozen=True, slots=True)
class GmailHistoryPage:
    messages: list[dict[str, Any]]
    history_id: str | None
    next_page_token: str | None


def _credential_values(connection: IntegrationConnection) -> dict[str, str]:
    if not connection.credential_ciphertext:
        raise ConflictError("Gmail credentials are unavailable")
    try:
        payload = json.loads(_open(connection.credential_ciphertext))
    except (TypeError, ValueError, ValidationError) as exc:
        raise ValidationError("Gmail credentials are invalid") from exc
    if not isinstance(payload, dict) or not payload.get("access_token"):
        raise ConflictError("Gmail access token is unavailable")
    return {str(key): str(value or "") for key, value in payload.items()}


def _mark_gmail_reauth(connection: IntegrationConnection, reason: str) -> None:
    connection.status = "REAUTH_REQUIRED"
    connection.last_error = reason[:500]
    connection.row_version += 1


def refresh_gmail_access_token(
    session: Session, context: TrustedContext, *, connection_id: UUID
) -> IntegrationConnection:
    connection = session.scalar(
        select(IntegrationConnection)
        .where(
            IntegrationConnection.id == connection_id,
            IntegrationConnection.tenant_id == context.tenant_id,
        )
        .with_for_update()
    )
    if connection is None:
        raise NotFoundError("Gmail connection was not found")
    credentials = _credential_values(connection)
    refresh_token = credentials.get("refresh_token", "")
    if not refresh_token:
        _mark_gmail_reauth(connection, "refresh_token_missing")
        raise ConflictError("Gmail reauthorization is required")
    client_id = _require_google_setting("gmail_client_id", "Gmail OAuth client is not configured")
    client_secret = _require_google_setting("gmail_client_secret", "Gmail OAuth client secret is not configured")
    token_url = str(getattr(get_settings(), "gmail_token_url", "https://oauth2.googleapis.com/token"))
    try:
        response = httpx.post(
            token_url,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=10.0,
        )
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise GmailProviderRetryable("Gmail token refresh failed") from exc
    if response.status_code >= 400:
        if response.status_code in {400, 401, 403}:
            _mark_gmail_reauth(connection, "refresh_token_rejected")
            raise ConflictError("Gmail reauthorization is required")
        raise GmailProviderRetryable("Gmail token refresh was throttled")
    access_token = str(body.get("access_token") or "") if isinstance(body, dict) else ""
    if not access_token:
        raise GmailProviderRetryable("Gmail token refresh returned no access token")
    connection.credential_ciphertext = _seal(
        json.dumps({"access_token": access_token, "refresh_token": refresh_token})
    )
    connection.credential_version += 1
    connection.last_error = None
    connection.row_version += 1
    session.flush()
    return connection


def _gmail_request(
    *,
    method: str,
    url: str,
    access_token: str,
    params: Mapping[str, str | list[str]] | None = None,
    json_body: dict[str, object] | None = None,
) -> httpx.Response:
    try:
        return httpx.request(
            method,
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            json=json_body,
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        raise GmailProviderRetryable("Gmail provider request failed") from exc


def _gmail_api_url(path: str) -> str:
    base = str(getattr(get_settings(), "gmail_api_base_url", "https://gmail.googleapis.com/gmail/v1")).rstrip("/")
    return f"{base}/{path.lstrip('/')}"


def _connection_for_provider(
    session: Session, context: TrustedContext, connection_id: UUID
) -> IntegrationConnection:
    connection = session.scalar(
        select(IntegrationConnection)
        .where(
            IntegrationConnection.id == connection_id,
            IntegrationConnection.tenant_id == context.tenant_id,
        )
    )
    if connection is None or connection.provider != "gmail":
        raise NotFoundError("Gmail connection was not found")
    if connection.status != "CONNECTED":
        raise ConflictError("Gmail connection is not connected")
    return connection


def _provider_response(response: httpx.Response, *, operation: str) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise GmailProviderRetryable(f"Gmail {operation} returned invalid data") from exc
    if response.status_code == 404 and operation == "history":
        raise GmailHistoryGap("Gmail history cursor is no longer available")
    if response.status_code == 429 or response.status_code >= 500:
        raise GmailProviderRetryable(f"Gmail {operation} is temporarily unavailable")
    if response.status_code >= 400 or not isinstance(body, dict):
        raise ConflictError(f"Gmail {operation} was rejected")
    return body


def fetch_gmail_history_page(
    session: Session,
    context: TrustedContext,
    *,
    connection_id: UUID,
    history_id: str,
    page_token: str | None = None,
) -> GmailHistoryPage:
    connection = _connection_for_provider(session, context, connection_id)
    credentials = _credential_values(connection)
    params = {
        "startHistoryId": history_id,
        "historyTypes": "messageAdded",
        "maxResults": str(MAX_HISTORY_PAGE),
    }
    if page_token:
        params["pageToken"] = page_token
    response = _gmail_request(
        method="GET",
        url=_gmail_api_url("users/me/history"),
        access_token=credentials["access_token"],
        params=params,
    )
    if response.status_code == 401:
        connection = refresh_gmail_access_token(session, context, connection_id=connection.id)
        credentials = _credential_values(connection)
        response = _gmail_request(
            method="GET",
            url=_gmail_api_url("users/me/history"),
            access_token=credentials["access_token"],
            params=params,
        )
    body = _provider_response(response, operation="history")
    messages: list[dict[str, Any]] = []
    seen: set[str] = set()
    for history in body.get("history", []):
        if not isinstance(history, dict):
            continue
        for added in history.get("messagesAdded", []):
            if not isinstance(added, dict) or not isinstance(added.get("message"), dict):
                continue
            message_ref = added["message"]
            message_id = str(message_ref.get("id") or "")
            if not message_id or message_id in seen:
                continue
            seen.add(message_id)
            messages.append(
                _fetch_message_metadata(
                    credentials["access_token"],
                    message_id,
                    history_id=str(body.get("historyId") or history_id),
                )
            )
    return GmailHistoryPage(
        messages=messages,
        history_id=str(body.get("historyId") or history_id),
        next_page_token=str(body["nextPageToken"]) if body.get("nextPageToken") else None,
    )


def sync_gmail_history_page(
    session: Session,
    context: TrustedContext,
    *,
    connection_id: UUID,
    history_id: str,
    page_token: str | None = None,
    now: datetime | None = None,
) -> GmailHistoryPage:
    try:
        page = fetch_gmail_history_page(
            session,
            context,
            connection_id=connection_id,
            history_id=history_id,
            page_token=page_token,
        )
    except GmailHistoryGap:
        mark_history_gap(
            session,
            context,
            connection_id=connection_id,
            reason="gmail_history_404",
            now=now,
        )
        raise
    process_history_page(
        session,
        context,
        connection_id=connection_id,
        history_id=history_id,
        next_history_id=page.history_id if page.next_page_token is None else None,
        messages=page.messages,
        now=now,
    )
    return page


def start_gmail_watch(
    session: Session, context: TrustedContext, *, connection_id: UUID
) -> IntegrationConnection:
    connection = _connection_for_provider(session, context, connection_id)
    topic = str(getattr(get_settings(), "gmail_pubsub_topic", "") or "").strip()
    if not topic:
        raise ConflictError("Gmail Pub/Sub topic is not configured")
    credentials = _credential_values(connection)
    response = _gmail_request(
        method="POST",
        url=_gmail_api_url("users/me/watch"),
        access_token=credentials["access_token"],
        json_body={"topicName": topic, "labelIds": ["INBOX"], "labelFilterBehavior": "INCLUDE"},
    )
    if response.status_code == 401:
        connection = refresh_gmail_access_token(session, context, connection_id=connection.id)
        credentials = _credential_values(connection)
        response = _gmail_request(
            method="POST",
            url=_gmail_api_url("users/me/watch"),
            access_token=credentials["access_token"],
            json_body={"topicName": topic, "labelIds": ["INBOX"], "labelFilterBehavior": "INCLUDE"},
        )
    body = _provider_response(response, operation="watch")
    history_id = str(body.get("historyId") or "")
    expiration_raw = str(body.get("expiration") or "")
    if not history_id or not expiration_raw:
        raise GmailProviderRetryable("Gmail watch response is incomplete")
    try:
        expires_at = datetime.fromtimestamp(int(expiration_raw) / 1000, tz=UTC)
    except (TypeError, ValueError, OSError) as exc:
        raise GmailProviderRetryable("Gmail watch expiry is invalid") from exc
    watch_id = str(body.get("watchId") or _hash(f"{connection.id}:{history_id}:{expiration_raw}")[:64])
    if connection.committed_history_id is None:
        connection.committed_history_id = history_id
    return renew_gmail_watch(
        session,
        context,
        connection_id=connection.id,
        watch_id=watch_id,
        expires_at=expires_at,
    )


def stop_gmail_watch(
    session: Session, context: TrustedContext, *, connection_id: UUID
) -> IntegrationConnection:
    connection = session.scalar(
        select(IntegrationConnection)
        .where(
            IntegrationConnection.id == connection_id,
            IntegrationConnection.tenant_id == context.tenant_id,
        )
        .with_for_update()
    )
    if connection is None or connection.provider != "gmail":
        raise NotFoundError("Gmail connection was not found")
    if connection.status not in {"CONNECTED", "DISCONNECTED"}:
        raise ConflictError("Gmail connection is not eligible for watch cleanup")
    if not connection.watch_id or not connection.credential_ciphertext:
        connection.watch_id = None
        connection.watch_expiry = None
        connection.credential_ciphertext = None
        connection.credential_version += 1
        connection.row_version += 1
        session.flush()
        return connection
    credentials = _credential_values(connection)
    response = _gmail_request(
        method="POST",
        url=_gmail_api_url("users/me/stop"),
        access_token=credentials["access_token"],
    )
    if response.status_code not in {200, 204, 404, 401, 403}:
        _provider_response(response, operation="watch_stop")
    connection.watch_id = None
    connection.watch_expiry = None
    connection.credential_ciphertext = None
    connection.credential_version += 1
    connection.row_version += 1
    session.flush()
    return connection


def _connected_send_connection(session: Session, action: ExternalAction) -> IntegrationConnection:
    account_id = str(action.approved_payload.get("provider_account_id") or "").strip()
    statement = select(IntegrationConnection).where(
        IntegrationConnection.tenant_id == action.tenant_id,
        IntegrationConnection.provider == "gmail",
        IntegrationConnection.status == "CONNECTED",
    )
    if account_id:
        statement = statement.where(IntegrationConnection.provider_account_id == account_id)
    connections = session.scalars(statement.order_by(IntegrationConnection.created_at.desc())).all()
    if len(connections) != 1:
        raise ConflictError("Exactly one connected Gmail account is required for this send")
    return connections[0]


def _gmail_raw_message(payload: dict[str, object], *, sender: str) -> str:
    from email.message import EmailMessage
    from email.policy import SMTP

    recipient = str(payload.get("recipient") or "").strip()
    subject = str(payload.get("subject") or "").strip()
    plain = str(payload.get("plain_text_body") or "")
    html = str(payload.get("html_body") or "")
    marker = str(payload.get("marker") or "").strip()
    if not recipient or not subject or not plain or not marker:
        raise ValidationError("Approved Gmail message is incomplete")
    if payload.get("attachment_hashes"):
        raise ConflictError("Approved Gmail attachments are not materialized")
    message = EmailMessage(policy=SMTP)
    message["To"] = recipient
    message["From"] = sender
    message["Subject"] = subject
    message["X-ScopeGuard-Marker"] = marker
    message.set_content(plain)
    if html:
        message.add_alternative(html, subtype="html")
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")


def dispatch_gmail_send(session: Session, *, action_id: UUID) -> str:
    from services.change_orders.service import (
        begin_gmail_send,
        record_gmail_send_success,
        record_gmail_send_unknown,
    )
    from services.workers.durable import mark_action_retry, mark_action_review_required

    action = session.scalar(
        select(ExternalAction).where(ExternalAction.id == action_id).with_for_update()
    )
    if action is None or action.provider != "gmail" or action.operation != "send":
        raise NotFoundError("Gmail send action was not found")
    connection = _connected_send_connection(session, action)
    credentials = _credential_values(connection)
    payload = dict(action.approved_payload)
    raw = _gmail_raw_message(payload, sender=connection.account_email)
    payload = dict(begin_gmail_send(session, action_id=action.id))
    try:
        response = _gmail_request(
            method="POST",
            url=_gmail_api_url("users/me/messages/send"),
            access_token=credentials["access_token"],
            json_body={"raw": raw},
        )
    except GmailProviderRetryable as exc:
        record_gmail_send_unknown(session, action_id=action.id, reason="provider_request_ambiguous")
        raise ConflictError("Gmail send outcome is unknown") from exc
    if response.status_code == 401:
        try:
            connection = refresh_gmail_access_token(session, _context(connection), connection_id=connection.id)
            credentials = _credential_values(connection)
            response = _gmail_request(
                method="POST",
                url=_gmail_api_url("users/me/messages/send"),
                access_token=credentials["access_token"],
                json_body={"raw": raw},
            )
        except GmailProviderRetryable:
            mark_action_retry(session, action_id=action.id, error_code="gmail_refresh_retry")
            raise
    if response.status_code == 429:
        mark_action_retry(session, action_id=action.id, error_code="gmail_429")
        raise GmailProviderRetryable("Gmail send is temporarily unavailable")
    if response.status_code >= 500:
        record_gmail_send_unknown(session, action_id=action.id, reason=f"gmail_{response.status_code}")
        raise ConflictError("Gmail send outcome is unknown")
    if response.status_code >= 400:
        mark_action_review_required(session, action_id=action.id, reason="gmail_provider_rejected")
        raise ConflictError("Gmail send was rejected")
    try:
        body = response.json()
    except ValueError as exc:
        record_gmail_send_unknown(session, action_id=action.id, reason="invalid_provider_response")
        raise ConflictError("Gmail send outcome is unknown") from exc
    provider_message_id = str(body.get("id") or "") if isinstance(body, dict) else ""
    if not provider_message_id:
        record_gmail_send_unknown(session, action_id=action.id, reason="missing_provider_message_id")
        raise ConflictError("Gmail send outcome is unknown")
    record_gmail_send_success(
        session,
        action_id=action.id,
        provider_message_id=provider_message_id,
        recipient=str(payload["recipient"]),
        plain_text_body=str(payload["plain_text_body"]),
        content_hash=str(payload["content_hash"]),
    )
    return provider_message_id


send_gmail_message = dispatch_gmail_send

def accept_gmail_pubsub_push(
    session: Session,
    *,
    account_email: str,
    history_id: str,
    delivery_id: str,
    payload_hash: str,
    occurred_at: datetime,
    topic_name: str | None = None,
) -> ExternalEvent:
    """Accept a native Gmail Pub/Sub envelope after transport authentication."""
    account_email = account_email.strip().casefold()
    values = (account_email, history_id, delivery_id, payload_hash)
    if not account_email or any(len(str(value)) == 0 or len(str(value)) > MAX_PUSH_ID_LENGTH for value in values):
        raise ValidationError("Gmail Pub/Sub identity is invalid")
    if len(payload_hash) != 64 or any(character not in "0123456789abcdef" for character in payload_hash):
        raise ValidationError("Gmail Pub/Sub payload hash is invalid")
    configured_topic = str(getattr(get_settings(), "gmail_pubsub_topic", "") or "").strip()
    if configured_topic and topic_name != configured_topic:
        raise ValidationError("Gmail Pub/Sub topic is not authorized")
    connection = session.scalar(
        select(IntegrationConnection)
        .where(
            IntegrationConnection.provider == "gmail",
            IntegrationConnection.account_email == account_email,
            IntegrationConnection.status == "CONNECTED",
        )
        .with_for_update()
    )
    if connection is None:
        raise NotFoundError("Gmail Pub/Sub connection is not active")
    context = _context(connection)
    event = ingest_external_event(
        session,
        context,
        provider="gmail",
        environment=get_settings().environment,
        provider_event_id=delivery_id,
        payload_hash=payload_hash,
        occurred_at=occurred_at,
        connection_id=connection.id,
    )
    enqueue_job(
        session,
        tenant_id=connection.tenant_id,
        project_id=None,
        kind="gmail.history_sync",
        payload_ref={
            "connection_id": str(connection.id),
            "history_id": connection.committed_history_id or history_id,
            "external_event_id": str(event.id),
        },
        correlation_id=event.correlation_id,
    )
    session.flush()
    return event


def _fetch_message_metadata(
    access_token: str, message_id: str, *, history_id: str
) -> dict[str, Any]:
    response = _gmail_request(
        method="GET",
        url=_gmail_api_url(f"users/me/messages/{message_id}"),
        access_token=access_token,
        params={"format": "full"},
    )
    detail = _provider_response(response, operation="message")
    detail["historyId"] = str(detail.get("historyId") or history_id)
    payload = detail.get("payload")
    if "headers" not in detail and isinstance(payload, dict):
        detail["headers"] = payload.get("headers", [])
    return detail


def fetch_gmail_backfill_page(
    session: Session,
    context: TrustedContext,
    *,
    connection_id: UUID,
    page_token: str | None = None,
) -> GmailHistoryPage:
    connection = _connection_for_provider(session, context, connection_id)
    sync = session.scalar(select(MailboxSync).where(MailboxSync.connection_id == connection.id))
    if sync is None or sync.coverage_start is None:
        raise ConflictError("Gmail initial backfill coverage is not initialized")
    credentials = _credential_values(connection)
    params: dict[str, str | list[str]] = {
        "q": f"after:{_utc(sync.coverage_start).strftime('%Y/%m/%d')}",
        "maxResults": str(MAX_HISTORY_PAGE),
        "includeSpamTrash": "false",
    }
    if page_token:
        params["pageToken"] = page_token
    response = _gmail_request(
        method="GET",
        url=_gmail_api_url("users/me/messages"),
        access_token=credentials["access_token"],
        params=params,
    )
    if response.status_code == 401:
        connection = refresh_gmail_access_token(session, context, connection_id=connection.id)
        credentials = _credential_values(connection)
        response = _gmail_request(
            method="GET",
            url=_gmail_api_url("users/me/messages"),
            access_token=credentials["access_token"],
            params=params,
        )
    body = _provider_response(response, operation="backfill")
    messages: list[dict[str, Any]] = []
    for message_ref in body.get("messages", []):
        if not isinstance(message_ref, dict):
            continue
        message_id = str(message_ref.get("id") or "")
        if message_id:
            messages.append(_fetch_message_metadata(credentials["access_token"], message_id, history_id=connection.committed_history_id or "0"))
    return GmailHistoryPage(
        messages=messages,
        history_id=connection.committed_history_id,
        next_page_token=str(body["nextPageToken"]) if body.get("nextPageToken") else None,
    )


def run_gmail_initial_backfill_page(
    session: Session,
    context: TrustedContext,
    *,
    connection_id: UUID,
    page_token: str | None = None,
    now: datetime | None = None,
) -> GmailHistoryPage:
    connection = session.scalar(
        select(IntegrationConnection)
        .where(
            IntegrationConnection.id == connection_id,
            IntegrationConnection.tenant_id == context.tenant_id,
        )
        .with_for_update()
    )
    sync = session.scalar(select(MailboxSync).where(MailboxSync.connection_id == connection_id).with_for_update())
    if connection is None or connection.provider != "gmail":
        raise NotFoundError("Gmail connection was not found")
    if connection.status == "PAUSED" and sync is not None and sync.status == "GAP_DETECTED":
        connection.status = "CONNECTED"
        connection.last_error = None
        connection.row_version += 1
        session.flush()
    if connection.status != "CONNECTED":
        raise ConflictError("Gmail connection is not eligible for initial backfill")
    if not page_token and not connection.watch_id:
        start_gmail_watch(session, context, connection_id=connection.id)
    page = fetch_gmail_backfill_page(
        session,
        context,
        connection_id=connection.id,
        page_token=page_token,
    )
    process_history_page(
        session,
        context,
        connection_id=connection.id,
        history_id=connection.committed_history_id or "0",
        next_history_id=None,
        messages=page.messages,
        mode="INITIAL_BACKFILL",
        now=now,
    )
    if page.next_page_token:
        enqueue_job(
            session,
            tenant_id=connection.tenant_id,
            project_id=None,
            kind="gmail.initial_backfill",
            payload_ref={"connection_id": str(connection.id), "page_token": page.next_page_token},
            correlation_id=context.correlation_id,
        )
    else:
        sync = session.scalar(select(MailboxSync).where(MailboxSync.connection_id == connection.id).with_for_update())
        if sync is not None:
            sync.mode = "INCREMENTAL"
            sync.status = "IDLE"
            sync.row_version += 1
        session.flush()
    return page


def schedule_gmail_maintenance(
    session: Session, *, now: datetime | None = None
) -> int:
    current = now or utc_now()
    connections = session.scalars(
        select(IntegrationConnection).where(
            IntegrationConnection.provider == "gmail",
            IntegrationConnection.status == "CONNECTED",
        )
    ).all()
    created = 0
    for connection in connections:
        pending = session.scalars(
            select(Job).where(
                Job.tenant_id == connection.tenant_id,
                Job.kind.in_(("gmail.initial_backfill", "gmail.watch_renew", "gmail.history_sync")),
                Job.state.in_(("QUEUED", "RUNNING", "RETRY_WAIT")),
            )
        ).all()
        pending_kinds = {
            job.kind for job in pending if str(job.payload_ref.get("connection_id") or "") == str(connection.id)
        }
        sync = session.scalar(select(MailboxSync).where(MailboxSync.connection_id == connection.id))
        if sync is not None and sync.mode == "INITIAL_BACKFILL" and sync.coverage_start is None:
            if "gmail.initial_backfill" not in pending_kinds:
                schedule_gmail_sync(
                    session,
                    _context(connection),
                    connection_id=connection.id,
                    initial_backfill=True,
                )
                created += 1
            continue
        if connection.watch_expiry is None or _utc(connection.watch_expiry) <= current + timedelta(days=1):
            if "gmail.watch_renew" not in pending_kinds:
                enqueue_job(
                    session,
                    tenant_id=connection.tenant_id,
                    project_id=None,
                    kind="gmail.watch_renew",
                    payload_ref={"connection_id": str(connection.id)},
                    correlation_id=uuid4(),
                )
                created += 1
        # Pub/Sub delivery is best-effort. The one-minute worker schedule is
        # also the durable catch-up path, so always keep a history job queued
        # while a cursor exists. pending_kinds prevents duplicate jobs.
        if connection.committed_history_id:
            if "gmail.history_sync" not in pending_kinds:
                enqueue_job(
                    session,
                    tenant_id=connection.tenant_id,
                    project_id=None,
                    kind="gmail.history_sync",
                    payload_ref={
                        "connection_id": str(connection.id),
                        "history_id": connection.committed_history_id,
                    },
                    correlation_id=uuid4(),
                )
                created += 1
    session.flush()
    return created