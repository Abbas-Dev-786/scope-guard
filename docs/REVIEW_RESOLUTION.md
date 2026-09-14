# Architecture Review Resolution and Acceptance

**Date:** 7 September 2026  
**PRD/TDD revision:** 1.1  
**Status:** 32 findings addressed in the specification; implementation verification pending

The historical [ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md) describes version 1.0. Its references and severity are preserved. This register shows where each design gap is addressed and what executable proof remains necessary.

“Specified” means the documentation now defines a behavior, constraint or explicit MVP limitation. It does not mean software exists, providers are configured, or tests have passed. Actual account eligibility and deployed behavior remain open release gates.

## 1. Finding-by-Finding Resolution

| Finding | Design resolution | Current specification | Acceptance case |
| --- | --- | --- | --- |
| 1. Commit/publication gap | Domain change, audit, next job and wakeup outbox committed together; scheduled job recovery | TDD §3, §14, §59 | A01 |
| 2. Side-effect idempotency | Immutable action intents, DISPATCHING/UNKNOWN_OUTCOME, provider-specific reconciliation | TDD §32, §36, §58 | A02 |
| 3. Stale/mutable approval | Canonical immutable revision includes recipient/body/terms/URL; expected version/hash; no post-approval regeneration | PRD §15–16; TDD §28–35 | A03 |
| 4. Tenant/project isolation | Trusted context for APIs/tools/jobs, per-object checks and composite ownership constraints | TDD §7, §46, §52–53; THREAT_MODEL.md | A04 |
| 5. Unsafe GitHub filters | Explicit reviewed read capabilities and deny-unknown server manifest | TDD §10, §49–50 | A05 |
| 6. Money units/types | Integer paise, INR, Decimal effort, bounds and deterministic rounding | PRD §7; TDD §20, §27 | A06 |
| 7. Evidence cannot overturn result | Validated evidence gate routes conflicts/coverage gaps to clarification and accepted scope to no action | TDD §19, §22–25 | A07 |
| 8. Scope amendment lifecycle | Immutable effective scope versions and atomic accepted amendment | PRD §9, §17–18; TDD §35, §44 | A08 |
| 9. Gmail sync omissions | Watch renewal, serialized cursor, bounded backfill, catch-up and 404 recovery | TDD §8; OPERATIONS.md §3–4 | A09 |
| 10. Duplicate requests/resources | Separate delivery/resource/request identities, many-to-many provenance, conservative merge/split | TDD §12, §17, §46 | A10 |
| 11. Shared client routing | Explicit precedence, shared candidate bindings, ambiguity decision and replay | PRD §6; TDD §17, §48 | A11 |
| 12. First-payment correlation | Preserve link/order/reference/account context; durable unmatched-event reconciliation | TDD §38–39 | A12 |
| 13. Payment/order conflation | Independent order/collection states, attempts and reversal facts; late-event monotonicity | PRD §17; TDD §39, §46–47 | A13 |
| 14. Reminder state/race | Due dates/policy/step/action history; pre-send reconciliation and local paid-state guard | PRD §15; TDD §41 | A14 |
| 15. Client token/identity | Opaque hashed revision grants, fragment exchange, atomic consumption, receipt-only access and explicit attribution limit | TDD §33–35; THREAT_MODEL.md §5 | A15 |
| 16. Conflicting enums/contracts | Shared canonical event registry, separate entity states and expected-row-version convention | PRD §17; TDD §13, §16, §47–48 | A16 |
| 17. Durable execution gap | Job leases, generations, heartbeats, attempts, deadlines and sweep recovery | TDD §3, §21, §59–60 | A17 |
| 18. Reproducible evidence | Snapshots/digests/excerpts, versioned locators, coverage and freshness guard | TDD §24–25, §45 | A18 |
| 19. Unfounded estimates | Decimal task ranges, verified history or cold-start label, calendar/capacity conditions | PRD §8, §30; TDD §26–27 | A19 |
| 20. Ingestion/error contracts | Supported formats/limits, isolated extraction, correction, confirmation and blocked project jobs | PRD §12; TDD §42–45 | A20 |
| 21. Provider eligibility/fallback | Manifest, current eligibility constraints, actual-account readiness gate and read/write fallback distinction | TDD §6–11; OPERATIONS.md §1 | A21 |
| 22. OAuth lifecycle | User-bound single-use state, identity check, serialized refresh, revoke/disconnect/reconnect | TDD §57; OPERATIONS.md §4 | A22 |
| 23. Consequential tool authority | All sends/payment mutations deterministic; exact action guard; memory nonauthoritative | PRD §10, §15; TDD §49, §51, §56 | A23 |
| 24. Revision/negotiation loop | Client comments never mutate price; new revision/reapproval; reject/waive/merge/split semantics | PRD §9, §26; TDD §47–48 | A24 |
| 25. Revenue ambiguity | Revenue Protected at client acceptance; collected separately, no duplicate increment, gross test totals | PRD §19, §30; TDD §35, §39 | A25 |
| 26. Notification/payment handoff | Verified freelancer SES notifications and capability-scoped receipt polling | PRD §4, §16, §27; TDD §34, §66 | A26 |
| 27. Commercial policy | Narrow INR/full-payment policy, explicit tax/due date/pay-before-work and unsupported-term handling | PRD §7; TDD §27, §36, §44 | A27 |
| 28. Validation/evaluation/budgets | Per-node validation, bounded repair, held-out repeat evaluation and durable usage limits | PRD §28; TDD §55, §62, §70–74 | A28 |
| 29. Late deployment decisions | First-phase deployed readiness slice, pinned versions/region and explicit network/identity record | TDD §5, §68, §75; OPERATIONS.md §1 | A29 |
| 30. Integrity/audit/privacy | Ownership/uniqueness constraints, immutable audit/revisions, deletion and retention contract | TDD §46, §61; OPERATIONS.md §5; THREAT_MODEL.md | A30 |
| 31. Operational readiness | Measured targets, freshness/lag alerts, restore/rollback/replay runbooks and incident owner | TDD §62; OPERATIONS.md | A31 |
| 32. Conflicting MVP scope | One PRD R01–R18 cut line, full API inventory, early deployment and acceptance mapping | PRD §20–23, §33; TDD §48, §75–78 | A32 |

