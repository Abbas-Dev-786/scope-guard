from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.domain.auth import TrustedContext
from services.domain.errors import AuthorizationError, ConflictError, NotFoundError, ValidationError
from services.domain.models import AgentRun, ClientContact, RequestRecord, ScopeAmendment, ScopeItem

from .gates import apply_evidence_gate, freeze_terms
from .persistence import (
    create_analysis_decision,
    create_draft_revision,
    create_workflow,
    finish_agent_run,
    record_scope_assessment,
    start_agent_run,
)
from .schemas import (
    ChangeOrderRoleOutput,
    CommunicationRoleOutput,
    EvidenceRoleOutput,
    GateDecision,
    ImpactRoleOutput,
    ProposalPayload,
    ScopeRoleOutput,
)
from .validation import validate_reference_ids


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    workflow_id: UUID
    decision_id: UUID
    assessment_id: UUID
    gate: GateDecision
    draft_revision_id: UUID | None


def _authorized_recipient(session: Session, context: TrustedContext, project_id: UUID, email: str) -> None:
    if "@" not in email or len(email) > 320:
        raise ValidationError("Communication recipient is invalid")
    from services.domain.models import Project

    project = session.scalar(select(Project).where(Project.id == project_id, Project.tenant_id == context.tenant_id))
    if project is None:
        raise NotFoundError("Project was not found")
    contacts = list(session.scalars(select(ClientContact).where(ClientContact.tenant_id == context.tenant_id, ClientContact.client_id == project.client_id)).all())
    if not any(contact.normalized_email == email.strip().lower() for contact in contacts):
        raise AuthorizationError("Communication recipient is not an authorized project contact")


def _persist_role_output(
    session: Session,
    context: TrustedContext,
    *,
    workflow_id: UUID,
    role: str,
    payload: dict[str, object],
    input_snapshot: dict[str, object],
) -> None:
    existing = session.scalar(select(AgentRun).where(AgentRun.workflow_id == workflow_id, AgentRun.node_name == role, AgentRun.attempt == 1).with_for_update())
    if existing is not None and existing.status in {"SUCCEEDED", "REVIEW_REQUIRED", "FAILED"}:
        return
    run = start_agent_run(
        session,
        context,
        workflow_id=workflow_id,
        node_name=role,
        attempt=1,
        model_id="validated-role-output",
        prompt_version="phase4-role-prompt-v1",
        schema_version="phase4-schemas-v1",
        tool_policy_version="read-only-manifest-v1",
        input_snapshot=input_snapshot,
    )
    if run.status in {"RUNNING", "REPAIRING"}:
        finish_agent_run(session, context, run_id=run.id, output=payload, usage={"input_tokens": 0, "output_tokens": 0})




def _validate_scope_references(session: Session, context: TrustedContext, project_id: UUID, preliminary: ScopeRoleOutput) -> None:
    if preliminary.matched_scope_item_ids:
        rows = set(session.scalars(select(ScopeItem.id).where(ScopeItem.id.in_(preliminary.matched_scope_item_ids), ScopeItem.tenant_id == context.tenant_id, ScopeItem.project_id == project_id)).all())
        if rows != set(preliminary.matched_scope_item_ids):
            raise AuthorizationError("Scope role cited an unknown or cross-project scope item")
    if preliminary.matched_amendment_ids:
        rows = set(session.scalars(select(ScopeAmendment.id).where(ScopeAmendment.id.in_(preliminary.matched_amendment_ids), ScopeAmendment.tenant_id == context.tenant_id, ScopeAmendment.project_id == project_id)).all())
        if rows != set(preliminary.matched_amendment_ids):
            raise AuthorizationError("Scope role cited an unknown or cross-project amendment")
    if preliminary.pending_request_ids:
        rows = set(session.scalars(select(RequestRecord.id).where(RequestRecord.id.in_(preliminary.pending_request_ids), RequestRecord.tenant_id == context.tenant_id, RequestRecord.project_id == project_id)).all())
        if rows != set(preliminary.pending_request_ids):
            raise AuthorizationError("Scope role cited an unknown or cross-project request")

