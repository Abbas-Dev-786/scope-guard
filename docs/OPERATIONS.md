# ScopeGuard Operations and Recovery

**Version:** 1.1
**Date:** 14 September 2026
**Status:** Staging runtime and local clean database provisioned; live provider, private-cloud authorization, and full recreation gates remain open

This document supports PRD R04 and R11–R18 and TDD §58–78. Defaults are initial engineering targets for the test environment, not achieved service claims or provider guarantees.

## 1. Deployment Readiness Record

Complete these fields with observed evidence before full implementation depends on the selected stack:

| Item | Required record | Current status |
| --- | --- | --- |
| AWS region | Nova Lite active in both candidate regions; staging deployed in us-east-1; Aurora major/proxy intersection remains conditional | Partial |
| Runtime/dependencies | Python/Node/pnpm/uv locks, AgentCore runtime, staging image revision 42, and production build verified | Verified for staging |
| Database | Fresh PostgreSQL 16.6 migrated through 0014 with no drift; staging Aurora/RDS Proxy route and health verified, but private role/backup limits remain unverified | Partial |
| Model | Nova Lite access, structured output, three-run evaluation, reviewed prices and staging ceiling verified | Verified for staging |
| Network | API health/readiness, public model/provider egress, and staging Lambda-to-RDS Proxy route verified; private DB role/security matrix remains open | Partial |
| Gmail | OAuth scopes and account identity, watch/push authentication, sync, read and send proof | Pending |
| Razorpay | Test Mode account read and provider lookup accepted; ScopeGuard-owned link/webhook correlation remains unproven | Partial |
| SES | Verified sender and sandbox acceptance observed; inbox delivery remains unverified | Partial |
| Hosting/Cognito | Pool/client/callback, protected-route rejection, and one deployed cross-tenant object boundary verified; broader owner/object authorization matrix remains open | Partial |
| Telemetry | Request/audit correlation and AgentCore CloudWatch/X-Ray enabled; full redacted end-to-end trace remains open | Partial |
| GitHub/Slack | Eligibility and approved read manifest if P1 integration is enabled | Optional; pending |
| Data lifecycle | KMS/private S3/log retention and immutable-role declarations verified; backup/restore/deletion exercise remains open | Partial |

Changing region/model/provider path requires updating the readiness record and affected acceptance tests. Do not commit credentials, email contents or bearer tokens in this record.

## 2. Initial Targets and Capacity

| Signal | Target or alarm |
| --- | --- |
| Healthy request-to-card latency | p95 <=120 seconds on the documented test load; preparation deadline 180 seconds |
| Provider ingress latency | p95 durable acknowledgement <=2 seconds for accepted bounded payloads |
| Pilot service availability | Initial monthly target 99.5%; measurement starts only once a pilot exists |
| Oldest runnable job/outbox | Warn at 2 minutes; actionable operator alert at 5 minutes |
| Expired job lease | Sweep every minute; alert if unresolved after two sweeps |
| Action uncertainty | Surface immediately; alert if unreconciled after 5 minutes |
| Gmail watch | Renew daily; warn on repeated failure or expiry within 24 hours |
| Gmail coverage | Catch-up every 15 minutes; warn if last successful sync >30 minutes during active monitoring |
| Unmatched payment | Retry with backoff for 24 hours, then manual review; keep replayable |
| Pending payment reconciliation | Every 15 minutes; daily recent-paid checks during 30-day receipt window |
| Preparation concurrency | One per tenant, four globally, configurable downward for provider limits |
| Database capacity | Limit worker concurrency/pools; reserve at least 30% of configured connections for API/recovery |
| Token budget | 40k input/8k output per analysis including retries; 250k/day per tenant; 1m/day deployment default |
| Monetary budget | Operator configures a ceiling and reviewed model prices before enabling analysis; no missing-price fallback |
| Backup objective | Initial RPO <=24 hours and RTO <=4 hours for the pilot target |

A burst/load fixture must report event volume, provider fixture/live mix, model/configuration versions and measured percentiles. No current workload capacity is claimed until tested. Payment/webhook/receipt handling reserves capacity and continues even if model budget is exhausted.

## 3. Routine Schedules

The one-minute sweeper republishes due outbox wakeups, dispatches runnable jobs, discovers expired leases, and finds orphaned domain intents. Jobs themselves remain the source of unfinished work.

Separate scheduled tasks renew Gmail watches daily; run mailbox catch-up every 15 minutes; reconcile pending payments every 15 minutes; check recently paid collection daily; draft overdue reminders at the defined three/seven-day steps; flag 14-day overdue review; expire unaccepted capabilities; and execute retention tasks.

Scheduler overlap uses unique job keys and claims. A stale lease on an external write results in reconciliation, never automatic second dispatch. Provider throttling lowers throughput and uses bounded Retry-After/backoff without losing jobs.

## 4. Runbooks

### Event publication or delivery failure

Inspect outbox entry results, permissions, bus/rule configuration and runnable-job age. Resume publisher/sweeper using original IDs. A stored domain transition already includes its next job, so recovery must not create a second business action. Do not delete pending outbox rows to silence alarms.

### Dead analysis worker

Check lease generation/deadline, output hashes and model usage. Resume same-input validated nodes only, otherwise rerun preparation within remaining attempt/budget limits. Cancel stale workers' future writes via generation checks. Do not reset aggregate versions or reuse another tenant's runtime session.

### Email or payment-link UNKNOWN_OUTCOME

