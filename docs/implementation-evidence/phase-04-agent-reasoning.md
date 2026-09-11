# Phase 04 agent reasoning verification

**Observed:** 8 September 2026
**Status:** Complete

## Implemented evidence

- Migrations `0008_phase4_analysis_context` and `0009_phase4_decisions_evaluation` persist canonical workflow context, agent runs, immutable scope assessments, decision inbox rows, draft revisions, evaluation reports, and durable budget windows/reservations.
- The Strands adapter creates fresh per-job roles with explicit read-only tools and structured Pydantic output. Scope, Evidence, Impact, Change Order, Communication, and Contract Structure responsibilities are distinct; mutation tools and provider credentials are never exposed.
- Strict schemas reject unknown fields, invalid classifications, malformed effort ranges, unsafe HTML, and untrusted recipients. One bounded repair is allowed; a second failure becomes a safe clarification/failure outcome.
- The deterministic evidence gate checks coverage, reference ownership, contradictions, accepted amendments, and baseline status. Accepted amendments can overturn a preliminary additional-scope result; incomplete or conflicting evidence cannot produce a priced proposal.
- Impact outputs retain task-level low/recommended/high decimal ranges, assumptions, dependencies, uncertainty, and cold-start labeling. Pricing uses frozen preference versions and deterministic Decimal arithmetic; calendar capacity produces conditional schedule terms. The synthetic fixture produces INR 1,500,000 paise, zero tax, and two working days at seven hours/day.
- Preparation limits cover 180 seconds per job, 60 seconds per node, 15 seconds per tool, 20 reads, 40,000 input tokens, 8,000 output tokens, three attempts, and one repair. Tenant (250,000/day) and deployment (1,000,000/day) reservations reconcile cumulatively. Missing or stale model prices pause model work.
- Connector manifests are deny-by-default and fail closed on unknown tools or changed read-only schemas. Scoped read context rechecks tenant/project/resource ownership.
- Authenticated decision inbox, decision detail/evidence, and workflow trace routes return bounded summaries, terms, coverage, assumptions, retries, and outcomes without raw prompts or chain-of-thought.
- The frozen synthetic dataset contains 120 unique contract/project-linked cases, split 60/60. The held-out set contains at least 20 additional-scope positives and 20 nonbillable cases; three pinned evaluation runs report confusion matrices, precision, recall, abstentions, reference validity, latency, and cost.

## Verification

~~~text
uv run pytest -q (temporary static test credentials)                  passed (62 passed, 4 skipped)
uv run pytest tests/unit/test_phase4_analysis.py -q                   passed (8 passed)
uv run pytest tests/unit/test_phase4_persistence.py -q                passed (2 passed)
RUN_POSTGRES_TESTS=1 uv run pytest tests/integration/test_postgres_foundation.py -q passed (4 passed)
uv run ruff check services tests migrations                            passed
uv run mypy services scripts                                           passed
uv run alembic upgrade head                                            passed (0009_phase4_decisions_evaluation)
uv run alembic current                                                 0009_phase4_decisions_evaluation (head)
uv run alembic check                                                    passed (no drift)
~~~

The PostgreSQL container is healthy and the Phase 4 schema is applied at head. The default local AWS SSO token is expired; temporary non-production static credentials were used only to generate presigned S3 test forms during the full local suite. No provider mutation was performed by the tests.

## Exit gate

Phase 4 produces supported proposal candidates, covered/no-action outcomes, or explicit clarification/failure decisions. It hands immutable draft content, evidence hashes, deterministic terms, and safe trace summaries to Phase 5 freelancer approval and client review.