All rows have status **Specified / not yet implementation-verified**. Provider eligibility in finding 21 is a recorded dependency, not a claim that documentation can grant access.

## 2. Required Acceptance Cases

| ID | Scenario | Required observed result |
| --- | --- | --- |
| A01 | Crash after domain commit; fail individual EventBridge entries; drop a published wakeup | Original next job survives and sweep executes it; one business effect |
| A02 | Provider send/link succeeds, response and DB save fail | UNKNOWN_OUTCOME; reconcile success or require review; no automatic repeat through another transport |
| A03 | Two tabs edit/approve concurrently; body/recipient/attachment changes after review | Stale command rejected; sent/accepted artifact matches approved revision; all versions preserved |
| A04 | Two tenants and two projects share similar contacts; substitute IDs across API/tool/download/cache/job paths | No unauthorized content or mutations; invalid ownership FKs rejected |
| A05 | MCP tools/list adds update_issue or changes a read schema | New capability denied until manifest review; provider credentials still reject writes |
| A06 | Fractional hours, malformed/nonfinite/negative effort, bounds/rounding; ₹15,000 link/payment | Exact 1,500,000 paise round trip; invalid values rejected without minimum-fee masking |
| A07 | Preliminary change later reveals prior approval or contradictory promise | Covered request produces no proposal; conflict produces clarification |
| A08 | Client accepts an amendment; repeated request arrives; second old-baseline proposal is approved | Effective scope contains amendment once; repetition covered; stale second approval requires revalidation |
| A09 | Expired watch, missing push, overlapping history pages, 404 and reconnect | Visible bounded recovery with coverage gap; cursor advances only after durable normalization; no duplicate active request |
| A10 | Same request across provider deliveries/channels; one message contains two changes | One associated proposal for same request; explicit split/merge preserves provenance; distinct changes retained |
| A11 | Client email/channel/repository maps to two projects | Explicit unique assignment or mapping decision; replay uses chosen project with audit |
| A12 | First payment arrives before local link persistence; same amount on another order/account | First observation reconciles later; unrelated observation cannot close request |
| A13 | Fail then capture; capture then delayed failure; expiry then verified capture; reversal | Correct authoritative collection state; no regressions or duplicated metric postings |
| A14 | Two reminder workers; paid state committed before dispatch; payment after dispatch begins | One step/action; queued obsolete send cancelled; in-flight residual timing recorded honestly |
| A15 | Link preview, forwarded token, wrong-order token, expired/revoked token and simultaneous acceptance | No GET side effect; scoped disclosure; single approval/amendment; receipt-only access after consumption |
| A16 | Validate documented examples, enums and all transition edges against shared schemas | No alternate spellings or workflow/payment-state confusion; version conflicts are deterministic |
| A17 | Kill analysis at every node/lease boundary and kill action worker after dispatch | Resume validated same-input work within budget; stale generation cannot commit; write becomes uncertain |
| A18 | Source edited/deleted; search pagination incomplete; evidence reference invented | Saved evidence remains explainable within retention; stale/invalid evidence cannot authorize unsupported proposal |
| A19 | Missing historical duration, unavailable client configuration, conflicting project capacity | Cold-start/range/conditions shown; no inferred actual hours or unsupported fixed date |
| A20 | Corrupt DOCX, expansion bomb, scanned/encrypted PDF, large file, event before scope confirmation | Bounded actionable rejection/pause; no active unconfirmed scope; no outbound parser fetch |
| A21 | Actual demo accounts from deployed runtime; disable chosen MCP read path | Eligibility/read capability proven; authorized REST parity or visible blocked state; no repeated uncertain write |
| A22 | OAuth state mismatch, revoked token, concurrent refresh, account switch, disconnect before dispatch | Correct owner/account maintained; reauthorization state; no automatic resurrection of cancelled actions |
| A23 | Agent passes a different amount/order/recipient or tries direct sending; memory suggests new rate | Command denied or frozen approved values loaded; no agent-side external mutation |
| A24 | Client requests discount, freelancer revises, old token is used; waiver repeated | New approval required; stale token invalid; waiver does not create collection |
| A25 | Client approval then payment, duplicate events, multiple revisions, reversal and test/live separation | Approved revenue increments once on acceptance; collection is independent; totals match authoritative records |
| A26 | Browser closed at proposal creation; client approves while link creation is slow | One actionable verified-address notification; pending receipt becomes link/review without creating duplicates |
| A27 | Contract requires post-delivery payment; zero-tax synthetic terms; timezone/DST/weekend boundaries | Unsupported contract routed to manual handling; approved terms/UTC due instant consistent |
| A28 | Malformed model output, invalid ID, loop, timeout, daily budget depletion; held-out dataset | Bounded failure without commitment; deterministic collection continues; specified quality/latency gates measured |
| A29 | Clean deployment with declared setup only | Cognito/API/AgentCore/DB/model/provider/SES/trace path works with pinned versions and intended identities |
| A30 | Invalid cross-owner relation, duplicate action, audit rewrite, export/delete, restored pre-deletion backup | Constraints hold; immutable history protected; secrets excluded; deletion reapplied before access |
| A31 | Stop scheduler/integration; fill queue; restore backup and roll back compatible application version | Actionable alarms, safe recovery, measured RPO/RTO, no resurrected external writes |
| A32 | Trace every R01–R18 requirement to API/component/test and rehearse submission | No contradictory hidden P0; required real integrations labeled honestly; five-minute video and assets complete |