def prepare_analysis(
    session: Session,
    context: TrustedContext,
    *,
    project_id: UUID,
    request_id: UUID,
    input_snapshot: dict[str, object],
    preliminary: ScopeRoleOutput,
    evidence: EvidenceRoleOutput | None,
    impact: ImpactRoleOutput | None = None,
    change_order: ChangeOrderRoleOutput | None = None,
    communication: CommunicationRoleOutput | None = None,
    workflow_key: str | None = None,
    policy_version: str = "analysis-policy-v1",
) -> AnalysisResult:
    """Complete a bounded analysis from validated role outputs and persist only safe artifacts."""
    request = session.scalar(select(RequestRecord).where(RequestRecord.id == request_id, RequestRecord.tenant_id == context.tenant_id, RequestRecord.project_id == project_id))
    if request is None:
        raise NotFoundError("Request was not found")
    workflow_snapshot = dict(input_snapshot)
    workflow_snapshot.pop("evidence_reference_ids", None)
    workflow = create_workflow(
        session,
        context,
        workflow_key=workflow_key or f"request:{request_id}:v{request.request_version}",
        input_snapshot=workflow_snapshot,
        project_id=project_id,
        request_id=request.id,
        policy_version=policy_version,
    )
    _validate_scope_references(session, context, project_id, preliminary)
    accepted_ids = set(session.scalars(select(ScopeAmendment.id).where(ScopeAmendment.tenant_id == context.tenant_id, ScopeAmendment.project_id == project_id)).all())
    _persist_role_output(session, context, workflow_id=workflow.id, role="scope", payload=preliminary.model_dump(mode="json"), input_snapshot=input_snapshot)
    if evidence is not None:
        _persist_role_output(session, context, workflow_id=workflow.id, role="evidence", payload=evidence.model_dump(mode="json"), input_snapshot=input_snapshot)
    gate = apply_evidence_gate(preliminary, evidence, accepted_amendment_ids=accepted_ids, required_baseline_complete=evidence is not None)
    evidence_ids = gate.evidence_reference_ids
    evidence_bundle_id = None
    if evidence is not None and evidence_ids:
        references = validate_reference_ids(session, context, project_id=project_id, reference_ids=evidence_ids)
        evidence_bundle_id = references[0].bundle_id
    elif gate.route == "PROPOSAL":
        raise ValidationError("A proposal requires evidence references")
    assessment = record_scope_assessment(
        session,
        context,
        project_id=project_id,
        workflow_id=workflow.id,
        request_id=request.id,
        classification=gate.classification,
        reason=gate.reason,
        coverage_status=(evidence.completeness if evidence is not None else "REQUIRES_CLARIFICATION"),
        input_snapshot=input_snapshot,
        evidence_bundle_id=evidence_bundle_id,
        request_version=request.request_version,
        matched_scope_item_ids=[str(item) for item in preliminary.matched_scope_item_ids],
        matched_amendment_ids=[str(item) for item in preliminary.matched_amendment_ids],
        pending_request_ids=[str(item) for item in preliminary.pending_request_ids],
        required_evidence_queries=preliminary.required_evidence_queries,
        uncertainty=preliminary.uncertainty,
    )
    details: dict[str, object] = {
        "classification": gate.classification,
        "coverage": evidence.completeness if evidence else "REQUIRES_CLARIFICATION",
        "evidence_reference_ids": [str(item) for item in evidence_ids],
        "required_questions": gate.required_questions,
        "uncertainty": preliminary.uncertainty,
    }
    draft_id = None
    if gate.route == "PROPOSAL":
        if impact is None or change_order is None or communication is None:
            raise ConflictError("Proposal route requires impact, change-order, and communication outputs")
        _authorized_recipient(session, context, project_id, communication.recipient_email)
        _persist_role_output(session, context, workflow_id=workflow.id, role="impact", payload=impact.model_dump(mode="json"), input_snapshot=input_snapshot)
        _persist_role_output(session, context, workflow_id=workflow.id, role="change_order", payload=change_order.model_dump(mode="json"), input_snapshot=input_snapshot)
        _persist_role_output(session, context, workflow_id=workflow.id, role="communication", payload=communication.model_dump(mode="json"), input_snapshot=input_snapshot)
        terms = freeze_terms(session, context, project_id=project_id, impact=impact)
        proposal = ProposalPayload(
            title=change_order.title,
            requested_change=change_order.requested_change,
            deliverables=change_order.deliverables,
            exclusions=change_order.exclusions,
            assumptions=change_order.assumptions + impact.assumptions,
            client_explanation=change_order.client_explanation,
            subject=communication.subject,
            plain_text_body=communication.plain_text_body,
            html_body=communication.html_body,
            recipient_email=communication.recipient_email,
            evidence_reference_ids=evidence_ids,
            terms=terms,
        )
        details["effort"] = {
            "low_hours": impact.low_hours,
            "recommended_hours": impact.recommended_hours,
            "high_hours": impact.high_hours,
            "cold_start": impact.cold_start,
            "dependencies": impact.dependencies,
        }
        decision = create_analysis_decision(
            session,
            context,
            project_id=project_id,
            request_id=request.id,
            workflow_id=workflow.id,
            kind="PROPOSAL_REVIEW",
            title=proposal.title,
            summary=proposal.client_explanation,
            safe_details=details,
            assessment_id=assessment.id,
            evidence_bundle_id=evidence_bundle_id,
            terms_snapshot=terms.model_dump(mode="json"),
            trace_summary={"roles": ["scope", "evidence", "impact", "change_order", "communication"], "private_reasoning": False},
        )
        draft_id = create_draft_revision(session, context, decision_id=decision.id, payload=proposal.model_dump(mode="json")).id
    else:
        kind = "CLARIFICATION" if gate.route == "CLARIFICATION" else "INTEGRATION_HEALTH"
        decision = create_analysis_decision(
            session,
            context,
            project_id=project_id,
            request_id=request.id,
            workflow_id=workflow.id,
            kind=kind,
            title="Clarification required" if gate.route == "CLARIFICATION" else "Request covered",
            summary=gate.reason,
            safe_details=details,
            assessment_id=assessment.id,
            evidence_bundle_id=evidence_bundle_id,
            trace_summary={"roles": ["scope", "evidence"], "private_reasoning": False},
        )
    workflow.state = "REVIEW_REQUIRED" if gate.route == "CLARIFICATION" else "SUCCEEDED"
    workflow.current_phase = "DECISION_READY"
    workflow.row_version += 1
    session.flush()
    return AnalysisResult(workflow.id, decision.id, assessment.id, gate, draft_id)
