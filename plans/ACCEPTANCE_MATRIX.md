# ScopeGuard implementation acceptance matrix

**Baseline:** PRD/TDD v1.1 and architecture resolution register, 7 September 2026  
**Implementation verification:** Phase 01 foundation evidence recorded; full cross-phase acceptance remains pending  
**Purpose:** Assign a primary implementation owner and proof for all R01–R18 requirements and A01–A32 review cases.

The [master plan](MASTER_PLAN.md) controls sequencing. Full scenarios remain authoritative in [REVIEW_RESOLUTION.md](../docs/REVIEW_RESOLUTION.md). Findings 1–32 map respectively to A01–A32. A primary phase implements the core behavior; collaborating phases extend it, and [phase 09](PHASE_09_RELEASE.md) verifies the complete release. A row passes only when every required scenario variant passes.

## 1. Product requirement coverage

| Requirement | Primary phase / task range | Component and API surface | Acceptance |
| --- | --- | --- | --- |
| R01 Tenant/authentication | 01 / P01-03–05 | domain ownership, API auth, me/preferences, verified-address onboarding | A04, A22, A23, A30 |
| R02 Clients/projects/routing | 03 / P03-07–10; foundation 01 | clients/contacts/projects, bindings, event assign/replay, routing UI | A11, A16 |
| R03 Contract/effective scope | 03 / P03-01–06; acceptance 05 | documents/chunks, upload/correction/confirm/revise, effective scope | A08, A18, A20 |
| R04 Gmail lifecycle | 06 / P06-01–11 | OAuth connection routes, Gmail webhook, sync/watch/catch-up workers | A09, A21, A22 |
| R05 Requests/dedupe | 03 / P03-07–09; revision 05 | event/request associations, clarify/merge/split and mapping replay | A10, A24 |
| R06 Reasoning/evidence | 04 / P04-01–12 | Strands nodes, evidence gate, decision/evidence/trace routes | A07, A18, A19, A28 |
| R07 Money/terms | 01 / P01-06–07; 04 / P04-05–06 | Decimal pricing, frozen commercial/calendar versions, supported terms | A06, A19, A27 |
| R08 Freelancer approval/send | 05 / P05-02–06 | immutable revisions, approve route, action guard and Gmail dispatcher | A02, A03, A23 |
| R09 Client review | 05 / P05-06–11 | capability exchange/session, review/approve/reject/request-changes | A03, A15, A24 |
| R10 Accepted amendments | 05 / P05-09–10 | atomic approval/scope/amendment/approved-revenue/payment-intent transaction | A08, A25 |
| R11 Test collection | 07 / P07-01–12 | link attempts, Razorpay webhook, payment fetch/reconcile/replace-link | A02, A06, A12, A13 |
| R12 Reminders | 08 / P08-01–04 | overdue jobs, drafts, approve/dismiss and paid-state dispatch guard | A14, A27 |
| R13 Notifications/handoff | 05 / P05-12; 07 / P07-10 | verified-address SES, client receipt polling and pending/link/review states | A26 |
| R14 Metrics | 08 / P08-05 | authoritative facts, dashboard aggregates and environment isolation | A25 |
| R15 Durability/replay | 02 / P02-01–11 | transactional jobs/outbox/audit, leases, actions, resolve/retry routes | A01, A02, A16, A17 |
| R16 Security/privacy/audit | 08 / P08-07–12; foundations 01–02 | ownership, protected history, export/delete/status, retention/restore | A04, A05, A15, A20, A22, A30, A31 |
| R17 Early/reproducible deployment | 00 / P00-01–10; 09 / P09-09 | infra, identities/network, pinned runtime/model/database/provider setup | A21, A29 |
| R18 Evaluation/demo | 09 / P09-01–13; 04 / P04-11–12 | held-out evaluation, adversarial/fault/e2e suites, release assets | A28, A31, A32 |

Current state: R01, the Phase 01 portions of R02/R07/R16, and the local scaffold for R17 have implementation evidence. Full requirement acceptance remains pending until their later phases and deployed/provider checks pass.

## 2. Acceptance ownership and required evidence

Planned test paths below are targets for implementation, not files claimed to exist. Use test names containing the A identifier so evidence can be traced independently of later file reorganization.

