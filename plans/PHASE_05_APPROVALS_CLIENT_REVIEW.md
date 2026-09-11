# Phase 05 — Exact approvals, sending and client acceptance

**Status:** Implemented | **Required:** Yes | **Depends on:** Phases 02–04  
**Owns:** R08, R09, R10, R13; A03, A08, A15, A24, A26  
**References:** [Master](MASTER_PLAN.md), [TDD](../docs/TDD.md) §28–35, §46–48, §56, §58, §64–66; [threat model](../docs/THREAT_MODEL.md).

## Objective and boundary

Close the human approval boundary from evidence-backed proposal to atomic client acceptance. Reuse the verified Gmail/SES adapters from readiness and durable action controls. Persist accepted payment intent now; phase 07 connects it to Razorpay and completes receipt-link delivery.

## Ordered implementation tasks

- [x] P05-01 Add proposal revisions, approvals, client capabilities/sessions, communication revisions, notifications and accepted payment-request intent records with required unique/ownership constraints. Create scope-amendment and approved-revenue facts in the same domain transaction.
- [x] P05-02 Assemble canonical immutable proposal artifacts before review: exact recipient, subject/body, attachment bytes/hashes, commercial terms, scope version, evidence digests and exact client URL. Store original opaque token only in the encrypted artifact; store its lookup hash separately.
- [x] P05-03 Build freelancer revision editing and exact review UI. Material edits create a new immutable revision. Approval submits only idempotency key, expected_row_version, revision ID and content hash; server loads frozen values.
- [x] P05-04 Under the domain locks, recheck effective scope and evidence freshness within 24 hours. Reject stale/changed inputs and require a new review. Commit approval, SEND_PENDING, next action/job/outbox and audit atomically.
- [x] P05-05 Implement deterministic Gmail send using exact approved content and a stable marker. Enable the client grant only when approved dispatch starts. Preserve UNKNOWN_OUTCOME and reconcile by exact marker/recipient/body; a no-hit lookup is inconclusive.
- [x] P05-06 Enforce seven-day client-grant expiry from freelancer approval; an unsent artifact older than 24 hours requires a new revision/token and approval. Revoke superseded/withdrawn capabilities and cancel unsent actions when eligibility changes.
- [x] P05-07 Implement /c fragment-token exchange via POST, then remove the fragment. Use hashed 256-bit opaque grants, scoped HttpOnly/Secure/SameSite=Strict cookies, CSRF/origin controls, no-store, no third-party resources, restrictive CSP and no-referrer. GET and link previews never approve or create payments.
- [x] P05-08 Implement scoped review/approve/reject/request-changes APIs and pages. Client comments never mutate price. Request-changes consumes approval authority and queues a new freelancer decision; new terms require new revision and freelancer approval.
- [x] P05-09 Implement atomic client acceptance under project/order locks: validate active exact revision and current baseline; consume once; record approval/amendment/new effective scope, approved-revenue fact, payment intent, receipt, audit and jobs together.
- [x] P05-10 Handle early client receipt when order is SEND_PENDING and the exact send is DISPATCHING/UNKNOWN_OUTCOME. Record RECEIPT_CONFIRMED without inventing a provider message ID. Late send callbacks cannot regress accepted state or trigger resend.
- [x] P05-11 Implement reject/waive/withdraw and negotiation behavior. Preserve history, invalidate affected unaccepted offers, avoid collection on waiver, and require revalidation of competing proposals based on an older scope version.
- [x] P05-12 Send deduplicated SES notifications to the verified freelancer address with authenticated deep links and no evidence body. Build pending/review receipt states, 24-hour receipt sessions and original-token receipt-only access for 30 days after acceptance; poll every three seconds initially for one minute, then every 15 seconds. Reads never create provider links.

## Implementation checkpoint

The Phase 5 domain, review, approval, receipt, Gmail action, and SES notification paths are implemented and covered by unit/provider-adapter tests. Live provider execution remains part of the exit gate. Proposal attachments are currently represented by immutable hashes; dispatch safely refuses an artifact when attachment bytes are not available.

## Verification

A03 tests two-tab edits, exact recipient/body/attachment/hash matching and stale freelancer/client commands. A08 tests single amendment posting, repeated now-covered work and competing old-baseline approvals.

A15 covers preview GETs, wrong/expired/revoked/forwarded grants, concurrent consumption, CSRF, token leakage and receipt-only access. Bearer possession is the explicitly disclosed synthetic-demo attribution model; do not claim verified legal signature.

A24 covers discount comments, new revisions, stale tokens, repeated waiver and preserved negotiation history. A26 closes the browser before notification and simulates delayed payment creation while receipt polling remains side-effect free.

Also inject send-success/save-loss, early client acceptance before send acknowledgment, disconnect before dispatch and late callbacks. Check every private/public object path in the A04 matrix.

## Exit gate and handoff

Exact approved content is sent through the real controlled Gmail path, client review cannot alter it, and one acceptance produces one immutable amendment/approved amount/payment intent. Pending payment is shown honestly until phase 07 finishes.

Hand off accepted intents and receipt contracts to [phase 07](PHASE_07_PAYMENTS.md), and send/cancellation contracts to [phase 06](PHASE_06_GMAIL_SYNC.md). Disable dispatch during recovery; never rollback an accepted amendment by deleting history or regenerate approved content after restore.

