# Phase 00–07 live-gate operator runbook

**Observed:** 14 September 2026
**Staging API:** `https://sj3udtpf6l.execute-api.us-east-1.amazonaws.com`
**Staging image:** `phase7-20260914-m10` / CloudFormation revision `42`

This runbook records the external observations still required after implementation and automated verification. Do not substitute fixtures, direct provider-created artifacts, or a successful HTTP request for the corresponding correlated evidence.

## 1. Cognito and authorization

1. Sign in through the deployed Cognito hosted UI using an authorized test user.
2. Capture a redacted request ID for `/api/v1/me` and one owner-scoped resource read.
3. Attempt the same resource with a second tenant or an altered object ID; record `401`/`404` and the request ID.
4. Record worker/tool/download/cache/trace authorization results without storing tokens or private payloads.

Exit evidence: token validation, server-derived owner, cross-tenant denial, and deployed object-authorization matrix.

## 2. Gmail and SES

1. From the web UI, connect Gmail and record the provider account identity and granted scopes.
2. Run bounded read/search and watch setup; record sync checkpoint and watch expiry.
3. Create a proposal, approve the exact revision, send it, and record the provider message ID and client-review state.
4. Exercise reconnect and disconnect; verify unsent work is cancelled and no send resurrects.
5. Confirm the controlled SES notification in the verified recipient inbox. Provider acceptance alone is not receipt evidence.

Exit evidence: live account read/search/watch/exact-send/reconnect/disconnect plus actual SES receipt.

## 3. Razorpay Test Mode

1. Create the payment link from the ScopeGuard client-review receipt flow, not from the Razorpay dashboard.
2. Verify the URL is Test Mode and record only redacted link/account/environment/reference fields.
3. Pay exactly the accepted INR amount with a Razorpay Test Mode method.
4. Deliver or observe the signed webhook and verify local state transitions to verified collection for the exact payment request.
5. Stop on `UNKNOWN_OUTCOME` or mismatch; never create a replacement to resolve uncertainty.

Exit evidence: ScopeGuard-created link, client receipt, provider acceptance, signed webhook observation, exact correlation, and monotonic local collection state.

## 4. Clean cloud recreation

Recreate the declared stack in an isolated test account/stack with the pinned templates, image digest, lockfiles, and migration head. Record configuration versions, sanitized A21/A29 observations, teardown result, and any prerequisite that cannot be recreated. The local clean PostgreSQL recreation is already recorded separately.

Do not record bearer tokens, OAuth codes, private email bodies, payment secrets, or full provider payloads.