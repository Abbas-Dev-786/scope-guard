# ScopeGuard Threat Model

**Version:** 1.0  
**Date:** 7 September 2026  
**Status:** Required controls specified; implementation verification pending

This model supports PRD R01, R08–R11 and R15–R18 and TDD §49–60. It covers the isolated hackathon test environment and identifies extra decisions needed before a real-user pilot.

## 1. Assets and Principals

Protect client communications, contracts, source evidence, generated proposals, exact approval records, payment associations, provider credentials, client bearer capabilities and tenant identity.

Principals are the authenticated freelancer, a possession-based client-link visitor, provider webhook senders, reasoning workers, deterministic action workers, the notification sender and an authorized operator. Every freelancer is an independent tenant. Agency roles are not implemented in the MVP.

The model can be wrong or influenced by malicious content. The frontend, provider payload fields and every resource ID supplied by a caller are untrusted until validated. A signed webhook proves provider origin, not automatic association with a ScopeGuard order.

## 2. Trust Boundaries

~~~mermaid
flowchart LR
    U[Browser] -->|Identity or scoped capability| A[API domain boundary]
    P[Provider] -->|Verified raw webhook| A
    A --> D[Protected database and S3]
    D --> J[Trusted job context]
    J --> M[Model with untrusted evidence]
    M --> V[Schema and evidence validation]
    V --> D
    D --> X[Approved action executor]
    X -->|Scoped credentials| P
~~~

The model cannot cross the action boundary directly. The runtime receives no unrestricted send/payment credentials. Search access never implies authorization to retrieve arbitrary IDs returned by other sources.

## 3. Threats and Required Controls

| Threat | Required control | Implementation verification |
| --- | --- | --- |
| User requests another user's project/document | Shared object-authorization policy plus composite ownership FKs; downloads and traces included | Two tenants, guessed IDs, nested resource substitutions |
| Same user's unrelated project leaks through search/thread retrieval | Trusted project filters and per-object validation; mixed threads explicitly assigned or filtered | Same client on two projects; direct thread fetch after scoped search |
| Background job supplies forged tenant/account | Tenant derived from stored authorized job; service authentication and least-privilege IAM | Tampered job payload and runtime invocation rejected |
| Runtime cache leaks previous user's context | Per-job/session agent construction; cache keys include tenant/connection/credential version | Alternating and concurrent tenant jobs |
| Prompt injection requests payments or secret disclosure | No consequential tools/credentials; untrusted-content separation; schema and policy validation | Injection in email, documents, issues and tool results |
| Unknown MCP mutation bypasses wildcard rules | Exact pinned manifest, schema comparison, deny unknown operations, read-only credentials | update/edit/close mutation tool discovery fails closed |
| Stale or altered proposal approved | Immutable canonical revision; expected version/hash; frozen recipients/body/terms; baseline recheck | Concurrent edit/approve and provider-draft mutation |
| Approval grants unrelated send authority | Action ID loads approved arguments internally; approval/order/tenant/digest guard | Arbitrary recipient/body/order/amount arguments rejected |
| Forwarded or stolen client link | 256-bit opaque token, hash at rest, short expiry, scope binding, revocation, minimal public disclosure | Wrong revision/order, revoked/expired grants and brute-force throttling |
| Link scanner approves an offer | GET is read-only; capability exchange and explicit CSRF-protected POST required | Prefetch/preview/navigation cannot accept |
| Concurrent client clicks consume a grant twice | Row locks, idempotency, immutable approval uniqueness and atomic consumption | Parallel approvals create one amendment/payment intent |
| Link token leaks through logs/analytics/referrer | Fragment exchange, removal from browser history, no third-party assets, no-referrer, redaction | Inspect server/app/trace logs and outbound browser requests |
| Public client route leaks internal evidence | Capability-bound response schema and no-store caching | Unauthorized GET and cache isolation tests |
| Forged/replayed/wrong-account webhook | Raw-body signature/JWT verification, freshness where applicable, fixed account/environment mapping, dedupe | Invalid body/signature/audience/account and duplicate deliveries |
| Lost publication silently stalls work | Transactional job/outbox insert, scheduled runnable-job recovery | Crash after commit and published-but-undelivered wakeup |
| Timeout leads to duplicate email/link | Persist intent before dispatch, UNKNOWN_OUTCOME, provider reconciliation, no blind retry | Provider success followed by connection/DB failure |
| Wrong payment closes an order | Verified merchant/link/order/reference/amount/currency association | Same amount on different account/order; event before link save |
| Delayed event regresses paid state | Serialized authoritative reconciliation and immutable payment facts | Permutations of failure/capture/refund observations |
| Paid client receives queued reminder | Reconcile and check payment version before dispatch; cancel queued reminders | Payment commits before send claim |
| Document exploits parser or exfiltrates URLs | Isolated bounded extraction, no network/active content, file/expansion limits | Corrupt archive, oversized/scanned/encrypted PDF, external resources |
| Rendered evidence runs script or loads tracking content | Sanitization, CSP, no remote images/active URLs | Stored XSS, script URL, embedded remote image |
| OAuth callback links wrong account | Single-use tenant-bound state, expected provider identity/redirect, credential versions | Cross-user callback state, account switch, concurrent refresh |
| Disconnected integration continues acting | Immediate local disable, credential-use guard, queued-action cancellation, async provider revocation | Disconnect immediately before read/send claim |
| Sensitive content leaks via observability | Metadata-only standard logs, protected evidence store, redacted tokens, owner-only traces | Canary secret/token checks in logs and exports |
| Endless model/tool work consumes budget | Durable per-job/tenant/global limits and deadline; no unlimited repair | Tool loop, oversized context, timeout and budget exhaustion |
| Operator changes financial truth without evidence | Constrained resolve actions, reason/evidence audit; no arbitrary mark-paid | Operator cannot forge success or rewrite accepted artifacts |
| Deleted data returns after restore | Deletion tombstones reapplied before access/workers resume | Restore a pre-deletion backup, verify data stays inaccessible |

