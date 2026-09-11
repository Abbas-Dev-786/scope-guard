# Phase 08 — Approved reminders, metrics and data lifecycle

**Status:** Not started | **Required:** Yes | **Depends on:** Phases 05–07  
**Owns:** R12, R14, completion of R16; A14, A25, A30  
**References:** [Master](MASTER_PLAN.md), [PRD](../docs/PRD.md) §15, §19, §24, §27; [TDD](../docs/TDD.md) §40–41, §46–48, §61–66; [operations](../docs/OPERATIONS.md) §3–6.

## Objective and boundary

Complete safe payment follow-up, meaningful totals and enforceable privacy lifecycle. Security and audit controls already exist; this phase adds their user workflows, retention execution and restore-compatible deletion records.

## Ordered implementation tasks

- [ ] P08-01 Add versioned reminder policy/steps, draft revisions, exact approvals and scheduling history. Compute overdue eligibility from the frozen agreed due instant, not link creation/replacement time.
- [ ] P08-02 Implement the Payment reminder role as an internal drafter: due+3 and due+7 days produce reviewable drafts; due+14 produces a human collection decision. Build list/approve/dismiss UI with recipient/body/version review. MVP sends always require freelancer approval.
- [ ] P08-03 Immediately before dispatch, reconcile provider collection to a result no more than 30 seconds old; acquire the payment-version guard using the canonical lock order. Cancel an obsolete queued action if paid state is already committed. Record the residual race when a payment arrives after dispatch begins.
- [ ] P08-04 Deduplicate reminder step/action/notification scheduling under overlapping workers and retries. Suppress reminders for paid/reversed/review-ineligible/disconnected/deleted states according to the canonical lifecycle; do not silently enable provider reminders.
- [ ] P08-05 Implement dashboard aggregates from authoritative accepted and collection facts. Revenue Protected posts once on client acceptance; collected is independent and net of reversals. Keep gross test amounts and test/live environment boundaries explicit; outstanding follows canonical collection obligations.
- [ ] P08-06 Complete operational views for mapping/clarification/stale revision, unknown actions, payment review and integration health. Ensure every required failure state has an actionable authorized path, not just a raw enum.
- [ ] P08-07 Implement authenticated account export with scoped private artifacts and bounded expiry. Include owned domain/evidence/audit data permitted by the policy; exclude secrets, bearer tokens and unrelated tenant records.
- [ ] P08-08 Implement account/project deletion jobs and status endpoints. Immediately disable processing, revoke capabilities/sessions and cancel unsent work; remove credentials and stop integrations asynchronously. Persist deletion tombstones that can be reapplied after restoring older backups.
- [ ] P08-09 Implement documented retention: raw/non-cited content 30 days; active cited artifacts/contracts/audit facts while active; deletion 90 days after archive or by user request; logs 30 days; primary deletion within seven days and backups aging out within 30 days. Purge transient grants daily and record exceptions/failures rather than claiming premature completion.
- [ ] P08-10 Enforce immutable audit/evidence write roles while supporting privileged, audited lifecycle deletion. Delete database records, search chunks and all relevant object versions in policy order; retain only the minimum permitted tombstone/operational proof.
- [ ] P08-11 Configure and exercise lifecycle schedules and alarms. Repeated deletion failure, stale jobs, uncertainty and connector/payment freshness must identify an accountable operator and next action.
- [ ] P08-12 Prepare restore fixtures containing a deleted tenant/project, waiting approval, pending payment, previously sent action, expired capability and retained evidence. Provide a tombstone replay and external-write-disable procedure for phase 09.

## Verification

A14 tests two reminder workers, duplicate schedules, paid-before-claim, paid-before-dispatch and payment-after-dispatch. Exactly one approved step dispatches where eligible; document the unavoidable in-flight timing case without claiming zero race.

A25 tests acceptance, duplicate payment observations, revised/waived orders and reversal: approved totals increment once on acceptance and collection remains independent. Test same-value records in a different tenant or environment.

A30 tests forbidden audit/revision rewrites, exports, deletion across object versions/records, retry idempotency and restoration of a pre-deletion backup. Phase 09 completes measured end-to-end restore proof.

## Exit gate and handoff

Approved reminders respect fresh paid state, financial dashboards reconcile to authoritative records and privacy workflows have verifiable lifecycle outcomes. No deleted tenant or cancelled action becomes eligible during routine replay.

Hand off all acceptance evidence, runbooks and restore fixtures to [phase 09](PHASE_09_RELEASE.md). A retention code deployment does not prove backup expiry occurred; record measured drills and outstanding time-based obligations honestly.

