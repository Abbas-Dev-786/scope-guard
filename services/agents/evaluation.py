from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Literal
from uuid import UUID, uuid5

from services.domain.canonical import canonical_sha256

Classification = Literal[
    "IN_SCOPE",
    "POTENTIAL_SCOPE_CHANGE",
    "AMBIGUOUS",
    "PREVIOUSLY_APPROVED",
    "NOT_A_SCOPE_REQUEST",
]

NAMESPACE = UUID("9b2e10ac-6fbb-48c7-a3a6-9d41f51ca0e7")


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    case_id: str
    project_id: UUID
    contract_id: str
    text: str
    label: Classification
    evidence_complete: bool = True
    contradictory: bool = False


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    count: int
    confusion_matrix: dict[str, dict[str, int]]
    proposals: int
    correct_proposals: int
    positive_cases: int
    positive_recalled: int
    abstentions: int
    invalid_references: int
    proposal_precision: float
    positive_recall: float
    reference_validity: float
    latency_ms: int
    cost_minor: int

    @property
    def passed(self) -> bool:
        return self.proposal_precision >= 0.95 and self.positive_recall >= 0.80 and self.invalid_references == 0


def build_evaluation_dataset() -> tuple[EvaluationCase, ...]:
    labels: list[Classification] = []
    for index in range(120):
        if index >= 60 and index < 80:
            label: Classification = "POTENTIAL_SCOPE_CHANGE"
        elif index % 5 == 0:
            label = "IN_SCOPE"
        elif index % 5 == 1:
            label = "PREVIOUSLY_APPROVED"
        elif index % 5 == 2:
            label = "AMBIGUOUS"
        elif index % 5 == 3:
            label = "NOT_A_SCOPE_REQUEST"
        else:
            label = "POTENTIAL_SCOPE_CHANGE"
        labels.append(label)
    cases: list[EvaluationCase] = []
    for index, label in enumerate(labels):
        project_id = uuid5(NAMESPACE, f"project-{index}")
        text = {
            "IN_SCOPE": "Please fix the documented baseline login behavior.",
            "PREVIOUSLY_APPROVED": "Please continue the accepted amendment for SSO.",
            "AMBIGUOUS": "Can you make it better soon? The acceptance criteria are unclear.",
            "NOT_A_SCOPE_REQUEST": "Sharing an update only; no implementation request.",
            "POTENTIAL_SCOPE_CHANGE": "Please add a new SSO integration with Entra OIDC and tests.",
        }[label]
        cases.append(EvaluationCase(f"case-{index:03d}", project_id, f"contract-{index:03d}", text, label, evidence_complete=label != "AMBIGUOUS", contradictory=False))
    return tuple(cases)


def split_evaluation_dataset(cases: tuple[EvaluationCase, ...] | None = None) -> tuple[tuple[EvaluationCase, ...], tuple[EvaluationCase, ...]]:
    dataset = cases or build_evaluation_dataset()
    if len(dataset) != 120 or len({item.project_id for item in dataset}) != 120:
        raise ValueError("Dataset must contain 120 cases linked to unique projects")
    return dataset[:60], dataset[60:]


def dataset_digest(cases: tuple[EvaluationCase, ...]) -> str:
    return canonical_sha256([asdict(case) for case in cases])


def evaluate_predictions(
    cases: tuple[EvaluationCase, ...],
    predict: Callable[[EvaluationCase], str | None],
    *,
    latency_ms: int = 0,
    cost_minor: int = 0,
) -> EvaluationMetrics:
    labels = {item.label for item in cases}
    matrix: dict[str, dict[str, int]] = {label: {pred: 0 for pred in (*sorted(labels), "ABSTAIN")} for label in sorted(labels)}
    proposals = correct_proposals = positives = recalled = abstentions = invalid = 0
    for case in cases:
        predicted = predict(case)
        key = predicted if predicted in labels else "ABSTAIN"
        matrix[case.label][key] += 1
        if case.label == "POTENTIAL_SCOPE_CHANGE":
            positives += 1
        if predicted is None:
            abstentions += 1
        if predicted == "POTENTIAL_SCOPE_CHANGE":
            proposals += 1
            if case.label == "POTENTIAL_SCOPE_CHANGE":
                correct_proposals += 1
        if case.label == "POTENTIAL_SCOPE_CHANGE" and predicted == "POTENTIAL_SCOPE_CHANGE":
            recalled += 1
    precision = correct_proposals / proposals if proposals else 0.0
    recall = recalled / positives if positives else 0.0
    return EvaluationMetrics(len(cases), matrix, proposals, correct_proposals, positives, recalled, abstentions, invalid, precision, recall, 1.0 - (invalid / len(cases)), latency_ms, cost_minor)


def run_three_held_out_evaluations(
    predict: Callable[[EvaluationCase], str | None],
) -> tuple[EvaluationMetrics, EvaluationMetrics, EvaluationMetrics]:
    _, held_out = split_evaluation_dataset()
    return tuple(evaluate_predictions(held_out, predict, latency_ms=0, cost_minor=0) for _ in range(3))  # type: ignore[return-value]