# Phase 01 foundation verification

**Observed:** 8 September 2026  
**Environment:** local synthetic fixtures; PostgreSQL 16.6 constraint tests; AWS us-east-1 foundation stack  
**Status:** Domain foundation and AWS security foundation deployed; private database and runtime identity gates remain open

## Implemented evidence

- A04 foundation: server-derived tenant context, composite ownership foreign keys, request schemas that forbid tenant injection, foreign-object 404 behavior, direct cross-owner FK rejection, and a two-tenant/two-project list-isolation fixture.
- A06: finite Decimal effort strings, ordered and bounded ranges, integer paise, explicit tax, INR-only validation, ceiling rounding, total caps, and the 1,500,000-paise minimum example.
- A16 foundation: canonical enums and event schemas, deterministic JSON/SHA-256, row-version conflicts, immutable business versions, and idempotency content conflicts.
- A27 foundation: full-payment terms, seven calendar days at project-local 17:00, 30-day expiry, pay-before-work policy, IANA timezone validation, and working-day calendars.
- Identity: Cognito issuer/signature/expiry/token-use validation; ID-token audience and access-token client checks; development authentication fails closed outside development.
- Onboarding: a verified-email Cognito principal creates one tenant and initial preference version transactionally; exact retries replay and changed bodies conflict.
- UI: Cognito S256 PKCE callback, development-only manual token gate, onboarding, preferences, client/contact management, and project edit/deletion-pending flows compile in the production build.
- Schema: all TDD section 46 tables have a documented owning phase and mutation class; Phase 01 tables have a PostgreSQL migration with composite ownership constraints and immutable-role grants.
## Deployed foundation evidence

- CloudFormation stack scopeguard-foundation-development is CREATE_COMPLETE in us-east-1.
- Cognito user pool us-east-1_B14OYNOU6, app client 34e5mk01lk0itt0vpr46p5rgj4, hosted domain scopeguard-359465684083-development.auth.us-east-1.amazonaws.com, and localhost PKCE callback are configured.
- Evidence bucket scopeguard-359465684083-development-us-east-1-v2 is private, versioned, and KMS encrypted.
- EventBridge bus scopeguard-development and KMS-encrypted /scopeguard/development/operations log group with 30-day retention are deployed.
- Stack resources verified: KMS key and alias, S3 bucket and policy, Cognito pool/client/domain, EventBridge bus, and operations log group.

## Observed verification

~~~text
uv run pytest -q                                      30 passed
  PostgreSQL-specific                                 3 passed within the suite
uv run ruff check services scripts tests              passed
uv run mypy services scripts                          25 files passed
pnpm contracts:generate                               passed
pnpm lint                                             passed
pnpm typecheck                                        passed
pnpm build                                            passed; dynamic client/project detail routes included
alembic upgrade head + alembic check on fresh DB      passed, no drift
local auth dependency chain                           missing 401; wrong 401; valid 200
~~~

## Gate still open

Actual Cognito tokens and hosted callback behavior have not been observed against a deployed user pool. Private Aurora/RDS Proxy connectivity, deployed worker/tool/cache/download/trace authorization, immutable database roles under deployed identities, and all later feature-resource authorization matrices remain unverified. A04 and A16 therefore stay cross-cutting and are not marked fully passed.