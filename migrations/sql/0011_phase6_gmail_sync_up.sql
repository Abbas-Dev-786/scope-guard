CREATE TABLE IF NOT EXISTS integration_connections (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  provider varchar(80) NOT NULL DEFAULT 'gmail' CHECK (provider = 'gmail'),
  provider_account_id varchar(255) NOT NULL,
  account_email varchar(320) NOT NULL,
  status varchar(32) NOT NULL DEFAULT 'CONNECTING' CHECK (status IN ('CONNECTING','CONNECTED','REAUTH_REQUIRED','DISCONNECTED','PAUSED')),
  credential_ciphertext text,
  credential_version integer NOT NULL DEFAULT 1 CHECK (credential_version >= 1),
  watch_id varchar(255),
  watch_expiry timestamptz,
  committed_history_id varchar(255),
  coverage_cutoff timestamptz,
  last_success_at timestamptz,
  last_error varchar(500),
  lease_until timestamptz,
  row_version bigint NOT NULL DEFAULT 1 CHECK (row_version >= 1),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_integration_connection_account UNIQUE (tenant_id, provider, provider_account_id)
);
CREATE INDEX IF NOT EXISTS ix_integration_connections_health ON integration_connections(tenant_id, provider, status, updated_at);

CREATE TABLE IF NOT EXISTS oauth_sessions (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  provider varchar(80) NOT NULL DEFAULT 'gmail' CHECK (provider = 'gmail'),
  state_hash varchar(64) NOT NULL UNIQUE,
  code_verifier_ciphertext text,
  redirect_uri varchar(1024) NOT NULL,
  expected_account_id varchar(255),
  expires_at timestamptz NOT NULL,
  consumed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_oauth_sessions_expiry ON oauth_sessions(expires_at);

CREATE TABLE IF NOT EXISTS mailbox_syncs (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  connection_id uuid NOT NULL REFERENCES integration_connections(id) ON DELETE RESTRICT UNIQUE,
  status varchar(32) NOT NULL DEFAULT 'IDLE' CHECK (status IN ('IDLE','RUNNING','REAUTH_REQUIRED','GAP_DETECTED','PAUSED')),
  mode varchar(32) NOT NULL DEFAULT 'INITIAL_BACKFILL' CHECK (mode IN ('INITIAL_BACKFILL','INCREMENTAL')),
  committed_history_id varchar(255),
  coverage_start timestamptz,
  coverage_end timestamptz,
  gap_detected_at timestamptz,
  gap_reason varchar(500),
  last_success_at timestamptz,
  lease_until timestamptz,
  row_version bigint NOT NULL DEFAULT 1 CHECK (row_version >= 1),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_mailbox_sync_health ON mailbox_syncs(tenant_id, status, last_success_at);
