from __future__ import annotations

import json
import os
from dataclasses import replace
from time import perf_counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from strands import Agent
from strands.models import BedrockModel

from services.agents.evaluation import (
    EvaluationInput,
    EvaluationPrediction,
    evaluate_predictions,
    split_evaluation_dataset,
)


class ModelPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classification: Literal[
        "IN_SCOPE",
        "POTENTIAL_SCOPE_CHANGE",
        "AMBIGUOUS",
        "PREVIOUSLY_APPROVED",
        "NOT_A_SCOPE_REQUEST",
    ] | None
    reference_ids: list[str] = Field(default_factory=list)


model_id = os.getenv("SCOPEGUARD_EVAL_MODEL_ID", "amazon.nova-lite-v1:0")
region = os.getenv("AWS_REGION", "us-east-1")
model = BedrockModel(model_id=model_id, region_name=region, temperature=0.0, max_tokens=512)
agent = Agent(
    model=model,
    callback_handler=None,
    system_prompt=(
        "You are the ScopeGuard evaluation classifier. Classify only from the supplied request and observed evidence metadata. "
        "The contract baseline is the stated existing scope: explicitly documented, contracted, acceptance-tested, or already approved work is not a new scope change. "
        "A request that explicitly says new, absent from contract, beyond baseline, or new deliverable is POTENTIAL_SCOPE_CHANGE unless it says it is already approved. "
        "Vague requests with missing requirements are AMBIGUOUS; status, thanks, or information-only messages are NOT_A_SCOPE_REQUEST; signed or accepted amendments are PREVIOUSLY_APPROVED. "
        "Do not invent facts. Return the requested structured output. Use null only when genuinely unsupported."
    ),
)
_, held_out = split_evaluation_dataset()
INPUT_PRICE_MINOR_PER_1K = 60
OUTPUT_PRICE_MINOR_PER_1K = 240
usage = {"input": 0, "output": 0, "calls": 0}

def predict(item: EvaluationInput) -> EvaluationPrediction:
    prompt = (
        "Choose exactly one classification: IN_SCOPE, POTENTIAL_SCOPE_CHANGE, AMBIGUOUS, "
        "PREVIOUSLY_APPROVED, or NOT_A_SCOPE_REQUEST.\n"
        f"case_id={item.case_id}\ncontract_id={item.contract_id}\n"
        f"evidence_complete={item.evidence_complete}\ncontradictory={item.contradictory}\n"
        f"allowed_reference_ids={list(item.allowed_reference_ids)!r}\n"
        f"request={item.text}\n"
        "reference_ids must contain only IDs from allowed_reference_ids and must be [] when none are needed."
    )
    result = agent(prompt, structured_output_model=ModelPrediction)
    output = getattr(result, "structured_output", None)
    if not isinstance(output, ModelPrediction):
        raise RuntimeError("Bedrock returned no validated evaluation output")
    metrics = getattr(result, "metrics", None)
    accumulated = getattr(metrics, "accumulated_usage", {}) if metrics is not None else {}
    if isinstance(accumulated, dict):
        usage["input"] += int(accumulated.get("inputTokens", accumulated.get("input_tokens", 0)) or 0)
        usage["output"] += int(accumulated.get("outputTokens", accumulated.get("output_tokens", 0)) or 0)
    usage["calls"] += 1
    return EvaluationPrediction(output.classification, tuple(output.reference_ids))

reports = []
for run in range(1, 4):
    started = perf_counter()
    input_before = usage["input"]
    output_before = usage["output"]
    report = evaluate_predictions(held_out, predict)
    run_cost_minor = ((usage["input"] - input_before) * INPUT_PRICE_MINOR_PER_1K + (usage["output"] - output_before) * OUTPUT_PRICE_MINOR_PER_1K + 999) // 1000
    report = replace(report, cost_minor=run_cost_minor)
    reports.append({
        "run": run,
        "metrics": {
            "count": report.count,
            "confusion_matrix": report.confusion_matrix,
            "proposals": report.proposals,
            "correct_proposals": report.correct_proposals,
            "positive_cases": report.positive_cases,
            "positive_recalled": report.positive_recalled,
            "abstentions": report.abstentions,
            "invalid_references": report.invalid_references,
            "proposal_precision": report.proposal_precision,
            "positive_recall": report.positive_recall,
            "reference_validity": report.reference_validity,
            "latency_ms": round((perf_counter() - started) * 1000),
            "cost_minor": report.cost_minor,
        },
    })
    print(json.dumps({"completed_run": run, "report": reports[-1], "usage": usage}, sort_keys=True), flush=True)
print(json.dumps({"model_id": model_id, "region": region, "reports": reports, "usage": usage}, sort_keys=True))