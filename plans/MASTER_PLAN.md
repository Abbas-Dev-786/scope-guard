# ScopeGuard master implementation plan

**Baseline:** PRD/TDD v1.1, 7 September 2026  
**Implementation status:** Phases 00–05 implemented locally and Phase 06 implementation complete; deployed live-provider acceptance remains open  
**Goal:** Deliver the complete R01–R18 synthetic-data, INR, Razorpay Test Mode MVP with deployed acceptance evidence.

## 1. Authority and scope

The [PRD](../docs/PRD.md) defines product scope. The [TDD](../docs/TDD.md) defines implementation contracts. The [resolution register](../docs/REVIEW_RESOLUTION.md) defines A01–A32, supported by the [threat model](../docs/THREAT_MODEL.md) and [operations runbooks](../docs/OPERATIONS.md). The [hackathon brief](../hackathon.md) defines submission requirements. These plans assign delivery order and verification ownership; they do not replace those specifications.

Implement single-owner tenants, projects and contacts; confirmed uploaded contracts; Gmail; at least four distinct Strands reasoning roles; evidence-backed decisions; deterministic pricing; exact freelancer approval and Gmail send; scoped client review; atomic scope amendments; Razorpay test collection; approved reminders; notifications; metrics; audit/privacy; recovery; AgentCore deployment; evaluation and demo assets.

GitHub, Slack, rendered PDFs, richer traces, tone memory and automatically sent reminders are optional P1. OCR, teams, live money and broader enterprise federation are outside this MVP. AgentCore remains required by the selected product architecture even though the competition brief permits alternatives.

## 2. Invariants every phase must preserve

1. Trusted server identity determines tenant/project scope across API, tool, job, cache, object download and trace. Composite database constraints enforce ownership; application roles cannot rewrite immutable history.
2. Agents propose and explain. Deterministic commands control amounts, schedules, approval, external messages and payment state. Model output and memory never authorize a write.
3. Human-confirmed effective scope is versioned. Evidence can overturn classification; missing or conflicting support requires clarification. No proposal is authorized from fabricated or stale references.
4. An immutable proposal freezes exact recipients, content, attachment bytes, client URL, scope/evidence versions and commercial terms before review. Concurrent or stale approvals fail.
5. Domain transitions, audit, next jobs and wakeup outbox commit together. The database owns unfinished work; scheduler recovery must survive lost EventBridge delivery.
6. Persist external intent before dispatch. A successful provider write with an unknown local result goes to reconciliation or review. No blind retry or transport fallback.
7. Client acceptance atomically records an amendment and approved revenue once. Full verified payment controls work eligibility; collection and reversals are separate facts.
8. INR values use integer paise and bounded Decimal effort. Unsupported commercial terms require manual handling. Reminders require exact freelancer approval and a fresh payment check.
9. Failures are visible, auditable and recoverable within bounds. Deletion and restore must prevent old capabilities, deleted data or pending writes from being resurrected.
10. All provider, quality, security and performance claims require observed evidence. Fixtures support development; actual-account tests remain separate release gates.

## 3. Delivery sequence and phase gates

| Phase | Prerequisites | Deliverable and exit gate |
| --- | --- | --- |
| [00 Readiness](PHASE_00_READINESS.md) | None | Account eligibility, pinned stack and deployed identity/API/DB/model/connector/SES trace proven |
| [01 Domain](PHASE_01_DOMAIN_FOUNDATION.md) | 00 | Authenticated project shell, ownership constraints, shared states, exact money and revision primitives |
| [02 Durability](PHASE_02_DURABLE_EXECUTION.md) | 01 | Atomic jobs/outbox/audit; fenced recovery and uncertainty handling proven under faults |
| [03 Contracts/requests](PHASE_03_CONTRACTS_REQUESTS.md) | 01, 02 | Confirmed scope and reproducible evidence; ambiguous routing and merge/split safely resolved |
| [04 Reasoning](PHASE_04_AGENT_REASONING.md) | 03 | Bounded Strands analysis; evidence gates and initial held-out evaluation pass |
| [05 Approvals](PHASE_05_APPROVALS_CLIENT_REVIEW.md) | 02, 03, 04 | Frozen review/send; client capability, negotiation and atomic acceptance work |
| [06 Gmail](PHASE_06_GMAIL_SYNC.md) | 02, 03; 05 for full journey | Durable real-mail ingestion, watch/catch-up recovery and disconnect guards pass |
| [07 Payments](PHASE_07_PAYMENTS.md) | 02, 05 | Real test-link handoff, first-event correlation, reconciliation and reversal semantics pass |
| [08 Operations features](PHASE_08_REMINDERS_PRIVACY.md) | 05, 06, 07 | Approved reminders, dashboard, export/deletion and lifecycle schedules pass |
| [09 Release](PHASE_09_RELEASE.md) | All 00–08 | A01–A32 and R01–R18 complete; restore, clean deployment and demo evidence recorded |
| [10 Optional](PHASE_10_OPTIONAL.md) | 00–08 stable; separate capacity | Selected P1 capabilities independently verified; phase 09 rerun where affected |

