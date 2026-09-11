CREATE TABLE users (
  id uuid PRIMARY KEY,
  cognito_sub varchar(255) NOT NULL UNIQUE,
  verified_email varchar(320) NOT NULL,
  timezone varchar(64) NOT NULL DEFAULT 'UTC',
  status varchar(32) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','DISABLED','DELETION_PENDING')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  row_version bigint NOT NULL DEFAULT 1 CHECK (row_version > 0)
);

CREATE TABLE preference_versions (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  version integer NOT NULL CHECK (version > 0),
  rate_minor bigint NOT NULL CHECK (rate_minor > 0 AND rate_minor <= 100000000),
  minimum_minor bigint NOT NULL CHECK (minimum_minor > 0 AND minimum_minor <= 100000000),
  increment_minor bigint NOT NULL CHECK (increment_minor > 0 AND increment_minor <= 100000000),
  communication_style varchar(32) NOT NULL,
  reminder_policy jsonb NOT NULL DEFAULT '{}'::jsonb,
  confirmed_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_preference_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT uq_preference_tenant_version UNIQUE (tenant_id, version)
);

CREATE TABLE clients (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  name varchar(200) NOT NULL,
  company varchar(200),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  row_version bigint NOT NULL DEFAULT 1 CHECK (row_version > 0),
  CONSTRAINT uq_clients_tenant_id UNIQUE (tenant_id, id)
);

CREATE TABLE client_contacts (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL,
  client_id uuid NOT NULL,
  normalized_email varchar(320) NOT NULL CHECK (normalized_email = lower(btrim(normalized_email))),
  display_name varchar(200) NOT NULL,
  role varchar(100),
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_contacts_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT uq_contact_email_per_client UNIQUE (tenant_id, client_id, normalized_email),
  CONSTRAINT fk_contact_client_owner FOREIGN KEY (tenant_id, client_id)
    REFERENCES clients(tenant_id, id) ON DELETE RESTRICT
);
CREATE INDEX ix_contacts_tenant_client ON client_contacts(tenant_id, client_id);

CREATE TABLE projects (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL,
  client_id uuid NOT NULL,
  name varchar(200) NOT NULL,
  status varchar(40) NOT NULL DEFAULT 'PAUSED_UNCONFIRMED_SCOPE'
    CHECK (status IN ('DRAFT','PAUSED_UNCONFIRMED_SCOPE','ACTIVE','ARCHIVED','DELETION_PENDING')),
  currency varchar(3) NOT NULL DEFAULT 'INR' CHECK (currency = 'INR'),
  base_contract_value_minor bigint NOT NULL DEFAULT 0
    CHECK (base_contract_value_minor BETWEEN 0 AND 100000000),
  current_scope_version_id uuid,
  preference_version_id uuid NOT NULL,
  timezone varchar(64) NOT NULL,
  calendar_version_id uuid,
  target_date date,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  row_version bigint NOT NULL DEFAULT 1 CHECK (row_version > 0),
  CONSTRAINT uq_projects_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT fk_project_client_owner FOREIGN KEY (tenant_id, client_id)
    REFERENCES clients(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT fk_project_preference_owner FOREIGN KEY (tenant_id, preference_version_id)
    REFERENCES preference_versions(tenant_id, id) ON DELETE RESTRICT
);
CREATE INDEX ix_projects_tenant_created ON projects(tenant_id, created_at, id);

CREATE TABLE calendar_versions (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  version integer NOT NULL CHECK (version > 0),
  weekdays jsonb NOT NULL,
  holiday_dates jsonb NOT NULL DEFAULT '[]'::jsonb,
  confirmed_daily_capacity_hours numeric(12,4) NOT NULL
    CHECK (confirmed_daily_capacity_hours > 0 AND confirmed_daily_capacity_hours <= 24),
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_calendar_project_id UNIQUE (tenant_id, project_id, id),
  CONSTRAINT uq_calendar_project_version UNIQUE (tenant_id, project_id, version),
  CONSTRAINT fk_calendar_project_owner FOREIGN KEY (tenant_id, project_id)
    REFERENCES projects(tenant_id, id) ON DELETE RESTRICT
);

ALTER TABLE projects ADD CONSTRAINT fk_project_current_calendar_owner
  FOREIGN KEY (tenant_id, id, calendar_version_id)
  REFERENCES calendar_versions(tenant_id, project_id, id)
  DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE api_idempotency (
  id uuid PRIMARY KEY,
  actor_scope varchar(255) NOT NULL,
  route varchar(255) NOT NULL,
  key varchar(128) NOT NULL,
  request_digest varchar(64) NOT NULL,
  response_ref jsonb NOT NULL,
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_api_idempotency_scope_route_key UNIQUE (actor_scope, route, key)
);
CREATE INDEX ix_api_idempotency_expiry ON api_idempotency(expires_at);

CREATE TABLE audit_events (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  project_id uuid,
  actor varchar(255) NOT NULL,
  action varchar(100) NOT NULL,
  resource_type varchar(100) NOT NULL,
  resource_id varchar(100) NOT NULL,
  resource_revision bigint,
  correlation_id uuid NOT NULL,
  causation_id uuid,
  before_state jsonb,
  after_state jsonb,
  content_digest varchar(64) NOT NULL,
  safe_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_audit_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT fk_audit_project_owner FOREIGN KEY (tenant_id, project_id)
    REFERENCES projects(tenant_id, id) ON DELETE RESTRICT
);
CREATE INDEX ix_audit_tenant_project_time ON audit_events(tenant_id, project_id, occurred_at);
