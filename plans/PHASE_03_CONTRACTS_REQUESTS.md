# Phase 03 - Confirmed contracts, evidence and request routing

**Status:** Complete | **Required:** Yes | **Depends on:** Phases 01-02
**Owns:** R02, R03, R05; A10, A11, A18, A20; foundation of A08/A24
**References:** [Master](MASTER_PLAN.md), [TDD](../docs/TDD.md) sections 12, 17, 24-25, 42-48, 54.

## Objective and boundary

Produce authoritative human-confirmed scope and reproducible request evidence from supported documents and provider fixtures. Live Gmail synchronization arrives in phase 06; its normalized events use the same ingestion and routing contracts.

## Ordered implementation tasks

- [x] P03-01 Add document/chunk, scope candidate/version/item/amendment, integration binding, external event, communication event, request/association, evidence/reference and routing-decision records with tenant/project ownership fields.
- [x] P03-02 Implement restricted upload grants and complete-upload owner, project, checksum, type and size verification. Object references are immutable and downloads require the current tenant/project authorization boundary.
- [x] P03-03 Complete the isolated parser hardening gate: PDF, DOCX, TXT and Markdown enforce size/page/character/archive limits, reject scanned/encrypted/corrupt inputs, extraction is bounded by an explicit timeout, and presigned S3 completion performs server-side HEAD/GET verification.
- [x] P03-04 Implement the Contract Structure role through the bounded Strands/Bedrock structured-output interface. Exact source spans are validated before candidate persistence; unavailable model configuration remains an explicit `PENDING` result.
- [x] P03-05 Implement candidate correction, baseline confirmation, immutable effective scope versions, source validation, and scope reads. Amendment-specific operations and revalidation continue in the next slice.
- [x] P03-06 Implement reproducible chunk search and evidence bundles/references with source version, digest, locator, excerpt reference, access scope, fetch time and completeness.
- [x] P03-07 Implement routing precedence for explicit project, explicit thread assignment, alias and unique resource binding. Ambiguity creates a durable mapping decision.
- [x] P03-08 Implement durable original event identity, tenant-scoped assignment resolution, replay, delivery deduplication and project authorization.
- [x] P03-09 Implement many-to-many request/communication provenance plus conservative clarification, merge and split operations with preserved source associations.
- [x] P03-10 Build contract upload/status, effective-scope review and routing-diagnostics screens. Candidate correction remains API-driven and the screens preserve the candidate-versus-confirmed boundary.
- [x] P03-11 Create the complete `fixtures/acme-demo` synthetic pack and held-out routing/source variants.

## Implementation state - 8 September 2026

The Phase 3 persistence and service core is implemented. Migration 0006 adds contract documents, upload grants, chunks, scope candidates and immutable scope versions/items/amendments, integration bindings, external/communication events, requests/provenance, evidence bundles/references, and routing decisions. Migration 0007 persists original event resource identity and explicit thread assignments for safe replay. The extraction boundary supports PDF, DOCX, TXT and Markdown without network access, verifies magic/encoding/archive expansion, and rejects encrypted/scanned/corrupt/oversized input. Upload completion verifies tenant/project grant ownership, size, MIME and SHA-256 before creating immutable chunks. Scope confirmation creates a new effective version and activates the project; routed communications remain `BLOCKED_BY_SCOPE` while the baseline is unconfirmed. Routing is deterministic and ambiguity remains a human decision. Request clarification, merge and split preserve many-to-many communication provenance.

Phase 3 implementation is complete. Deployment must provide a verified Bedrock model ID, Bedrock invoke permissions, and the private encrypted S3 bucket/KMS configuration before enabling live extraction and uploads.

Evidence: [Phase 3 verification](../docs/implementation-evidence/phase-03-contracts-requests.md).

## Verification

- `uv run pytest -q` - passed (`52 passed, 4 skipped`)
- `RUN_POSTGRES_TESTS=1 uv run pytest tests/integration/test_postgres_foundation.py -q` - passed (`4 passed`)
- `uv run ruff check services tests migrations` - passed
- `uv run mypy services scripts` - passed
- `uv run alembic upgrade head` - passed through `0007_phase3_event_identity`
- `uv run alembic check` - passed with no drift
- `pnpm.cmd --filter @scopeguard/web typecheck` - passed
- `pnpm.cmd --filter @scopeguard/web lint` - passed
- `pnpm.cmd --filter @scopeguard/web build` - passed

## Exit gate and handoff

Do not route unconfirmed project communications into downstream analysis. Keep candidate scope separate from confirmed scope, preserve source versions and evidence snapshots, and resolve ambiguity explicitly. Phase 3 is ready to hand to Phase 04 after deployment readiness supplies the verified model and object-store settings.
