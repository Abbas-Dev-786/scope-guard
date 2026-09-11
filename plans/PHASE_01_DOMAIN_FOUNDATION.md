# Phase 01 — Identity, domain contracts and commercial primitives

**Status:** In progress | **Required:** Yes | **Depends on:** Phase 00  
**Owns:** R01 and foundation of R02/R07/R16; A04, A06, A16, A27  
**References:** [Master](MASTER_PLAN.md), [TDD](../docs/TDD.md) §7, §20, §27–28, §46–48, §52–57, §67.

## Objective and boundary

Create a trusted, testable domain layer and authenticated project shell. Implement invariants before asynchronous agents or external writes depend on them. Define the complete schema relationship map now and deliver feature tables incrementally.

## Ordered implementation tasks

- [x] P01-01 Define shared API/event schemas, canonical enums and the transition registry directly from TDD §13/16/47. Generate frontend types from the same source. Separate business revision numbers, row_version, provider event IDs and request identities.
- [x] P01-02 Map every TDD §46 entity, ownership relation, uniqueness rule and immutable field. Plan migrations including cyclic references and pre-routing nullability. Add matching composite unique keys before composite foreign keys; document deletion behavior without cascading away required immutable history.
- [x] P01-03 Implement users, preference versions, clients/contacts, projects and calendar versions. Add tenant/project composite constraints and referencing-column indexes. Use server-derived tenant context; never accept tenant identity from request bodies.
- [ ] P01-04 Implement Cognito session validation and object authorization across service entry points. Define scoped repository access, download/cache/trace keys and trusted worker/tool context constructors. Add verified notification-address behavior without trusting a client-supplied verified flag.
- [x] P01-05 Implement current-user/preferences/client/contact/project routes from TDD §48, bounded pagination, typed errors, request IDs and mutation idempotency. Enforce expected_row_version on edits and reject a reused idempotency key with different request content.
- [x] P01-06 Implement deterministic commercial validation: INR integer paise; finite Decimal effort strings with 0 < low <= recommended <= high <= 1000; contractual rate, minimum fee and rounding; total cap 100,000,000 paise; explicit tax component from zero to total. Invalid effort must fail before minimum-fee calculation.
- [x] P01-07 Implement the supported terms validator and versioned calendar/capacity model. Freeze full-payment policy, seven-calendar-day due instant at 17:00 project IANA time zone, 30-day link expiry and work-start prerequisites. Unsupported contract terms require an explicit manual-handling result.
- [x] P01-08 Implement canonical serialization/hash primitives for later proposals, including exact content and attachment digests. Define immutable version insertion and restricted update roles; schema drift or a reordered serialization cannot silently change approval meaning.
- [x] P01-09 Build login/onboarding, preferences, client/contact and project screens with empty/error/version-conflict states. Project deletion initially marks disabled/pending cleanup and cancels eligibility for new work; complete cleanup in phase 08.
- [x] P01-10 Add CI checks for shared schema generation, application build/type validation, migrations and domain invariants. Use the selected production database major for integration tests, with two tenants and two projects as baseline fixtures.

## Implementation state — 8 September 2026

All local implementation tasks except the cross-cutting remainder of P01-04 are complete. The us-east-1 foundation stack now provides deployed Cognito and encrypted storage/event/logging primitives. P01-04 currently covers Cognito verification, persisted tenant authorization, composite database ownership, verified-email onboarding and connector policy context. Its checkbox stays open until deployed worker/tool/cache/download/trace entry points exist and the same authorization matrix is observed there; the private database gate also remains open.

Evidence: [Phase 01 verification](../docs/implementation-evidence/phase-01-foundation.md) and [schema inventory](../docs/decisions/schema-table-inventory.md).

## Verification

- A04: substitute nested client/project IDs, test unauthorized list/detail/edit and direct invalid foreign-key inserts. Extend the same matrix as later routes/tools/jobs arrive.
- A06: reject malformed, nonfinite, negative, reversed and excessive effort; test fractional rounding and bounds. The synthetic 14 hours at INR 1,000/hour with INR 15,000 minimum yields 1,500,000 paise; do not use floating-point money.
- A16: validate canonical examples and legal/illegal transitions; verify row-version conflict behavior and idempotency body conflicts.
- A27: test unsupported post-delivery terms, explicit zero-tax fixture, calendar-day due dates across weekends/DST and conditional working-day estimates. Freeze UTC instants with their source time zone/version.
- Verify immutable-role restrictions and fresh/existing database migration paths.

## Exit gate and handoff

A new owner can manage isolated project data through authenticated screens. Shared schema/API primitives compile, direct cross-owner relations fail, and money/terms/version tests pass. Publish a schema ownership/migration inventory with no unexplained cyclic references.

Hand off domain services and trusted context to [phase 02](PHASE_02_DURABLE_EXECUTION.md). A04/A16 remain cross-cutting gates; passing foundation tests does not certify future endpoints. Avoid destructive schema rollback; use compatible forward migrations when persisted data would be lost.

