# Phase 04 — Bounded Strands reasoning and evaluation

**Status:** Complete | **Required:** Yes | **Depends on:** Phase 03
**Owns:** R06 and analytical R07/R18; A05, A07, A19, A23, A28
**References:** [Master](MASTER_PLAN.md), [TDD](../docs/TDD.md) §19–29, §49–56, §62, §70–74.

## Objective and boundary

Turn confirmed scope and authorized evidence into a supported, explainable proposal candidate. Prove quality and limits before allowing human approval to trigger a send. Pricing and scheduling continue to use phase 01 deterministic services.

## Ordered implementation tasks

- [x] P04-01 Implement persisted node inputs/outputs, agent_runs, assessments, evidence bundles, draft/decision revisions and durable budget windows/reservations. Workflows, agent runs, immutable scope assessments, evidence bundles, decision inbox rows, draft revisions, and cumulative tenant/deployment token/cost reservations are persisted with versioned inputs and safe summaries.
- [x] P04-02 Implement Scope, Evidence, Impact, Change Order and Communication roles with distinct responsibilities and narrow capabilities; integrate the Contract Structure role from phase 03. The primary demo must show at least four meaningful distinct Strands roles.
- [x] P04-03 Validate every structured output against shared schemas, reference existence, allowed classifications and trusted ownership. Allow only one bounded repair; invalid output terminates safely with a visible failure/clarification state.
- [x] P04-04 Implement the evidence gate after preliminary classification. Accepted scope or prior amendments can overturn an additional-scope finding. Conflicting promises, unavailable required evidence or incomplete coverage require clarification; no priced unsupported proposal continues.
- [x] P04-05 Implement task-level low/recommended/high effort ranges with cited assumptions and cold-start labeling when history is absent. Do not infer actual hours from commits/issues. Apply calendar capacity and prerequisites without an unsupported fixed delivery promise.
- [x] P04-06 Call deterministic money/terms services with validated effort and frozen preference/calendar versions. The synthetic fixture yields INR 15,000, zero explicit tax and two working days at seven hours/day, conditional on full payment and prerequisites.
- [x] P04-07 Enforce cumulative preparation deadline 180 seconds, node 60 seconds, tool 15 seconds, 20 reads, 40k input/8k output tokens, three bounded job attempts and one repair. Reserve/reconcile usage across retries; do not reset allowance on resume.
- [x] P04-08 Enforce 250k tokens per tenant/day and 1m deployment/day defaults plus reviewed model-price configuration and explicit monetary ceilings. Missing prices or depleted budget pause analysis while deterministic collection and receipt handling continue.
- [x] P04-09 Implement deny-unknown MCP manifests, scoped read adapters and no-write runtime credentials. Revalidate manifest/schema changes; tool arguments cannot widen tenant/project scope. Treat provider content as untrusted data, including instructions embedded in documents.
- [x] P04-10 Build decision inbox/detail/evidence/trace views showing scope references, coverage, reasoning summaries, cold-start assumptions, price inputs and clarification reasons. Display persisted safe summaries, not private chain-of-thought or secret-bearing raw prompts.
- [x] P04-11 Create at least 120 labeled contract-linked synthetic cases, split 60 development/60 held-out by contract/project. Include all five canonical classifications and at least 20 positive additional-scope and 20 nonbillable held-out cases. Freeze the split before tuning.
- [x] P04-12 Run three held-out evaluations with pinned versions. Report per-run counts/confusion matrices, proposal precision, positive recall, abstentions, reference validity, latency and cost. Preserve failures and rerun after relevant changes.

## Implementation state - 14 September 2026

Phase 4 is implemented across migrations `0008_phase4_analysis_context` and `0009_phase4_decisions_evaluation`. The bounded workflow persists canonical context, agent runs, immutable scope assessments, durable tenant/deployment token and cost reservations, sanitized decision inbox rows, immutable draft revisions, and pinned evaluation reports. Strict Pydantic schemas validate role outputs; one repair is allowed. The Scope, Evidence, Impact, Change Order, and Communication roles are isolated to read-only capabilities. Evidence gating, accepted-amendment overturns, contradiction clarification, cold-start effort ranges, frozen deterministic INR pricing/scheduling, tool-manifest fail-closed checks, decision/evidence/trace routes, and the 120-case held-out evaluation harness are implemented.

The Phase 4 implementation gates and live Bedrock quality evaluation are complete. The non-oracle fixture harness, durable budget enforcement, and three pinned Bedrock runs are verified. Phase 5 owns freelancer approval, immutable change-order approval, provider sending, and client review.

The development PostgreSQL container runs migration `0014_payment_webhook_async` at `head`; Alembic reports no drift and the PostgreSQL foundation suite passes (4 tests).

Evidence: [Phase 4 verification](../docs/implementation-evidence/phase-04-agent-reasoning.md).

## Verification and quality gate

Observed verification: `uv run pytest -q` passed 62 tests with 4 documented skips using temporary non-production credentials for presigned-form generation; `RUN_POSTGRES_TESTS=1 uv run pytest tests/integration/test_postgres_foundation.py -q` passed 4 tests; `uv run ruff check services tests migrations` and `uv run mypy services scripts` passed; `uv run alembic upgrade head`, `current`, and `check` passed at `0009_phase4_decisions_evaluation`. The deterministic held-out harness runs three pinned evaluations and records confusion matrices, precision, recall, abstentions, reference validity, latency, and cost.

A07 proves new evidence overturns the preliminary result and contradictions lead to clarification. A19 proves missing history/configuration cannot produce fabricated duration or unconditional dates.

A05/A23 attempt unknown mutation tools, changed read schemas, cross-owner arguments, alternate money/recipient/order values and memory-based rate changes. No agent-side consequential write is allowed.

A28 injects malformed output, invalid IDs, loops, timeouts and exhausted daily budgets. Resume respects cumulative limits. Each held-out run requires precision >=95%, positive recall >=80% and zero unsupported factual references reaching proposals. Clarification is an abstention for precision and a miss for positive recall; disclose small-sample limitations.

## Exit gate and handoff

Fixture-driven analysis produces supported candidates or explicit covered/clarification/failure outcomes, passes the defined quality gate and meets bounded execution constraints. Record measured latency without treating fixtures as live-connector performance.

Hand off validated candidate content, evidence hashes, commercial inputs and quality baselines to [phase 05](PHASE_05_APPROVALS_CLIENT_REVIEW.md). Roll back prompts/models only with versioned configuration and fresh evaluation; invalidate stale outputs when inputs or scope changed.

