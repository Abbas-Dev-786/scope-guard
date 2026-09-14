from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from time import perf_counter
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
    allowed_reference_ids: tuple[str, ...] = ()

    def model_input(self) -> EvaluationInput:
        """Return only information a classifier may observe; the gold label stays hidden."""
        return EvaluationInput(
            case_id=self.case_id,
            project_id=self.project_id,
            contract_id=self.contract_id,
            text=self.text,
            evidence_complete=self.evidence_complete,
            contradictory=self.contradictory,
            allowed_reference_ids=self.allowed_reference_ids,
        )


@dataclass(frozen=True, slots=True)
class EvaluationInput:
    case_id: str
    project_id: UUID
    contract_id: str
    text: str
    evidence_complete: bool
    contradictory: bool
    allowed_reference_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvaluationPrediction:
    classification: Classification | None
    reference_ids: tuple[str, ...] = ()


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
        return (
            self.proposal_precision >= 0.95
            and self.positive_recall >= 0.80
            and self.invalid_references == 0
        )


_SCENARIOS: dict[Classification, tuple[str, ...]] = {
    "IN_SCOPE": (
        "Fix the documented baseline login redirect for {component}.",
        "Complete the already-contracted responsive layout for {component}.",
        "Correct the acceptance-tested validation defect in {component}.",
        "Please deliver the contracted CSV field mapping for {component}.",
    ),
    "PREVIOUSLY_APPROVED": (
        "Continue amendment AM-{number} for the approved SSO work in {component}.",
        "Finish the accepted change order covering audit export in {component}.",
        "The signed amendment already adds webhooks to {component}; proceed.",
        "Resume the previously approved accessibility extension for {component}.",
    ),
    "AMBIGUOUS": (
        "Can you make {component} better soon? Acceptance criteria are missing.",
        "Please improve the experience around {component}; scope is not specified.",
        "Something feels off in {component}. Can you handle it?",
        "We may need changes to {component}, but requirements are still undecided.",
    ),
    "NOT_A_SCOPE_REQUEST": (
        "Status update for {component}: stakeholders approved the current demo.",
        "Thanks for the work on {component}; no implementation is requested.",
        "For information only, the {component} launch meeting moved to Friday.",
        "Sharing feedback about {component}; please do not make changes yet.",
    ),
    "POTENTIAL_SCOPE_CHANGE": (
        "Add a new Entra OIDC integration and tests to {component}.",
        "Build a new PDF export workflow for {component}; it is absent from contract.",
        "Add multi-currency invoicing to {component} as a new deliverable.",
        "Create a native mobile offline mode for {component}, beyond baseline scope.",
    ),
}


def build_evaluation_dataset() -> tuple[EvaluationCase, ...]:
    labels: list[Classification] = []
    for index in range(120):
        if 60 <= index < 80:
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

    components = (
        "account settings",
        "billing dashboard",
        "project timeline",
        "client portal",
        "notification center",
        "reporting screen",
    )
    cases: list[EvaluationCase] = []
    for index, label in enumerate(labels):
        project_id = uuid5(NAMESPACE, f"project-{index}")
        template = _SCENARIOS[label][(index // 5) % len(_SCENARIOS[label])]
        text = template.format(component=components[index % len(components)], number=100 + index)
        evidence_complete = label != "AMBIGUOUS"
        contradictory = label == "AMBIGUOUS" and index % 2 == 0
        cases.append(
            EvaluationCase(
                case_id=f"case-{index:03d}",
                project_id=project_id,
                contract_id=f"contract-{index:03d}",
                text=f"{text} [request {index:03d}]",
                label=label,
                evidence_complete=evidence_complete,
                contradictory=contradictory,
                allowed_reference_ids=(f"reference-{index:03d}",),
            )
        )
    return tuple(cases)


def split_evaluation_dataset(
    cases: tuple[EvaluationCase, ...] | None = None,
) -> tuple[tuple[EvaluationCase, ...], tuple[EvaluationCase, ...]]:
    dataset = cases or build_evaluation_dataset()
    if len(dataset) != 120 or len({item.project_id for item in dataset}) != 120:
        raise ValueError("Dataset must contain 120 cases linked to unique projects")
    return dataset[:60], dataset[60:]


def dataset_digest(cases: tuple[EvaluationCase, ...]) -> str:
    return canonical_sha256([asdict(case) for case in cases])


def _prediction(value: EvaluationPrediction | Classification | None) -> EvaluationPrediction:
    if isinstance(value, EvaluationPrediction):
        return value
    return EvaluationPrediction(value)


def evaluate_predictions(
    cases: tuple[EvaluationCase, ...],
    predict: Callable[[EvaluationInput], EvaluationPrediction | Classification | None],
    *,
    latency_ms: int | None = None,
    cost_minor: int = 0,
) -> EvaluationMetrics:
    labels = {item.label for item in cases}
    matrix: dict[str, dict[str, int]] = {
        label: {pred: 0 for pred in (*sorted(labels), "ABSTAIN")} for label in sorted(labels)
    }
    proposals = correct_proposals = positives = recalled = abstentions = invalid = 0
    started = perf_counter()
    for case in cases:
        prediction = _prediction(predict(case.model_input()))
        predicted = prediction.classification
        key = predicted if predicted in labels else "ABSTAIN"
        matrix[case.label][key] += 1
        invalid += sum(
            reference_id not in case.allowed_reference_ids
            for reference_id in prediction.reference_ids
        )
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
    measured_latency_ms = round((perf_counter() - started) * 1000)
    precision = correct_proposals / proposals if proposals else 0.0
    recall = recalled / positives if positives else 0.0
    return EvaluationMetrics(
        len(cases),
        matrix,
        proposals,
        correct_proposals,
        positives,
        recalled,
        abstentions,
        invalid,
        precision,
        recall,
        1.0 - (invalid / len(cases)),
        measured_latency_ms if latency_ms is None else latency_ms,
        cost_minor,
    )


def run_three_held_out_evaluations(
    predict: Callable[[EvaluationInput], EvaluationPrediction | Classification | None],
    *,
    cost_minor_per_run: int = 0,
) -> tuple[EvaluationMetrics, EvaluationMetrics, EvaluationMetrics]:
    _, held_out = split_evaluation_dataset()
    reports = tuple(
        evaluate_predictions(held_out, predict, cost_minor=cost_minor_per_run) for _ in range(3)
    )
    return reports  # type: ignore[return-value]
