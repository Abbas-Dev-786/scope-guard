# ScopeGuard

## Product Requirements Document

**Version:** 1.1  
**Status:** Revised hackathon MVP specification; implementation and account verification pending  
**Updated:** 7 September 2026  
**Track:** Professional Agents  
**Tagline:** Stop doing work you didn't get paid for.

This revision incorporates the 32 findings in [the original architecture review](ARCHITECTURE_REVIEW.md). [REVIEW_RESOLUTION.md](REVIEW_RESOLUTION.md) maps each finding to its design resolution and required verification. This document owns product scope and behavior; [TDD.md](TDD.md) owns technical contracts. P0 means required MVP functionality, P1 means optional enhancement, and P2 means post-hackathon. Review severity is a separate prioritization system.

# 1. Executive Summary

ScopeGuard protects software freelancers from unrecorded additional work. It monitors configured project communication, compares requests with confirmed scope and approved amendments, gathers evidence, estimates effort, calculates a suggested price, and prepares a change order and client message.

The freelancer authorizes the exact proposal and message. The client reviews that same revision, approves or requests changes, and receives a Razorpay test payment link. ScopeGuard records approval, tracks collection, and prepares overdue reminders. Ambiguous or contradictory evidence produces a clarification decision rather than an unsupported billable proposal.

The MVP supports independent freelancers, Gmail, uploaded contracts, INR, and test payments. GitHub and Slack evidence are optional enhancements. Agents prepare decisions; deterministic application services authorize and execute external actions.

# 2. Hackathon Alignment

The product addresses the Professional Agents track through nontrivial Strands reasoning and a complete request-to-collection demonstration. The local [hackathon brief](../hackathon.md) requires a public code repository, runnable setup instructions, MIT or Apache license, README, architecture diagram, and a demo video of at most five minutes.

AgentCore is optional under that brief, but remains ScopeGuard's chosen deployment target and an MVP delivery requirement. Verify deployed connectivity early. A public live demo is optional; any such demo uses synthetic projects and isolated test credentials.

# 3. Problem Statement

Freelancers must identify new requests, locate the governing scope, distinguish prior commitments from new work, estimate changes, negotiate approval, and collect payment. The repeated administrative effort encourages unrecorded work.

Success means reducing that effort without creating unnecessary disputes, duplicate requests for payment, or misleading confidence. The product identifies differences from recorded scope; it does not determine legal enforceability.

# 4. Product Vision

A user should receive one actionable decision when judgment is needed, including when evidence is ambiguous. They should not have to keep the dashboard open.

ScopeGuard sends transactional email notifications to the freelancer's verified account address, with authenticated deep links. The dashboard remains the authoritative decision interface. Monitoring failures produce an actionable health notification; ordinary successful analysis does not.

# 5. Product Principles

- Evidence before judgment: show supporting and contradicting sources, retrieval coverage, and limitations.
- Autonomous preparation, human commitment: freeze and approve content, recipients, terms, price, and schedule together.
- Least privilege: restrict both agent capabilities and the objects each tool can access.
- Durable execution: accepted events and decisions survive crashes; uncertain external outcomes are reconciled.
- Clear ownership: the database owns business facts; the payment provider supplies payment facts; humans authorize commitments.
- Honest presentation: estimates are ranges and assumptions; model confidence is not displayed as a probability of correctness.
- Auditable and private: retain protected decision evidence according to an explicit retention policy.

# 6. Target Users

The MVP serves one independent software freelancer per account, with multiple clients and projects. Each account is a separate tenant; team membership and delegated approvers are P2.

Multiple projects may share a client, channel, or repository. Sender email alone is a routing hint, not proof of project identity. Unresolved mapping requires human assignment and supports replay.

# 7. Initial Market Focus and Commercial Policy

The initial focus is software projects using fixed-price change orders.

MVP commercial rules:

