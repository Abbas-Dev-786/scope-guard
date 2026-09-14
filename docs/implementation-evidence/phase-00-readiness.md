# Phase 00 readiness record

**Observed:** 14 September 2026
**Commit:** repository initialized on `main`; no commit created
**Environment:** local Windows workspace plus AWS us-east-1 development account
**Overall status:** Staging API, private-database readiness, Bedrock model access, and AgentCore runtime are verified; Gmail/SES delivery, Razorpay correlation, and full cloud-recreation evidence remain open

| Item | Current observation | Status |
| --- | --- | --- |
| uv/Python | uv 0.11.31; CPython 3.11.15; `uv.lock` passes locked use | Local verified |
| Node/pnpm | Node 22.14.0; pnpm 10.6.1; Next.js 16.2.9 pinned | Local verified |
| Database | PostgreSQL 16.6 container migrated into a fresh verification database; `alembic check` reports no drift | Local verified |
| API/domain | FastAPI/Lambda entry point, OpenAPI contracts and 30 tests pass, including PostgreSQL checks | Local verified |
| Frontend | Next.js production build passes with sign-in, PKCE callback, onboarding, preferences, client/contact and project routes | Local verified |
| Infrastructure | Foundation CloudFormation passes current `cfn-lint`; KMS, private S3, Cognito, EventBridge and encrypted log group are declared | Local verified |
| AWS CLI/account | AWS CLI 2.36.40; deployment profile scopeguard-deploy resolves to arn:aws:iam::359465684083:user/scopeguard-deployer | Verified (us-east-1) |
| AWS region | Nova Lite is ACTIVE in ap-south-1 and us-east-1; Aurora PostgreSQL 16.6 is not offered as a standard version in either region, so the deployed us-east-1 choice remains conditional on the production Aurora major/proxy decision | Partial |
| AgentCore/model | `amazon.nova-lite-v1:0` direct invocation and AgentCore runtime invocation returned `READY`; runtime ARN and trace delivery recorded below | Deployed verified; three-run evaluation recorded |
| Cognito | User pool us-east-1_B14OYNOU6, client 34e5mk01lk0itt0vpr46p5rgj4, hosted domain and localhost callback deployed; deletion protection is ACTIVE | Deployed verified |
| Local authentication | Missing token 401, wrong development token 401, exact provisioned synthetic identity 200 against PostgreSQL | Local verified |
| Gmail | Deny-by-default capability boundary exists; OAuth/read/watch/send account evidence is absent | Blocked external |
| SES | Sender identity is verified and account is sandboxed; actual notification receipt is absent | Partial |
| Razorpay | Test Mode account read accepted; existing paid link observed, but ScopeGuard payment-request correlation is not proven | Partial |
| Telemetry | Request IDs and audit correlation are implemented; encrypted /scopeguard/development/operations log group deployed with 30-day retention | Partial |
| Model costs | Staging uses reviewed Nova Lite rates in micro-USD and a 10,000,000 micro-USD/day ceiling; local development remains fail-closed by default | Staging verified |

A21/A29 remain open only for the still-pending provider and clean-recreation variants; the deployed AgentCore, direct model, API/database health, and protected-route portions are recorded as verified. Local fixtures, imports, linting and builds do not substitute for provider or deployed-runtime behavior. The retained empty bucket from the failed first create is scopeguard-359465684083-development-us-east-1; the active stack uses scopeguard-359465684083-development-us-east-1-v2.

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

Record live Cognito/object authorization, private cloud database route, Gmail read/send/watch, SES receipt, ScopeGuard-created Razorpay payment correlation, and full cloud recreation. Use the [live-gate operator runbook](live-gate-operator-runbook.md).

## Verification update â€” 14 September 2026

