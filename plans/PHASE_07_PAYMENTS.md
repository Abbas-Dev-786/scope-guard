# Phase 07 — Razorpay Test Mode collection and reconciliation

**Status:** Implementation deployed; controlled round trip pending | **Required:** Yes | **Depends on:** Phases 02 and 05
**Owns:** R11; A12, A13; payment-specific A02/A06/A25/A26
**References:** [Master](MASTER_PLAN.md), [TDD](../docs/TDD.md) §11, §35–39, §46–48, §58; [operations](../docs/OPERATIONS.md).

## Objective and boundary

Convert accepted immutable payment intents into one correctly correlated payable test link, then verify collection independently of order approval. Retain uncertainty, attempt history and reversal facts. Do not introduce live money, partial payments, refunds or payouts.

## Ordered implementation tasks

- [x] P07-01 Complete payment_requests, payment_link_attempts, payment_attempts and payment_observations. Preserve one request per accepted revision, uniquely numbered attempts, same-account/environment references and at most one verified payable link.
- [x] P07-02 Implement deterministic link-intent validation against the accepted revision, INR/paise total, explicit tax/terms, full-payment rule, frozen due date and expiry. Generate a unique digest reference of at most 40 characters and persist it before dispatch.
- [x] P07-03 Implement controlled Razorpay Test Mode creation through external-action workers. Disable provider customer notifications/reminders. Track real API/link usage against verified account constraints; routine tests use fixtures.
- [x] P07-04 Implement provider-success/local-save-loss reconciliation using account/environment/reference and all available link/order/payment identities. No result is not proof of no link. Keep UNKNOWN_OUTCOME/REVIEW_REQUIRED visible and never create a replacement to escape uncertainty.
- [x] P07-05 Implement authenticated bounded webhook ingress with durable raw observation storage, duplicate delivery handling and asynchronous normalization. Preserve signature-verification context and redacted correlation while excluding secrets.
- [x] P07-06 Normalize link/order/reference/payment IDs, account, environment, currency, total, status and relevant timestamps. Accept a first unknown payment as a durable unmatched observation; retry association for 24 hours, then retain for manual review/replay.
- [x] P07-07 Implement authoritative provider verification and monotonic collection transitions. Exact account/order/amount matching is mandatory. A later failure cannot regress verified capture; expiry does not override later verified collection; reversals are separate human-review facts.
- [x] P07-08 Add pending-request reconciliation every 15 minutes and daily checks of recent paid collection for 30 days. Continue without agent/model availability. Reserve API/database capacity and protect against concurrent webhook/reconciler updates.
- [x] P07-09 Implement payment fetch/reconcile/replace-link routes and operator views. Replacement requires authoritative unpaid cancellation/expiry of the old link; preserve old observations/history and due date. Block replacement while old collection is uncertain.
- [x] P07-10 Complete the phase 05 receipt handoff with capability-scoped link/status retrieval. Validate provider URL/account expectations; never accept arbitrary model/client payment URLs. Polling only reads persisted results.
- [x] P07-11 Expose accepted versus collected/reversed/outstanding facts for the dashboard. Work eligibility requires full verified payment and prerequisites; do not post approved revenue again on collection.
- [ ] P07-12 Run the INR 15,000 -> 1,500,000 paise controlled test round trip through actual link creation, client receipt, test payment and verified collection. Record provider acceptance, observation and local state separately.

## Implementation checkpoint

The first Phase 7 slice is implemented and unit-verified: payment-link attempts, payment attempts, durable raw observations, stable <=40-character references, INR paise/full-payment validation, frozen due/expiry, disabled provider notifications/reminders, signed webhook verification, duplicate delivery idempotency, mismatch quarantine, and monotonic paid state. The Razorpay transport remains fail-closed until Test Mode account credentials are configured.

The implementation is deployed in staging on the Lambda-compatible image `phase7-20260914-m10`; the function reported `Active` with `LastUpdateStatus=Successful`. P07-05 is locally complete: authenticated raw ingress is persisted before acknowledgment, duplicate deliveries are idempotent, and a durable worker normalizes the payload under tenant ownership checks. P07-12 remains open until the controlled INR 15,000 Test Mode acceptance-to-payment round trip is performed with the client receipt and Razorpay webhook.
## Verification

A12 delivers the first payment before link persistence, then replays it after reconciliation. Same amount on another order/account/environment must not close the request.

A13 permutes failure, capture, delayed failure, expiry and reversal with duplicates. Verify monotonic collection and exactly one logical metric posting.

Repeat A02 for create-success/response-loss and A06 for exact paise boundaries. Test link replacement with uncertain/paid/cancelled/expired old links, late events on prior attempts and concurrent creators. A26 verifies slow link creation transitions pending receipt to link or review without extra creates.

## Exit gate and handoff

The real Test Mode acceptance-to-payment path is observed; mismatches/orphans remain replayable and cannot falsely mark paid. Unknown outcomes never lead to an automatic duplicate payable link. Histories remain intact.

Hand off verified payment state/version, due date and fresh reconciliation contract to [phase 08](PHASE_08_REMINDERS_PRIVACY.md). On incident recovery, disable creates, reconcile existing references first and resume only with established account/state identity.

