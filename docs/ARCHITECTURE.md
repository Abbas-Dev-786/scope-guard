# ScopeGuard architecture

ScopeGuard is a professional-workflow agent: it analyzes a scope-change request, cites source evidence, prepares a proposal, and pauses for explicit human approval before external communication or payment collection.

```mermaid
flowchart LR
  Browser[Next.js web UI\nCognito PKCE] --> API[FastAPI Lambda API]
  API --> Auth[Cognito JWT\nserver-derived tenant]
  API --> Proxy[RDS Proxy\nTLS]
  Proxy --> DB[(Aurora PostgreSQL)]
  API --> S3[(Private S3 + KMS)]
  API --> Queue[EventBridge / durable jobs]
  Queue --> Worker[Worker Lambda]
  Worker --> Agent[Strands AgentCore]
  Agent --> Bedrock[Amazon Bedrock\nNova Lite]
  Worker --> Gmail[Gmail API\nOAuth + watch]
  Worker --> SES[Amazon SES]
  Worker --> Razorpay[Razorpay Test Mode]
  API --> Audit[Immutable audit\ncorrelation + traces]
```

The agent has no direct consequential provider tools. Deterministic services own approval, email, payment-link creation, webhook verification, tenant authorization, idempotency, and recovery transitions.