- INR only, Razorpay Test Mode only; no real collections.
- A positive, freelancer-approved fixed additional price. Suggested prices derive from confirmed rates, decimal effort, a minimum fee, and explicit rounding.
- The approved total includes any applicable tax; the user enters the tax component, defaulting explicitly to zero for the synthetic demo. ScopeGuard does not calculate tax obligations.
- Full payment requested after client approval, due seven calendar days after approval at 17:00 in the project's frozen IANA timezone.
- Approval adds an accepted amendment to scope; work commencement is conditional on verified full payment. Delivery estimates are measured from payment and confirmed client prerequisites.
- No partial payments, installments, automatic discounts, or refunds initiated by ScopeGuard. A goodwill waiver is recorded without a payment request.
- Contracts with incompatible collection terms require manual handling. The product must not silently substitute these defaults.

Tax, deposit, milestone, multi-currency, and more flexible payment policies are P2. The agreed terms are visible before either approval.

# 8. Primary User Journey

The freelancer creates Acme SaaS Platform, adds Sarah as the client contact, connects Gmail, and uploads a supported SOW. ScopeGuard extracts scope; the freelancer corrects it and confirms baseline version 1. Monitoring starts only after confirmation and successful connection setup.

The SOW includes email/password and Google sign-in, and excludes additional identity providers. Sarah requests Microsoft Entra ID sign-in using OIDC for one tenant with account linking; SAML, SCIM, and multi-tenant enterprise federation are explicitly outside the demo request.

An explicit thread/project binding identifies Acme. GitHub or Slack can enrich the evidence if connected, but the core journey works with the confirmed contract, approved amendments, and Gmail.

# 9. Core Workflow

~~~text
Verified event -> durable ingestion -> normalize and resolve project/request
-> load confirmed effective scope
-> Scope Agent -> Evidence Agent where needed
-> validate evidence and reconsider classification
   -> covered / previously approved / irrelevant: record no action
   -> insufficient / conflicting: clarification decision
   -> supported additional work: estimate -> deterministic price -> draft
-> immutable proposal revision -> notify freelancer
-> freelancer approves exact revision and message
-> deterministic approved-send action -> client review
-> client approval transaction: record approval + append scope amendment
   + update approved revenue + queue payment creation
-> payment link shown on approval page
-> verified provider collection -> update collected revenue and work eligibility
-> overdue reminder drafting / human-approved reminder sending
~~~

Reject, waive, split, merge, revise, withdraw-before-acceptance, and manual-review outcomes are supported as defined in TDD §47–48. No approval token or retry may authorize a superseded revision.

# 10. Agent Responsibilities

| Role | Responsibility | Boundary |
| --- | --- | --- |
| Scope Agent | Classify a bounded request against effective scope | Read only; preliminary assessment |
| Evidence Agent | Gather supporting/contradicting evidence and coverage | Cannot treat missing search results as proof of absence |
| Impact Agent | Task breakdown, effort range, dependencies, uncertainty | No authoritative pricing or delivery-date arithmetic |
| Change Order Agent | Draft deliverables, exclusions, assumptions | Money and terms injected by application |
| Communication Agent | Draft factual, diplomatic client text | Internal drafts only; no send credentials/tools |
| Payment Agent | Draft reminder wording and summarize collection context | No payment creation, payment-state mutation, or sending |
| Contract Structure Agent | Extract candidate scope items and terms | Human confirmation required before activation |

A deterministic evidence gate may overturn the preliminary assessment. Pricing, schedule calculation, proposal assembly, sending, payment creation, and payment verification are application operations. At least four distinct Strands reasoning roles execute in the primary demonstration; ingestion and reminder agents run in separate short jobs.

# 11. MCP Strategy

MCP is the preferred agent interface for approved read capabilities. Provider events start workflows; MCP does not replace ingestion.

Each adapter declares its exact capabilities, eligibility, authentication, quotas, pagination, and timeout behavior. REST fallback is permitted when it preserves authorization and evidence semantics. A provider write with an uncertain outcome cannot be repeated through a fallback.

Google/Slack account eligibility and deployed connector access are acceptance gates, not assumed completed setup. Technical references and verification dates are maintained in TDD §6–11.

# 12. MVP Integrations and Document Upload

