# ADR 0001 — Phase 00 implementation stack

**Date:** 7 September 2026  
**Status:** Accepted for local foundation; cloud compatibility pending actual-account verification

## Decision

- Python 3.11, managed exclusively through uv with `.python-version`, `pyproject.toml` and `uv.lock`.
- FastAPI/Pydantic v2 and synchronous SQLAlchemy 2/psycopg for the bounded Lambda API; Mangum is the Lambda adapter.
- PostgreSQL 16.6 for local invariant and migration testing. The selected Aurora PostgreSQL major remains pending the actual region/runtime intersection and must match locally before deployed evidence is accepted.
- Next.js 16.2.9 App Router with React 19.2 and Node 20.9 minimum; the local toolchain currently uses Node 22.14.
- Strands Agents with a separate Bedrock AgentCore entrypoint. Agents have no consequential provider tools. Deterministic domain/action services remain separate.
- CloudFormation for stable account-independent foundations. AgentCore Starter Toolkit configuration is generated only after selecting an actually supported account/region and inspecting IAM.

## Evidence used

Context7 was queried on 7 September 2026 against `/vercel/next.js/v16.2.9`, `/websites/fastapi_tiangolo`, `/astral-sh/uv`, `/websites/strandsagents`, `/aws/bedrock-agentcore-sdk-python`, and `/aws/bedrock-agentcore-starter-toolkit`.

The documentation confirms that Next.js 16 requires Node 20.9 or newer; uv uses a shared lock and `.python-version`; FastAPI derives validation/OpenAPI from Pydantic and supports dependency-based authentication; Strands supports async invocation with structured output; AgentCore provides a Python entrypoint and supports Python 3.11. The starter toolkit defaults must not be treated as proof that the intended ap-south-1 runtime/model/database intersection is available.

## Consequences

The API remains portable between local PostgreSQL and the target Aurora major, but PostgreSQL-specific migration tests are mandatory. Synchronous database access is bounded by small pools and short transactions. Model/provider calls must never occur inside those transactions.

The cloud readiness gate stays open until actual identities, accounts, regions and provider behavior are observed. Changing a pinned major or deployment path updates this record and invalidates affected evidence.
