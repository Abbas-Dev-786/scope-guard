# Phase 09 — Recovery proof, hardening and release assets

**Status:** Not started | **Required:** Yes | **Depends on:** Phases 00–08  
**Owns:** R18 and final R17/R16 verification; A31, A32; final confirmation of every acceptance case  
**References:** [Master](MASTER_PLAN.md), [acceptance matrix](ACCEPTANCE_MATRIX.md), [TDD](../docs/TDD.md) §68–78, [operations](../docs/OPERATIONS.md), [threat model](../docs/THREAT_MODEL.md), [brief](../hackathon.md).

## Objective and boundary

Demonstrate that the complete deployed Test Mode MVP is reproducible, safe under the specified failures and ready for its documented submission. Correctness tests are developed in owning phases; this phase assembles release evidence and closes remaining integration gaps.

## Ordered implementation tasks

- [ ] P09-01 Reconcile every PRD R01–R18 requirement, TDD §48 route, §64 screen and A01–A32 case with implemented components and executable evidence. Record missing/failed variants as release blockers. Verify no optional example became an undocumented required feature.
- [ ] P09-02 Run the full deployed adversarial matrix: two tenants/two projects, nested API/tool/job/cache/download/trace IDs, poisoned content, unknown tools, invalid grants, OAuth account switching and forged/mismatched provider observations. Require zero unauthorized external writes and no private-data disclosure.
- [ ] P09-03 Run transaction/provider-boundary fault tests across the complete product: lost wakeups, partial publication, worker/node crashes, stale fences, ambiguous sends/creates, early client acceptance, stale scope, unmatched first payment and reminder races. Verify operator resolution preserves history.
- [ ] P09-04 Execute the release held-out evaluation three times with pinned model/prompt/schema/tool versions. Require TDD §70 thresholds in each run and zero unsupported proposal citations; attach counts, abstention handling, provenance/range checks and observed cost.
- [ ] P09-05 Execute a declared load fixture with event volume, tenant mix and fixture/live provider mix. Measure request-to-card p95 <=120 seconds, durable ingress acknowledgment p95 <=2 seconds, queue lag, database connection reserve and payment/API progress while analysis is saturated or budget-exhausted.
- [ ] P09-06 Stop scheduler/connector paths and fill a bounded queue. Demonstrate the one-minute recovery sweep, two-minute warning/five-minute actionable lag alert, expired-lease alert after two sweeps, uncertainty alert after five minutes and Gmail freshness/watch alerts. Confirm operators can reach the relevant runbook.
- [ ] P09-07 Perform a measured backup restore with outbound writes disabled. Restore compatible database/object versions, check referenced hashes, reapply deletion tombstones and revoke old grants before user access. Convert in-flight writes to uncertain state, reconcile provider evidence, catch up Gmail/payments and verify waiting approval/payment plus already-sent/deleted fixtures before re-enabling dispatch.
- [ ] P09-08 Record actual recovery point/time against RPO <=24 hours and RTO <=4 hours initial targets. Test compatible application rollback and migration forward repair. A failed restore remains a release blocker; do not report the pilot monthly availability target as an observed result.
- [ ] P09-09 Recreate the completed app from a clean declared setup, including infrastructure, migrations, locks, model/access configuration, secrets references, callbacks and telemetry. Rerun A21/A29 using actual accounts and intended deployed identities; verify redaction and Test Mode isolation.
- [ ] P09-10 Rehearse the actual Gmail -> Strands -> exact freelancer approval/send -> client acceptance/amendment -> receipt link -> verified Razorpay test payment -> collection dashboard flow. Include covered/contradictory alternatives and notification with the browser closed.
- [ ] P09-11 Complete root README setup/reset/troubleshooting, configuration prerequisites, architecture diagram, chosen MIT or Apache-2.0 license, synthetic fixtures, evaluation/failure evidence index and remaining product limits. Check the brief's required account/submission fields; keep credentials and personal data out of public assets.
- [ ] P09-12 Record an honest video of at most five minutes using TDD §77's sequence. Label shortened waits, test payments and fixture-only segments. Prepare repository/submission material locally; record public repository/video locations only after their actual authorized publication.
- [ ] P09-13 Produce a release decision record: completed R/A coverage, build/configuration versions, unresolved items, operator ownership, restore evidence and enabled optional features. Treat any real-user pilot as a separate gate for identity attribution, account eligibility, region/retention, live-money policy and operational ownership.

## Release acceptance checklist

- [ ] All required phases have completed their exit gates; every R01–R18 row has component/API/test evidence.
- [ ] All A01–A32 required variants pass; actual-provider results are distinguished from mocks.
- [ ] No unsupported factual proposal, unauthorized read/write, stale approved artifact or duplicate logical collection effect is observed in the required suite.
- [ ] Quality, latency, budget, recovery and alarm outcomes have timestamps and versions.
- [ ] Clean setup reproduces the completed deployed app; required accounts work from that runtime.
- [ ] README, license, architecture, synthetic fixtures and <=5-minute video are complete and truthful.
- [ ] Required unverified capability is marked blocked rather than described as complete.

## Rollback and handoff

For an incident, stop external dispatch first, preserve durable intents/audit and use the compatibility/restore runbook. Do not reset payment or send state to force a replay. Re-enable only after provider and deletion reconciliation.

The release record distinguishes local release readiness from actual publication/submission and from future pilot approval. Optional [phase 10](PHASE_10_OPTIONAL.md) can ship later; any enabled enhancement must rerun affected release gates before being included in the candidate.

