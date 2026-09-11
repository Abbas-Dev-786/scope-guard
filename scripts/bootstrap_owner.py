from __future__ import annotations

import argparse
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from services.api.database import SessionLocal
from services.domain.models import PreferenceVersion, User


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision one verified ScopeGuard tenant owner")
    parser.add_argument("--cognito-sub", required=True)
    parser.add_argument("--verified-email", required=True)
    parser.add_argument("--timezone", default="Asia/Kolkata")
    args = parser.parse_args()
    try:
        ZoneInfo(args.timezone)
    except ZoneInfoNotFoundError as exc:
        raise SystemExit(f"Unknown IANA timezone: {args.timezone}") from exc
    with SessionLocal.begin() as session:
        if session.scalar(select(User).where(User.cognito_sub == args.cognito_sub)):
            raise SystemExit("That Cognito subject is already provisioned")
        tenant_id = uuid.uuid4()
        session.add(
            User(
                id=tenant_id,
                cognito_sub=args.cognito_sub,
                verified_email=args.verified_email.strip().casefold(),
                timezone=args.timezone,
            )
        )
        session.flush()
        session.add(
            PreferenceVersion(
                tenant_id=tenant_id,
                version=1,
                rate_minor=100_000,
                minimum_minor=1_500_000,
                increment_minor=50_000,
                communication_style="professional",
                reminder_policy={"approval_required": True, "steps_days": [3, 7, 14]},
            )
        )
    print(f"Provisioned tenant {tenant_id}")


if __name__ == "__main__":
    main()
