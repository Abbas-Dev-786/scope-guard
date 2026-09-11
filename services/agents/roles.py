from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from time import monotonic
from uuid import UUID

from services.connectors.policy import load_manifest
from services.domain.auth import TrustedContext
from services.domain.errors import AuthorizationError, ConflictError, ValidationError

from .limits import AnalysisLimits, validate_node_timeout, validate_tool_timeout
from .validation import validate_safe_summary

RoleCallable = Callable[[Mapping[str, object], AnalysisLimits], object]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    provider: str
    operation: str
    read_only: bool = True
    timeout_seconds: float = 15.0

    def __post_init__(self) -> None:
        validate_tool_timeout(self.timeout_seconds)
        if not self.read_only:
            raise AuthorizationError("Reasoning roles can only receive read-only tools")


@dataclass(frozen=True, slots=True)
class RoleDefinition:
    name: str
    responsibility: str
    tools: tuple[ToolDefinition, ...]
    output_schema: str

    def __post_init__(self) -> None:
        if not self.name or not self.responsibility:
            raise ValidationError("Role definitions require a name and responsibility")
        if any(not tool.read_only for tool in self.tools):
            raise AuthorizationError("Role tool manifest contains a mutation capability")


ROLE_DEFINITIONS: tuple[RoleDefinition, ...] = (
    RoleDefinition(
        "contract_structure",
        "Extract candidate scope items from authorized contract chunks; never confirm scope or price work.",
        (),
        "ValidatedScopeCandidate",
    ),
    RoleDefinition(
        "scope",
        "Classify the request against the confirmed baseline and accepted amendments.",
        (),
        "ScopeRoleOutput",
    ),
    RoleDefinition(
        "evidence",
        "Retrieve authorized immutable evidence and report coverage or contradictions.",
        (ToolDefinition("contract.search", "internal", "contract.search"), ToolDefinition("gmail.read", "gmail", "messages.get")),
        "EvidenceRoleOutput",
    ),
    RoleDefinition(
        "impact",
        "Break supported additional work into bounded effort ranges and dependencies.",
        (),
        "ImpactRoleOutput",
    ),
    RoleDefinition(
        "change_order",
        "Draft the proposal content from validated evidence and impact only.",
        (),
        "ChangeOrderRoleOutput",
    ),
    RoleDefinition(
        "communication",
        "Draft a factual client message without send credentials or provider tools.",
        (),
        "CommunicationRoleOutput",
    ),
)


@dataclass(frozen=True, slots=True)
class RoleStageResult:
    role: str
    status: str
    output: object | None
    duration_ms: int
    retry_count: int = 0
    evidence_count: int = 0
    safe_summary: str = ""


@dataclass(frozen=True, slots=True)
class ScopedReadContext:
    context: TrustedContext
    project_id: UUID
    workflow_id: UUID
    allowed_resource_ids: frozenset[str] = frozenset()

    def authorize_result(self, *, tenant_id: UUID, project_id: UUID, resource_id: str | None = None) -> None:
        if tenant_id != self.context.tenant_id or project_id != self.project_id:
            raise AuthorizationError("Read result is outside the trusted analysis scope")
        if resource_id is not None and self.allowed_resource_ids and resource_id not in self.allowed_resource_ids:
            raise AuthorizationError("Read result resource is outside the allowed set")


class RoleGraph:
    """Small deterministic orchestration shell; provider model invocation stays behind role callables."""

    def __init__(self, *, definitions: tuple[RoleDefinition, ...] = ROLE_DEFINITIONS, limits: AnalysisLimits | None = None) -> None:
        self.definitions = definitions
        self.limits = limits or AnalysisLimits()
        self._by_name = {definition.name: definition for definition in definitions}
        self._results: list[RoleStageResult] = []

    @property
    def results(self) -> tuple[RoleStageResult, ...]:
        return tuple(self._results)

    def run_role(self, role: str, payload: Mapping[str, object], invoke: RoleCallable) -> RoleStageResult:
        definition = self._by_name.get(role)
        if definition is None:
            raise ValidationError("Unknown analysis role")
        self.limits.check_deadline()
        validate_node_timeout(60.0)
        started = monotonic()
        try:
            output = invoke(payload, self.limits)
            summary = validate_safe_summary(f"{role} role completed")
            result = RoleStageResult(role, "SUCCEEDED", output, int((monotonic() - started) * 1000), safe_summary=summary)
        except ConflictError as exc:
            result = RoleStageResult(role, "CLARIFICATION", None, int((monotonic() - started) * 1000), safe_summary=str(exc)[:1000])
        except Exception as exc:
            result = RoleStageResult(role, "FAILED", None, int((monotonic() - started) * 1000), safe_summary=f"{role} role failed: {type(exc).__name__}")
        self._results.append(result)
        return result

    def run_pipeline(self, inputs: Mapping[str, object], invocations: Mapping[str, RoleCallable]) -> tuple[RoleStageResult, ...]:
        for definition in self.definitions:
            invoke = invocations.get(definition.name)
            if invoke is None:
                continue
            self.run_role(definition.name, inputs, invoke)
            if self._results[-1].status in {"CLARIFICATION", "FAILED"}:
                break
        return self.results


def read_only_role_manifest() -> dict[str, object]:
    """Build a deny-by-default manifest with no deterministic actions or credentials."""
    manifest = load_manifest()
    providers = manifest.get("providers", {})
    if not isinstance(providers, dict):
        raise AuthorizationError("Connector manifest providers are invalid")
    safe: dict[str, list[str]] = {}
    for provider, config in providers.items():
        if not isinstance(config, dict):
            raise AuthorizationError("Connector manifest provider config is invalid")
        reads = config.get("read", [])
        actions = config.get("agent_actions", [])
        if not isinstance(reads, list) or not isinstance(actions, list) or actions:
            raise AuthorizationError("Agent manifest contains mutation or malformed capabilities")
        safe[str(provider)] = [str(item) for item in reads]
    return {"schema_version": manifest.get("schema_version", 1), "default_policy": "deny", "read": safe}


def validate_tool_inventory(provider: str, inventory: Mapping[str, Mapping[str, object]]) -> None:
    """Fail closed when discovered names or schemas differ from reviewed manifest."""
    manifest = load_manifest().get("providers", {})
    config = manifest.get(provider) if isinstance(manifest, dict) else None
    allowed = config.get("read", []) if isinstance(config, dict) else []
    if not isinstance(allowed, list):
        raise AuthorizationError("Reviewed tool manifest is malformed")
    for name, schema in inventory.items():
        if name not in allowed:
            raise AuthorizationError("Discovered tool is not in the reviewed read manifest")
        if not isinstance(schema, Mapping) or schema.get("read_only") is not True:
            raise AuthorizationError("Discovered tool schema is not explicitly read-only")