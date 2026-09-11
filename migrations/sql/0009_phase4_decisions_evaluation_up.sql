CREATE TABLE IF NOT EXISTS analysis_decisions (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  request_id uuid REFERENCES request_records(id) ON DELETE RESTRICT,
  workflow_id uuid NOT NULL REFERENCES workflow_instances(id) ON DELETE RESTRICT,
  assessment_id uuid REFERENCES scope_assessments(id) ON DELETE RESTRICT,
  evidence_bundle_id uuid REFERENCES evidence_bundles(id) ON DELETE RESTRICT,
  kind varchar(40) NOT NULL CHECK (kind IN ('PROPOSAL_REVIEW','CLARIFICATION','PROJECT_MAPPING','INTEGRATION_HEALTH','ACTION_UNCERTAINTY')),
  status varchar(40) NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','RESOLVED','DISMISSED','STALE')),
  title varchar(240) NOT NULL,
  summary text NOT NULL,
  safe_details jsonb NOT NULL DEFAULT '{}'::jsonb,
  terms_snapshot jsonb,
  trace_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  row_version bigint NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_analysis_decisions_inbox ON analysis_decisions (tenant_id, status, created_at);
CREATE INDEX IF NOT EXISTS ix_analysis_decisions_project ON analysis_decisions (tenant_id, project_id, created_at);

CREATE TABLE IF NOT EXISTS analysis_draft_revisions (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  request_id uuid REFERENCES request_records(id) ON DELETE RESTRICT,
  workflow_id uuid NOT NULL REFERENCES workflow_instances(id) ON DELETE RESTRICT,
  decision_id uuid NOT NULL REFERENCES analysis_decisions(id) ON DELETE RESTRICT,
  revision integer NOT NULL CHECK (revision > 0),
  content_hash varchar(64) NOT NULL,
  payload jsonb NOT NULL,
  status varchar(32) NOT NULL DEFAULT 'CURRENT' CHECK (status IN ('CURRENT','SUPERSEDED','REVOKED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (decision_id, revision)
);
CREATE INDEX IF NOT EXISTS ix_analysis_drafts_tenant ON analysis_draft_revisions (tenant_id, project_id, created_at);

CREATE TABLE IF NOT EXISTS analysis_evaluation_runs (
  id uuid PRIMARY KEY,
  dataset_version varchar(120) NOT NULL,
  split varchar(20) NOT NULL CHECK (split IN ('development','held_out')),
  run_number integer NOT NULL CHECK (run_number BETWEEN 1 AND 3),
  model_version varchar(255) NOT NULL,
  prompt_version varchar(120) NOT NULL,
  tool_policy_version varchar(120) NOT NULL,
  metrics jsonb NOT NULL,
  passed boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (dataset_version, split, run_number, model_version, prompt_version, tool_policy_version)
);