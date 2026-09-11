from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from services.change_orders.service import (
    accept_client,
    assemble_change_order,
    begin_gmail_send,
    exchange_capability,
    freelancer_decide,
    materialize_ses_notification,
    read_client_review,
    record_gmail_send_success,
)
from services.domain.auth import TrustedContext
from services.domain.errors import ConflictError
from services.domain.models import (
    AnalysisDecision,
    AnalysisDraftRevision,
    Base,
    CalendarVersion,
    ChangeOrder,
    Client,
    ClientContact,
    ExternalAction,
    Notification,
    PaymentRequest,
    PreferenceVersion,
    Project,
    ProposalRevision,
    RequestRecord,
    ScopeVersion,
    User,
    WorkflowInstance,
)


@pytest.fixture
def fixture(tmp_path: Path) -> tuple[TrustedContext, sessionmaker[Session]]:
    tenant = uuid4()
    engine = create_engine("sqlite+pysqlite:///" + str(tmp_path / "phase5.db"))
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as s:
        s.add(User(id=tenant, cognito_sub="phase5-owner", verified_email="owner@example.test", timezone="UTC"))
        pref = PreferenceVersion(tenant_id=tenant, version=1, rate_minor=100000, minimum_minor=1500000, increment_minor=50000)
        s.add(pref)
        client = Client(tenant_id=tenant, name="Acme")
        s.add(client)
        s.flush()
        s.add(ClientContact(tenant_id=tenant, client_id=client.id, normalized_email="client@example.test", display_name="Client"))
        project = Project(tenant_id=tenant, client_id=client.id, name="Project", preference_version_id=pref.id, timezone="UTC")
        s.add(project)
        s.flush()
        s.add(CalendarVersion(tenant_id=tenant, project_id=project.id, version=1, weekdays=[0, 1, 2, 3, 4], holiday_dates=[], confirmed_daily_capacity_hours=7))
        s.flush()
        calendar = s.scalar(select(CalendarVersion).where(CalendarVersion.project_id == project.id))
        project.calendar_version_id = calendar.id
        scope = ScopeVersion(tenant_id=tenant, project_id=project.id, version=1, confirmation_actor="owner", content_hash="b" * 64)
        s.add(scope)
        s.flush()
        project.current_scope_version_id = scope.id
        req = RequestRecord(tenant_id=tenant, project_id=project.id, summary="Add export")
        s.add(req)
        s.flush()
        workflow = WorkflowInstance(tenant_id=tenant, project_id=project.id, workflow_key="phase5-workflow", input_digest="c" * 64, request_id=req.id)
        s.add(workflow)
        s.flush()
        decision = AnalysisDecision(tenant_id=tenant, project_id=project.id, request_id=req.id, workflow_id=workflow.id, kind="PROPOSAL_REVIEW", title="Export", summary="Additional export", safe_details={})
        s.add(decision)
        s.flush()
        s.add(AnalysisDraftRevision(tenant_id=tenant, project_id=project.id, request_id=req.id, workflow_id=workflow.id, decision_id=decision.id, revision=1, content_hash="d" * 64, payload={
            "title": "Export", "requested_change": "Add export", "deliverables": ["CSV export"], "exclusions": [], "assumptions": [],
            "client_explanation": "This is additional work.", "subject": "Scope change", "plain_text_body": "Please approve.",
            "html_body": "<p>Please approve.</p>", "recipient_email": "client@example.test", "evidence_reference_ids": [str(uuid4())],
            "terms": {"total_minor": 1500000, "tax_minor": 0, "currency": "INR", "preference_version_id": str(pref.id)}
        }))
    return TrustedContext(tenant_id=tenant, subject="phase5-owner", email="owner@example.test", email_verified=True, correlation_id=uuid4()), factory