| Case / review finding | Primary phase and tasks | Collaborating phases | Required proof | Status |
| --- | --- | --- | --- | --- |
| A01 Commit/publication | 02 / P02-02–04, P02-11 | 03–08, 09 | Integration fault records for crash after commit, per-entry publish failure and dropped published wakeup; one business effect | Pending |
| A02 Uncertain external write | 02 / P02-06–09, P02-11 | 05, 07, 09 | Gmail send and Razorpay create success/save-loss; persisted uncertainty, evidence-based resolution and no blind repeat | Pending |
| A03 Exact stale-safe approval | 05 / P05-02–06, P05-09 | 01, 07, 09 | Concurrent review/edit, stale commands, exact content/recipient/attachment hash and accepted revision | Pending |
| A04 Tenant/project isolation | 01 / P01-02–05, P01-10 | Every feature, 09 | Two-tenant/two-project matrix over API/tool/job/cache/download/trace; direct cross-owner FK rejection | Foundation implemented; full gate pending |
| A05 Capability allowlist | 04 / P04-09 | 02, optional 10, 09 | Unknown tool and changed schema denied; scoped provider credentials reject mutations even if model requests them | Phase 04 implemented and unit-verified |
| A06 Money units/bounds | 01 / P01-06 | 04, 07, 09 | Decimal/property tests for invalid effort, rounding and cap; real 1,500,000-paise link/payment round trip | Foundation implemented; full gate pending |
| A07 Evidence overturns result | 04 / P04-03–04, P04-11–12 | 03, 09 | Covered prior approval removes proposal; conflicting/incomplete evidence produces clarification | Phase 04 implemented and unit-verified |
| A08 Effective-scope amendment | 05 / P05-09–11 | 03, 04, 09 | One accepted amendment, now-covered repeated request and rejection/revalidation of competing stale baseline | Pending |
| A09 Gmail recovery | 06 / P06-03–08 | 02, 03, 09 | Missing push/expiry/overlap/404/reconnect; durable cursor progress, coverage gaps and no duplicate active request | Pending |
| A10 Delivery/resource/request identity | 03 / P03-01, P03-07–09 | 06, optional 10, 09 | Same business request across deliveries/channels, multi-change message, audited merge/split provenance | Pending |
| A11 Ambiguous project routing | 03 / P03-07–10 | 01, 06, 09 | Shared-contact/channel/repository fixtures require explicit assignment; replay honors selected project once | Pending |
| A12 First-payment correlation | 07 / P07-04–07 | 02, 05, 09 | Observation before link save later associates; wrong order/account/environment cannot close payment | Pending |
| A13 Payment monotonicity | 07 / P07-06–09 | 08, 09 | Permuted failure/capture/expiry/reversal with duplicates; authoritative state and preserved attempts | Pending |
| A14 Reminder race | 08 / P08-01–04 | 02, 07, 09 | Concurrent workers, <=30-second fresh check, paid-before-dispatch cancellation and recorded in-flight residual race | Pending |
| A15 Client capability safety | 05 / P05-06–10, P05-12 | 01, 08, 09 | GET/preview no side effect; scoped/expired/revoked/forwarded tokens; one consumption; receipt-only access | Pending |
| A16 Canonical contracts/states | 01 / P01-01, P01-05, P01-10 | Every feature, 09 | Shared schemas validate examples/enums/transitions; no row-version/business-revision conflation | Foundation implemented; full gate pending |
| A17 Worker fencing/recovery | 02 / P02-04–06, P02-11 | 04, 05, 07, 09 | Kill every node/lease boundary; valid same-input resume within budget; stale commits denied; write uncertainty | Pending |
| A18 Reproducible evidence | 03 / P03-02, P03-06 | 04, 05, 08, 09 | Edited/deleted/missing/paginated sources and invented IDs; retained explainability and stale-approval guard | Pending |
| A19 Estimate provenance | 04 / P04-05–06 | 01, 03, 09 | Missing history/config/capacity produces ranges/cold-start conditions; no invented hours or unsupported date | Phase 04 implemented and unit-verified |
| A20 Bounded ingestion | 03 / P03-02–05 | 02, 04, 09 | Corrupt/bomb/scanned/encrypted/oversized files; no parser egress; paused unconfirmed scope | Pending |
| A21 Actual provider readiness | 00 / P00-01, P00-06–08 | 06, 07, optional 10, 09 | Deployed actual-account read/send/test-link/notification proof; authorized read fallback or explicit blocked state | Pending |
| A22 OAuth lifecycle | 06 / P06-01–02, P06-08 | 00, 02, 05, 09 | State/account mismatch, revoked/concurrent refresh, disconnect-before-send and no cancelled-send resurrection | Pending |
| A23 Consequential authority | 04 / P04-06, P04-09 | 01, 02, 05, 07–08, 09 | Agent amount/order/recipient substitution and memory-rate attack denied; deterministic frozen action values used | Phase 04 implemented and unit-verified |
| A24 Negotiation/revisions | 05 / P05-08, P05-11 | 03, 08, 09 | Discount comments -> new revision/reapproval; old token invalid; repeated waiver produces no collection | Pending |
| A25 Revenue meaning | 08 / P08-05 | 05, 07, 09 | Acceptance posts approved once; independent collection/reversal; duplicates/revisions/environment isolation reconcile | Pending |
| A26 Notification/receipt handoff | 05 / P05-12 | 00, 07, 09 | Browser-closed verified-address delivery; delayed link appears through read-only receipt without duplicate create | Pending |
| A27 Commercial/calendar policy | 01 / P01-06–07 | 03–05, 07–08, 09 | Unsupported terms manual; explicit tax; due UTC instant across DST/weekends and conditional work start | Foundation implemented; full gate pending |
| A28 Evaluation/budgets | 04 / P04-03, P04-07–08, P04-11–12 | 02, 09 | 120-case split/three held-out runs; malformed/loop/timeout/budget bounds; deterministic collection continues | Phase 04 implemented and unit-verified |
| A29 Deployed reproducibility | 00 / P00-02–10 | 01–08, 09 | Clean declared setup proves final Cognito/API/AgentCore/DB/model/provider/SES trace with pinned identities/versions | Pending |
| A30 Integrity/privacy/restore | 08 / P08-07–12 | 01–03, 05, 09 | Invalid relations/duplicate action/audit rewrite rejected; export/delete; pre-deletion restore reapplies tombstones | Pending |
| A31 Operational recovery | 09 / P09-05–09 | 00, 02, 06–08 | Scheduler/connector outage alarms, measured RPO/RTO, compatible rollback and no resurrected external writes | Pending |
| A32 Scope/submission completeness | 09 / P09-01, P09-10–13 | All required phases | Full R/API/component/test inventory, real-vs-fixture labels, clean setup/license/architecture and <=5-minute video | Pending |

