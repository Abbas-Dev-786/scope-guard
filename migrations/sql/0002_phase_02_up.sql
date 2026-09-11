CREATE TABLE jobs (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  project_id uuid,
  kind varchar(120) NOT NULL,
  payload_ref jsonb NOT NULL,
  state varchar(32) NOT NULL DEFAULT 'QUEUED'
    CHECK (state IN ('QUEUED','RUNNING','RETRY_WAIT','SUCCEEDED','FAILED_REQUIRES_REVIEW','CANCELLED')),
  available_at timestamptz NOT NULL DEFAULT now(),
  lease_until timestamptz,
  lease_owner varchar(255),
  fencing_generation bigint NOT NULL DEFAULT 0 CHECK (fencing_generation >= 0),
  attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0 AND attempt_count <= max_attempts),
  max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 3),
  deadline_at timestamptz,
  last_error varchar(500),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_jobs_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT fk_jobs_project_owner FOREIGN KEY (tenant_id, project_id)
    REFERENCES projects(tenant_id, id) ON DELETE RESTRICT
);
CREATE INDEX ix_jobs_runnable ON jobs(state, available_at, lease_until);
CREATE INDEX ix_jobs_tenant_state ON jobs(tenant_id, state);

CREATE TABLE outbox_events (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  aggregate_type varchar(100) NOT NULL,
  aggregate_id varchar(100) NOT NULL,
  event_type varchar(120) NOT NULL,
  payload jsonb NOT NULL,
  correlation_id uuid NOT NULL,
  causation_id uuid,
  published_at timestamptz,
  publish_attempts integer NOT NULL DEFAULT 0,
  last_error varchar(500),
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_outbox_tenant_id UNIQUE (tenant_id, id)
);
CREATE INDEX ix_outbox_unpublished ON outbox_events(published_at, created_at);
CREATE INDEX ix_outbox_aggregate ON outbox_events(tenant_id, aggregate_type, aggregate_id);

CREATE TABLE consumer_receipts (
  id uuid PRIMARY KEY,
  consumer_name varchar(120) NOT NULL,
  event_id uuid NOT NULL,
  result_ref jsonb NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_consumer_event UNIQUE (consumer_name, event_id)
);
CREATE INDEX ix_consumer_receipts_event ON consumer_receipts(event_id);

CREATE TABLE workflow_instances (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  project_id uuid,
  workflow_key varchar(160) NOT NULL,
  input_digest varchar(64) NOT NULL,
  state varchar(32) NOT NULL DEFAULT 'RUNNING'
    CHECK (state IN ('RUNNING','SUCCEEDED','FAILED','REVIEW_REQUIRED','CANCELLED')),
  budget_minor bigint CHECK (budget_minor IS NULL OR budget_minor >= 0),
  reserved_minor bigint NOT NULL DEFAULT 0 CHECK (reserved_minor >= 0),
  current_job_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fk_workflows_project_owner FOREIGN KEY (tenant_id, project_id)
    REFERENCES projects(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT fk_workflows_job_owner FOREIGN KEY (tenant_id, current_job_id)
    REFERENCES jobs(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT uq_workflows_key UNIQUE (tenant_id, workflow_key)
);

CREATE TABLE external_actions (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  project_id uuid,
  action_key varchar(160) NOT NULL,
  provider varchar(80) NOT NULL,
  operation varchar(120) NOT NULL,
  state varchar(32) NOT NULL DEFAULT 'READY'
    CHECK (state IN ('READY','DISPATCHING','RETRY_WAIT','SUCCEEDED','RECEIPT_CONFIRMED',
                    'UNKNOWN_OUTCOME','REVIEW_REQUIRED','CANCELLED')),
  approved_payload jsonb NOT NULL,
  payload_digest varchar(64) NOT NULL,
  idempotency_key varchar(160) NOT NULL,
  receipt_ref jsonb,
  uncertainty_reason varchar(500),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fk_actions_project_owner FOREIGN KEY (tenant_id, project_id)
    REFERENCES projects(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT uq_actions_key UNIQUE (tenant_id, action_key)
);
CREATE INDEX ix_actions_state ON external_actions(state, updated_at);

CREATE TABLE action_attempts (
  id uuid PRIMARY KEY,
  action_id uuid NOT NULL REFERENCES external_actions(id) ON DELETE RESTRICT,
  attempt_number integer NOT NULL CHECK (attempt_number BETWEEN 1 AND 3),
  state varchar(32) NOT NULL,
  provider_request_id varchar(255),
  dispatched_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  outcome_ref jsonb,
  error_code varchar(120),
  error_message varchar(500),
  CONSTRAINT uq_action_attempt_number UNIQUE (action_id, attempt_number)
);
CREATE INDEX ix_action_attempts_action ON action_attempts(action_id, attempt_number);

CREATE OR REPLACE FUNCTION prevent_audit_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit_events are immutable';
END;
$$;
CREATE TRIGGER audit_events_immutable
  BEFORE UPDATE OR DELETE ON audit_events
  FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation();