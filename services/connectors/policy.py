from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import cast

from services.domain.errors import AuthorizationError


@lru_cache
def load_manifest() -> dict[str, object]:
    path = Path(__file__).with_name("capabilities.json")
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("Connector manifest must be an object")
    return cast(dict[str, object], parsed)


def require_capability(provider: str, capability: str, *, actor: str) -> None:
    providers = load_manifest().get("providers", {})
    config = providers.get(provider) if isinstance(providers, dict) else None
    if not isinstance(config, dict):
        raise AuthorizationError("Connector capability is not approved")
    if actor not in {"agent", "reader", "deterministic"}:
        raise AuthorizationError("Unknown connector actor")
    key = (
        "agent_actions"
        if actor == "agent"
        else "read"
        if actor == "reader"
        else "deterministic_actions"
    )
    allowed = config.get(key, [])
    if capability not in allowed:
        raise AuthorizationError("Connector capability is not approved")
