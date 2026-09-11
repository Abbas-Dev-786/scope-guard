ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS request_id uuid;
ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS scope_version_id uuid;
ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS preference_version_id uuid;
ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS current_phase varchar(80);
ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS policy_version varchar(120);
ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS correlation_id uuid;
ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS row_version bigint NOT NULL DEFAULT 1;
ALTER TABLE workflow_instances DROP CONSTRAINT IF EXISTS ck_workflows_row_version;
ALTER TABLE workflow_instances ADD CONSTRAINT ck_workflows_row_version CHECK (row_version >= 1);

CREATE TABLE IF NOT EXISTS agent_runs (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  workflow_id uuid NOT NULL REFERENCES workflow_instances(id) ON DELETE RESTRICT,
  node_name varchar(120) NOT NULL,
  attempt integer NOT NULL DEFAULT 1 CHECK (attempt BETWEEN 1 AND 3),
  model_id varchar(255) NOT NULL,
  prompt_version varchar(120) NOT NULL,
  schema_version varchar(120) NOT NULL,
  tool_policy_version varchar(120) NOT NULL,
  input_hash varchar(64) NOT NULL,
  input_ref jsonb NOT NULL,
  output_ref jsonb,
  output_hash varchar(64),
  usage jsonb,
  status varchar(32) NOT NULL DEFAULT 'RUNNING' CHECK (status IN ('RUNNING','SUCCEEDED','REPAIRING','FAILED','REVIEW_REQUIRED')),
  error_code varchar(120),
  error_message varchar(500),
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_agent_run_node_attempt UNIQUE (workflow_id,node_name,attempt)
);
CREATE INDEX IF NOT EXISTS ix_agent_runs_workflow ON agent_runs(tenant_id,workflow_id,node_name,attempt);

CREATE TABLE IF NOT EXISTS scope_assessments (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  request_id uuid REFERENCES request_records(id) ON DELETE RESTRICT,
  workflow_id uuid NOT NULL REFERENCES workflow_instances(id) ON DELETE RESTRICT,
  classification varchar(40) NOT NULL CHECK (classification IN ('IN_SCOPE','POTENTIAL_SCOPE_CHANGE','AMBIGUOUS','PREVIOUSLY_APPROVED','NOT_A_SCOPE_REQUEST')),
  reason text NOT NULL,
  evidence_bundle_id uuid REFERENCES evidence_bundles(id) ON DELETE RESTRICT,
  scope_version_id uuid REFERENCES scope_versions(id) ON DELETE RESTRICT,
  request_version integer,
  coverage_status varchar(32) NOT NULL CHECK (coverage_status IN ('COMPLETE','PARTIAL','UNAVAILABLE','REQUIRES_CLARIFICATION')),
  matched_scope_item_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  matched_amendment_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  pending_request_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  required_evidence_queries jsonb NOT NULL DEFAULT '[]'::jsonb,
  uncertainty varchar(32) CHECK (uncertainty IS NULL OR uncertainty IN ('LOW','MEDIUM','HIGH')),
  input_digest varchar(64) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_scope_assessments_request ON scope_assessments(tenant_id,project_id,request_id,created_at);

CREATE TABLE IF NOT EXISTS analysis_budget_windows (
  id uuid PRIMARY KEY,
  tenant_id uuid REFERENCES users(id) ON DELETE RESTRICT,
  scope_key varchar(160) NOT NULL,
  window_start date NOT NULL,
  token_limit bigint NOT NULL CHECK (token_limit > 0),
  tokens_reserved bigint NOT NULL DEFAULT 0 CHECK (tokens_reserved >= 0),
  tokens_used bigint NOT NULL DEFAULT 0 CHECK (tokens_used >= 0),
  cost_limit_minor bigint CHECK (cost_limit_minor IS NULL OR cost_limit_minor >= 0),
  cost_reserved_minor bigint NOT NULL DEFAULT 0 CHECK (cost_reserved_minor >= 0),
  cost_used_minor bigint NOT NULL DEFAULT 0 CHECK (cost_used_minor >= 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_analysis_budget_window UNIQUE (scope_key,window_start)
);

CREATE TABLE IF NOT EXISTS analysis_budget_reservations (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  workflow_id uuid NOT NULL REFERENCES workflow_instances(id) ON DELETE RESTRICT,
  window_id uuid NOT NULL REFERENCES analysis_budget_windows(id) ON DELETE RESTRICT,
  reservation_key varchar(160) NOT NULL,
  token_reserved bigint NOT NULL CHECK (token_reserved > 0),
  cost_reserved_minor bigint NOT NULL DEFAULT 0 CHECK (cost_reserved_minor >= 0),
  token_used bigint NOT NULL DEFAULT 0 CHECK (token_used >= 0),
  cost_used_minor bigint NOT NULL DEFAULT 0 CHECK (cost_used_minor >= 0),
  status varchar(32) NOT NULL DEFAULT 'RESERVED' CHECK (status IN ('RESERVED','RECONCILED','RELEASED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_analysis_budget_reservation UNIQUE (tenant_id,reservation_key)
);