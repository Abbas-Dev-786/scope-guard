from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass

from services.api.config import get_settings


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    observation: str


def command_check(name: str, args: list[str]) -> Check:
    executable = shutil.which(args[0])
    if executable is None:
        return Check(name, "BLOCKED", f"{args[0]} is not installed")
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check(name, "BLOCKED", type(exc).__name__)
    line = (result.stdout or result.stderr).strip().splitlines()
    return Check(
        name,
        "READY" if result.returncode == 0 else "BLOCKED",
        line[0] if line else f"exit {result.returncode}",
    )


def main() -> None:
    settings = get_settings()
    checks = [
        command_check("uv", ["uv", "--version"]),
        command_check("node", ["node", "--version"]),
        command_check("pnpm", ["pnpm.cmd", "--version"]),
        command_check("docker", ["docker", "--version"]),
        command_check("aws_cli", ["aws", "--version"]),
        Check(
            "database_url",
            "READY" if "replace" not in settings.database_url else "BLOCKED",
            "configured without displaying credentials",
        ),
        Check(
            "cognito",
            "BLOCKED"
            if settings.cognito_user_pool_id.startswith("replace")
            or settings.cognito_client_id.startswith("replace")
            else "CONFIGURED_UNVERIFIED",
            "configuration placeholders checked; actual issuer call is a separate test",
        ),
        Check(
            "bedrock_model",
            "BLOCKED"
            if settings.bedrock_model_id.startswith("replace")
            else "CONFIGURED_UNVERIFIED",
            "model identifier checked; invocation is a separate actual-account test",
        ),
        Check(
            "model_cost_ceiling",
            "BLOCKED" if settings.max_model_cost_minor_per_day <= 0 else "CONFIGURED_UNVERIFIED",
            "positive operator ceiling required before analysis",
        ),
        Check(
            "dev_auth",
            "LOCAL_ONLY" if settings.allow_dev_auth else "DISABLED",
            f"environment={settings.environment}",
        ),
    ]
    print(json.dumps({"phase": "00", "checks": [asdict(check) for check in checks]}, indent=2))
    if any(check.status == "BLOCKED" for check in checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
