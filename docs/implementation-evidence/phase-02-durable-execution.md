# Phase 02 durable execution verification

**Observed:** 8 September 2026
**Environment:** local SQLite unit fixtures and PostgreSQL 16.6 integration database
**Status:** Complete

## Implemented evidence

- Migrations 0002 through 0005 add tenant-scoped jobs, outbox events, consumer receipts, workflow instances, external actions, action attempts, correlation/causation fields, capacity reservations, and an audit immutability trigger.
- Migration 0003 repairs legacy Phase 01 constraint names; migration 0004 keeps workflow job references tenant-safe with restrictive deletion; migration 0005 is PostgreSQL-version compatible and applies cleanly.
- `commit_durable_command` commits domain state, audit, next jobs, and outbox effects together. `execute_consumer_once` returns the original result on duplicate delivery.
- Job claiming uses a 60-second lease, fencing generation, attempt limits, bounded exponential retry delay, terminal review state, and stale-worker rejection. Heartbeat and completion require the current worker and fence.
- Outbox publication commits each attempt marker before network publication and records per-entry failure. Recovery discovers lost wakeups, expired leases, and stale dispatching actions.
- External actions use explicit legal transitions. Provider outcomes distinguish pre-dispatch failure, success, and uncertainty. Unknown outcomes cannot retry without explicit duplicate-risk acknowledgement.
- Analysis capacity is lease-backed, limited to one active reservation per tenant and four globally by default, and recovers expired reservations without blocking protected work.
- Deterministic connector guards validate manifest capability and canonical approved payloads. Read-only agent manifests exclude mutation capabilities and unknown actors are denied.
- Tenant-scoped operational routes expose job listing/retry, action resolution, and health metrics. Correlation fields are bounded and payload-free in observability output.
- Crash injection covers transaction persistence, outbox attempt/publish/result boundaries, job claim, action dispatch persistence, provider success, and action result save.

## Verification

~~~text
uv run pytest -q                                      passed (40 passed, 4 skipped)
RUN_POSTGRES_TESTS=1 uv run pytest tests/integration/test_postgres_foundation.py -q
  4 passed
uv run ruff check services tests                     passed
uv run mypy services scripts                         passed
uv run alembic upgrade head                          passed
uv run alembic check                                 passed; no drift
~~~

## Handoff

Phase 02 does not claim provider-specific live integrations. Later phases must implement each provider adapter against these contracts, preserve the durable intent/attempt records, and reconcile uncertain outcomes before enabling writes.
