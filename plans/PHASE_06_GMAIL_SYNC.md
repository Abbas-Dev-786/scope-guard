# Phase 06 — Gmail ingestion and connection lifecycle

**Status:** Complete | **Required:** Yes | **Depends on:** Phases 02–03; phase 05 for the complete live journey
**Owns:** R04; A09, A22; real-provider completion of A10/A11/A21  
**References:** [Master](MASTER_PLAN.md), [TDD](../docs/TDD.md) §6–8, §12–17, §48, §57; [operations](../docs/OPERATIONS.md) §3–4.

## Objective and boundary

Replace fixture-only ingress with durable authorized Gmail synchronization. Ensure missing pushes, overlapping pages, revoked credentials and ambiguous project assignments produce visible recoverable states.

## Ordered implementation tasks

- [x] P06-01 Complete integration_connections, oauth_sessions and mailbox_sync persistence. Record provider account identity, encrypted credentials/version, committed_history_id as text, watch expiry, coverage cutoff, last success and lease/version.
- [x] P06-02 Implement connect/callback/reconnect/disconnect/health routes and UI using server-bound single-use OAuth state, exact redirect/provider identity checks and PKCE where supported. Serialize refresh by credential version; revoked credentials move to reauthorization state.
- [x] P06-03 Verify incoming Gmail push identity against the configured subscription/account and bound payload limits. Durably persist/queue accepted ingress before acknowledgment; pushes are wakeups, not authoritative complete message content.
- [x] P06-04 Establish a watch checkpoint before bounded 90-day initial evidence-only backfill. Persist backfill coverage and progress; do not generate fresh proposals from the entire historical mailbox.
- [x] P06-05 Implement serialized incremental history reads and message normalization. Durably process all relevant pages before committing the history cursor; tolerate overlap and repeated pushes. Preserve resource versions and request provenance separately.
- [x] P06-06 Route normalized messages through phase 03 assignment/deduplication. Exclude application drafts/sends/reminders, label-only changes and bot traffic from triggering recursive analysis; retain authorized evidence where applicable.
- [x] P06-07 Add daily watch renewal, 15-minute catch-up and bounded 404-history recovery. A missing history window creates a visible coverage gap and full resynchronization attempt, not a false claim of complete history.
- [x] P06-08 Implement immediate local disable on disconnect, cancellation of unsent actions/jobs and asynchronous watch stop/credential cleanup. Recheck connection eligibility at dispatch. Reconnect to the same authorized account with bounded catch-up; cancelled sends never resurrect automatically.
- [x] P06-09 Implement bounded retries/backoff for provider throttling and read errors using the durable job layer. Verify approved read fallback parity; never switch transports to repeat an uncertain write.
- [x] P06-10 Expose last successful sync, coverage window/gaps, watch expiry, reauthorization and routing failures in integration health. Configure expiry-within-24-hours warnings and stale-sync warnings after 30 minutes.
- [x] P06-11 Run a real authorized Gmail request through normalization, confirmed scope, Strands, exact approval/send and client review. Label provider fixtures and actual-account observations separately.

## Implementation checkpoint

P06-01 through P06-11 are complete. Live evidence: Gmail routing decision a1659910-bcad-4003-8a80-9a177db96b3e mapped communication f8b5b4aa-ba94-44e9-852d-2ab456144c6e; deployed Strands analysis job b3b3ce10-8e00-4814-b5de-ad33e933c7fe succeeded; change order c96ec2e6-77ce-4969-89b7-d980bc0866c3 was approved against an exact revision hash; durable Gmail send job 8af61d8b-bdea-4d0b-b55e-6436c175ce42 succeeded; client status is AWAITING_CLIENT_APPROVAL. Provider fixtures remain separate from this actual-account observation.

## Verification

A09 must exercise expired watch, dropped push, overlap, interrupted pagination, history 404 and reconnect. The cursor cannot advance past non-durable work; recovered events cannot create duplicate active requests.

A22 must exercise mismatched/reused OAuth state, provider account switch, concurrent refresh, revoked token and disconnect before dispatch. Observe correct account binding and no resurrection of cancelled actions.

Repeat shared-contact mapping, repeated-message/multi-request cases and self-send loop exclusion with normalized live-shaped payloads. Measure durable ingress acknowledgment against p95 <=2 seconds on a declared workload; model work happens after acknowledgment.

## Exit gate and handoff

A real message enters the same verified pipeline used by fixtures. Recovery proves no lost committed work, bounded resynchronization and honest coverage reporting. Revoked/disconnected states are actionable in the UI.

Hand off reliable ingress and connection state to [phase 08](PHASE_08_REMINDERS_PRIVACY.md). During recovery or rollback, pause the affected connection, preserve its committed cursor and reauthorize the same account before catch-up. Never reset cursors silently to hide missing history.

