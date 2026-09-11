# Infrastructure scaffold

The foundation is implemented and deployed in the development AWS account. Stack `scopeguard-foundation-development` is CREATE_COMPLETE in us-east-1 and creates Cognito, encryption, the private evidence bucket, EventBridge bus and encrypted operational logging. Database, proxy, API networking and AgentCore deployment remain behind the Phase 00 readiness gates.

## Required sequence after account access exists

1. Install and authenticate a current AWS CLI; verify the account and selected region.
2. Complete `docs/implementation-evidence/phase-00-readiness.md`, including the actual AgentCore/model/Aurora intersection. Do not assume ap-south-1 is supported merely because it is the configured preference.
3. Deploy the foundation stack with a unique lowercase evidence bucket name and allowed callback/logout URLs.
4. Build the API image from `Dockerfile.api`, then add the account-specific private VPC/Aurora/RDS Proxy/API stack using the recorded database major and identities.
5. Run `uv run agentcore configure -e services/agents/runtime.py -r <verified-region>` and inspect the generated configuration/IAM before deployment. Keep IAM authorization enabled.
6. Store secrets in Secrets Manager references, provision the owner from the verified Cognito subject, and execute actual provider readiness tests.

Changing region, model, database major or provider path invalidates the affected evidence and requires a new readiness record. Never place tokens, message bodies or credentials in CloudFormation parameters committed to the repository.
