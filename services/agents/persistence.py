from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.domain.auth import TrustedContext
from services.domain.canonical import canonical_sha256
from services.domain.errors import ConflictError, NotFoundError, ValidationError
from services.domain.models import (
    AgentRun,
    AnalysisBudgetReservation,
    AnalysisBudgetWindow,
    AnalysisDecision,
    AnalysisDraftRevision,
    AnalysisEvaluationRun,
    EvidenceReference,
    Project,
    ScopeAssessment,
    WorkflowInstance,
)

DEFAULT_TENANT_TOKEN_LIMIT = 250_000
DEFAULT_COST_LIMIT_MINOR: int | None = None


@dataclass(frozen=True, slots=True)
class BudgetReservationResult:
    reservation: AnalysisBudgetReservation
    window: AnalysisBudgetWindow


def _project(session: Session, context: TrustedContext, project_id: UUID | None) -> Project | None:
    if project_id is None:
        return None
    project = session.scalar(select(Project).where(Project.id == project_id, Project.tenant_id == context.tenant_id))
    if project is None:
        raise NotFoundError("Project was not found")
    return project


def create_workflow(
    session: Session,
    context: TrustedContext,
    *,
    workflow_key: str,
    input_snapshot: dict[str, object],
    project_id: UUID | None = None,
    request_id: UUID | None = None,
    scope_version_id: UUID | None = None,
    preference_version_id: UUID | None = None,
    policy_version: str = "analysis-policy-v1",
    current_phase: str = "PREPARATION",
) -> WorkflowInstance:
    if not workflow_key or len(workflow_key) > 160:
        raise ValidationError("Workflow key is required")
    _project(session, context, project_id)
    digest = canonical_sha256(input_snapshot)
    existing = session.scalar(select(WorkflowInstance).where(WorkflowInstance.tenant_id == context.tenant_id, WorkflowInstance.workflow_key == workflow_key).with_for_update())
    if existing is not None:
        if existing.input_digest != digest:
            raise ConflictError("Workflow key already refers to a different input snapshot")
        return existing
    workflow = WorkflowInstance(
        tenant_id=context.tenant_id,
        project_id=project_id,
        workflow_key=workflow_key,
        input_digest=digest,
        state="RUNNING",
        request_id=request_id,
        scope_version_id=scope_version_id,
        preference_version_id=preference_version_id,
        current_phase=current_phase,
        policy_version=policy_version,
        correlation_id=context.correlation_id,
    )
    session.add(workflow)
    session.flush()
    return workflow


def start_agent_run(
    session: Session,
    context: TrustedContext,
    *,
    workflow_id: UUID,
    node_name: str,
    attempt: int,
    model_id: str,
    prompt_version: str,
    schema_version: str,
    tool_policy_version: str,
    input_snapshot: dict[str, object],
) -> AgentRun:
    if not 1 <= attempt <= 3:
        raise ValidationError("Agent attempts must be between one and three")
    workflow = session.scalar(select(WorkflowInstance).where(WorkflowInstance.id == workflow_id, WorkflowInstance.tenant_id == context.tenant_id))
    if workflow is None:
        raise NotFoundError("Workflow was not found")
    input_hash = canonical_sha256(input_snapshot)
    existing = session.scalar(select(AgentRun).where(AgentRun.workflow_id == workflow_id, AgentRun.node_name == node_name, AgentRun.attempt == attempt).with_for_update())
    if existing is not None:
        if existing.input_hash != input_hash:
            raise ConflictError("Agent node attempt already has a different input")
        return existing
    run = AgentRun(
        tenant_id=context.tenant_id,
        workflow_id=workflow_id,
        node_name=node_name,
        attempt=attempt,
        model_id=model_id,
        prompt_version=prompt_version,
        schema_version=schema_version,
        tool_policy_version=tool_policy_version,
        input_hash=input_hash,
        input_ref=input_snapshot,
    )
    session.add(run)
    session.flush()
    return run


