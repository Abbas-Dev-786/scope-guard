CREATE TABLE IF NOT EXISTS payment_link_attempts (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  payment_request_id uuid NOT NULL REFERENCES payment_requests(id) ON DELETE RESTRICT,
  attempt_number integer NOT NULL CHECK (attempt_number BETWEEN 1 AND 3),
  provider_account_id varchar(255) NOT NULL,
  provider_environment varchar(32) NOT NULL DEFAULT 'test' CHECK (provider_environment = 'test'),
  reference_id varchar(40) NOT NULL,
  amount_minor bigint NOT NULL CHECK (amount_minor > 0 AND amount_minor <= 100000000),
  currency varchar(3) NOT NULL DEFAULT 'INR' CHECK (currency = 'INR'),
  status varchar(32) NOT NULL DEFAULT 'READY' CHECK (status IN ('READY','CREATED','UNKNOWN_OUTCOME','REVIEW_REQUIRED','EXPIRED','CANCELLED')),
  provider_link_id varchar(255) UNIQUE,
  provider_order_id varchar(255),
  short_url varchar(1024),
  provider_status varchar(64),
  action_id uuid REFERENCES external_actions(id) ON DELETE RESTRICT,
  provider_payload jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_payment_link_attempt_number UNIQUE (payment_request_id, attempt_number)
);
CREATE INDEX IF NOT EXISTS ix_payment_link_attempt_request_status ON payment_link_attempts(tenant_id,payment_request_id,status);

CREATE TABLE IF NOT EXISTS payment_attempts (
  id uuid PRIMARY KEY,
  tenant_id uuid REFERENCES users(id) ON DELETE RESTRICT,
  project_id uuid REFERENCES projects(id) ON DELETE RESTRICT,
  link_attempt_id uuid REFERENCES payment_link_attempts(id) ON DELETE RESTRICT,
  provider_payment_id varchar(255) NOT NULL UNIQUE,
  provider_order_id varchar(255),
  amount_minor bigint NOT NULL CHECK (amount_minor > 0 AND amount_minor <= 100000000),
  currency varchar(3) NOT NULL DEFAULT 'INR' CHECK (currency = 'INR'),
  status varchar(32) NOT NULL,
  captured boolean NOT NULL DEFAULT false,
  provider_created_at timestamptz,
  provider_payload jsonb,
  observed_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_payment_attempt_link_observed ON payment_attempts(link_attempt_id,observed_at);

CREATE TABLE IF NOT EXISTS payment_observations (
  id uuid PRIMARY KEY,
  tenant_id uuid REFERENCES users(id) ON DELETE RESTRICT,
  project_id uuid REFERENCES projects(id) ON DELETE RESTRICT,
  payment_request_id uuid REFERENCES payment_requests(id) ON DELETE RESTRICT,
  link_attempt_id uuid REFERENCES payment_link_attempts(id) ON DELETE RESTRICT,
  payment_attempt_id uuid REFERENCES payment_attempts(id) ON DELETE RESTRICT,
  provider_account_id varchar(255) NOT NULL,
  provider_environment varchar(32) NOT NULL DEFAULT 'test' CHECK (provider_environment = 'test'),
  provider_event_id varchar(255) NOT NULL,
  event_type varchar(120) NOT NULL,
  provider_link_id varchar(255),
  provider_payment_id varchar(255),
  provider_order_id varchar(255),
  reference_id varchar(40),
  amount_minor bigint,
  currency varchar(3),
  observed_status varchar(64) NOT NULL,
  signature_verified boolean NOT NULL DEFAULT false,
  raw_payload jsonb NOT NULL,
  observed_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  association_state varchar(32) NOT NULL DEFAULT 'UNMATCHED',
  next_retry_at timestamptz,
  associated_at timestamptz,
  CONSTRAINT uq_payment_observation_event UNIQUE (provider_account_id,provider_environment,provider_event_id)
);
CREATE INDEX IF NOT EXISTS ix_payment_observations_request_time ON payment_observations(tenant_id,payment_request_id,observed_at);