| Integration | Priority | Required behavior |
| --- | --- | --- |
| Gmail | P0 | OAuth, project-scoped search/read, new-message ingestion, catch-up, watch renewal, approved client sends |
| Razorpay | P0 | Test link creation, correlation, signed webhook processing, reconciliation |
| Contract upload | P0 | Text PDFs, DOCX, TXT, Markdown; extraction, source references, correction, confirmation |
| GitHub | P1 | Read-only issues/PR/commit evidence in configured repositories |
| Slack | P1 | Authorized channel/thread evidence; real-time triggers optional |
| AgentCore Memory | P1 | Communication preferences only; never authoritative rates, contracts, or approvals |

Uploads are limited to 10 MiB and 100 pages or 250,000 extracted characters. Scanned-only/encrypted PDFs, embedded active content, and corrupted files are rejected with actionable explanations. OCR is P2. No analysis starts from incomplete or unconfirmed extraction.

Gmail disconnect stops new monitoring and unsent connector actions. Reconnect exposes any coverage gap and performs bounded catch-up. It never changes the connected account silently.

# 13. AWS Architecture

Use Next.js/TypeScript, Cognito, API Gateway/Lambda, Python Strands on Bedrock AgentCore Runtime, PostgreSQL, private S3, EventBridge, Secrets Manager, and CloudWatch.

PostgreSQL transactions store accepted events, business transitions, jobs, audit records, and outgoing events. EventBridge provides prompt wakeups; scheduled database reconciliation recovers missed delivery. No graph stays suspended while awaiting a person.

A deployed vertical slice must prove identity, database connectivity, external egress, one model call, one connector read, and tracing before full feature development.

# 14. High-Level Architecture

~~~mermaid
flowchart TD
    A[Gmail or user action] --> B[Validated API ingress]
    B --> C[PostgreSQL transaction and outbox]
    C --> D[EventBridge wakeup and recovery scheduler]
    D --> E[Durable job dispatcher]
    E --> F[Strands on AgentCore]
    F --> G[Evidence gate and immutable proposal]
    G --> H[Freelancer notification and exact approval]
    H --> I[Approved send executor]
    I --> J[Client revision approval]
    J --> K[Scope amendment and payment intent]
    K --> L[Razorpay Test Mode]
    L --> M[Verified payment reconciliation]
    M --> N[Collection status and reminder cancellation]
~~~

Every retrieval and command has a trusted tenant/project context. Contracts and evidence remain protected in S3 and the database.

# 15. Human Approval Model

| Action | Authorization |
| --- | --- |
| Read configured sources, classify, estimate, draft | Autonomous within fixed scope and budgets |
| Confirm extracted scope or amend baseline | Freelancer |
| Final proposal price, tax, terms, schedule, recipients, message | Freelancer approval of exact immutable revision |
| Send approved change order | Deterministic executor using that approval |
| Accept client counterproposal | New revision and freelancer reapproval |
| Accept the proposal | Client bearer-link approval of exact revision in the MVP |
| Create full test payment link | Deterministic command after valid client approval |
| Check provider status, cancel queued obsolete reminders | Autonomous deterministic processing |
| Draft overdue reminder | Autonomous |
| Send overdue reminder | Freelancer approval of exact reminder in MVP |
| Refund, payout, signed-contract mutation | Unavailable |

A client bearer link records possession-based approval, not verified signer identity or a guaranteed digital signature. The MVP uses synthetic clients; a real-user pilot must explicitly accept this attribution level or add email verification. Forwarded and revoked links are covered by acceptance tests.

# 16. Primary Screens

| Screen | Required content and behavior |
| --- | --- |
| Dashboard | Proposed value, client-approved Revenue Protected, collected value, outstanding value; test-mode badge |
| Decision inbox | Change, clarification, mapping, reminder, and operational decisions with status |
| Proposal review | Exact revision, baseline, total/tax/terms, recipient, message, assumptions, evidence; edit/reject/waive/approve |
| Evidence view | Quoted source excerpts, immutable locators, retrieval times, contradictions, incomplete-source indicators |
| Project workspace | Baseline and amendment history, accepted work, payment-dependent work eligibility, pending requests |
| Integrations | Account identity, scope, binding rules, last successful sync, coverage gaps, disconnect/reconnect |
| Client review | Frozen deliverables, price/tax, payment/delivery terms; approve/request changes/reject; no internal evidence |
| Client payment/receipt | Pending link creation, retry/help state, payment URL, provider-confirmed receipt |

