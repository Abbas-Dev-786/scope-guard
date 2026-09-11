# ADR 0002 — Schema ownership and migration order

**Date:** 7 September 2026  
**Status:** Phase 01 accepted; later table groups planned

## Ownership rule

Users are tenant identities. Every tenant-owned table carries tenant_id and UNIQUE(tenant_id,id); every project-owned table additionally carries project_id and UNIQUE(tenant_id,project_id,id). Relationships use matching composite keys. API queries include the trusted tenant in the predicate and return the same 404 for absent and foreign objects.

The complete per-table ownership and mutation classification is maintained in [schema-table-inventory.md](schema-table-inventory.md).

## Migration groups

1. Phase 01: users, immutable preference versions, clients/contacts, projects, immutable calendar versions, API idempotency and append-only audit events.
2. Phase 02: jobs, outbox, consumer receipts, workflow/action attempts and durable external actions.
3. Phase 03: connections/bindings, documents/chunks, effective scope, communications, requests and evidence provenance.
4. Phase 04: agent runs, assessments, decisions and budget reservations.
5. Phase 05: change orders/revisions, approvals, client capabilities/sessions and notification facts.
6. Phase 07: payment requests/link attempts/observations and provider facts.
7. Phase 08: reminders and deletion lifecycle records.

## Cycles and immutability

Projects are inserted with no current calendar or current scope. The initial immutable calendar is inserted with a project composite foreign key, then the project pointer is updated. The current-calendar composite foreign key is DEFERRABLE INITIALLY DEFERRED in PostgreSQL. Current-scope references are added when scope tables exist in Phase 03.

Preference and calendar business version numbers are independent from mutable row_version. Normal application roles receive INSERT/SELECT only on immutable history; the lifecycle role is separate and is introduced solely for audited deletion. Rollback uses compatible forward repair when removing persisted history would violate evidence or audit commitments.
