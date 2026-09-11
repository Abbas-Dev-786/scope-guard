CREATE TABLE IF NOT EXISTS change_orders (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  request_id uuid NOT NULL REFERENCES request_records(id) ON DELETE RESTRICT,
  number integer NOT NULL CHECK (number > 0),
  current_revision_id uuid,
  status varchar(40) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','AWAITING_FREELANCER_APPROVAL','SEND_PENDING','AWAITING_CLIENT_APPROVAL','REVISION_REQUESTED','CLIENT_APPROVED','REJECTED_BY_FREELANCER','REJECTED_BY_CLIENT','WITHDRAWN','EXPIRED')),
  row_version bigint NOT NULL DEFAULT 1 CHECK (row_version >= 1),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_change_orders_tenant_id UNIQUE (tenant_id,id),
  CONSTRAINT uq_change_order_number UNIQUE (tenant_id,project_id,number)
);
CREATE INDEX IF NOT EXISTS ix_change_orders_project_status ON change_orders(tenant_id,project_id,status,created_at);

CREATE TABLE IF NOT EXISTS proposal_revisions (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  change_order_id uuid NOT NULL REFERENCES change_orders(id) ON DELETE RESTRICT,
  revision_number integer NOT NULL CHECK (revision_number > 0),
  baseline_version_id uuid NOT NULL REFERENCES scope_versions(id) ON DELETE RESTRICT,
  request_version integer NOT NULL,
  preference_version_id uuid NOT NULL REFERENCES preference_versions(id) ON DELETE RESTRICT,
  total_minor bigint NOT NULL CHECK (total_minor > 0 AND total_minor <= 100000000),
  tax_minor bigint NOT NULL DEFAULT 0 CHECK (tax_minor >= 0 AND tax_minor <= total_minor),
  currency varchar(3) NOT NULL DEFAULT 'INR' CHECK (currency = 'INR'),
  title varchar(240) NOT NULL,
  requested_change text NOT NULL,
  deliverables jsonb NOT NULL,
  exclusions jsonb NOT NULL DEFAULT '[]'::jsonb,
  assumptions jsonb NOT NULL DEFAULT '[]'::jsonb,
  client_explanation text NOT NULL,
  recipient_contact_id uuid NOT NULL REFERENCES client_contacts(id) ON DELETE RESTRICT,
  recipient_email varchar(320) NOT NULL,
  subject varchar(240) NOT NULL,
  plain_text_body text NOT NULL,
  html_body text NOT NULL,
  attachment_hashes jsonb NOT NULL DEFAULT '[]'::jsonb,
  terms_json jsonb NOT NULL,
  evidence_digest varchar(64) NOT NULL,
  evidence_reference_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  canonical_artifact_ref jsonb NOT NULL,
  canonical_artifact_hash varchar(64) NOT NULL,
  approval_url varchar(1024) NOT NULL,
  token_ciphertext text NOT NULL,
  status varchar(32) NOT NULL DEFAULT 'CURRENT' CHECK (status IN ('CURRENT','SUPERSEDED','REVOKED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_proposal_revisions_tenant_id UNIQUE (tenant_id,id),
  CONSTRAINT uq_proposal_revision_number UNIQUE (change_order_id,revision_number)
);
CREATE INDEX IF NOT EXISTS ix_proposal_revisions_current ON proposal_revisions(tenant_id,change_order_id,status);
ALTER TABLE change_orders ADD CONSTRAINT fk_change_order_current_revision FOREIGN KEY (current_revision_id) REFERENCES proposal_revisions(id) DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE IF NOT EXISTS approvals (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  change_order_id uuid NOT NULL REFERENCES change_orders(id) ON DELETE RESTRICT,
  revision_id uuid NOT NULL REFERENCES proposal_revisions(id) ON DELETE RESTRICT,
  actor_type varchar(32) NOT NULL CHECK (actor_type IN ('FREELANCER','CLIENT')),
  actor_identifier varchar(255) NOT NULL,
  content_hash varchar(64) NOT NULL,
  decision varchar(32) NOT NULL CHECK (decision IN ('APPROVED','REJECTED','REQUEST_CHANGES','WAIVED')),
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  comment varchar(2000),
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_approval_revision_actor_decision UNIQUE (revision_id,actor_type,decision)
);

CREATE TABLE IF NOT EXISTS client_capabilities (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  change_order_id uuid NOT NULL REFERENCES change_orders(id) ON DELETE RESTRICT,
  revision_id uuid NOT NULL REFERENCES proposal_revisions(id) ON DELETE RESTRICT,
  client_id uuid NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
  token_hash varchar(64) NOT NULL UNIQUE,
  content_hash varchar(64) NOT NULL,
  purpose varchar(32) NOT NULL DEFAULT 'REVIEW' CHECK (purpose IN ('REVIEW','RECEIPT')),
  activated_at timestamptz,
  expires_at timestamptz,
  consumed_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_client_capabilities_scope ON client_capabilities(tenant_id,change_order_id,revision_id);

CREATE TABLE IF NOT EXISTS client_sessions (
  id uuid PRIMARY KEY,
  capability_id uuid NOT NULL REFERENCES client_capabilities(id) ON DELETE RESTRICT,
  session_hash varchar(64) NOT NULL UNIQUE,
  csrf_hash varchar(64) NOT NULL,
  purpose varchar(32) NOT NULL CHECK (purpose IN ('REVIEW','RECEIPT')),
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS payment_requests (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  accepted_revision_id uuid NOT NULL UNIQUE REFERENCES proposal_revisions(id) ON DELETE RESTRICT,
  total_minor bigint NOT NULL CHECK (total_minor > 0 AND total_minor <= 100000000),
  tax_minor bigint NOT NULL CHECK (tax_minor >= 0 AND tax_minor <= total_minor),
  currency varchar(3) NOT NULL DEFAULT 'INR' CHECK (currency = 'INR'),
  status varchar(32) NOT NULL DEFAULT 'NOT_REQUESTED' CHECK (status IN ('NOT_REQUESTED','CREATION_PENDING','PENDING','REVIEW_REQUIRED','PAID','EXPIRED','CANCELLED','REVERSED')),
  due_at timestamptz,
  expire_at timestamptz,
  paid_at timestamptz,
  row_version bigint NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS approved_revenue_facts (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  change_order_id uuid NOT NULL REFERENCES change_orders(id) ON DELETE RESTRICT,
  revision_id uuid NOT NULL UNIQUE REFERENCES proposal_revisions(id) ON DELETE RESTRICT,
  amount_minor bigint NOT NULL CHECK (amount_minor > 0 AND amount_minor <= 100000000),
  tax_minor bigint NOT NULL CHECK (tax_minor >= 0 AND tax_minor <= amount_minor),
  currency varchar(3) NOT NULL DEFAULT 'INR' CHECK (currency = 'INR'),
  fact_type varchar(32) NOT NULL DEFAULT 'APPROVED',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS notifications (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  change_order_id uuid REFERENCES change_orders(id) ON DELETE RESTRICT,
  revision_id uuid REFERENCES proposal_revisions(id) ON DELETE RESTRICT,
  channel varchar(32) NOT NULL DEFAULT 'SES' CHECK (channel = 'SES'),
  verified_recipient varchar(320) NOT NULL,
  state varchar(32) NOT NULL DEFAULT 'PENDING' CHECK (state IN ('PENDING','SENT','UNKNOWN_OUTCOME','FAILED','CANCELLED')),
  action_id uuid REFERENCES external_actions(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_notification_revision_channel UNIQUE (tenant_id,change_order_id,revision_id,channel)
);
