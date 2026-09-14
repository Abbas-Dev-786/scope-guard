from __future__ import annotations

import base64
import binascii
import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Cookie, Header, Query, Request, Response, status
from sqlalchemy import select

from services.agents.persistence import (
    get_analysis_decision,
    get_decision_evidence,
    get_workflow_trace,
    list_analysis_decisions,
)
from services.api.auth import CurrentContext, DbSession, VerifiedIdentity
from services.api.operations import list_jobs, resolve_action, retry_failed_job
from services.api.schemas import (
    ActionRead,
    ActionResolveRequest,
    AnalysisDecisionDetailRead,
    AnalysisDecisionRead,
    AnalysisEvidenceRead,
    CapabilityExchangeRequest,
    ChangeOrderRead,
    ClientAcceptanceRequest,
    ClientCreate,
    ClientDecisionRequest,
    ClientRead,
    ClientReceiptRead,
    ClientReviewRead,
    ClientUpdate,
    CompleteUploadRequest,
    ContactCreate,
    ContactRead,
    DocumentCandidateRead,
    DocumentDownloadRead,
    DocumentRead,
    DocumentUploadRequest,
    FreelancerApprovalRequest,
    FreelancerDecisionRequest,
    GmailOAuthStartRead,
    GmailPushRequest,
    IntegrationConnectionRead,
    JobRead,
    JobRetryRequest,
    OnboardingCreate,
    OnboardingRead,
    OperationsHealthRead,
    Page,
    PaymentLinkReplaceRequest,
    PaymentRequestRead,
    PreferenceRead,
    PreferenceUpdate,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    ProposalRevisionEdit,
    ProposalRevisionRead,
    RequestClarify,
    RequestCreate,
    RequestMerge,
    RequestRead,
    RoutingDecisionRead,
    RoutingEventRequest,
    RoutingResolveRequest,
    RoutingResultRead,
    ScopeCandidateCorrection,
    ScopeCandidateRead,
    ScopeConfirmRequest,
    ScopeItemRead,
    ScopeRead,
    StructureExtractionRead,
    UploadGrantRead,
    UserRead,
    WithdrawalRequest,
    WorkflowTraceRead,
)
from services.api.service import (
    create_client,
    create_contact,
    create_project,
    delete_project,
    execute_idempotent,
    get_client,
    get_project,
    list_clients,
    list_contacts,
    list_projects,
    onboard_owner,
    read_preference,
    update_client,
    update_preference,
    update_project,
)
from services.domain.auth import TrustedContext
from services.domain.errors import AuthenticationError, ValidationError
from services.domain.models import AnalysisDraftRevision, User
from services.workers.observability import metrics

router = APIRouter(prefix="/api/v1")
public_router = APIRouter(prefix="/public/v1")
webhook_router = APIRouter()
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]


@router.post("/onboarding", response_model=OnboardingRead, status_code=status.HTTP_201_CREATED)
def onboarding(
    request: OnboardingCreate,
    session: DbSession,
    principal: VerifiedIdentity,
    idempotency_key: IdempotencyKey,
) -> OnboardingRead:
    if principal.email_verified is not True or not principal.email:
        raise AuthenticationError("A verified Cognito email is required for onboarding")
    existing = session.scalar(select(User).where(User.cognito_sub == principal.subject))
    tenant_id = existing.id if existing is not None else uuid4()
    context = TrustedContext(
        tenant_id=tenant_id,
        subject=principal.subject,
        email=principal.email,
        email_verified=True,
        correlation_id=uuid4(),
    )
    return execute_idempotent(
        session,
        context,
        "POST /api/v1/onboarding",
        idempotency_key,
        request,
        OnboardingRead,
        lambda: onboard_owner(session, context, request),
        actor_scope=f"identity:{principal.subject}",
    )


@router.get("/me", response_model=UserRead)
def me(session: DbSession, context: CurrentContext) -> UserRead:
    user = session.get(User, context.tenant_id)
    return UserRead.model_validate(user)


@router.get("/preferences", response_model=PreferenceRead)
def preferences(session: DbSession, context: CurrentContext) -> PreferenceRead:
    return read_preference(session, context)


