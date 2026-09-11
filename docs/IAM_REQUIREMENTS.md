# AWS services and IAM requirements

This inventory is based on the current implementation, `docs/TDD.md`, the phase plans, `infra/cloudformation/foundation.yaml`, the AgentCore runtime, and the connector manifest.

Create the human IAM user as a deployment/operator identity. Do not attach the application runtime permissions to that user. The deployed API, workers, notification sender, scheduler, and AgentCore runtime need separate IAM roles with narrower permissions.

## Current development bootstrap state

The development deployment uses IAM user scopeguard-deployer through group ScopeGuardFoundationDeployers in account 359465684083, region us-east-1. Its policy is a temporary foundation bootstrap policy with region conditions and wildcard creation resources. It is not an application runtime role. Before production or shared environments, replace it with a CloudFormation execution role and remove bootstrap delete/create permissions from the human identity. The source policy uses the valid S3 actions s3:GetEncryptionConfiguration and s3:PutEncryptionConfiguration.
## Services required by this project

| Service | Why ScopeGuard needs it | Current state |
| --- | --- | --- |
| IAM | Deployment roles, Lambda/AgentCore execution roles, service-linked roles, and `iam:PassRole` | Required for deployment |
| STS | `GetCallerIdentity` for readiness and deployment identity checks | Required |
| CloudFormation | Foundation and account-specific infrastructure deployment | Foundation template exists |
| Amazon Cognito | Freelancer user pool, verified email, OAuth authorization-code + PKCE | Foundation template and JWT verifier exist |
| Amazon S3 | Private versioned originals, evidence, artifacts, exports, and encrypted object storage | Foundation bucket exists |
| AWS KMS | S3 encryption, CloudWatch Logs encryption, secret/object encryption | Foundation key exists |
| Amazon EventBridge | Durable wakeups for jobs and connector/payment events | Event bus exists; application rules later |
| CloudWatch Logs | Lambda/AgentCore/application logs | Foundation log group exists |
| CloudWatch Metrics/Alarms | Queue age, leases, connector freshness, payment uncertainty, model spend, and operational alarms | Planned in later phases |
| AWS X-Ray / OpenTelemetry export | Trace correlation and runtime diagnostics | Planned; verify the selected AgentCore export path |
| AWS Lambda | API, webhook, action-worker, scheduler, and lifecycle handlers | Dockerfile and Mangum handler exist; deployment stack pending |
| API Gateway | Authenticated API, public capability routes, webhooks, and throttling | TDD target; stack pending |
| Amazon Aurora PostgreSQL | Production relational database | Local PostgreSQL 16.6 only; Aurora major still requires readiness verification |
| Amazon RDS Proxy | Bounded private Lambda/database connections | TDD target; stack pending |
| Amazon VPC/EC2 networking | Private subnets, route tables, security groups, NAT or approved egress, and database isolation | Account-specific stack pending |
| AWS Secrets Manager | Database, provider OAuth, Razorpay, and other secret references | Required by design; not yet provisioned |
| Amazon ECR | Store API and AgentCore container images | Dockerfiles exist; repository/deployment pending |
| Amazon Bedrock Runtime | Exact model invocation by the AgentCore execution role | Model ID and region are still unverified |
| Amazon Bedrock AgentCore | Deploy and invoke the Strands runtime | Runtime entrypoint exists; deployed runtime pending |
| Amazon SES | Verified freelancer notification delivery and client receipt notifications | Required by design; sender/receipt pending |
| EventBridge Scheduler | One-minute recovery sweep and periodic connector/payment/retention jobs | Required by TDD; schedules pending |

These AWS services are not currently required by the repository: DynamoDB, SQS, SNS, Step Functions, ECS/Fargate, OpenSearch, AppSync, and Neptune. Do not add them to the IAM user unless a later architecture decision introduces them.

The frontend hosting service is not selected in the repository. If the web app is hosted on Amplify, CloudFront + S3, or another service, add only that hosting service after the hosting decision. The current local Next.js app does not require an AWS hosting permission.

## Permissions for the human deployment user

The safest arrangement is for this user to call CloudFormation with a narrowly scoped CloudFormation execution role. In that arrangement, the user gets stack-management permissions plus `iam:PassRole` to only the deployment roles. The CloudFormation execution role receives the resource-creation permissions below.

### Baseline identity and stack permissions

Grant these to the deployment user, scoped to the project’s deployment regions and stack ARNs where the action supports resource scoping:

```text
sts:GetCallerIdentity

cloudformation:CreateStack
cloudformation:UpdateStack
cloudformation:DeleteStack
cloudformation:DescribeStacks
cloudformation:DescribeStackEvents
cloudformation:DescribeChangeSet
cloudformation:CreateChangeSet
cloudformation:ExecuteChangeSet
cloudformation:DeleteChangeSet
cloudformation:GetTemplate
cloudformation:ValidateTemplate
cloudformation:ListStackResources
cloudformation:ListStacks
cloudformation:ContinueUpdateRollback
cloudformation:GetStackPolicy
cloudformation:SetStackPolicy

iam:GetRole
iam:PassRole                 # only the named deployment/runtime roles
```