## 3. Planned suite organization

| Suite target | Responsibilities |
| --- | --- |
| tests/unit/ | Money/calendar, hashes, state transitions, deterministic classification/evidence validators and scoped command policy |
| tests/integration/ | Real database constraints/transactions, concurrency/fencing, immutable object references, OAuth/provider fixture contracts and fault injection |
| tests/evaluation/ | Frozen development/held-out datasets, three-run metrics, provenance, injection and bounded model behavior |
| tests/e2e/ | Authenticated/private and client/public journeys, notifications, approval/payment/reminder alternatives and actual-provider checks |
| infra/ and release run records | Clean deployment, identities/egress, alarm exercises, backup/restore and compatible rollback |

Select exact file names/frameworks in phase 00. Do not write tests solely to mirror an implementation branch; prove the invariant and failure result. Mocked provider success is insufficient for A21/A29 or the real demo.

## 4. Evidence record template

Store sanitized run records with the implemented test artifacts; keep sensitive raw provider data in access-controlled storage. A suggested release evidence directory is docs/implementation-evidence/, to be created during implementation.

~~~yaml
case_id: A01
task_ids: [P02-02, P02-03, P02-11]
status: Pending
timestamp_utc: null
owner: Unassigned
commit: null
environment: null
execution_kind: null # local-mock, deployed-fixture, actual-provider, restore-drill
configuration_and_migration_versions: []
model_prompt_schema_tool_versions: []
fixture_and_variants: []
expected_invariants: []
observed_result: null
sanitized_artifact_references: []
failures_and_remediation: []
superseded_evidence: []
~~~

Record actual observations before changing status to Passed. Failed and blocked variants remain visible. Configuration/model/prompt/schema/tool changes invalidate affected prior results and trigger scoped reruns; unchanged unrelated checks need not be repeated during each phase.

## 5. Execution tracking convention

Each phase file contains stable checkbox task IDs. Add an assigned owner, start date and evidence reference when execution begins; leave unfinished boxes unchecked. Track blockers with their dependency, current observation and next action. A phase may have implementation tasks done while acceptance is still pending.

Use this matrix for acceptance status and phase checkboxes for task progress. Do not maintain a second contradictory acceptance register: the resolution document remains the scenario definition, and its verification summary should point to actual run evidence when available.