def test_exact_approval_send_and_acceptance(fixture: tuple[TrustedContext, sessionmaker[Session]]) -> None:
    context, factory = fixture
    with factory.begin() as s:
        decision_id = s.scalar(select(AnalysisDecision.id))
        order = assemble_change_order(s, context, decision_id=decision_id)
        revision = s.get(ProposalRevision, order.current_revision_id)
        assert order.status == "AWAITING_FREELANCER_APPROVAL"
        from services.change_orders.service import approve_freelancer
        with pytest.raises(ConflictError):
            approve_freelancer(s, context, change_order_id=order.id, expected_row_version=order.row_version, revision_id=revision.id, content_hash="0" * 64)
        approve_freelancer(s, context, change_order_id=order.id, expected_row_version=order.row_version, revision_id=revision.id, content_hash=revision.canonical_artifact_hash)
        from services.change_orders.service import _unprotect
        token = _unprotect(revision.token_ciphertext)
    with factory.begin() as s:
        action = s.scalar(select(ExternalAction).where(ExternalAction.provider == "gmail"))
        payload = begin_gmail_send(s, action_id=action.id)
        assert payload["plain_text_body"] == revision.plain_text_body
    with factory.begin() as s:
        action = s.scalar(select(ExternalAction).where(ExternalAction.provider == "gmail"))
        record_gmail_send_success(s, action_id=action.id, provider_message_id="gmail-1", recipient=revision.recipient_email, plain_text_body=revision.plain_text_body, content_hash=revision.canonical_artifact_hash)
        credentials = exchange_capability(s, token=token)
        assert read_client_review(s, session_token=credentials.session_token)["revision_id"] == str(revision.id)
        result = accept_client(s, session_token=credentials.session_token, csrf_token=credentials.csrf_token, change_order_id=order.id, expected_row_version=4, revision_id=revision.id, content_hash=revision.canonical_artifact_hash, client_idempotency_key="client-1")
        assert result.change_order.status == "CLIENT_APPROVED"
        replay = accept_client(s, session_token=credentials.session_token, csrf_token=credentials.csrf_token, change_order_id=order.id, expected_row_version=999, revision_id=revision.id, content_hash=revision.canonical_artifact_hash, client_idempotency_key="client-1")
        assert replay.payment_request.id == result.payment_request.id
    with factory() as s:
        assert s.scalar(select(PaymentRequest)) is not None
        assert s.scalar(select(ChangeOrder)).status == "CLIENT_APPROVED"
        with pytest.raises(ConflictError):
            accept_client(s, session_token=credentials.session_token, csrf_token=credentials.csrf_token, change_order_id=order.id, expected_row_version=4, revision_id=revision.id, content_hash=revision.canonical_artifact_hash, client_idempotency_key="client-2")


def test_phase5_decisions_refresh_and_encrypted_notification(fixture: tuple[TrustedContext, sessionmaker[Session]]) -> None:
    context, factory = fixture
    with factory.begin() as s:
        decision_id = s.scalar(select(AnalysisDecision.id))
        order = assemble_change_order(s, context, decision_id=decision_id)
        ses_action = s.scalar(select(ExternalAction).where(ExternalAction.provider == "ses"))
        assert ses_action is not None
        materialized = materialize_ses_notification(s, action_id=ses_action.id)
        assert isinstance(materialized["approval_url"], str) and "#t=" in materialized["approval_url"]
        assert revision_token_not_in_payload(ses_action.approved_payload, str(materialized["approval_url"]))
        freelancer_decide(s, context, change_order_id=order.id, decision="REJECTED", comment="Not ready")
        assert order.status == "REJECTED_BY_FREELANCER"

def revision_token_not_in_payload(payload: dict[str, object], materialized_url: str) -> bool:
    return materialized_url.split("#t=", 1)[1] not in str(payload)


def test_ses_dispatch_uses_verified_sender_and_review_link_only(
    fixture: tuple[TrustedContext, sessionmaker[Session]], monkeypatch: pytest.MonkeyPatch
) -> None:
    context, factory = fixture
    from services.api import config as api_config
    from services.integrations import ses

    settings = SimpleNamespace(
        capability_encryption_key="phase5-secret",
        environment="test",
        client_review_base_url="https://app.example.test",
        ses_from_email="verified@example.test",
        ses_configuration_set="",
        aws_region="us-east-1",
    )
    monkeypatch.setattr(api_config, "get_settings", lambda: settings)
    monkeypatch.setattr(ses, "get_settings", lambda: settings)
    calls: list[dict[str, object]] = []

    class FakeClient:
        def send_email(self, **request: object) -> dict[str, str]:
            calls.append(request)
            return {"MessageId": "ses-message-1"}

    monkeypatch.setattr(ses, "_client", lambda: FakeClient())
    with factory.begin() as session:
        decision_id = session.scalar(select(AnalysisDecision.id))
        order = assemble_change_order(session, context, decision_id=decision_id)
        action = session.scalar(select(ExternalAction).where(ExternalAction.provider == "ses"))
        assert action is not None
        message_id = ses.dispatch_ses_notification(session, action_id=action.id)
        assert message_id == "ses-message-1"
        assert action.state == "SUCCEEDED"
        assert session.scalar(select(Notification).where(Notification.action_id == action.id)).state == "SENT"
    request = calls[0]
    assert request["FromEmailAddress"] == "verified@example.test"
    assert request["Destination"] == {"ToAddresses": ["owner@example.test"]}
    content = request["Content"]
    assert isinstance(content, dict)
    simple = content["Simple"]
    assert isinstance(simple, dict)
    body = simple["Body"]
    assert isinstance(body, dict)
    text_body = body["Text"]["Data"]
    assert str(order.id) not in str(text_body)
    assert "https://app.example.test/c#t=" in str(text_body)
    assert "This is additional work." not in str(text_body)