Freeze repeats. Inspect approved action/revision digest and provider evidence. Gmail lookup validates message marker, recipient and content; missing search results do not establish failure. Razorpay lookup validates the persisted reference, merchant/environment and exact amount.

Record confirmed success with provider evidence; record confirmed rejection before retrying. If ambiguity remains, show REVIEW_REQUIRED. Manual resend requires explicit acknowledgement of possible duplicate delivery, while payment-link replacement requires authoritative old-link cancellation/expiry and no collection. Never fabricate provider IDs or mark a payment paid manually.

### Gmail watch expiry, history 404 or revoked OAuth

Pause claims of complete monitoring. Renew/re-authorize the intended account, keep its old checkpoint, and run bounded full sync/catch-up with deduplication. Record recoverable and unrecoverable coverage windows. Initial or restored historical messages are evidence-only unless explicitly selected for new analysis.

Disconnect prevents credential use immediately. Provider watch-stop/revocation failures are retried independently; they must not re-enable the connection. Reconnect never silently changes the provider account or revives cancelled sends.

### Payment mismatch or out-of-order observation

Keep raw authenticated observation, account/link/order/reference association and provider snapshots. Serialize reconciliation and fetch current authoritative state. Preserve capture/reversal facts; a delayed failure cannot negate verified collection. Unmatched events remain durable for later association.

If a reversal occurs, set REVERSED and create a human review decision. Do not issue refunds, new payment requests or reminders automatically. Keep the approval/amendment audit intact.

### Obsolete reminder

If payment is committed before reminder dispatch is claimed, cancel the reminder. If dispatch already started, record the timing and suppress future reminders; do not claim the email was recalled. Provider notifications/reminders remain disabled so two systems do not independently chase the same payment.

### Account or project deletion

Disable logins/access where applicable, grants, connectors, jobs and unsent actions first. Queue deletion across relational rows, S3 versions, derived search/embeddings, logs within policy and optional memory. Record progress without retaining deleted personal content in the deletion journal. Uncertain in-flight effects are resolved/audited before losing necessary reconciliation references.

A tenant export is authenticated, time-limited and excludes secrets/bearer grants. Project deletion checks ownership and does not delete another project's shared connection. Deleting a whole account revokes all its connections.

## 5. Retention and Restore

Initial synthetic-test defaults:

| Data | Retention/deletion policy |
| --- | --- |
| Raw provider payloads and non-cited communication snapshots | 30 days |
| Confirmed contracts, cited evidence, revisions, approvals and payment facts | While project is active; delete 90 days after archive or through requested deletion |
| Operational logs | 30 days; metadata only, no secrets or raw content |
| Job/action diagnostics | 30 days after terminal completion; required financial/action evidence follows project retention |
| OAuth state and client sessions | Purge expired transient records daily; retain only minimal security audit |
| API idempotency responses | 30 days; domain action uniqueness remains with the order |
| Backups | Encrypted, 30-day rolling retention; access limited to restoration role |
| Deletion completion | Primary stores within seven days of approved request; backups age out within 30 days |
| Optional embeddings/memory | Same deletion boundary as their source; invalidate immediately when source access is removed |

These are product defaults for synthetic data. A real-user pilot must explicitly review evidence retention, contractual record needs and deletion expectations before activation. Disconnect revokes access but does not itself delete previously authorized project evidence; the UI explains separate deletion controls.

Configure daily encrypted database backups/PITR as supported by the selected deployment, and protected versioned S3 evidence backups in the approved region. Verify backup access, integrity and quotas. Deletion tasks must enumerate and purge relevant object versions; a delete marker alone is not evidence of physical deletion.

Restore procedure:

1. Disable provider writes, notifications and automatic job dispatch.
2. Restore database and evidence to a consistent point; verify revision hashes and referential integrity.
3. Reapply deletion tombstones and revoke old public sessions/grants before access resumes.
4. Treat all restored DISPATCHING actions as UNKNOWN_OUTCOME; reconcile against provider state before any retry.
5. Resume Gmail/payment catch-up from recorded checkpoints, declaring any coverage gaps.
6. Verify a waiting approval, pending payment, deleted tenant and completed send before reenabling workers.

Run a restore exercise before a real-user pilot. Record actual RPO/RTO and discrepancies; a backup configuration screenshot alone is insufficient.

## 6. Deployment, Migration and Rollback

Infrastructure is reproducible and environment-separated. Migration deployment records schema compatibility and backup point. Prefer additive changes; new workers understand queued schema versions before producers emit them.

Rollback pauses new producers/dispatch, reverts compatible code/configuration and preserves immutable approvals, events and payment facts. Do not reverse external actions or delete committed data as an application rollback. Incompatible migrations require a planned restore/reconciliation process.

Service credentials rotate through versioned secret references. Check active jobs against connection/credential version; invalid credentials produce reauthorization rather than uncontrolled retries. Keep an audited operator identity for recovery, separate from application credentials.

## 7. Incident Ownership and Release Status

The deploying project owner is the initial incident owner. Record named ownership/contact in environment configuration before enabling real provider connections. Tenant-visible health decisions and operator alarms have separate audiences; no sensitive communication content is sent in alerts.

Record incidents with timeline, affected tenant/project scope, confirmed effects, uncertainty, recovery actions and evidence. Security incidents rotate/revoke relevant credentials and capabilities and pause affected writes before recovery.

Every readiness item and acceptance result is pending until actual evidence is entered in REVIEW_RESOLUTION.md. Documentation changes do not constitute deployed controls or passing tests.