def finish_agent_run(
    session: Session,
    context: TrustedContext,
    *,
    run_id: UUID,
    output: dict[str, object],
    usage: dict[str, object] | None = None,
) -> AgentRun:
    run = session.scalar(select(AgentRun).where(AgentRun.id == run_id, AgentRun.tenant_id == context.tenant_id).with_for_update())
    if run is None:
        raise NotFoundError("Agent run was not found")
    if run.status not in {"RUNNING", "REPAIRING"}:
        raise ConflictError("Agent run is already terminal")
    run.output_ref = output
    run.output_hash = canonical_sha256(output)
    run.usage = usage
    run.status = "SUCCEEDED"
    run.completed_at = datetime.now(UTC)
    session.flush()
    return run


def fail_agent_run(
    session: Session,
    context: TrustedContext,
    *,
    run_id: UUID,
    error_code: str,
    error_message: str,
    review_required: bool = False,
) -> AgentRun:
    run = session.scalar(select(AgentRun).where(AgentRun.id == run_id, AgentRun.tenant_id == context.tenant_id).with_for_update())
    if run is None:
        raise NotFoundError("Agent run was not found")
    run.status = "REVIEW_REQUIRED" if review_required else "FAILED"
    run.error_code = error_code[:120]
    run.error_message = error_message[:500]
    run.completed_at = datetime.now(UTC)
    session.flush()
    return run


def record_scope_assessment(
    session: Session,
    context: TrustedContext,
    *,
    project_id: UUID,
    workflow_id: UUID,
    classification: str,
    reason: str,
    coverage_status: str,
    input_snapshot: dict[str, object],
    request_id: UUID | None = None,
    evidence_bundle_id: UUID | None = None,
    scope_version_id: UUID | None = None,
    request_version: int | None = None,
    matched_scope_item_ids: list[str] | None = None,
    matched_amendment_ids: list[str] | None = None,
    pending_request_ids: list[str] | None = None,
    required_evidence_queries: list[str] | None = None,
    uncertainty: str | None = None,
) -> ScopeAssessment:
    _project(session, context, project_id)
    workflow = session.scalar(select(WorkflowInstance).where(WorkflowInstance.id == workflow_id, WorkflowInstance.tenant_id == context.tenant_id))
    if workflow is None:
        raise NotFoundError("Workflow was not found")
    if classification not in {"IN_SCOPE", "POTENTIAL_SCOPE_CHANGE", "AMBIGUOUS", "PREVIOUSLY_APPROVED", "NOT_A_SCOPE_REQUEST"}:
        raise ValidationError("Unsupported scope assessment classification")
    if coverage_status not in {"COMPLETE", "PARTIAL", "UNAVAILABLE", "REQUIRES_CLARIFICATION"}:
        raise ValidationError("Unsupported evidence coverage status")
    assessment = ScopeAssessment(
        tenant_id=context.tenant_id,
        project_id=project_id,
        request_id=request_id,
        workflow_id=workflow_id,
        classification=classification,
        reason=reason,
        evidence_bundle_id=evidence_bundle_id,
        scope_version_id=scope_version_id,
        request_version=request_version,
        coverage_status=coverage_status,
        matched_scope_item_ids=matched_scope_item_ids or [],
        matched_amendment_ids=matched_amendment_ids or [],
        pending_request_ids=pending_request_ids or [],
        required_evidence_queries=required_evidence_queries or [],
        uncertainty=uncertainty,
        input_digest=canonical_sha256(input_snapshot),
    )
    session.add(assessment)
    session.flush()
    return assessment