@router.patch("/preferences", response_model=PreferenceRead)
def patch_preferences(
    request: PreferenceUpdate,
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> PreferenceRead:
    return execute_idempotent(
        session,
        context,
        "PATCH /api/v1/preferences",
        idempotency_key,
        request,
        PreferenceRead,
        lambda: update_preference(session, context, request),
    )


@router.post("/clients", response_model=ClientRead, status_code=status.HTTP_201_CREATED)
def post_client(
    request: ClientCreate,
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> ClientRead:
    return execute_idempotent(
        session,
        context,
        "POST /api/v1/clients",
        idempotency_key,
        request,
        ClientRead,
        lambda: create_client(session, context, request),
    )


@router.get("/clients", response_model=Page[ClientRead])
def clients(
    session: DbSession,
    context: CurrentContext,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> Page[ClientRead]:
    return list_clients(session, context, limit, cursor)


@router.get("/clients/{client_id}", response_model=ClientRead)
def client(client_id: UUID, session: DbSession, context: CurrentContext) -> ClientRead:
    return ClientRead.model_validate(get_client(session, context, client_id))


@router.patch("/clients/{client_id}", response_model=ClientRead)
def patch_client(
    client_id: UUID,
    request: ClientUpdate,
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> ClientRead:
    route = f"PATCH /api/v1/clients/{client_id}"
    return execute_idempotent(
        session,
        context,
        route,
        idempotency_key,
        request,
        ClientRead,
        lambda: update_client(session, context, client_id, request),
    )


@router.post(
    "/clients/{client_id}/contacts", response_model=ContactRead, status_code=status.HTTP_201_CREATED
)
def post_contact(
    client_id: UUID,
    request: ContactCreate,
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> ContactRead:
    route = f"POST /api/v1/clients/{client_id}/contacts"
    return execute_idempotent(
        session,
        context,
        route,
        idempotency_key,
        request,
        ContactRead,
        lambda: create_contact(session, context, client_id, request),
    )


@router.get("/clients/{client_id}/contacts", response_model=list[ContactRead])
def contacts(client_id: UUID, session: DbSession, context: CurrentContext) -> list[ContactRead]:
    return list_contacts(session, context, client_id)


@router.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def post_project(
    request: ProjectCreate,
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> ProjectRead:
    return execute_idempotent(
        session,
        context,
        "POST /api/v1/projects",
        idempotency_key,
        request,
        ProjectRead,
        lambda: create_project(session, context, request),
    )


@router.get("/projects", response_model=Page[ProjectRead])
def projects(
    session: DbSession,
    context: CurrentContext,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> Page[ProjectRead]:
    return list_projects(session, context, limit, cursor)


@router.get("/projects/{project_id}", response_model=ProjectRead)
def project(project_id: UUID, session: DbSession, context: CurrentContext) -> ProjectRead:
    return ProjectRead.model_validate(get_project(session, context, project_id))


@router.patch("/projects/{project_id}", response_model=ProjectRead)
def patch_project(
    project_id: UUID,
    request: ProjectUpdate,
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> ProjectRead:
    route = f"PATCH /api/v1/projects/{project_id}"
    return execute_idempotent(
        session,
        context,
        route,
        idempotency_key,
        request,
        ProjectRead,
        lambda: update_project(session, context, project_id, request),
    )


@router.delete("/projects/{project_id}", response_model=ProjectRead)
def remove_project(
    project_id: UUID,
    expected_row_version: Annotated[int, Query(gt=0)],
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> ProjectRead:
    request: dict[str, object] = {"expected_row_version": expected_row_version}
    route = f"DELETE /api/v1/projects/{project_id}"
    return execute_idempotent(
        session,
        context,
        route,
        idempotency_key,
        request,
        ProjectRead,
        lambda: delete_project(session, context, project_id, expected_row_version),
    )


@router.get("/operations/jobs", response_model=list[JobRead], tags=["operations"])
def operation_jobs(
    session: DbSession,
    context: CurrentContext,
    state: Annotated[str | None, Query(max_length=32)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[JobRead]:
    return list_jobs(session, context, state=state, limit=limit)


@router.post(
    "/operations/jobs/{job_id}/retry",
    response_model=JobRead,
    tags=["operations"],
)
def retry_operation_job(
    job_id: UUID,
    request: JobRetryRequest,
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> JobRead:
    route = f"POST /api/v1/operations/jobs/{job_id}/retry"
    return execute_idempotent(
        session,
        context,
        route,
        idempotency_key,
        request,
        JobRead,
        lambda: retry_failed_job(session, context, job_id, request.reason),
    )


@router.post(
    "/operations/actions/{action_id}/resolve",
    response_model=ActionRead,
    tags=["operations"],
)
def resolve_operation_action(
    action_id: UUID,
    request: ActionResolveRequest,
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> ActionRead:
    route = f"POST /api/v1/operations/actions/{action_id}/resolve"
    return execute_idempotent(
        session,
        context,
        route,
        idempotency_key,
        request,
        ActionRead,
        lambda: resolve_action(
            session,
            context,
            action_id,
            resolution=request.resolution,
            duplicate_risk_acknowledged=request.duplicate_risk_acknowledged,
            receipt_ref=request.receipt_ref,
        ),
    )


@router.get("/operations/health", response_model=OperationsHealthRead, tags=["operations"])
def operation_health() -> OperationsHealthRead:
    return OperationsHealthRead.model_validate(metrics.health())


@router.post(
    "/projects/{project_id}/documents",
    response_model=UploadGrantRead,
    status_code=status.HTTP_201_CREATED,
    tags=["contracts"],
)
def post_contract_document(
    project_id: UUID,
    request: DocumentUploadRequest,
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> UploadGrantRead:
    from services.contracts.service import create_upload_grant

    def create() -> UploadGrantRead:
        grant = create_upload_grant(
            session,
            context,
            project_id=project_id,
            object_key=request.object_key,
            mime_type=request.mime_type,
            expected_size_bytes=request.expected_size_bytes,
        )
        return UploadGrantRead(
            document_id=grant.document.id,
            object_key=grant.document.object_key,
            object_version=grant.document.object_version,
            upload_token=grant.token,
            expires_at=grant.expires_at,
            expected_size_bytes=request.expected_size_bytes,
            expected_mime_type=request.mime_type,
            upload_url=grant.upload_url,
            upload_fields=grant.upload_fields,
        )

    return execute_idempotent(
        session,
        context,
        f"POST /api/v1/projects/{project_id}/documents",
        idempotency_key,
        request,
        UploadGrantRead,
        create,
    )


@router.get("/documents/{document_id}", response_model=DocumentRead, tags=["contracts"])
def contract_document(
    document_id: UUID, session: DbSession, context: CurrentContext
) -> DocumentRead:
    from services.contracts.service import get_document

    return DocumentRead.model_validate(get_document(session, context, document_id))


@router.post(
    "/documents/{document_id}/complete-upload", response_model=DocumentRead, tags=["contracts"]
)
def complete_contract_upload(
    document_id: UUID,
    request: CompleteUploadRequest,
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> DocumentRead:
    from services.contracts.service import complete_upload, get_upload_source
    from services.contracts.storage import (
        ObjectStoreUnavailable,
        ObjectStoreVerificationError,
        fetch_private_object,
    )

    if request.content_base64 is not None:
        try:
            content = base64.b64decode(request.content_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValidationError("content_base64 is invalid") from exc
    else:
        source = get_upload_source(
            session, context, document_id=document_id, upload_token=request.upload_token
        )
        session.rollback()
        try:
            content = fetch_private_object(
                object_key=source.object_key,
                expected_size_bytes=source.expected_size_bytes,
                expected_mime_type=source.expected_mime_type,
                expected_sha256=request.sha256,
            )
        except ObjectStoreUnavailable as exc:
            raise ValidationError("Private object storage is not configured") from exc
        except ObjectStoreVerificationError as exc:
            raise ValidationError(str(exc)) from exc

    def complete() -> DocumentRead:
        return DocumentRead.model_validate(
            complete_upload(
                session,
                context,
                document_id=document_id,
                upload_token=request.upload_token,
                content=content,
                declared_sha256=request.sha256,
                declared_mime_type=request.mime_type,
            )
        )

    return execute_idempotent(
        session,
        context,
        f"POST /api/v1/documents/{document_id}/complete-upload",
        idempotency_key,
        request,
        DocumentRead,
        complete,
    )


@router.patch(
    "/documents/{document_id}/candidate-scope",
    response_model=ScopeCandidateRead,
    tags=["contracts"],
)
def patch_candidate_scope(
    document_id: UUID,
    request: ScopeCandidateCorrection,
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> ScopeCandidateRead:
    from services.contracts.service import correct_scope_candidate

    def correct() -> ScopeCandidateRead:
        candidate = correct_scope_candidate(
            session,
            context,
            candidate_id=request.candidate_id,
            corrected_text=request.corrected_text,
            reason=request.reason,
        )
        if candidate.document_id != document_id:
            raise ValueError("Candidate does not belong to document")
        return ScopeCandidateRead(
            candidate_id=candidate.id,
            status=candidate.status,
            corrected_text=candidate.corrected_text,
        )

    return execute_idempotent(
        session,
        context,
        f"PATCH /api/v1/documents/{document_id}/candidate-scope",
        idempotency_key,
        request,
        ScopeCandidateRead,
        correct,
    )


@router.post("/projects/{project_id}/scope/confirm", response_model=ScopeRead, tags=["contracts"])
def confirm_project_scope(
    project_id: UUID,
    request: ScopeConfirmRequest,
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> ScopeRead:
    from services.contracts.service import confirm_scope
    from services.domain.models import ScopeItem, ScopeVersionItem

    def confirm() -> ScopeRead:
        version = confirm_scope(
            session, context, project_id=project_id, candidate_ids=request.candidate_ids
        )
        items = session.scalars(
            select(ScopeItem)
            .join(ScopeVersionItem, ScopeVersionItem.scope_item_id == ScopeItem.id)
            .where(
                ScopeVersionItem.scope_version_id == version.id,
                ScopeItem.tenant_id == context.tenant_id,
            )
        ).all()
        return ScopeRead(
            version=version.version,
            content_hash=version.content_hash,
            confirmed_at=version.confirmed_at,
            items=[ScopeItemRead.model_validate(item) for item in items],
        )

    return execute_idempotent(
        session,
        context,
        f"POST /api/v1/projects/{project_id}/scope/confirm",
        idempotency_key,
        request,
        ScopeRead,
        confirm,
    )


@router.get("/projects/{project_id}/scope", response_model=ScopeRead, tags=["contracts"])
def project_scope(project_id: UUID, session: DbSession, context: CurrentContext) -> ScopeRead:
    from services.contracts.service import read_confirmed_scope
    from services.domain.models import ScopeItem, ScopeVersionItem

    version = read_confirmed_scope(session, context, project_id)
    items = session.scalars(
        select(ScopeItem)
        .join(ScopeVersionItem, ScopeVersionItem.scope_item_id == ScopeItem.id)
        .where(
            ScopeVersionItem.scope_version_id == version.id,
            ScopeItem.tenant_id == context.tenant_id,
        )
    ).all()
    return ScopeRead(
        version=version.version,
        content_hash=version.content_hash,
        confirmed_at=version.confirmed_at,
        items=[ScopeItemRead.model_validate(item) for item in items],
    )


def _integration_read(
    session: DbSession, context: CurrentContext, connection_id: UUID
) -> IntegrationConnectionRead:
    from services.integrations.gmail import read_gmail_health

    item = next(
        (row for row in read_gmail_health(session, context) if row["id"] == connection_id), None
    )
    if item is None:
        raise ValidationError("Gmail connection was not found")
    return IntegrationConnectionRead.model_validate(item)


@router.post(
    "/integrations/gmail/connect", response_model=GmailOAuthStartRead, tags=["integrations"]
)
def connect_gmail_route(session: DbSession, context: CurrentContext) -> GmailOAuthStartRead:
    from services.integrations.gmail import start_gmail_oauth

    result = start_gmail_oauth(session, context)
    return GmailOAuthStartRead(authorization_url=result.authorization_url, state=result.state)


@router.get(
    "/integrations/gmail/callback", response_model=IntegrationConnectionRead, tags=["integrations"]
)
def gmail_callback_route(
    state: Annotated[str, Query(min_length=1)],
    session: DbSession,
    code: Annotated[str | None, Query(min_length=1)] = None,
    error: Annotated[str | None, Query(max_length=128)] = None,
) -> IntegrationConnectionRead:
    if error:
        raise ValidationError("Gmail authorization was declined")
    if code is None:
        raise ValidationError("Gmail callback is incomplete")
    from services.integrations.gmail import complete_gmail_oauth_callback

    connection = complete_gmail_oauth_callback(session, state=state, code=code)
    context = TrustedContext(
        tenant_id=connection.tenant_id,
        subject=f"gmail:{connection.provider_account_id}",
        email=connection.account_email,
        email_verified=True,
        correlation_id=uuid4(),
    )
    return _integration_read(session, context, connection.id)


@router.post(
    "/integrations/gmail/{connection_id}/reconnect",
    response_model=GmailOAuthStartRead,
    tags=["integrations"],
)
def reconnect_gmail_route(
    connection_id: UUID, session: DbSession, context: CurrentContext
) -> GmailOAuthStartRead:
    from services.integrations.gmail import get_connection, start_gmail_oauth

    connection = get_connection(session, context, connection_id)
    result = start_gmail_oauth(session, context, expected_account_id=connection.provider_account_id)
    return GmailOAuthStartRead(authorization_url=result.authorization_url, state=result.state)


@router.get(
    "/integrations/gmail", response_model=list[IntegrationConnectionRead], tags=["integrations"]
)
def gmail_connections_route(
    session: DbSession, context: CurrentContext
) -> list[IntegrationConnectionRead]:
    from services.integrations.gmail import read_gmail_health

    return [
        IntegrationConnectionRead.model_validate(item)
        for item in read_gmail_health(session, context)
    ]


@router.get(
    "/integrations/health", response_model=list[IntegrationConnectionRead], tags=["integrations"]
)
def integrations_health_route(
    session: DbSession, context: CurrentContext
) -> list[IntegrationConnectionRead]:
    return gmail_connections_route(session, context)


@router.delete(
    "/integrations/gmail/{connection_id}",
    response_model=IntegrationConnectionRead,
    tags=["integrations"],
)
def disconnect_gmail_route(
    connection_id: UUID, session: DbSession, context: CurrentContext
) -> IntegrationConnectionRead:
    from services.integrations.gmail import disconnect_gmail

    disconnect_gmail(session, context, connection_id=connection_id)
    return _integration_read(session, context, connection_id)


@webhook_router.post("/webhooks/gmail", status_code=status.HTTP_202_ACCEPTED, tags=["integrations"])
def gmail_push_webhook(
    body: dict[str, object],
    session: DbSession,
    x_goog_topic: Annotated[str | None, Header(alias="x-goog-topic")] = None,
) -> dict[str, str]:
    from services.integrations.gmail import accept_gmail_pubsub_push, accept_gmail_push

    message = body.get("message") if isinstance(body, dict) else None
    if isinstance(message, dict) and "data" in message:
        encoded = str(message.get("data") or "")
        try:
            decoded = base64.b64decode(encoded + ("=" * (-len(encoded) % 4)), validate=True)
            notification = json.loads(decoded.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
            raise ValidationError("Gmail Pub/Sub payload is invalid") from exc
        if not isinstance(notification, dict):
            raise ValidationError("Gmail Pub/Sub notification is invalid")
        published = str(message.get("publishTime") or "")
        try:
            occurred_at = (
                datetime.fromisoformat(published.replace("Z", "+00:00"))
                if published
                else datetime.now(UTC)
            )
        except ValueError as exc:
            raise ValidationError("Gmail Pub/Sub publish time is invalid") from exc
        topic_name = x_goog_topic
        event = accept_gmail_pubsub_push(
            session,
            account_email=str(notification.get("emailAddress") or ""),
            history_id=str(notification.get("historyId") or ""),
            delivery_id=str(message.get("messageId") or ""),
            payload_hash=hashlib.sha256(decoded).hexdigest(),
            occurred_at=occurred_at,
            topic_name=topic_name,
        )
    else:
        request = GmailPushRequest.model_validate(body)
        event = accept_gmail_push(
            session,
            provider_account_id=request.provider_account_id,
            watch_id=request.watch_id,
            history_id=request.history_id,
            delivery_id=request.delivery_id,
            payload_hash=request.payload_hash,
            occurred_at=request.occurred_at,
            verification_token=request.verification_token,
        )
    return {"event_id": str(event.id), "status": "accepted"}


@router.post("/integration-events/route", response_model=RoutingResultRead, tags=["routing"])
def route_integration_event(
    request: RoutingEventRequest,
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> RoutingResultRead:
    from services.contracts.service import ingest_external_event, route_external_event
    from services.domain.models import CommunicationEvent, RoutingDecision

    def route() -> RoutingResultRead:
        event = ingest_external_event(
            session,
            context,
            provider=request.provider,
            environment=request.environment,
            provider_event_id=request.provider_event_id,
            payload_hash=request.payload_hash,
            occurred_at=request.occurred_at,
        )
        result = route_external_event(
            session,
            context,
            external_event_id=event.id,
            resource_type=request.resource_type,
            resource_id=request.resource_id,
            source_version=request.source_version,
            content_ref=request.content_ref,
            occurred_at=request.occurred_at,
            explicit_project_id=request.explicit_project_id,
            alias=request.alias,
            sender=request.sender,
            thread_id=request.thread_id,
        )
        if isinstance(result, CommunicationEvent):
            return RoutingResultRead(
                kind="communication",
                id=result.id,
                status="MAPPED",
                project_id=result.project_id,
                resource_type=result.resource_type,
                resource_id=result.resource_id,
                source_version=result.source_version,
            )
        if isinstance(result, RoutingDecision):
            return RoutingResultRead(
                kind="decision",
                id=result.id,
                status=result.status,
                candidate_projects=result.candidate_projects,
            )
        raise ValueError("Unsupported routing result")

    return execute_idempotent(
        session,
        context,
        "POST /api/v1/integration-events/route",
        idempotency_key,
        request,
        RoutingResultRead,
        route,
    )


@router.get("/routing-decisions", response_model=list[RoutingDecisionRead], tags=["routing"])
def routing_decisions(session: DbSession, context: CurrentContext) -> list[RoutingDecisionRead]:
    from services.contracts.service import list_routing_decisions

    return [
        RoutingDecisionRead.model_validate(item)
        for item in list_routing_decisions(session, context)
    ]


@router.post(
    "/requests", response_model=RequestRead, status_code=status.HTTP_201_CREATED, tags=["requests"]
)
def post_request(
    request: RequestCreate,
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> RequestRead:
    from services.contracts.requests import create_request

    def create() -> RequestRead:
        return RequestRead.model_validate(
            create_request(
                session,
                context,
                project_id=request.project_id,
                summary=request.summary,
                communication_ids=request.communication_ids,
            )
        )

    return execute_idempotent(
        session, context, "POST /api/v1/requests", idempotency_key, request, RequestRead, create
    )


@router.post(
    "/requests/{request_id}/analyze",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["analysis"],
)
def analyze_request_route(
    request_id: UUID, session: DbSession, context: CurrentContext, idempotency_key: IdempotencyKey
) -> JobRead:
    from services.contracts.requests import get_request
    from services.workers.durable import enqueue_job

    request = get_request(session, context, request_id)

    def enqueue() -> JobRead:
        job = enqueue_job(
            session,
            tenant_id=context.tenant_id,
            project_id=request.project_id,
            kind="analysis.prepare",
            payload_ref={"request_id": str(request.id), "request_version": request.request_version},
            correlation_id=context.correlation_id,
            deadline_at=datetime.now(UTC) + timedelta(minutes=8),
        )
        return JobRead.model_validate(job)

    return execute_idempotent(
        session,
        context,
        f"POST /api/v1/requests/{request_id}/analyze",
        idempotency_key,
        {},
        JobRead,
        enqueue,
    )


@router.get("/requests/{request_id}", response_model=RequestRead, tags=["requests"])
def get_request_route(request_id: UUID, session: DbSession, context: CurrentContext) -> RequestRead:
    from services.contracts.requests import get_request

    return RequestRead.model_validate(get_request(session, context, request_id))


@router.post("/requests/{request_id}/clarify", response_model=RequestRead, tags=["requests"])
def clarify_request_route(
    request_id: UUID,
    request: RequestClarify,
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> RequestRead:
    from services.contracts.requests import clarify_request

    def clarify() -> RequestRead:
        return RequestRead.model_validate(
            clarify_request(session, context, request_id=request_id, correction=request.correction)
        )

    return execute_idempotent(
        session,
        context,
        f"POST /api/v1/requests/{request_id}/clarify",
        idempotency_key,
        request,
        RequestRead,
        clarify,
    )


@router.post("/requests/{request_id}/merge", response_model=RequestRead, tags=["requests"])
def merge_request_route(
    request_id: UUID,
    request: RequestMerge,
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> RequestRead:
    from services.contracts.requests import merge_requests

    def merge() -> RequestRead:
        return RequestRead.model_validate(
            merge_requests(
                session,
                context,
                target_request_id=request_id,
                source_request_id=request.source_request_id,
                reason=request.reason,
            )
        )

    return execute_idempotent(
        session,
        context,
        f"POST /api/v1/requests/{request_id}/merge",
        idempotency_key,
        request,
        RequestRead,
        merge,
    )


@router.post(
    "/integration-events/{event_id}/assign", response_model=RoutingResultRead, tags=["routing"]
)
def assign_integration_event(
    event_id: UUID,
    request: RoutingResolveRequest,
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> RoutingResultRead:
    from services.contracts.service import resolve_routing_decision
    from services.domain.models import CommunicationEvent

    def assign() -> RoutingResultRead:
        result = resolve_routing_decision(
            session,
            context,
            decision_id=event_id,
            project_id=request.project_id,
            actor=context.subject,
        )
        if isinstance(result, CommunicationEvent):
            return RoutingResultRead(
                kind="communication",
                id=result.id,
                status="MAPPED",
                project_id=result.project_id,
                resource_type=result.resource_type,
                resource_id=result.resource_id,
                source_version=result.source_version,
            )
        return RoutingResultRead(
            kind="decision",
            id=result.id,
            status=result.status,
            candidate_projects=result.candidate_projects,
        )

    return execute_idempotent(
        session,
        context,
        f"POST /api/v1/integration-events/{event_id}/assign",
        idempotency_key,
        request,
        RoutingResultRead,
        assign,
    )


@router.post(
    "/integration-events/{event_id}/replay", response_model=RoutingResultRead, tags=["routing"]
)
def replay_integration_event(
    event_id: UUID,
    request: RoutingResolveRequest,
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> RoutingResultRead:
    from services.contracts.service import replay_external_event
    from services.domain.models import CommunicationEvent

    def replay() -> RoutingResultRead:
        result = replay_external_event(
            session, context, external_event_id=event_id, project_id=request.project_id
        )
        if isinstance(result, CommunicationEvent):
            return RoutingResultRead(
                kind="communication",
                id=result.id,
                status="MAPPED",
                project_id=result.project_id,
                resource_type=result.resource_type,
                resource_id=result.resource_id,
                source_version=result.source_version,
            )
        return RoutingResultRead(
            kind="decision",
            id=result.id,
            status=result.status,
            candidate_projects=result.candidate_projects,
        )

    return execute_idempotent(
        session,
        context,
        f"POST /api/v1/integration-events/{event_id}/replay",
        idempotency_key,
        request,
        RoutingResultRead,
        replay,
    )


@router.get(
    "/documents/{document_id}/download", response_model=DocumentDownloadRead, tags=["contracts"]
)
def download_contract_document(
    document_id: UUID, session: DbSession, context: CurrentContext
) -> DocumentDownloadRead:
    from services.contracts.service import get_document
    from services.contracts.storage import ObjectStoreUnavailable, create_private_download

    document = get_document(session, context, document_id)
    try:
        download_url = create_private_download(object_key=document.object_key)
    except ObjectStoreUnavailable:
        download_url = None
    return DocumentDownloadRead(
        document_id=document.id,
        object_key=document.object_key,
        object_version=document.object_version,
        sha256=document.sha256,
        access_scope=f"tenant:{context.tenant_id}:project:{document.project_id}",
        download_url=download_url,
    )


@router.get(
    "/projects/{project_id}/documents", response_model=list[DocumentRead], tags=["contracts"]
)
def project_documents(
    project_id: UUID, session: DbSession, context: CurrentContext
) -> list[DocumentRead]:
    from services.contracts.service import list_documents

    return [
        DocumentRead.model_validate(item) for item in list_documents(session, context, project_id)
    ]


@router.get(
    "/documents/{document_id}/candidates",
    response_model=list[DocumentCandidateRead],
    tags=["contracts"],
)
def document_candidates(
    document_id: UUID, session: DbSession, context: CurrentContext
) -> list[DocumentCandidateRead]:
    from services.contracts.service import list_candidates

    return [
        DocumentCandidateRead.model_validate(item)
        for item in list_candidates(session, context, document_id)
    ]


@router.post(
    "/documents/{document_id}/extract-scope",
    response_model=StructureExtractionRead,
    tags=["contracts"],
)
def extract_document_scope(
    document_id: UUID,
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> StructureExtractionRead:
    from services.api.config import get_settings
    from services.contracts.service import get_document, persist_structure_candidates
    from services.contracts.structure import (
        BedrockStructureProvider,
        StructureExtractionResult,
        StructureProviderUnavailable,
        extract_scope_candidates,
    )
    from services.domain.models import DocumentChunk

    document = get_document(session, context, document_id)
    chunks = list(
        session.scalars(
            select(DocumentChunk)
            .where(
                DocumentChunk.document_id == document.id,
                DocumentChunk.tenant_id == context.tenant_id,
            )
            .order_by(DocumentChunk.chunk_index)
        )
    )
    session.rollback()
    if not chunks:
        extraction = StructureExtractionResult(status="PENDING", reason="no_extracted_chunks")
    else:
        try:
            provider = BedrockStructureProvider(
                model_id=get_settings().bedrock_model_id,
                region_name=get_settings().aws_region,
                timeout_seconds=get_settings().contract_structure_model_timeout_seconds,
            )
        except StructureProviderUnavailable as exc:
            extraction = StructureExtractionResult(status="PENDING", reason=str(exc))
        else:
            extraction = extract_scope_candidates(provider, chunks)

    def persist() -> StructureExtractionRead:
        persisted = []
        if extraction.status == "READY":
            persisted = persist_structure_candidates(
                session,
                context,
                document_id=document_id,
                candidates=extraction.candidates,
                extractor_version=extraction.reason or "scope-structure-v1",
            )
        return StructureExtractionRead(
            status=extraction.status,
            reason=extraction.reason,
            candidates=[DocumentCandidateRead.model_validate(item) for item in persisted],
        )

    return execute_idempotent(
        session,
        context,
        f"POST /api/v1/documents/{document_id}/extract-scope",
        idempotency_key,
        {},
        StructureExtractionRead,
        persist,
    )


@router.get("/decisions", response_model=list[AnalysisDecisionRead], tags=["analysis"])
def analysis_decisions(
    session: DbSession,
    context: CurrentContext,
    status: Annotated[str | None, Query(max_length=40)] = None,
    project_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[AnalysisDecisionRead]:
    return [
        AnalysisDecisionRead.model_validate(item)
        for item in list_analysis_decisions(
            session, context, status=status, project_id=project_id, limit=limit
        )
    ]


@router.get(
    "/decisions/{decision_id}", response_model=AnalysisDecisionDetailRead, tags=["analysis"]
)
def analysis_decision(
    decision_id: UUID, session: DbSession, context: CurrentContext
) -> AnalysisDecisionDetailRead:
    decision = get_analysis_decision(session, context, decision_id)
    revision = session.scalar(
        select(AnalysisDraftRevision).where(
            AnalysisDraftRevision.decision_id == decision.id,
            AnalysisDraftRevision.status == "CURRENT",
        )
    )
    payload = AnalysisDecisionDetailRead.model_validate(decision)
    return payload.model_copy(
        update={
            "draft_revision_id": revision.id if revision else None,
            "draft_revision": revision.payload if revision else None,
        }
    )


@router.get(
    "/decisions/{decision_id}/evidence",
    response_model=list[AnalysisEvidenceRead],
    tags=["analysis"],
)
def analysis_decision_evidence(
    decision_id: UUID, session: DbSession, context: CurrentContext
) -> list[AnalysisEvidenceRead]:
    return [
        AnalysisEvidenceRead.model_validate(item)
        for item in get_decision_evidence(session, context, decision_id)
    ]


@router.get("/workflows/{workflow_id}/trace", response_model=WorkflowTraceRead, tags=["analysis"])
def analysis_workflow_trace(
    workflow_id: UUID, session: DbSession, context: CurrentContext
) -> WorkflowTraceRead:
    return WorkflowTraceRead.model_validate(get_workflow_trace(session, context, workflow_id))


def _change_order_read(session: DbSession, order: object) -> ChangeOrderRead:
    from services.domain.models import ChangeOrder, ProposalRevision

    if not isinstance(order, ChangeOrder):
        raise ValidationError("Change order is unavailable")
    revision = (
        session.scalar(
            select(ProposalRevision).where(
                ProposalRevision.id == order.current_revision_id,
                ProposalRevision.tenant_id == order.tenant_id,
            )
        )
        if order.current_revision_id
        else None
    )
    if revision is None:
        return ChangeOrderRead.model_validate(order).model_copy(update={"revision": None})
    from services.change_orders.service import materialize_client_approval_url

    revision_read = ProposalRevisionRead.model_validate(revision).model_copy(
        update={"approval_url": materialize_client_approval_url(revision)}
    )
    return ChangeOrderRead.model_validate(order).model_copy(update={"revision": revision_read})


@router.post(
    "/decisions/{decision_id}/change-order",
    response_model=ChangeOrderRead,
    status_code=status.HTTP_201_CREATED,
    tags=["proposals"],
)
def assemble_change_order_route(
    decision_id: UUID,
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> ChangeOrderRead:
    from services.change_orders.service import assemble_change_order

    def assemble() -> ChangeOrderRead:
        return _change_order_read(
            session, assemble_change_order(session, context, decision_id=decision_id)
        )

    return execute_idempotent(
        session,
        context,
        f"POST /api/v1/decisions/{decision_id}/change-order",
        idempotency_key,
        {},
        ChangeOrderRead,
        assemble,
    )


@router.get("/change-orders/{change_order_id}", response_model=ChangeOrderRead, tags=["proposals"])
def get_change_order_route(
    change_order_id: UUID, session: DbSession, context: CurrentContext
) -> ChangeOrderRead:
    from services.change_orders.service import read_change_order

    return _change_order_read(
        session, read_change_order(session, context, change_order_id=change_order_id)
    )


@router.post(
    "/change-orders/{change_order_id}/revisions", response_model=ChangeOrderRead, tags=["proposals"]
)
def create_change_order_revision_route(
    change_order_id: UUID,
    request: ProposalRevisionEdit,
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> ChangeOrderRead:
    from services.change_orders.service import create_revision, read_change_order

    def create() -> ChangeOrderRead:
        create_revision(
            session,
            context,
            change_order_id=change_order_id,
            edits=request.model_dump(exclude_none=True),
        )
        return _change_order_read(
            session, read_change_order(session, context, change_order_id=change_order_id)
        )

    return execute_idempotent(
        session,
        context,
        f"/api/v1/change-orders/{change_order_id}/revisions",
        idempotency_key,
        request,
        ChangeOrderRead,
        create,
    )


@router.post(
    "/change-orders/{change_order_id}/approve", response_model=ChangeOrderRead, tags=["proposals"]
)
def approve_change_order_route(
    change_order_id: UUID,
    request: FreelancerApprovalRequest,
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> ChangeOrderRead:
    from services.change_orders.service import approve_freelancer, read_change_order

    def approve() -> ChangeOrderRead:
        approve_freelancer(
            session,
            context,
            change_order_id=change_order_id,
            expected_row_version=request.expected_row_version,
            revision_id=request.revision_id,
            content_hash=request.content_hash,
        )
        return _change_order_read(
            session, read_change_order(session, context, change_order_id=change_order_id)
        )

    return execute_idempotent(
        session,
        context,
        f"/api/v1/change-orders/{change_order_id}/approve",
        idempotency_key,
        request,
        ChangeOrderRead,
        approve,
    )


@router.post(
    "/change-orders/{change_order_id}/reject", response_model=ChangeOrderRead, tags=["proposals"]
)
def reject_change_order_route(
    change_order_id: UUID,
    request: FreelancerDecisionRequest,
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> ChangeOrderRead:
    from services.change_orders.service import freelancer_decide, read_change_order

    def reject() -> ChangeOrderRead:
        freelancer_decide(
            session,
            context,
            change_order_id=change_order_id,
            decision="REJECTED",
            comment=request.comment,
        )
        return _change_order_read(
            session, read_change_order(session, context, change_order_id=change_order_id)
        )

    return execute_idempotent(
        session,
        context,
        f"/api/v1/change-orders/{change_order_id}/reject",
        idempotency_key,
        request,
        ChangeOrderRead,
        reject,
    )


@router.post(
    "/change-orders/{change_order_id}/waive", response_model=ChangeOrderRead, tags=["proposals"]
)
def waive_change_order_route(
    change_order_id: UUID,
    request: FreelancerDecisionRequest,
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> ChangeOrderRead:
    from services.change_orders.service import freelancer_decide, read_change_order

    def waive() -> ChangeOrderRead:
        freelancer_decide(
            session,
            context,
            change_order_id=change_order_id,
            decision="WAIVED",
            comment=request.comment,
        )
        return _change_order_read(
            session, read_change_order(session, context, change_order_id=change_order_id)
        )

    return execute_idempotent(
        session,
        context,
        f"/api/v1/change-orders/{change_order_id}/waive",
        idempotency_key,
        request,
        ChangeOrderRead,
        waive,
    )


@router.post(
    "/change-orders/{change_order_id}/withdraw", response_model=ChangeOrderRead, tags=["proposals"]
)
def withdraw_change_order_route(
    change_order_id: UUID,
    request: WithdrawalRequest,
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> ChangeOrderRead:
    from services.change_orders.service import read_change_order, withdraw_change_order

    def withdraw() -> ChangeOrderRead:
        withdraw_change_order(
            session, context, change_order_id=change_order_id, reason=request.reason
        )
        return _change_order_read(
            session, read_change_order(session, context, change_order_id=change_order_id)
        )

    return execute_idempotent(
        session,
        context,
        f"/api/v1/change-orders/{change_order_id}/withdraw",
        idempotency_key,
        request,
        ChangeOrderRead,
        withdraw,
    )


@router.get(
    "/payment-requests/{payment_request_id}", response_model=PaymentRequestRead, tags=["payments"]
)
def payment_requests_route(
    payment_request_id: UUID, session: DbSession, context: CurrentContext
) -> PaymentRequestRead:
    from services.payments.service import read_payment_request

    return PaymentRequestRead.model_validate(
        read_payment_request(session, context, payment_request_id=payment_request_id)
    )


@router.post(
    "/payment-requests/{payment_request_id}/create-link",
    response_model=PaymentRequestRead,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["payments"],
)
def create_payment_link_route(
    payment_request_id: UUID,
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> PaymentRequestRead:
    from services.payments.service import prepare_payment_link, read_payment_request

    def create() -> PaymentRequestRead:
        _action, job = prepare_payment_link(session, context, payment_request_id=payment_request_id)
        return PaymentRequestRead.model_validate(
            read_payment_request(
                session,
                context,
                payment_request_id=payment_request_id,
                job_id=getattr(job, "id", None),
            )
        )

    return execute_idempotent(
        session,
        context,
        f"POST /api/v1/payment-requests/{payment_request_id}/create-link",
        idempotency_key,
        {},
        PaymentRequestRead,
        create,
    )


@router.post(
    "/payment-requests/{payment_request_id}/replace-link",
    response_model=PaymentRequestRead,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["payments"],
)
def replace_payment_link_route(
    payment_request_id: UUID,
    request: PaymentLinkReplaceRequest,
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> PaymentRequestRead:
    from services.payments.service import read_payment_request, replace_payment_link

    def replace() -> PaymentRequestRead:
        _action, job = replace_payment_link(
            session,
            context,
            payment_request_id=payment_request_id,
            expected_row_version=request.expected_row_version,
        )
        return PaymentRequestRead.model_validate(
            read_payment_request(
                session,
                context,
                payment_request_id=payment_request_id,
                job_id=getattr(job, "id", None),
            )
        )

    return execute_idempotent(
        session,
        context,
        f"POST /api/v1/payment-requests/{payment_request_id}/replace-link",
        idempotency_key,
        request,
        PaymentRequestRead,
        replace,
    )


@router.post(
    "/payment-requests/{payment_request_id}/reconcile",
    response_model=PaymentRequestRead,
    tags=["payments"],
)
def reconcile_payment_route(
    payment_request_id: UUID,
    session: DbSession,
    context: CurrentContext,
    idempotency_key: IdempotencyKey,
) -> PaymentRequestRead:
    from services.payments.service import read_payment_request, reconcile_payment_request

    def reconcile() -> PaymentRequestRead:
        reconcile_payment_request(session, context, payment_request_id=payment_request_id)
        return PaymentRequestRead.model_validate(
            read_payment_request(session, context, payment_request_id=payment_request_id)
        )

    return execute_idempotent(
        session,
        context,
        f"POST /api/v1/payment-requests/{payment_request_id}/reconcile",
        idempotency_key,
        {},
        PaymentRequestRead,
        reconcile,
    )


@webhook_router.post("/webhooks/razorpay", tags=["payments"])
async def razorpay_webhook(
    request: Request,
    session: DbSession,
    x_razorpay_signature: Annotated[str | None, Header(alias="X-Razorpay-Signature")] = None,
    x_razorpay_event_id: Annotated[str | None, Header(alias="X-Razorpay-Event-Id")] = None,
) -> dict[str, object]:
    from services.api.config import get_settings
    from services.integrations.razorpay import RazorpayProvider
    from services.payments.service import accept_payment_webhook

    raw_body = await request.body()
    if len(raw_body) > 262_144:
        raise ValidationError("Razorpay webhook payload exceeds 256 KiB")
    provider = RazorpayProvider(
        key_id="",
        key_secret="",
        api_base_url="",
        account_id=str(get_settings().razorpay_account_id or "").strip(),
    )
    if not provider.account_id or not provider.verify_webhook_signature(
        raw_body, x_razorpay_signature or ""
    ):
        raise ValidationError("Razorpay webhook signature is invalid")
    try:
        payload = json.loads(raw_body)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValidationError("Razorpay webhook payload is invalid") from exc
    if not isinstance(payload, dict):
        raise ValidationError("Razorpay webhook payload is invalid")
    event_type = str(payload.get("event") or "").strip()
    if not event_type:
        raise ValidationError("Razorpay webhook event is missing")
    ingress, job = accept_payment_webhook(
        session,
        provider_account_id=provider.account_id,
        provider_environment="test",
        provider_event_id=x_razorpay_event_id or "",
        event_type=event_type,
        payload=payload,
        signature_verified=True,
    )
    return {
        "ingress_id": str(ingress.id),
        "job_id": str(job.id) if job else None,
        "status": "accepted",
    }


def _public_response(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"


@public_router.post("/capabilities/exchange", response_model=dict[str, str], tags=["client"])
def exchange_capability_route(
    request: CapabilityExchangeRequest, response: Response, session: DbSession
) -> dict[str, str]:
    from services.change_orders.service import exchange_capability

    credentials = exchange_capability(session, token=request.token)
    _public_response(response)
    response.set_cookie(
        "scopeguard_client_session",
        credentials.session_token,
        max_age=86400,
        httponly=True,
        secure=True,
        samesite="none",
        path="/public/v1",
    )
    return {
        "change_order_id": str(credentials.capability.change_order_id),
        "csrf_token": credentials.csrf_token,
    }


@public_router.get(
    "/change-orders/{change_order_id}", response_model=ClientReviewRead, tags=["client"]
)
def client_review_route(
    change_order_id: UUID,
    session: DbSession,
    response: Response,
    scopeguard_client_session: str | None = Cookie(default=None),
) -> ClientReviewRead:
    from services.change_orders.service import read_client_review

    if not scopeguard_client_session:
        raise ValidationError("Invalid client session")
    payload = read_client_review(session, session_token=scopeguard_client_session)
    if payload["change_order_id"] != str(change_order_id):
        raise ValidationError("Invalid client session")
    _public_response(response)
    return ClientReviewRead.model_validate(payload)


@public_router.get(
    "/change-orders/{change_order_id}/receipt", response_model=ClientReceiptRead, tags=["client"]
)
def client_receipt_route(
    change_order_id: UUID,
    session: DbSession,
    response: Response,
    scopeguard_client_session: str | None = Cookie(default=None),
) -> ClientReceiptRead:
    from services.change_orders.service import verify_receipt_session

    if not scopeguard_client_session:
        raise ValidationError("Invalid client session")
    payload = verify_receipt_session(session, session_token=scopeguard_client_session)
    if payload["change_order_id"] != str(change_order_id):
        raise ValidationError("Invalid client session")
    _public_response(response)
    return ClientReceiptRead.model_validate(payload)


@public_router.post("/session/refresh", response_model=dict[str, str], tags=["client"])
def refresh_client_session_route(
    response: Response,
    session: DbSession,
    scopeguard_client_session: str | None = Cookie(default=None),
) -> dict[str, str]:
    from services.change_orders.service import refresh_client_session

    if not scopeguard_client_session:
        raise ValidationError("Invalid client session")
    credentials = refresh_client_session(session, session_token=scopeguard_client_session)
    _public_response(response)
    response.set_cookie(
        "scopeguard_client_session",
        credentials.session_token,
        max_age=86400,
        httponly=True,
        secure=True,
        samesite="none",
        path="/public/v1",
    )
    return {
        "change_order_id": str(credentials.capability.change_order_id),
        "csrf_token": credentials.csrf_token,
    }


@public_router.post(
    "/change-orders/{change_order_id}/request-changes",
    response_model=dict[str, str],
    tags=["client"],
)
def client_request_changes_route(
    change_order_id: UUID,
    request: ClientDecisionRequest,
    response: Response,
    session: DbSession,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    scopeguard_client_session: str | None = Cookie(default=None),
) -> dict[str, str]:
    from services.change_orders.service import client_decide

    if not scopeguard_client_session or not csrf_token:
        raise ValidationError("Client session and CSRF token are required")
    order = client_decide(
        session,
        session_token=scopeguard_client_session,
        csrf_token=csrf_token,
        change_order_id=change_order_id,
        expected_row_version=request.expected_row_version,
        revision_id=request.revision_id,
        content_hash=request.content_hash,
        decision="REQUEST_CHANGES",
        comment=request.comment,
    )
    _public_response(response)
    return {
        "change_order_id": str(order.id),
        "revision_id": str(request.revision_id),
        "status": order.status,
    }


@public_router.post(
    "/change-orders/{change_order_id}/reject", response_model=dict[str, str], tags=["client"]
)
def client_reject_route(
    change_order_id: UUID,
    request: ClientDecisionRequest,
    response: Response,
    session: DbSession,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    scopeguard_client_session: str | None = Cookie(default=None),
) -> dict[str, str]:
    from services.change_orders.service import client_decide

    if not scopeguard_client_session or not csrf_token:
        raise ValidationError("Client session and CSRF token are required")
    order = client_decide(
        session,
        session_token=scopeguard_client_session,
        csrf_token=csrf_token,
        change_order_id=change_order_id,
        expected_row_version=request.expected_row_version,
        revision_id=request.revision_id,
        content_hash=request.content_hash,
        decision="REJECTED",
        comment=request.comment,
    )
    _public_response(response)
    return {
        "change_order_id": str(order.id),
        "revision_id": str(request.revision_id),
        "status": order.status,
    }


@public_router.post(
    "/change-orders/{change_order_id}/approve", response_model=ClientReceiptRead, tags=["client"]
)
def client_accept_route(
    change_order_id: UUID,
    request: ClientAcceptanceRequest,
    response: Response,
    session: DbSession,
    idempotency_key: IdempotencyKey,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    scopeguard_client_session: str | None = Cookie(default=None),
) -> ClientReceiptRead:
    from services.change_orders.service import accept_client

    if not scopeguard_client_session or not csrf_token:
        raise ValidationError("Client session and CSRF token are required")
    result = accept_client(
        session,
        session_token=scopeguard_client_session,
        csrf_token=csrf_token,
        change_order_id=change_order_id,
        expected_row_version=request.expected_row_version,
        revision_id=request.revision_id,
        content_hash=request.content_hash,
        client_idempotency_key=idempotency_key,
    )
    _public_response(response)
    response.set_cookie(
        "scopeguard_client_session",
        result.receipt.session_token,
        max_age=86400,
        httponly=True,
        secure=True,
        samesite="none",
        path="/public/v1",
    )
    return ClientReceiptRead(
        change_order_id=result.change_order.id,
        revision_id=result.receipt.capability.revision_id,
        status=result.change_order.status,
        payment_status=result.payment_request.status,
        payment_request_id=result.payment_request.id,
    )
