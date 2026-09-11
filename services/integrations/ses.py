
"""Deterministic Amazon SES notification dispatch."""
from __future__ import annotations

from html import escape
from typing import Any
from uuid import UUID

import boto3  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.api.config import get_settings
from services.change_orders.service import (
    materialize_ses_notification,
    record_ses_notification_success,
    record_ses_notification_unknown,
)
from services.domain.errors import ConflictError, NotFoundError, ValidationError
from services.domain.models import ExternalAction
from services.workers.durable import (
    begin_action_dispatch,
    mark_action_retry,
    mark_action_review_required,
)


class SesProviderRetryable(RuntimeError):
    """An SES failure that is safe to retry through the durable job layer."""

def _client() -> Any:
    settings = get_settings()
    return boto3.client("sesv2", region_name=settings.aws_region)


def _message(payload: dict[str, object]) -> tuple[str, str, str, str]:
    recipient = str(payload.get("recipient") or "").strip().casefold()
    subject = str(payload.get("subject") or "").strip()
    approval_url = str(payload.get("approval_url") or "").strip()
    if not recipient or not subject or not approval_url:
        raise ValidationError("SES notification content is incomplete")
    text = f"A ScopeGuard change-order review is ready.\n\nReview it here: {approval_url}\n"
    html = (
        "<p>A ScopeGuard change-order review is ready.</p>"
        f'<p><a href="{escape(approval_url, quote=True)}">Review change order</a></p>'
    )
    return recipient, subject, text, html


def dispatch_ses_notification(session: Session, *, action_id: UUID) -> str:
    """Send one approved SES notification and persist its provider receipt."""
    action = session.scalar(
        select(ExternalAction).where(ExternalAction.id == action_id).with_for_update()
    )
    if action is None or action.provider != "ses" or action.operation != "send_change_order":
        raise NotFoundError("SES notification action was not found")
    settings = get_settings()
    sender = str(settings.ses_from_email or "").strip()
    if not sender:
        raise ConflictError("SES sender identity is not configured")
    if action.state not in {"READY", "RETRY_WAIT"}:
        raise ConflictError("SES notification is not dispatchable")
    payload = materialize_ses_notification(session, action_id=action.id)
    recipient, subject, text_body, html_body = _message(payload)
    begin_action_dispatch(session, action_id=action.id)
    request: dict[str, object] = {
        "FromEmailAddress": sender,
        "Destination": {"ToAddresses": [recipient]},
        "Content": {
            "Simple": {
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": text_body, "Charset": "UTF-8"}, "Html": {"Data": html_body, "Charset": "UTF-8"}},
            }
        },
    }
    if settings.ses_configuration_set:
        request["ConfigurationSetName"] = settings.ses_configuration_set
    try:
        response = _client().send_email(**request)
        provider_message_id = str(response.get("MessageId") or "")
        if not provider_message_id:
            raise RuntimeError("SES response did not include a message id")
    except ClientError as exc:
        error = exc.response.get("Error", {}) if isinstance(exc.response, dict) else {}
        code = str(error.get("Code") or "")
        if code in {"Throttling", "TooManyRequestsException", "ServiceUnavailableException", "RequestTimeout"}:
            mark_action_retry(session, action_id=action.id, error_code=f"ses_{code.lower()}")
            raise SesProviderRetryable("SES is temporarily unavailable") from exc
        mark_action_review_required(session, action_id=action.id, reason="ses_provider_rejected")
        raise ConflictError("SES notification was rejected") from exc
    except BotoCoreError as exc:
        record_ses_notification_unknown(session, action_id=action.id, reason=type(exc).__name__)
        raise
    except RuntimeError as exc:
        record_ses_notification_unknown(session, action_id=action.id, reason=type(exc).__name__)
        raise
    record_ses_notification_success(
        session, action_id=action.id, provider_message_id=provider_message_id
    )
    return provider_message_id


send_ses_notification = dispatch_ses_notification