# ScopeGuard implementation plans

Created 7 September 2026 from the revised architecture. Planning is complete when these documents are reviewed; implementation remains **Not started**.

Start with [MASTER_PLAN.md](MASTER_PLAN.md), then use [ACCEPTANCE_MATRIX.md](ACCEPTANCE_MATRIX.md) to track proof. Execute the required phases in dependency order:

| Phase | Plan | Outcome |
| --- | --- | --- |
| 00 | [Readiness](PHASE_00_READINESS.md) | Actual accounts and an early deployed slice |
| 01 | [Domain and identity](PHASE_01_DOMAIN_FOUNDATION.md) | Trusted ownership, shared contracts, commercial rules |
| 02 | [Durable execution](PHASE_02_DURABLE_EXECUTION.md) | Recoverable jobs, audit, outbox and external actions |
| 03 | [Contracts and requests](PHASE_03_CONTRACTS_REQUESTS.md) | Confirmed scope, evidence, routing and request provenance |
| 04 | [Agent reasoning](PHASE_04_AGENT_REASONING.md) | Validated proposals with measured evidence quality |
| 05 | [Approvals and client review](PHASE_05_APPROVALS_CLIENT_REVIEW.md) | Exact approved sends and atomic accepted amendments |
| 06 | [Gmail synchronization](PHASE_06_GMAIL_SYNC.md) | Reliable live ingestion and OAuth lifecycle |
| 07 | [Payment collection](PHASE_07_PAYMENTS.md) | Correlated, reconciled Razorpay Test Mode collection |
| 08 | [Reminders, metrics and privacy](PHASE_08_REMINDERS_PRIVACY.md) | Approved reminders, accurate totals and data lifecycle |
| 09 | [Hardening and release](PHASE_09_RELEASE.md) | Failure/restore evidence and reproducible submission |
| 10 | [Optional enhancements](PHASE_10_OPTIONAL.md) | Independently gated P1 additions |

All checkboxes represent future work. A plan, fixture, mock response or successful deployment by itself does not prove acceptance. Phase 10 is excluded from the MVP completion gate.

