# Phase 02 - Durable jobs, audit and external-action control

**Status:** Complete | **Required:** Yes | **Depends on:** Phase 01
**Owns:** R15; A01, A02, A17; foundation of A23/A30/A31
**References:** [Master](MASTER_PLAN.md), [TDD](../docs/TDD.md) section 3, sections 12-16, 46-50, 56, 58-62.

## Objective and boundary

Make every business transition recoverable before attaching agents or live product sends. Build reusable intent, dispatch, reconciliation, capacity, and recovery contracts with fault-injectable provider adapters. Provider-specific completion continues in phases 05-07.

## Ordered implementation tasks

- [x] P02-01 Add jobs, outbox_events, consumer_receipts, workflow_instances, external_actions and action_attempts; protect audit records with a PostgreSQL immutability trigger. Enforce unique business/job/action keys and immutable approved payload references.
- [x] P02-02 Implement transaction helpers that commit domain state, audit, next jobs and outbox together. Duplicate consumer delivery returns the prior logical result. Define and enforce lock order: project -> order -> payment -> action.
- [x] P02-03 Implement outbox publication with per-entry success/failure handling and the one-minute recovery sweep for runnable jobs, lost wakeups, expired leases, and orphaned domain intents.
- [x] P02-04 Implement atomic job claim, 60-second lease, 20-second heartbeat, fencing generation, bounded backoff, and terminal review states. Cap attempts at three within a cumulative deadline/budget. Stale workers cannot commit.
- [x] P02-05 Add analysis concurrency limits of one per tenant/four globally, lease-backed database reservations, recovery of expired reservations, and protected-capacity policy metadata.
- [x] P02-06 Implement external-action states READY, DISPATCHING, RETRY_WAIT, SUCCEEDED, RECEIPT_CONFIRMED, UNKNOWN_OUTCOME, REVIEW_REQUIRED and CANCELLED with legal transitions and persisted dispatch attempts.
- [x] P02-07 Define connector response contracts for definite pre-dispatch failure, definite success and uncertain outcome. Reconciliation uses provider evidence; a search miss remains uncertain.
- [x] P02-08 Implement exact approved-action guards and read-only agent capability manifests. Unknown actors, tools, and changed payloads are denied by default.
- [x] P02-09 Implement tenant-scoped operational job retry/action resolve routes and a minimal trace/health view. Uncertainty resend requires explicit duplicate-risk acknowledgement and receipt confirmation suppresses resend.
- [x] P02-10 Add redacted correlation across request, workflow, job, action and provider observation fields plus queue/uncertainty metrics and health status.
- [x] P02-11 Add deterministic provider fixtures and crash hooks at transaction, publish, claim, dispatch, provider-success and result-save boundaries, with SQLite unit and PostgreSQL integration coverage.

## Implementation state - 8 September 2026

Phase 02 is complete as a reusable local durable-execution slice. PostgreSQL migrations 0002 through 0005 provide the durable schema, legacy constraint repair, safe workflow job deletion behavior, job correlation/causation, capacity reservations, and audit immutability. Worker helpers provide transactionally persisted intent, commit-before-publish outbox handling, idempotent consumer receipts, atomic claims, leases, heartbeats, fencing, bounded retries, expiry recovery, lost-wakeup discovery, orphan-action uncertainty, and explicit duplicate-risk acknowledgement for uncertain external actions. Connector contracts, deterministic capability guards, tenant-scoped operations routes, health metrics, and crash injection hooks are covered by focused tests.

Provider-specific adapters and live send integrations remain owned by later phases; Phase 02 supplies their durable contracts and recovery boundaries.

Evidence: [Phase 02 verification](../docs/implementation-evidence/phase-02-durable-execution.md).

## Verification

- `uv run pytest -q` - passed (`40 passed, 4 skipped`)
- `RUN_POSTGRES_TESTS=1 uv run pytest tests/integration/test_postgres_foundation.py -q` - passed (`4 passed`)
- `uv run ruff check services tests` - passed
- `uv run mypy services scripts` - passed
- `uv run alembic upgrade head` - passed
- `uv run alembic check` - passed with no drift

## Exit gate and handoff

The failure harness proves transaction/outbox recovery, bounded fenced execution, capacity lease recovery, and uncertainty state transitions. Operational views expose blocked/review work with actionable reasons. Unknown outcomes remain visible until evidence resolves them. Phase 03 can consume the transaction, job, action, connector, and correlation APIs.
