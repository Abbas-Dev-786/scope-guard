# Phase 03 contracts, evidence and request routing verification

**Observed:** 8 September 2026
**Environment:** local SQLite fixtures and PostgreSQL 16.6 integration database
**Status:** Complete - implementation acceptance passed

## Implemented evidence

- Migrations `0006_phase3_contracts` and `0007_phase3_event_identity` add documents, upload grants, immutable chunks, scope candidates/effective versions/items/amendments, integration bindings, durable external and communication events, requests/provenance, evidence bundles/references, mapping decisions, and thread assignments.
- Upload completion verifies tenant/project ownership, one-time grant expiry, expected size/MIME, SHA-256, UTF-8 text, PDF/DOCX signatures, archive expansion, page limits and extracted character limits before persisting chunks.
- Extraction has no HTTP, subprocess or provider access. Encrypted/scanned PDFs, corrupt archives/XML, binary text and unsupported MIME types become actionable rejected states, and the worker has an explicit timeout result. Presigned S3 completion validates private-object size, MIME, metadata and body before extraction.
- Scope candidates are separate from confirmed scope. Corrections retain a reason; confirmation creates a new immutable effective version, links source chunks, marks source documents confirmed, and activates the project.
- External delivery IDs deduplicate by tenant/connection. Original resource type, resource ID, source version and content reference are persisted for replay.
- Routing precedence is explicit project, explicit thread assignment, alias, then unique active binding. Multiple or zero candidates create an open routing decision; no fuzzy selection is performed.
- Communications retain source version identity and can associate with many requests. Clarification increments request version; merge and split preserve provenance associations.
- Evidence bundles preserve searched-source snapshots, digest, cutoff, completeness and immutable references with source version, locator, excerpt reference, content hash, fetch time and access scope.
- Authenticated/idempotent API routes expose upload grants, inline or presigned-object completion, authorized document reads/download references, scope correction/confirmation/read, structured candidate extraction, routing decisions, event routing/assignment/replay, and request creation/clarification/merge. The web app exposes contract intake, model extraction, scope review and routing diagnostics screens.

## Verification

~~~text
uv run pytest -q                                      passed (52 passed, 4 skipped)
RUN_POSTGRES_TESTS=1 uv run pytest tests/integration/test_postgres_foundation.py -q
  4 passed
uv run ruff check services tests migrations           passed
uv run mypy services scripts                          passed
uv run alembic upgrade head                           passed through 0007_phase3_event_identity
uv run alembic check                                  passed; no drift
~~~

## Deployment prerequisites

The implementation gates are closed. Live deployment still requires a verified `SCOPEGUARD_BEDROCK_MODEL_ID`, `bedrock:InvokeModel`/stream permissions, `SCOPEGUARD_CONTRACT_OBJECT_BUCKET`, and matching KMS/bucket policies. Missing settings fail closed with explicit pending or validation responses; they do not bypass source or tenant checks. A live Bedrock smoke call on 8 September 2026 returned `READY` with one validated candidate using `amazon.nova-lite-v1:0`. A temporary encrypted S3 put/fetch/delete smoke test also passed against the foundation bucket.