### Container and AgentCore deployment

The deployment user or CI role needs ECR push permissions for the two images:

```text
ecr:GetAuthorizationToken    # Resource * is required by AWS
ecr:BatchCheckLayerAvailability
ecr:CompleteLayerUpload
ecr:InitiateLayerUpload
ecr:UploadLayerPart
ecr:PutImage
ecr:BatchGetImage
ecr:DescribeRepositories
ecr:CreateRepository          # bootstrap only
ecr:PutLifecyclePolicy        # recommended retention policy
```

The AgentCore control plane uses the `bedrock-agentcore` IAM namespace. The deployer normally needs the scoped runtime operations below, plus tagging and the exact execution role pass permission:

```text
bedrock-agentcore:CreateAgentRuntime
bedrock-agentcore:UpdateAgentRuntime
bedrock-agentcore:GetAgentRuntime
bedrock-agentcore:DeleteAgentRuntime
bedrock-agentcore:CreateAgentRuntimeEndpoint
bedrock-agentcore:UpdateAgentRuntimeEndpoint
bedrock-agentcore:GetAgentRuntimeEndpoint
bedrock-agentcore:DeleteAgentRuntimeEndpoint
bedrock-agentcore:TagResource
bedrock-agentcore:UntagResource
bedrock-agentcore:InvokeAgentRuntime       # deployment smoke test/operator use
iam:CreateServiceLinkedRole                 # only the AgentCore service-linked roles, if absent
iam:PassRole                                # only the AgentCore execution role
```

The AgentCore starter toolkit can generate additional role or network permissions based on the selected region and VPC mode. Review the generated policy before applying it; do not replace that review with `AdministratorAccess`.

For model discovery and readiness checks, allow the deployer/operator to read model metadata. Model invocation belongs on the AgentCore execution role:

```text
bedrock:ListFoundationModels
bedrock:GetFoundationModel
bedrock:InvokeModel
bedrock:InvokeModelWithResponseStream
bedrock:Converse
bedrock:ConverseStream
```

Restrict invocation to the selected foundation-model ARN after the model and region are chosen. Remove unused invocation variants after confirming the Strands provider path.

### If the user directly deploys networking and data infrastructure

Prefer a CloudFormation execution role. If direct provisioning is unavoidable, the deployment identity needs the following service families, scoped to the named VPC, subnets, security groups, Aurora cluster, instances, proxy, and secret resources:

```text
ec2:Describe*
ec2:CreateVpc
ec2:CreateSubnet
ec2:CreateRouteTable
ec2:AssociateRouteTable
ec2:CreateInternetGateway
ec2:AttachInternetGateway
ec2:CreateNatGateway
ec2:AllocateAddress
ec2:CreateSecurityGroup
ec2:AuthorizeSecurityGroupIngress
ec2:AuthorizeSecurityGroupEgress
ec2:RevokeSecurityGroupIngress
ec2:RevokeSecurityGroupEgress
ec2:CreateTags
ec2:Delete*                    # only during controlled teardown

rds:Describe*
rds:CreateDBCluster
rds:ModifyDBCluster
rds:DeleteDBCluster
rds:CreateDBInstance
rds:ModifyDBInstance
rds:DeleteDBInstance
rds:CreateDBProxy
rds:ModifyDBProxy
rds:DeleteDBProxy
rds:RegisterDBProxyTargets
rds:DeregisterDBProxyTargets
rds:DescribeDBProxies
rds:DescribeDBProxyTargets

secretsmanager:CreateSecret
secretsmanager:DescribeSecret
secretsmanager:PutSecretValue
secretsmanager:UpdateSecret
secretsmanager:TagResource
secretsmanager:DeleteSecret       # recovery-window deletion only

lambda:CreateFunction
lambda:UpdateFunctionCode
lambda:UpdateFunctionConfiguration
lambda:GetFunction
lambda:DeleteFunction
lambda:PublishVersion
lambda:CreateAlias
lambda:UpdateAlias
lambda:DeleteAlias
lambda:AddPermission
lambda:RemovePermission
lambda:InvokeFunction             # smoke test only, scoped to the API/worker functions

apigateway:GET
apigateway:POST
apigateway:PATCH
apigateway:PUT
apigateway:DELETE

cognito-idp:CreateUserPool
cognito-idp:UpdateUserPool
cognito-idp:DeleteUserPool
cognito-idp:DescribeUserPool
cognito-idp:CreateUserPoolClient
cognito-idp:UpdateUserPoolClient
cognito-idp:DeleteUserPoolClient
cognito-idp:DescribeUserPoolClient
cognito-idp:CreateUserPoolDomain
cognito-idp:DeleteUserPoolDomain
cognito-idp:DescribeUserPoolDomain

s3:CreateBucket
s3:PutEncryptionConfiguration
s3:GetEncryptionConfiguration
s3:PutBucketVersioning
s3:GetBucketVersioning
s3:PutBucketPublicAccessBlock
s3:GetBucketPublicAccessBlock
s3:PutBucketPolicy
s3:GetBucketPolicy
s3:PutLifecycleConfiguration
s3:GetLifecycleConfiguration
s3:ListBucket
s3:DeleteBucket                  # controlled teardown only

kms:CreateKey
kms:DescribeKey
kms:EnableKeyRotation
kms:PutKeyPolicy
kms:CreateAlias
kms:UpdateAlias
kms:DeleteAlias
kms:TagResource

events:CreateEventBus
events:DescribeEventBus
events:DeleteEventBus
events:PutRule
events:PutTargets
events:RemoveTargets
events:DeleteRule
events:TagResource
events:UntagResource

logs:CreateLogGroup
logs:DescribeLogGroups
logs:PutRetentionPolicy
logs:AssociateKmsKey
logs:DisassociateKmsKey
logs:DeleteLogGroup             # controlled teardown only
```