The default is sequential execution. With additional developers, phase 06 can overlap phase 04/05 after phase 03 contracts stabilize; payment adapter fixtures can be prepared after phase 02, but end-to-end payment completion requires phase 05 acceptance. These are staffing options, not instructions to delegate this planning task.

The critical path is readiness -> identity/domain -> durability -> confirmed scope -> reasoning -> exact approval/acceptance -> payment -> operational features -> release. Gmail readiness starts in phase 00 and full synchronization must join before phase 08. Optional work never delays or substitutes for a required gate.

## 4. Repository and migration strategy

Use the target layout in TDD §67:

| Location | Responsibility | First owner |
| --- | --- | --- |
| apps/web/ | Authenticated screens, review and receipt pages | 00–01 |
| services/api/ | Auth, typed routes, idempotency, public/provider ingress | 01 |
| services/domain/ | Ownership, transitions, money, revisions and transactions | 01 |
| services/workers/ | Dispatch, leases, outbox, sync, actions, reconciliation | 02 |
| services/connectors/ | Scoped reads, manifest checks, deterministic provider adapters | 00/02 |
| services/agents/ | Validated Strands nodes, prompts and bounded orchestration | 03–04 |
| packages/shared-schemas/ | Canonical states/events/API schemas and generated web types | 01 |
| infra/ | Reproducible AWS configuration, network, policies and alarms | 00 onward |
| migrations/ | Ordered schema and ownership/immutability constraints | 01 onward |
| tests/ and fixtures/acme-demo/ | Invariant, integration, evaluation and deployed journey proof | Every phase |

Phase 01 defines the full TDD §46 relationship map and migration ordering, then creates identity/commercial primitives. Phase 02 adds execution/audit; phase 03 adds document/scope/evidence/request records; phase 04 adds analysis artifacts and budgets; phase 05 adds proposals/approval/client grants and the durable payment-request intent; phase 06 adds production OAuth/sync records; phase 07 adds link attempts and payment observations; phase 08 adds reminders/notifications/privacy lifecycle records as needed. Shared tables may appear earlier when a producing phase needs them.

Resolve cyclic foreign keys explicitly through staged creation, appropriate nullability or deferred constraints without weakening ownership. Business revision numbers and row_version are separate. Every migration carries an upgrade check against existing fixtures and compatible rollback or forward-repair guidance. Never keep a database transaction open across a provider/model call.

Select the migration/test/build tooling and precise framework/runtime versions in phase 00 after checking current official documentation through Context7 where available. Pin decisions; do not assume unverified cross-region or cross-version support.

## 5. API and UX completeness

Generate the executable API contract from shared schemas and reconcile it against TDD §48:

| API/UI group | Implementation owner |
| --- | --- |
| Current user, preferences, clients, contacts, projects and navigation | 01 |
| Actions resolve, jobs retry, basic workflow trace and queue health | 02 |
| Document upload/download/correction/retry; scope confirmation/revision | 03 |
| Bindings, mapping diagnostics, event assignment/replay; request clarify/merge/split | 03 |
| Decision inbox/detail/evidence; persisted analysis trace | 04 |
| Proposal revision/approve/reject/waive/withdraw; client exchange/session/review/receipt | 05 |
| Connections connect/callback/disconnect/reconnect/health; Gmail ingress | 06 |
| Payment fetch/reconcile/replace-link; Razorpay ingress and receipt-link result | 07 |
| Reminders approve/dismiss; dashboard; account export/delete; project deletion completion | 08 |
| Complete route inventory and deployed authorization regression | 09 |

The verified-address notification path starts in phase 00 and becomes a durable, usable notification in phase 05. Phase 05 persists payment intent and renders pending/review receipt states; phase 07 supplies the actual provider link. Do not leave fake successful collection in an intermediate UI. Project deletion initially uses a guarded lifecycle state and disabled work; phase 08 completes physical cleanup and status reporting before release.

Required user-visible failure states include unconfirmed scope, unsupported terms/file, ambiguous routing, clarification, stale revision, disconnected integration, exhausted analysis budget, uncertain external action, payment pending/review and deletion in progress. Implement each beside its happy path.

## 6. Milestones and planning assumptions

- **M0 Feasible:** phase 00 evidence proves actual accounts and architecture.
- **M1 Recoverable foundation:** phases 01–03 support durable, isolated fixture ingestion and confirmed scope.
- **M2 Reviewable decision:** phases 04–05 produce and approve exact evidence-backed revisions with client acceptance.
- **M3 Real test collection:** phases 06–07 run the real Gmail-to-Razorpay Test Mode journey.
- **M4 Operable MVP:** phase 08 completes collection follow-up, metrics and data lifecycle.
- **M5 Release candidate:** phase 09 proves required acceptance and reproducibility.