Editing creates a new revision. A stale tab receives a conflict and must reload. Client review is accessible after sending; it remains readable after approval using a separate limited receipt session.

# 17. Canonical Lifecycles

Business states are separated; the same word must not refer interchangeably to graph progress and payment status.

| Entity | States |
| --- | --- |
| Assessment classification | IN_SCOPE, POTENTIAL_SCOPE_CHANGE, AMBIGUOUS, PREVIOUSLY_APPROVED, NOT_A_SCOPE_REQUEST |
| Request | OPEN, CLARIFICATION_REQUIRED, PROPOSAL_OPEN, COVERED, WAIVED, DECLINED, MERGED, RESOLVED |
| Change order | DRAFT, AWAITING_FREELANCER_APPROVAL, SEND_PENDING, AWAITING_CLIENT_APPROVAL, REVISION_REQUESTED, CLIENT_APPROVED, REJECTED_BY_FREELANCER, REJECTED_BY_CLIENT, WITHDRAWN, EXPIRED |
| Collection | NOT_REQUESTED, CREATION_PENDING, PENDING, REVIEW_REQUIRED, PAID, EXPIRED, CANCELLED, REVERSED |
| Job | QUEUED, RUNNING, RETRY_WAIT, SUCCEEDED, FAILED_REQUIRES_REVIEW, CANCELLED |

Full transitions, guards, immutable revision rules, and independent delivery-action states are in TDD §47. CLIENT_APPROVED does not become PAID: the payment request changes independently. A confirmed reversal changes collection status, preserves approval history, and requires review.

# 18. Core Data Model

The domain consists of tenant users; clients and contacts; projects and versioned commercial preferences; integration connections, routing bindings and mailbox sync state; immutable documents/chunks; confirmed scope versions, items and amendments; provider deliveries and normalized communications; requests and request-message links; assessments, evidence snapshots and agent runs; change orders with immutable proposal revisions; approvals and client capabilities; payment requests and attempts; jobs, outbox, consumer receipts and external-action intents; notifications, reminders, audit records and deletion tasks.

All tenant-owned relationships must prove common ownership. Amounts use integer paise plus INR. Row concurrency versions are separate from business content revisions. TDD §46 defines required constraints and fields.

# 19. Revenue Protected Metric

Revenue Protected is the total value of effective, client-approved additional scope, counted once per accepted change order. It increases at client approval, not payment.

Collected Additional Revenue is verified net collected value after confirmed reversals. Outstanding is the unpaid balance of active requests; Proposed Value counts only current unaccepted proposals. Refund/reversal facts do not erase the approval audit. Commercial rescission is a human-reviewed amendment rather than a silent deletion.

Totals are displayed gross, including the disclosed tax component. Test and production data must never share a total; the MVP displays test totals only. Captured scope value is not evidence that all of it would otherwise have been lost.

# 20. P0 — Required MVP Requirements

| ID | Requirement |
| --- | --- |
| R01 | Single-owner tenant isolation, authentication, verified notification address |
| R02 | Clients/projects/preferences, shared-client routing, diagnostic assignment and replay |
| R03 | Supported uploads, extraction correction, confirmed versioned effective scope |
| R04 | Gmail OAuth, read/search, watch renewal, durable sync and disconnect/reconnect |
| R05 | Request deduplication, repeated-message association, clarification and human merge/split |
| R06 | Strands classification/evidence/impact/drafting with validation and bounded execution |
| R07 | INR decimal-safe pricing, explicit tax/payment/schedule terms |
| R08 | Immutable proposal revision, stale-approval protection, deterministic approved send |
| R09 | Scoped client review, approve/reject/request-changes, expiry/revocation, receipt access |
| R10 | Atomic client approval and scope amendment; new evidence uses effective scope |
| R11 | Razorpay test link, exact units/correlation, replay-safe collection and reconciliation |
| R12 | Due dates, overdue detection, internal reminder drafts and approved sends |
| R13 | Out-of-app freelancer notifications and client payment-link handoff |
| R14 | Accurate approved/collected/outstanding test metrics |
| R15 | Transactional outbox/jobs/actions, unknown-outcome handling, operational replay |
| R16 | Protected audit/evidence, retention, deletion, threat model and restore procedure |
| R17 | Early AgentCore deployment and reproducible environment/setup |
| R18 | Quality thresholds, adversarial/failure tests, five-minute demo and submission assets |

