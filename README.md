# ScopeGuard

ScopeGuard is an evidence-backed scope-change workflow for independent software freelancers. The repository implements the Phase 00–06 local domain, approval, provider-adapter, and Gmail lifecycle paths. AWS/provider live acceptance remains open until deployed endpoints and controlled real-account observations are recorded.

## Prerequisites

- Python 3.11 and uv 0.11+
- Node.js 20.9+ and pnpm 10+
- Docker for the PostgreSQL 16.6 development database
- AWS, Gmail, SES and Razorpay Test Mode accounts for deployed Phase 00 verification

Python dependencies and commands are managed with uv.

## Local setup

~~~powershell
Copy-Item .env.example .env
uv sync --locked --dev
pnpm.cmd install --frozen-lockfile
docker compose up -d postgres
uv run alembic upgrade head
~~~

Set `SCOPEGUARD_ALLOW_DEV_AUTH=true` only while `SCOPEGUARD_ENVIRONMENT=development`. Start the API and web application in separate terminals:

~~~powershell
uv run uvicorn services.api.app:app --reload --port 8000
pnpm.cmd dev:web
~~~

Open `http://localhost:3000/sign-in`. With `NEXT_PUBLIC_ALLOW_MANUAL_TOKEN=true`, use `dev:00000000-0000-4000-8000-000000000001`, then complete onboarding. Alternatively, provision the same synthetic owner before sign-in:

~~~powershell
uv run python scripts/bootstrap_owner.py --cognito-sub 00000000-0000-4000-8000-000000000001 --verified-email owner@example.com
~~~

For a deployed user pool, set `NEXT_PUBLIC_COGNITO_DOMAIN`, `NEXT_PUBLIC_COGNITO_CLIENT_ID`, and `NEXT_PUBLIC_COGNITO_REDIRECT_URI`; set manual-token access to false. The browser uses Cognito authorization code flow with S256 PKCE and validates OAuth state before token exchange. The onboarding API requires a verified email claim.

## Verification

~~~powershell
uv run ruff check services scripts migrations tests
uv run mypy services scripts
uv run pytest
pnpm.cmd contracts:generate
pnpm.cmd lint
pnpm.cmd typecheck
pnpm.cmd build
uvx cfn-lint infra/cloudformation/foundation.yaml
uv run python scripts/check_readiness.py
~~~

To include PostgreSQL-specific checks, point `SCOPEGUARD_DATABASE_URL` at a migrated disposable database and set `RUN_POSTGRES_TESTS=1` before `uv run pytest`. The regular suite also uses SQLite with foreign keys enabled for fast invariant checks.

## Current boundaries

Implemented locally: uv-managed Python environment, FastAPI/Lambda entry point, Cognito JWT verifier, PKCE sign-in callback, verified-email onboarding, tenant-scoped foundational APIs, PostgreSQL migration, immutable preference/calendar records, exact money/terms utilities, connector deny-by-default policy, Next.js management screens, a linted CloudFormation foundation, and an AgentCore/Strands readiness entry point.

Pending actual-account evidence: AWS deployment and region intersection, AgentCore model invocation, deployed Cognito callback, private Aurora/RDS Proxy path, Gmail OAuth/read/send/watch, SES delivery, Razorpay Test Mode link/reconciliation, and end-to-end traces. These remain release blockers.

See [plans/README.md](plans/README.md), [docs/PRD.md](docs/PRD.md), [docs/TDD.md](docs/TDD.md), and [Phase 0/1 evidence](docs/implementation-evidence/phase-01-foundation.md).