# Phase 10 — Optional enhancements after the required baseline

**Status:** Not started / optional backlog | **Required:** No  
**Depends on:** Phases 00–08 stable and separate capacity; repeat affected phase 09 gates before inclusion  
**References:** [Master](MASTER_PLAN.md), [PRD](../docs/PRD.md) §21–23, [TDD](../docs/TDD.md) §9–10, §50–51, §63.

## Objective and selection rule

Add only explicitly selected P1 improvements after required behavior is stable. Each item is independently optional. Keep this work off the MVP critical path and disable it by default until its own eligibility/security/quality evidence is complete.

This phase is a future backlog, not authorization to connect additional accounts, send messages, enable automatic reminders or publish anything during the current planning task.

## Independent work packages

- [ ] P10-01 **GitHub read evidence/triggers:** verify actual account and reviewed read manifest; require provider-side read-only permissions. Normalize resource versions and project bindings, preserve exact commit/issue locators, coverage and snapshot hashes. Deny unknown mutation tools/schema changes. Test A04/A05/A10/A11/A18/A21 against fixtures and actual scoped accounts.
- [ ] P10-02 **Slack authorized evidence/events:** verify installation/scopes and authorized channel history availability. Implement authenticated ingress, scoped reads, bounded pagination, deduplication, ambiguous project routing and disconnect behavior using existing contracts. Missing/private/inaccessible history stays a coverage gap. Repeat A04/A10/A11/A18/A21/A22.
- [ ] P10-03 **Frozen PDF rendering:** generate a bounded, sanitized representation before freelancer review and include its exact bytes/digest in the immutable revision. Do not render a materially different attachment after approval. Test renderer isolation, snapshot comparison, A03/A15/A20 and exact sent attachment integrity.
- [ ] P10-04 **Richer trace presentation:** improve persisted event/node summaries, evidence navigation and latency/cost views without exposing secrets, raw private reasoning or unauthorized cross-project data. Repeat trace authorization/redaction checks and test incomplete/recovered runs.
- [ ] P10-05 **Communication-tone memory:** store only scoped, user-controllable tone preferences with retention/deletion support. Never use memory to override rates, scope, evidence, recipient or approval. Verify two-tenant isolation, poisoned-memory behavior, A23 and privacy restore.
- [ ] P10-06 **Policy-authorized automatic reminders:** treat as a separate product/security change. Specify explicit user consent, exact policy/version boundaries, eligible recipients/content, revocation and audit; retain fresh reconciliation and dispatch guards. Update PRD/TDD/threat model and A14/A23/A27 before implementation. MVP exact approval remains active until this separate gate passes.

## Verification and completion per selected item

For each selected package, record the owner, independent scope, account eligibility, schema/API impact, feature flag, failure states, acceptance IDs and actual evidence. Reevaluate agent quality when a new evidence source or memory affects outputs. Recheck canonical proposal hashes if rendering/content changes.

The item is complete only after its own negative/authorization/recovery tests and affected phase 09 checks pass. A disabled optional connector must not break Gmail, contract analysis, approval, collection or deletion.

## Deferred scope

OCR, team accounts, broader enterprise federation, unrestricted autonomous sending and live-money operations remain outside this plan's required delivery. Moving any into scope requires a separate design and acceptance plan rather than treating it as incidental polish.

