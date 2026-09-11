from __future__ import annotations

from collections.abc import Mapping

from services.connectors.policy import load_manifest, require_capability
from services.domain.canonical import canonical_sha256
from services.domain.errors import AuthorizationError
from services.domain.models import ExternalAction


def guard_deterministic_action(
    action: ExternalAction,
    *,
    capability: str,
    approved_payload: Mapping[str, object],
) -> None:
    """Require a manifest-approved deterministic action with unchanged content."""
    require_capability(action.provider, capability, actor="deterministic")
    digest = canonical_sha256(dict(approved_payload))
    if digest != action.payload_digest:
        raise AuthorizationError("Approved action payload has changed")
    if action.state not in {"READY", "RETRY_WAIT"}:
        raise AuthorizationError("Action is not dispatchable in its current state")


def read_only_agent_manifest() -> dict[str, object]:
    """Return only read capabilities; mutation capabilities never enter agent context."""
    manifest = load_manifest()
    providers = manifest.get("providers", {})
    if not isinstance(providers, dict):
        return {"schema_version": manifest.get("schema_version", 1), "providers": {}}
    return {
        "schema_version": manifest.get("schema_version", 1),
        "default_policy": "deny",
        "providers": {
            provider: {"read": list(config.get("read", []))}
            for provider, config in providers.items()
            if isinstance(config, dict)
        },
    }