- Staging API image `phase7-20260914-m10` was published and the synchronized CloudFormation stack now records image `m10` / revision `42`; both API and worker Lambdas reported `Active` with successful updates.
- `GET /health/live` returned HTTP 200 and `GET /health/ready` returned HTTP 200; the readiness endpoint executes `SELECT 1` through the Lambda database connection.
- Unauthenticated protected routes `/api/v1/me` and `/api/v1/integrations/health` returned HTTP 401.
- `pnpm typecheck`, `pnpm lint`, `pnpm build`, the full Python test suite, OpenAPI generation, Alembic drift check, and both CloudFormation templates passed verification.
- A minimal direct Bedrock `amazon.nova-lite-v1:0` invocation returned `READY`.
- AgentCore runtime `services_agents_runtime-An2wIED6Jp` deployed successfully in `us-east-1`; the bounded invocation returned `{"output":"READY\\n","role":"readiness"}` and CloudWatch/X-Ray observability was enabled. Three consecutive bounded invocations returned the same readiness response.
- Cognito pool deletion protection is ACTIVE; the OAuth client is configured for authorization-code flow and the localhost callback.
- SES account read-only checks show sandbox mode, 200/day quota, 1/sec rate, and a verified sender. One controlled `SendEmail` request from the verified sender to itself was accepted; inbox receipt is not claimed.
- Razorpay Test Mode credentials/account identity passed a read-only `GET /v1/payment_links` check. An existing paid INR 1,500,000 link was observed, but its local ScopeGuard payment-request correlation is not proven.
- Staging carries reviewed Nova Lite rates in micro-USD: input `60`, output `240`, daily ceiling `10,000,000`, version `aws-bedrock-nova-lite-v1-2026-08-01`; see `docs/decisions/0003-model-pricing.md`.

Remaining Phase 00â€“07 evidence: controlled Gmail OAuth/read/send/watch and SES inbox receipt, one ScopeGuard-created Razorpay link paid and reconciled through its signed webhook, deployed object-authorization evidence and full cloud-stack recreation. Fixtures and unrelated provider links do not close those gates.

## Clean local recreation — 14 September 2026

A fresh PostgreSQL 16.6 database named `scopeguard_clean_20260914` was created from the declared `docker-compose.yml` service. `uv run alembic upgrade head` applied migrations `0001_phase_01` through `0014_payment_webhook_async`; `alembic current` reported `0014_payment_webhook_async (head)` and `alembic check` reported no drift. `RUN_POSTGRES_TESTS=1 uv run pytest tests/integration/test_postgres_foundation.py -q` passed 4 tests against that new database. This closes the clean local database recreation portion; full cloud-stack recreation and live-provider authorization remain open for P00-10/A29.
## Current staging recheck — 14 September 2026

- `GET /health/live` returned `{"status":"ok"}` with HTTP 200.
- `GET /health/ready` returned `{"status":"ready"}` with HTTP 200.
- Unauthenticated `GET /api/v1/me` returned HTTP 401.
- CloudFormation stack `scopeguard-staging` is `UPDATE_COMPLETE`, deployment revision `42`, image `359465684083.dkr.ecr.us-east-1.amazonaws.com/scopeguard-api-staging:phase7-20260914-m10`.
## Deployed identity isolation observation — 14 September 2026

Two temporary Cognito SRP users authenticated against the staging pool and onboarded successfully. One owner-created client was readable by its owner (HTTP 200) and returned HTTP 404 to the other tenant; the other tenant's own client-list route returned HTTP 200. All temporary test users were deleted after the run. This closes the deployed owner-identity/basic tenant-boundary portion while the broader P01-04 matrix remains open.
## Private database/proxy recheck — 14 September 2026

The staging API, worker, and migration Lambda URLs were corrected to use `scopeguard-staging-proxy.proxy-cm92iauwqqj3.us-east-1.rds.amazonaws.com` rather than the Aurora cluster endpoint. The missing Lambda-to-proxy security-group ingress rule was added and deployed. CloudFormation `scopeguard-staging` completed successfully; the Aurora cluster is `available` on `aurora-postgresql` 17.7, the RDS Proxy and target group are `CREATE_COMPLETE`, and API live/readiness checks returned HTTP 200. Credentials and full connection URLs are not retained in evidence.
The deployed proxy reported `available` with `RequireTLS=True`; target inspection included AVAILABLE target-health rows. This confirms the proxy/TLS path is operational, while the broader AgentCore private-database role and trace matrix remains open under P00-05/P01-04.