def reserve_analysis_budget(
    session: Session,
    context: TrustedContext,
    *,
    workflow_id: UUID,
    reservation_key: str,
    token_amount: int,
    cost_amount_minor: int = 0,
    window_start: date | None = None,
    token_limit: int = DEFAULT_TENANT_TOKEN_LIMIT,
    cost_limit_minor: int | None = DEFAULT_COST_LIMIT_MINOR,
    scope_key: str | None = None,
) -> BudgetReservationResult:
    if token_amount <= 0 or token_amount > token_limit:
        raise ValidationError("Token reservation is outside the configured limit")
    if cost_amount_minor < 0 or (cost_limit_minor is not None and cost_amount_minor > cost_limit_minor):
        raise ValidationError("Cost reservation is outside the configured limit")
    workflow = session.scalar(select(WorkflowInstance).where(WorkflowInstance.id == workflow_id, WorkflowInstance.tenant_id == context.tenant_id))
    if workflow is None:
        raise NotFoundError("Workflow was not found")
    day = window_start or datetime.now(UTC).date()
    scope_key = scope_key or f"tenant:{context.tenant_id}"
    window = session.scalar(select(AnalysisBudgetWindow).where(AnalysisBudgetWindow.scope_key == scope_key, AnalysisBudgetWindow.window_start == day).with_for_update())
    if window is None:
        window = AnalysisBudgetWindow(tenant_id=None if scope_key == "deployment" else context.tenant_id, scope_key=scope_key, window_start=day, token_limit=token_limit, cost_limit_minor=cost_limit_minor)
        session.add(window)
        session.flush()
    elif window.token_limit != token_limit or window.cost_limit_minor != cost_limit_minor:
        raise ConflictError("Budget window configuration changed during analysis")
    existing = session.scalar(select(AnalysisBudgetReservation).where(AnalysisBudgetReservation.tenant_id == context.tenant_id, AnalysisBudgetReservation.reservation_key == reservation_key).with_for_update())
    if existing is not None:
        if existing.workflow_id != workflow_id or existing.token_reserved != token_amount or existing.cost_reserved_minor != cost_amount_minor:
            raise ConflictError("Budget reservation key already has different values")
        return BudgetReservationResult(existing, window)
    if window.tokens_reserved + window.tokens_used + token_amount > window.token_limit:
        raise ConflictError("Tenant analysis token budget is exhausted")
    if window.cost_limit_minor is not None and window.cost_reserved_minor + window.cost_used_minor + cost_amount_minor > window.cost_limit_minor:
        raise ConflictError("Tenant analysis cost budget is exhausted")
    window.tokens_reserved += token_amount
    window.cost_reserved_minor += cost_amount_minor
    reservation = AnalysisBudgetReservation(tenant_id=context.tenant_id, workflow_id=workflow_id, window_id=window.id, reservation_key=reservation_key, token_reserved=token_amount, cost_reserved_minor=cost_amount_minor)
    session.add(reservation)
    session.flush()
    return BudgetReservationResult(reservation, window)


def reconcile_analysis_budget(
    session: Session,
    context: TrustedContext,
    *,
    reservation_id: UUID,
    token_used: int,
    cost_used_minor: int = 0,
) -> AnalysisBudgetReservation:
    if token_used < 0 or cost_used_minor < 0:
        raise ValidationError("Usage values cannot be negative")
    reservation = session.scalar(select(AnalysisBudgetReservation).where(AnalysisBudgetReservation.id == reservation_id, AnalysisBudgetReservation.tenant_id == context.tenant_id).with_for_update())
    if reservation is None:
        raise NotFoundError("Budget reservation was not found")
    if reservation.status != "RESERVED":
        raise ConflictError("Budget reservation is already reconciled")
    if token_used > reservation.token_reserved or cost_used_minor > reservation.cost_reserved_minor:
        raise ConflictError("Usage exceeded the reserved budget")
    window = session.scalar(select(AnalysisBudgetWindow).where(AnalysisBudgetWindow.id == reservation.window_id).with_for_update())
    if window is None:
        raise NotFoundError("Budget window was not found")
    window.tokens_reserved -= reservation.token_reserved
    window.cost_reserved_minor -= reservation.cost_reserved_minor
    window.tokens_used += token_used
    window.cost_used_minor += cost_used_minor
    reservation.token_used = token_used
    reservation.cost_used_minor = cost_used_minor
    reservation.status = "RECONCILED"
    session.flush()
    return reservation

def create_analysis_decision(
    session: Session,
    context: TrustedContext,
    *,
    project_id: UUID,
    workflow_id: UUID,
    kind: str,
    title: str,
    summary: str,
    safe_details: dict[str, object],
    assessment_id: UUID | None = None,
    evidence_bundle_id: UUID | None = None,
    request_id: UUID | None = None,
    terms_snapshot: dict[str, object] | None = None,
    trace_summary: dict[str, object] | None = None,
) -> AnalysisDecision:
    _project(session, context, project_id)
    workflow = session.scalar(select(WorkflowInstance).where(WorkflowInstance.id == workflow_id, WorkflowInstance.tenant_id == context.tenant_id))
    if workflow is None:
        raise NotFoundError("Workflow was not found")
    if kind not in {"PROPOSAL_REVIEW", "CLARIFICATION", "PROJECT_MAPPING", "INTEGRATION_HEALTH", "ACTION_UNCERTAINTY"}:
        raise ValidationError("Unsupported decision kind")
    if not title.strip() or not summary.strip():
        raise ValidationError("Decision title and summary are required")
    decision = AnalysisDecision(
        tenant_id=context.tenant_id,
        project_id=project_id,
        request_id=request_id,
        workflow_id=workflow_id,
        assessment_id=assessment_id,
        evidence_bundle_id=evidence_bundle_id,
        kind=kind,
        title=title[:240],
        summary=summary[:4000],
        safe_details=safe_details,
        terms_snapshot=terms_snapshot,
        trace_summary=trace_summary or {},
    )
    session.add(decision)
    session.flush()
    return decision


def create_draft_revision(
    session: Session,
    context: TrustedContext,
    *,
    decision_id: UUID,
    payload: dict[str, object],
) -> AnalysisDraftRevision:
    decision = session.scalar(select(AnalysisDecision).where(AnalysisDecision.id == decision_id, AnalysisDecision.tenant_id == context.tenant_id).with_for_update())
    if decision is None:
        raise NotFoundError("Analysis decision was not found")
    previous = session.scalar(select(AnalysisDraftRevision).where(AnalysisDraftRevision.decision_id == decision_id, AnalysisDraftRevision.status == "CURRENT").with_for_update())
    revision_number = (previous.revision + 1) if previous is not None else 1
    if previous is not None:
        previous.status = "SUPERSEDED"
    revision = AnalysisDraftRevision(
        tenant_id=context.tenant_id,
        project_id=decision.project_id,
        request_id=decision.request_id,
        workflow_id=decision.workflow_id,
        decision_id=decision.id,
        revision=revision_number,
        content_hash=canonical_sha256(payload),
        payload=payload,
    )
    session.add(revision)
    session.flush()
    return revision


def list_analysis_decisions(
    session: Session,
    context: TrustedContext,
    *,
    status: str | None = None,
    project_id: UUID | None = None,
    limit: int = 20,
) -> list[AnalysisDecision]:
    if not 1 <= limit <= 100:
        raise ValidationError("Decision limit must be between one and one hundred")
    query = select(AnalysisDecision).where(AnalysisDecision.tenant_id == context.tenant_id)
    if status is not None:
        if status not in {"OPEN", "RESOLVED", "DISMISSED", "STALE"}:
            raise ValidationError("Unsupported decision status")
        query = query.where(AnalysisDecision.status == status)
    if project_id is not None:
        _project(session, context, project_id)
        query = query.where(AnalysisDecision.project_id == project_id)
    return list(session.scalars(query.order_by(AnalysisDecision.created_at.desc()).limit(limit)).all())


def get_analysis_decision(session: Session, context: TrustedContext, decision_id: UUID) -> AnalysisDecision:
    decision = session.scalar(select(AnalysisDecision).where(AnalysisDecision.id == decision_id, AnalysisDecision.tenant_id == context.tenant_id))
    if decision is None:
        raise NotFoundError("Analysis decision was not found")
    return decision


def get_decision_evidence(session: Session, context: TrustedContext, decision_id: UUID) -> list[EvidenceReference]:
    decision = get_analysis_decision(session, context, decision_id)
    if decision.evidence_bundle_id is None:
        return []
    return list(session.scalars(select(EvidenceReference).where(EvidenceReference.tenant_id == context.tenant_id, EvidenceReference.project_id == decision.project_id, EvidenceReference.bundle_id == decision.evidence_bundle_id).order_by(EvidenceReference.fetched_at)).all())


def get_workflow_trace(session: Session, context: TrustedContext, workflow_id: UUID) -> dict[str, object]:
    workflow = session.scalar(select(WorkflowInstance).where(WorkflowInstance.id == workflow_id, WorkflowInstance.tenant_id == context.tenant_id))
    if workflow is None:
        raise NotFoundError("Workflow was not found")
    runs = list(session.scalars(select(AgentRun).where(AgentRun.tenant_id == context.tenant_id, AgentRun.workflow_id == workflow_id).order_by(AgentRun.created_at, AgentRun.node_name, AgentRun.attempt)).all())
    return {
        "workflow_id": str(workflow.id),
        "state": workflow.state,
        "current_phase": workflow.current_phase,
        "policy_version": workflow.policy_version,
        "stages": [
            {
                "role": run.node_name,
                "status": run.status,
                "attempt": run.attempt,
                "usage": run.usage or {},
                "error_code": run.error_code,
                "started_at": run.started_at.isoformat(),
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            }
            for run in runs
        ],
    }

def record_evaluation_run(
    session: Session,
    *,
    dataset_version: str,
    split: str,
    run_number: int,
    model_version: str,
    prompt_version: str,
    tool_policy_version: str,
    metrics: dict[str, object],
) -> AnalysisEvaluationRun:
    if split not in {"development", "held_out"} or not 1 <= run_number <= 3:
        raise ValidationError("Evaluation split or run number is invalid")
    if not dataset_version or not model_version or not prompt_version or not tool_policy_version:
        raise ValidationError("Evaluation versions are required")
    passed = bool(metrics.get("passed", False))
    existing = session.scalar(select(AnalysisEvaluationRun).where(AnalysisEvaluationRun.dataset_version == dataset_version, AnalysisEvaluationRun.split == split, AnalysisEvaluationRun.run_number == run_number, AnalysisEvaluationRun.model_version == model_version, AnalysisEvaluationRun.prompt_version == prompt_version, AnalysisEvaluationRun.tool_policy_version == tool_policy_version).with_for_update())
    if existing is not None:
        if existing.metrics != metrics:
            raise ConflictError("Pinned evaluation run already has different metrics")
        return existing
    row = AnalysisEvaluationRun(dataset_version=dataset_version, split=split, run_number=run_number, model_version=model_version, prompt_version=prompt_version, tool_policy_version=tool_policy_version, metrics=metrics, passed=passed)
    session.add(row)
    session.flush()
    return row

def reserve_deployment_budget(
    session: Session,
    context: TrustedContext,
    *,
    workflow_id: UUID,
    reservation_key: str,
    token_amount: int,
    cost_amount_minor: int = 0,
    window_start: date | None = None,
    token_limit: int = 1_000_000,
    cost_limit_minor: int | None = None,
) -> BudgetReservationResult:
    """Reserve the deployment-wide daily allowance in the same durable ledger."""
    return reserve_analysis_budget(
        session,
        context,
        workflow_id=workflow_id,
        reservation_key=reservation_key,
        token_amount=token_amount,
        cost_amount_minor=cost_amount_minor,
        window_start=window_start,
        token_limit=token_limit,
        cost_limit_minor=cost_limit_minor,
        scope_key="deployment",
    )