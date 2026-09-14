# Phase 00 — Account readiness and deployed feasibility

**Status:** In progress — deployed runtime and budget gates verified; live Gmail/SES delivery, Razorpay correlation, and full cloud recreation remain | **Required:** Yes | **Depends on:** None
**Owns:** R17; A21, A29
**References:** [Master](MASTER_PLAN.md), TDD §5–11, §68, §75; [readiness record](../docs/OPERATIONS.md), [threat model](../docs/THREAT_MODEL.md).

## Objective and boundary

Prove the chosen architecture can run with the actual demo accounts before building the full product. Deliver a thin deployed slice and reproducible configuration. This phase does not claim production approval/payment safety or a finished workflow.

## Ordered implementation tasks

- [ ] P00-01 Inventory AWS, Gmail, Razorpay Test Mode and SES account access, domain/callback requirements, deployment permissions, test recipients and quotas. Record verified facts and blocking dependencies in OPERATIONS §1 without secrets.
- [ ] P00-02 Check current official documentation through Context7 for exact deployment/SDK/API choices. Verify the runtime/model/database region intersection; evaluate ap-south-1 first, recording the actual supported selection. Pin model IDs, Python/Strands/AgentCore/frontend versions, database major, build/migration tools and dependency locks. Record decisions and sources in docs/decisions/.
- [x] P00-03 Scaffold the TDD §67 repository, root setup instructions, configuration schema and example environment files containing placeholders. Select infrastructure tooling and create separate development/test configuration. Keep production/live payment credentials out of the MVP.
- [x] P00-04 Deploy the smallest frontend/Cognito/API path. Validate a server-derived owner identity and rejected unauthorized request; connect to private Aurora through the declared proxy/pool path with a bounded query.
- [ ] P00-05 Invoke a minimal Strands role through deployed AgentCore and the selected Bedrock model. Prove runtime identity, outbound connectivity, private database access through the intended service boundary, timeout behavior and a correlated redacted trace.
- [ ] P00-06 Exercise scoped Gmail read/search and a controlled exact-content send with recorded test authorization. Verify push/watch feasibility, OAuth account identity and permitted scopes. Prove SES delivery to an eligible verified test recipient. Label actual receipt separately from provider acceptance.
- [ ] P00-07 Verify Razorpay Test Mode link creation, exact INR units, same-account/environment reference lookup and webhook feasibility using a controlled test intent. Track real calls against the account's verified limits. Preserve an ambiguous result for review; never repeat an uncertain create merely to finish the spike.
- [ ] P00-08 Document the connector manifest and deterministic write boundary; check available read-path fallback against equivalent authorization and response semantics. Missing real provider capability is a blocker, not a reason to label fixtures live.
- [x] P00-09 Set reviewed model prices and explicit monetary/token limits before enabling analysis. Record estimated infrastructure cost drivers, operator-configured ceilings, database connection reserve and teardown/reset instructions.
- [ ] P00-10 Recreate the slice from declared setup in a clean test environment, or record exactly which existing prerequisites are required. Store sanitized A21/A29 observations with configuration/commit versions and list remaining full-journey checks.

## Implementation state — 14 September 2026

P00-03 and P00-09 are complete. Deployed Cognito SRP authentication, onboarding, server-derived owner identity, one cross-tenant resource boundary, and the private Aurora/RDS Proxy readiness path are now observed. A fresh local PostgreSQL 16.6 database was recreated from docker-compose, migrated through 0014, and passed the PostgreSQL foundation suite; the local P00-10 portion is therefore evidenced. The us-east-1 AWS foundation stack has deployed Cognito, private S3, KMS, EventBridge and encrypted logging resources. P00-01, P00-02, P00-05, P00-06, P00-07, P00-08 and P00-10 remain open where external account facts, private-cloud identity/database paths, provider calls, or full cloud recreation are not observed.

See [the readiness run](../docs/implementation-evidence/phase-00-readiness.md).

## Deliverables

- Initial apps/web, services, packages/shared-schemas, infra, tests and fixture structure from TDD §67.
- Pinned dependency/build configuration, secret references, environment boundaries and a migration-tool decision.
- Completed observed readiness fields for required accounts, identities, regions, network and telemetry.
- Minimal deployed path evidence plus an explicit list of spike code to promote or replace in phases 01–02.

## Verification and exit gate

Prove valid/invalid identity, intended database route, actual model invocation, authorized connector read/send and actual notification delivery from the deployed environment. Check that logs contain no credentials, client grants or private message bodies. A29 is initially demonstrated here and repeated against the completed app in phase 09.

The gate remains open if the selected runtime, real Gmail send/read, SES or Razorpay test path is unavailable. Fixture-backed work may continue on independent domain tasks while a provider blocker is tracked, but cannot close M0 or support a release claim.

## Risks, recovery and handoff

External test calls consume quota and may produce lasting test artifacts; use fixed controlled fixtures, bounded calls and recorded intent. Never relax scopes, expose the database or disable approval guards to pass readiness. Preserve pinned configuration and avoid recreating scarce provider artifacts during routine tests.

Hand off validated versions/accounts/network to [phase 01](PHASE_01_DOMAIN_FOUNDATION.md), plus sanitized provider fixtures for later adapters. Assign owners and estimate remaining milestones using actual spike results.