## 4. Credential and Network Policy

Runtime preparation identity cannot call generic send/payment commands. The action worker accesses only the credentials necessary for its provider/action. The API uses its own scoped database identity. The notification sender is deployment-controlled and can address only the tenant's verified notification destination for authorized notification jobs.

Database and object storage are private. Private subnet egress is explicitly provisioned; outbound access is limited to required provider/AWS endpoints where operationally practical. No model-generated endpoint is permitted. Secrets are retrieved by deterministic code and excluded from model inputs and ordinary logging.

Application roles cannot modify immutable proposal revisions, approvals or audit records. Operator/admin access is separate, authenticated and audited. No shared production credentials are used in demo fixtures.

## 5. Residual Risks and Product Limits

- Bearer-link approval proves possession, not independently verified identity or authority to bind a client organization. The synthetic demo accepts this limitation. A real-user pilot must record acceptance of that attribution model or add verified email approval.
- Human review and schema validation reduce but cannot eliminate misleading model conclusions. Unsupported or contradictory evidence must abstain; the evaluation gates measure the remaining risk on a limited dataset.
- Exactly-once external email delivery is not guaranteed. Uncertain outcomes block automatic repeats; an explicit manual resend can still duplicate a message.
- A payment can arrive after a reminder has started dispatching. Rechecks suppress locally known obsolete reminders; the product cannot recall an in-flight email.
- Provider outages, permission changes and lost history can create coverage gaps. These must be visible rather than represented as complete monitoring.
- Audit retention and deletion require policy decisions before handling real confidential/contractual data. The test-mode retention defaults are not a claim of legal compliance for every jurisdiction.

## 6. Security Release Gate

Before enabling the demo with real provider connections, pass the two-tenant isolation, exact-approval, webhook verification, capability replay, tool denylist-by-default, parser/rendering and unknown-write tests using synthetic data.

Before a real-user pilot, additionally document provider distribution eligibility, approved data region, retention policy, client attribution, backup/restore evidence, incident owner and credential rotation/revocation tests. Store outcomes in REVIEW_RESOLUTION.md. This document currently specifies controls; none is represented as implemented verification.
