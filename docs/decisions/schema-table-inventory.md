# Schema table ownership inventory

**Source of truth:** TDD section 46  
**Purpose:** Fix ownership, immutability, and delivery phase before later migrations are written.

Every tenant-owned table carries `tenant_id` and `UNIQUE (tenant_id, id)`. Every project-owned table also carries `project_id` and `UNIQUE (tenant_id, project_id, id)`. References to tenant/project-owned records use those composite keys. “Immutable” means ordinary application roles can insert and select; corrections create a new revision. Lifecycle deletion uses a separately granted role.

| Table | Ownership | Phase | Mutation class |
| --- | --- | ---: | --- |
| users | tenant identity | 01 | versioned row |
| preference_versions | tenant | 01 | immutable |
| clients | tenant | 01 | versioned row |
| client_contacts | tenant + client | 01 | append/remove by lifecycle |
| projects | tenant + client | 01 | versioned row |
| calendar_versions | tenant + project | 01 | immutable |
| api_idempotency | actor scope | 01 | expiring receipt |
| audit_events | tenant, optional project | 01 | append-only |
| jobs | tenant, optional project | 02 | leased/versioned |
| outbox_events | tenant + job | 02 | monotonic publication |
| consumer_receipts | consumer + event | 02 | insert-only |
| workflow_instances | tenant, optional project/request | 02 | versioned state |
| external_actions | tenant, optional project/revision | 02 | fenced/versioned |
| action_attempts | external action | 02 | append-only attempts |
| integration_connections | tenant + provider account | 03 | versioned state |
| oauth_sessions | tenant + provider | 03 | single-use state |
| project_integration_bindings | tenant + project + connection | 03 | versioned state |
| thread_assignments | tenant + project + connection | 03 | audited assignment |
| mailbox_sync | tenant + connection | 03 | leased/versioned |
| documents | tenant + project | 03 | immutable source after acceptance |
| document_chunks | tenant + project + document | 03 | immutable source |
| scope_versions | tenant + project | 03 | immutable |
| scope_items | tenant + project + authoritative source | 03 | immutable |
| scope_version_items | tenant + project + scope version/item | 03 | immutable membership |
| external_events | tenant + connection | 03 | immutable provider receipt |
| communication_events | tenant, project after routing | 03 | immutable source version |
| requests | tenant + project | 03 | versioned state |
| request_communications | tenant + project + request/event | 03 | audited association |
| agent_runs | tenant + workflow | 04 | immutable attempts |
| scope_assessments | tenant + project/request/workflow | 04 | immutable validated output |
| evidence_bundles | tenant + project/assessment | 04 | immutable snapshot |
| evidence_references | tenant + bundle/source | 04 | immutable provenance |
| budget_windows | tenant/deployment scope + UTC day | 04 | atomic counters |
| budget_reservations | job + budget window | 04 | monotonic settlement |
| change_orders | tenant + project/request | 05 | versioned state |
| proposal_revisions | tenant + project/change order | 05 | immutable |
| approvals | tenant + project/revision | 05 | immutable |
| client_capabilities | tenant + project/revision/client | 05 | activation/consumption state |
| client_sessions | capability | 05 | expiring/revocable |
| scope_amendments | tenant + project/accepted revision | 05 | immutable |
| decisions | tenant, optional project | 05 | versioned state |
| decision_revisions | decision | 05 | immutable |
| communication_draft_revisions | tenant + project/reminder | 05 | immutable |
| payment_requests | tenant + project/accepted revision | 07 | versioned state |
| payment_link_attempts | tenant + project/payment request/action | 07 | immutable attempt facts |
| payment_attempts | tenant + payment/link/provider account | 07 | monotonic provider facts |
| payment_observations | tenant + connection/external event | 07 | reconciliation state |
| reminders | tenant + project/payment request | 08 | versioned state |
| reminder_approvals | tenant + project/reminder/draft | 08 | immutable |
| notifications | tenant + decision/action | 08 | monotonic delivery state |
| deletion_tasks | tenant + resource scope | 08 | lifecycle state |

The exact fields, checks, partial uniqueness, hot indexes, and lock order remain defined in TDD sections 46–47. Later migrations must update this inventory and the owning phase together when a relationship changes.
