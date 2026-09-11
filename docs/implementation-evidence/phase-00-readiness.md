# Phase 00 readiness record

**Observed:** 8 September 2026  
**Commit:** repository initialized on `main`; no commit created  
**Environment:** local Windows workspace plus AWS us-east-1 development account  
**Overall status:** Foundation stack deployed; provider/runtime/database readiness remains open

| Item | Current observation | Status |
| --- | --- | --- |
| uv/Python | uv 0.11.31; CPython 3.11.15; `uv.lock` passes locked use | Local verified |
| Node/pnpm | Node 22.14.0; pnpm 10.6.1; Next.js 16.2.9 pinned | Local verified |
| Database | PostgreSQL 16.6 container migrated into a fresh verification database; `alembic check` reports no drift | Local verified |
| API/domain | FastAPI/Lambda entry point, OpenAPI contracts and 30 tests pass, including PostgreSQL checks | Local verified |
| Frontend | Next.js production build passes with sign-in, PKCE callback, onboarding, preferences, client/contact and project routes | Local verified |
| Infrastructure | Foundation CloudFormation passes current `cfn-lint`; KMS, private S3, Cognito, EventBridge and encrypted log group are declared | Local verified |
| AWS CLI/account | AWS CLI 2.36.40; deployment profile scopeguard-deploy resolves to arn:aws:iam::359465684083:user/scopeguard-deployer | Verified (us-east-1) |
| AWS region | Foundation resources deployed successfully in us-east-1; Aurora/runtime/model intersection remains unverified | Partial |
| AgentCore/model | SDK, starter toolkit, CLI and readiness entry point are installed; exact model ID and invocation evidence are absent | Blocked external |
| Cognito | User pool us-east-1_B14OYNOU6, client 34e5mk01lk0itt0vpr46p5rgj4, hosted domain and localhost callback deployed; deletion protection is ACTIVE | Deployed verified |
| Local authentication | Missing token 401, wrong development token 401, exact provisioned synthetic identity 200 against PostgreSQL | Local verified |
| Gmail | Deny-by-default capability boundary exists; OAuth/read/watch/send account evidence is absent | Blocked external |
| SES | Foundation requirement is documented; verified sender and receipt evidence are absent | Blocked external |
| Razorpay | Test-only capability boundary exists; merchant/reference/link evidence is absent | Blocked external |
| Telemetry | Request IDs and audit correlation are implemented; encrypted /scopeguard/development/operations log group deployed with 30-day retention | Partial |
| Model costs | Token limits are configured; exact model price and a positive monetary ceiling are absent | Blocked external |

No A21 or A29 result is marked passed. Local fixtures, imports, linting and builds do not substitute for provider or deployed-runtime behavior. The retained empty bucket from the failed first create is scopeguard-359465684083-development-us-east-1; the active stack uses scopeguard-359465684083-development-us-east-1-v2.

## Commands observed

~~~text
uv run pytest -q                                      30 passed
uv run ruff check services scripts tests              passed
uv run mypy services scripts                          25 files passed
pnpm contracts:generate                               passed
pnpm lint / pnpm typecheck / pnpm build               passed
uvx cfn-lint infra/cloudformation/foundation.yaml     passed
alembic upgrade head + alembic check on fresh DB      passed, no drift
aws cloudformation deploy (scopeguard-foundation-development, us-east-1)  CREATE_COMPLETE
aws cloudformation list-stack-resources                         all 9 resources CREATE_COMPLETE
aws cognito-idp describe-user-pool                               deletion protection ACTIVE; MFA OPTIONAL
~~~

## Next evidence needed

Choose an exact Bedrock model and reviewed price; set a positive operator monetary ceiling; deploy the API/database/AgentCore identities; then record actual Cognito authorization, private database route, model invocation, Gmail read/send/watch, SES receipt, Razorpay test creation/reference lookup and a redacted correlated trace.