## 3. Product Requirement Traceability

| PRD requirement | Primary TDD sections | Acceptance |
| --- | --- | --- |
| R01 Tenant/authentication | 7, 46, 52–57 | A04, A22, A23, A30 |
| R02 Clients/projects/routing | 17, 46, 48 | A11, A16 |
| R03 Contract/effective scope | 25, 42–46 | A08, A18, A20 |
| R04 Gmail lifecycle | 8, 14–15, 57 | A09, A21, A22 |
| R05 Requests/dedupe | 12, 17, 47–48 | A10, A24 |
| R06 Reasoning/evidence | 19, 21–26, 55, 70 | A07, A18, A19, A28 |
| R07 Money/terms | 20, 26–28, 36 | A06, A19, A27 |
| R08 Freelancer approval/send | 28–32, 56, 58 | A02, A03, A23 |
| R09 Client capability/review | 33–35, 47–48 | A03, A15, A24 |
| R10 Accepted amendments | 35, 44, 46 | A08, A25 |
| R11 Test collection | 11, 36–39, 47, 58 | A02, A06, A12, A13 |
| R12 Reminders | 40–41, 48 | A14, A27 |
| R13 Notifications/handoff | 34, 63–66 | A26 |
| R14 Metrics | 35, 39, 62; PRD §19 | A25 |
| R15 Durability/replay | 3, 14, 46, 58–60 | A01, A02, A16, A17 |
| R16 Security/privacy/audit | 46, 53–57, 61; supporting runbooks | A04, A05, A15, A20, A22, A30, A31 |
| R17 Early deployment | 5, 68, 75 | A21, A29 |
| R18 Evaluation/demo | 69–78 | A28, A31, A32 |

## 4. Current Verification Record

| Verification | Status |
| --- | --- |
| PRD/TDD rewritten around the 32 findings | Completed at documentation level |
| Security, operations and acceptance specifications added | Completed at documentation level |
| Static document structure, local links, numbering and cross-reference checks | Passed 7 September 2026: 36/79 consecutive sections, local links, balanced fences, two JSON examples, legacy-enum scan, R01–R18 and A01–A32 coverage; not application tests |
| Pricing example arithmetic/bounds check | Three decimal arithmetic examples and INR/paise conversion checked with PowerShell/.NET on 7 September 2026. Python is unavailable, so the Python snippet and its error/bounds paths remain unexecuted; no provider integration proof |
| Application implementation / migrations / OpenAPI schemas | Implemented through Phase 07; full Python suite, OpenAPI generation, migration drift check, web typecheck/lint/build pass |
| Actual OAuth/MCP/SES/Razorpay account readiness | Partial: SES sender/account and Razorpay Test Mode read accepted; Gmail live OAuth/send/watch, SES receipt, and ScopeGuard payment correlation remain pending |
| Deployed AgentCore/network/database/model path | AgentCore runtime invocation, direct Bedrock invocation, staging API health/database check and protected-route 401 evidence verified; full private/clean-recreation trace remains pending |
| A01–A32 executable acceptance and security results | Pending |
| Restore and measured service levels | Pending |
| Real-user pilot decisions | Pending; MVP remains synthetic Test Mode |

Implementation evidence should add timestamp, commit/configuration/model versions, environment, case ID, observed outcome and a sanitized log/artifact reference. Keep failed outcomes and remediation history. Never replace pending with passed solely because a corresponding paragraph exists.