R01–R18 are the single MVP cut line used by the TDD and resolution checklist. A feature cannot remain implicitly P0 in an example after being deferred here.

# 21. P1 — Optional Enhancements

GitHub read evidence; Slack authorized evidence and events; GitHub triggers; PDF rendering of frozen change orders; a richer trace UI; communication-tone memory; automatic policy-authorized reminders after their own safety/consent gate. None is required to complete R01–R18.

# 22. P2 — Post-Hackathon

Team accounts, delegated approvals, stronger client identity, OCR, Drive/Outlook/Teams/Jira/Linear integrations, accounting/e-signature integrations, timesheets, advanced profitability, taxes calculated by jurisdiction, deposits/milestones/partial collection, multiple currencies, and negotiation assistance.

A real-user pilot additionally requires provider eligibility, privacy/retention review, restoration evidence, and the client-attribution decision recorded in the release checklist.

# 23. Explicit Non-Goals

The MVP is not a project-management suite, accounting system, time tracker, coding agent, autonomous negotiator, legal adviser, or replacement for signed contracts. It does not infer hours worked from commits, guarantee delivery dates, guarantee exactly-once email delivery, or claim deployment/verification is complete merely because this specification exists.

# 24. Security and Privacy Requirements

Every API/tool/job enforces tenant and project ownership, including direct source-ID retrieval. Credentials stay outside model context. Tool permissions deny unknown operations; provider credentials restrict writes independently where possible.

Approvals bind exact artifacts. Public tokens are high entropy, hashed at rest, revision-scoped, expiring, revocable, and consumed atomically. Public pages expose only client-facing information. Untrusted content is sanitized and cannot grant tools or change authorization.

Retain only configured project data needed for the task. Delete tenant data on request using the lifecycle in [OPERATIONS.md](OPERATIONS.md); disconnect immediately revokes use of the connector. [THREAT_MODEL.md](THREAT_MODEL.md) specifies threats, controls, and required adversarial tests.

# 25. Failure Handling

The product distinguishes prepared, queued, sending, sent, unknown outcome, and action required. Provider acceptance is not represented as guaranteed inbox delivery.

If an external write times out, reconcile before retrying. If success cannot be established safely, show an actionable uncertainty decision and block automatic repeats. A payment mismatch remains REVIEW_REQUIRED. Lost notifications do not lose the underlying decision.

Integration failure, missing scope, exhausted model budget, stale evidence, and unmapped communication remain visible and recoverable. Ordinary reads use bounded retries; persistent failures require review. Details are in TDD §58–60.

# 26. UX Requirements

Decision cards are the primary interaction. Show why action is requested, what will be sent, who will receive it, which revision is being approved, and the consequences. Never show raw secrets, model reasoning traces, or implementation fields on client pages.

Rejection reasons include covered, duplicate, waive charge, decline work, and irrelevant. Clarification supports corrected scope or request information. A client price request never edits the already-approved amount in place.

# 27. Notification Policy

Send one freelancer email per actionable decision revision to the verified account address, without sensitive evidence in the email body. The deep link requires login. Persist outcomes; repeated underlying events do not create repeated notifications.

Use a deployment-controlled transactional email sender for application notifications. Gmail handles approved client communication. Automatic marketing or third-party recipients are outside the product.

The client approval page polls its authorized receipt/payment endpoint while a payment link is being created. It shows a pending state immediately, the link when available, and a support/review state if creation is unresolved. Razorpay automatic reminders and link notifications are disabled; ScopeGuard owns this experience.

# 28. Success Metrics and Release Targets

Measure decision turnaround, false proposals, evidence correctness, clarification frequency, freelancer edits/waivers, approval rate, collection delay, and monitoring coverage. Do not equate rejection with model error without the user's rejection reason.

