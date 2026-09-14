# ADR 0003 — Reviewed Bedrock model price and analysis ceiling

**Date:** 14 September 2026  
**Status:** Accepted for staging Test Mode

## Decision

ScopeGuard uses `amazon.nova-lite-v1:0` in `us-east-1`. The AWS pricing catalog effective 1 August 2026 reports `$0.000060` per 1K input tokens and `$0.000240` per 1K output tokens for the standard on-demand model.

The durable analysis budget stores model cost in **micro-USD** so sub-cent token prices remain representable:

- input: `60` micro-USD per 1K tokens
- output: `240` micro-USD per 1K tokens
- staging daily ceiling: `10,000,000` micro-USD (`$10.00`)
- price version: `aws-bedrock-nova-lite-v1-2026-08-01`
- review timestamp: `2026-09-14T00:00:00Z`

The API and worker receive these values through CloudFormation-managed environment variables. Local development remains fail-closed until a developer explicitly supplies a reviewed price and ceiling in `.env`.

## Evidence

- AWS Pricing Catalog query in `us-east-1` returned the standard Nova Lite input and output dimensions and effective date above.
- Staging stack `scopeguard-staging` reached `UPDATE_COMPLETE`, revision `42`.
- `scopeguard-staging-api` exposes the same price version, values, and ceiling in its environment.
- Existing budget tests continue to use integer cost units and pass.