For schedules, add `scheduler:CreateSchedule`, `scheduler:GetSchedule`, `scheduler:UpdateSchedule`, `scheduler:DeleteSchedule`, `scheduler:TagResource`, and `scheduler:UntagResource`, plus `iam:PassRole` to the scheduler invocation role.

For alarms and traces, add `cloudwatch:PutMetricAlarm`, `cloudwatch:DescribeAlarms`, `cloudwatch:DeleteAlarms`, `cloudwatch:PutMetricData`, and read-only `xray:GetTraceSummaries`/`xray:BatchGetTraces` for operators if those features are enabled.

## Runtime roles

These permissions belong on separate roles, never on the human IAM user as a blanket policy.

| Role | Required permissions |
| --- | --- |
| API Lambda role | `logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents`; `rds-db:connect` to the RDS Proxy database-user ARN; `secretsmanager:GetSecretValue` for only the database/provider secret ARNs; `kms:Decrypt` for the matching KMS key; `s3:GetObject`, `s3:PutObject`, `s3:HeadObject`, and multipart actions limited to tenant artifact prefixes; `events:PutEvents` to the ScopeGuard bus; `lambda:InvokeFunction` only if it dispatches a named worker. Cognito API permissions are not needed because JWTs are verified locally against the Cognito JWKS endpoint. |
| AgentCore execution role | `logs:*` write subset; `bedrock:InvokeModel`/`InvokeModelWithResponseStream` or `bedrock:Converse`/`ConverseStream` against the exact model ARN; only the scoped S3 read references needed for evidence; `events:PutEvents` only if the runtime publishes a bounded completion event. It must not have SES, Gmail, Razorpay, payment, or generic provider-write permissions. |
| Durable worker role | `rds-db:connect`, scoped S3 read/write, `events:PutEvents`, `secretsmanager:GetSecretValue`, matching `kms:Decrypt`, and only the named Lambda/AgentCore invocation actions needed by the workflow. |
| Notification role | CloudWatch log writes, `ses:SendEmail` and/or `ses:SendRawEmail` constrained to the verified SES identity and approved recipient behavior, plus the minimum database read/update path through RDS Proxy. |
| Scheduler role | `lambda:InvokeFunction` only on the named sweeper/worker functions. The scheduler itself should not receive database, S3, Bedrock, or provider credentials. |
| Migration/operator role | Database migration access through the private path and the database credential from one named Secrets Manager secret. Keep this separate from the public API role and do not grant broad `rds:*` to the running application. |

S3 and KMS resources also need resource policies/key policies that trust these roles. IAM permissions alone do not override an explicit bucket or key policy deny.

## External credentials that are not AWS IAM permissions

The project also requires separate non-AWS credentials:

- Google Cloud project and Gmail OAuth client. Gmail push delivery uses Google Pub/Sub; configure the Gmail watch topic and grant the Gmail publisher permission to publish to that topic. Store OAuth client/refresh secrets in AWS Secrets Manager.
- Razorpay Test Mode key ID/secret, webhook secret, merchant/account identity, and test-mode limits. Store the keys in AWS Secrets Manager. Do not grant Razorpay access to the AgentCore role.
- A verified SES identity and test recipient in the selected AWS region.
- A chosen frontend hosting and DNS/TLS arrangement if the Next.js app will be deployed. Route 53, ACM, CloudFront, Amplify, or S3 permissions are not currently justified by the repository because no hosting choice is recorded.

## Recommended order

1. Create the human deployment user with MFA and no access keys used by the application.
2. Create a deployment role and CloudFormation execution role; grant the user only stack management and `iam:PassRole` to named roles.
3. Deploy the foundation stack and inspect the generated AgentCore IAM requirements for the verified region.
4. Create separate API, AgentCore, worker, notification, scheduler, and migration roles.
5. Add exact resource ARNs and conditions after account IDs, region, VPC, bucket, key, proxy, secret, model, bus, and function names are known.
6. Run the readiness checks and remove bootstrap-only create/delete permissions from the human user.