No start date, team size or committed deadline was supplied. The brief's six-week duration is context, not a validated estimate for this scope. After phase 00, estimate remaining task IDs using actual team capacity and spike results; assign owners and dates in the execution tracker. Reforecast at each milestone. If capacity is insufficient, cut phase 10 first; changing R01–R18 requires updating the PRD/TDD and acceptance mapping explicitly.

Roles needed are application/domain, frontend, agent/evaluation, infrastructure/security and a release owner; one person may hold several. No people are assigned by this plan. The implementer must record an accountable owner for each active phase and production incident responsibilities before release.

## 7. Verification and evidence

[ACCEPTANCE_MATRIX.md](ACCEPTANCE_MATRIX.md) maps every R and A identifier to its primary implementation phase, collaborating phases and expected proof. Every phase includes business-invariant tests, negative paths and real-deployment checks appropriate to its change. Phase 09 assembles and reruns the deployed release gate; it is not the first time correctness is tested.

Record each result with case ID, task ID, timestamp, commit, migration/configuration/model/prompt/tool-policy versions, environment, fixture, observed outcome and a sanitized artifact reference. Distinguish local mock, deployed fixture and actual-provider execution. Preserve failures and remediation.

Required gates include:

- At least 120 contract-linked evaluation cases, split 60 development/60 held-out by contract/project; held-out includes at least 20 positive and 20 nonbillable cases.
- Three held-out runs with precision >=95% and positive recall >=80% in each, zero unsupported citations in proposals, and disclosed abstentions/confusion counts.
- Zero unauthorized reads/writes in the two-tenant/two-project adversarial suite.
- Healthy request-to-card p95 <=120 seconds and durable ingress acknowledgment p95 <=2 seconds on a declared workload; preparation deadline 180 seconds.
- Fault injection across commit/publication/provider-write boundaries; paid/reminder races; concurrent approval; stale evidence; deleted/restored data.
- Measured restore against initial RPO <=24h and RTO <=4h targets. Pilot monthly 99.5% availability remains a target until a pilot observation window exists.

An acceptance row becomes Passed only when all required variants are covered. A blocking failed variant keeps the row open. Documentation checks performed while creating these plans are not implementation evidence.

## 8. Risks and decisions to resolve

| Risk/dependency | Owner phase | Planned response and blocking condition |
| --- | --- | --- |
| AgentCore/model/Aurora region intersection or identity/egress failure | 00 | Prove deployed path early; record supported region and pin versions; no silent runtime substitution |
| Gmail OAuth account eligibility, push permission, SES sending restrictions | 00, 06 | Verify real accounts and controlled delivery; release blocked if required path remains fixture-only |
| Razorpay Test Mode/reference lookup or call limits | 00, 07 | Verify current constraints, track real link calls and reserve quota; use mocks for routine tests |
| Large schema and cross-owner/cyclic relationships | 01–03 | Map constraints/migration order first; negative ownership tests at every relation boundary |
| Send/create timeout cannot establish provider result | 02, 05, 07 | Persist uncertainty and reconcile; require evidenced resolution or explicit duplicate-risk decision |
| Incomplete Gmail history or contradictory evidence | 03, 04, 06 | Record coverage, preserve snapshots, revalidate freshness and route unsupported cases to clarification |
| Evaluation quality or model cost/latency misses | 04, 09 | Bounded execution, reviewed prices, diagnostic cases and reevaluation; no weaker thresholds by default |
| Client attribution is bearer possession | 05, 09 | Disclose synthetic-demo limit; explicit stronger identity decision before real-user pilot |
| Reminder dispatch/payment arrival race | 07–08 | Fresh reconciliation and locked state guard; retain honest in-flight residual-risk record |
| Restore resurrects deleted content or old external actions | 08–09 | Durable deletion tombstones, capability revocation and disabled writes until reconciliation |
| Schedule pressure hides required work | Every phase | Milestone reforecast; defer optional features; mark required unverified work as blocked release |

## 9. Completion and change control

All implementation tasks begin unchecked. Suggested states are Not started, In progress, Blocked, Ready for verification and Complete. A phase is Complete only when its exit gate has evidence and its handoff artifacts exist. Do not equate a pull request merge with acceptance.

For a design change, update the authoritative specification first, then affected phase tasks, shared schemas and acceptance rows. Security, exact approval, payment correctness and recovery failures block release. Maintain old evidence as historical and invalidate results affected by code/model/config changes.

The final deliverable is runnable documented code, migrations/infrastructure, pinned configuration, required test evidence, a chosen MIT or Apache-2.0 license, architecture material and an honest video of at most five minutes. Publication, submission and any real-user pilot remain separate actions; this task creates the local implementation plans only.