Initial release targets are engineering gates, not achieved performance claims:

- Held-out proposal precision at least 95%; recall at least 80% on supported additional-scope requests.
- Every surfaced factual claim has a valid retrieved reference; unsupported claims and cross-tenant leaks are release blockers.
- Zero unauthorized external writes in the adversarial suite.
- Healthy end-to-end request-to-card p95 at most 120 seconds on the documented load fixture.
- All failure/replay scenarios in REVIEW_RESOLUTION.md pass before declaring dependability.

TDD §70 defines sample size, labels, repeated runs, and validation. OPERATIONS.md defines availability/recovery targets.

# 29. Hackathon Success Criteria

Demonstrate a real Gmail message, meaningful Strands reasoning, a supported proposed change, exact freelancer approval, real approved Gmail send, client approval of that revision, an updated effective scope and approved-revenue metric, a Razorpay test link, verified payment, and a collected-revenue update.

The demo must also show an evidence limitation or clarification example, a visible test-mode indicator, and the approval boundary. Failure-safety acceptance is tested separately rather than squeezed into the video.

# 30. Demo Scenario

Acme has a ₹3,00,000 base contract. The confirmed SOW excludes the explicitly defined Microsoft Entra OIDC integration in §8. A relevant earlier email describes it as a later-phase candidate. Any optional GitHub search is described as bounded evidence, not proof that no code exists.

The Impact Agent proposes 12–16 hours with explicit assumptions. The application recommends 14 hours at ₹1,000/hour with a ₹15,000 minimum fee and ₹500 rounding increment: ₹15,000 total, including ₹0 tax in the synthetic fixture.

The freelancer confirms +2 working days from verified payment and supplied client configuration. Client approval updates Revenue Protected to ₹15,000 and records the amendment. Test payment updates Collected Additional Revenue to ₹15,000; it does not increment Revenue Protected again.

# 31. Agent Trace Demo

The optional trace lists workflow stages, validated summaries, actual measured durations, evidence counts, tool outcomes, and human decisions. It does not expose chain-of-thought or label illustrative milliseconds as benchmarks. The main UI uses qualitative uncertainty and evidence coverage, not uncalibrated confidence percentages.

# 32. Technology Stack

Next.js + TypeScript; Cognito; Python + Strands + Bedrock; AgentCore Runtime; API Gateway/Lambda; Aurora PostgreSQL; private S3; EventBridge plus scheduled database recovery; Secrets Manager; CloudWatch; a deployment-controlled transactional email sender.

The concrete runtime, region, dependency versions, connector access, and model IDs must be pinned and demonstrated in the implementation readiness record. TDD §5 and OPERATIONS.md define defaults and release checks.

# 33. Development Priority

1. Prove account eligibility and a minimal deployed AgentCore/database/model/connector path.
2. Implement tenant ownership, schema constraints, revisions, jobs/outbox/actions, and money contracts.
3. Implement contract confirmation, effective scope, and evidence/request flows with fixtures.
4. Implement validated Strands preparation and evaluate it against held-out cases.
5. Implement freelancer notification/approval, client review/revisions, and approved sending.
6. Connect real Gmail synchronization and Razorpay test collection/reconciliation.
7. Complete reminders, failure/replay/restore tests, privacy controls, and required APIs.
8. Add optional integrations only after R01–R18 are stable.
9. Finalize setup instructions, architecture, license, recording, and submission.

Error handling and authorization are part of each phase, not final polish.

# 34. MVP Definition

The MVP is complete when R01–R18 and their acceptance checks pass in the deployed test environment. A happy-path video alone is insufficient evidence for durable execution or safe approval/payment behavior. External-account and runtime checks remain pending until recorded with actual results.

# 35. One-Sentence Pitch

ScopeGuard watches configured conversations against your approved scope, catches possible extra work, prepares the change order, and brings you one evidence-backed decision before anything is committed.

# 36. Short Pitch

Freelancers lose time turning informal requests into documented, paid changes. ScopeGuard gathers the scope and context, prepares an estimate and proposal, and asks the freelancer to approve the exact communication. It then records the client's decision and tracks collection. The freelancer spends more time building and less time administering changes.
