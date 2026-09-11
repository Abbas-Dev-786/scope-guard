CREATE TABLE IF NOT EXISTS contract_documents (
  id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  object_key varchar(512) NOT NULL, object_version varchar(255) NOT NULL,
  sha256 varchar(64) NOT NULL, size_bytes bigint NOT NULL CHECK (size_bytes BETWEEN 0 AND 10485760),
  mime_type varchar(120) NOT NULL, source_type varchar(32) NOT NULL,
  status varchar(40) NOT NULL DEFAULT 'UPLOADED', extractor_version varchar(120),
  rejection_reason varchar(500), created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz,
  CONSTRAINT uq_contract_documents_tenant_id UNIQUE (tenant_id,id),
  CONSTRAINT uq_contract_document_object_version UNIQUE (tenant_id,project_id,object_key,object_version),
  CONSTRAINT ck_contract_document_status CHECK (status IN ('UPLOADED','EXTRACTING','AWAITING_SCOPE_REVIEW','CONFIRMED','REJECTED','FAILED_REQUIRES_REVIEW'))
);
CREATE INDEX IF NOT EXISTS ix_contract_documents_project_created ON contract_documents(tenant_id,project_id,created_at);

CREATE TABLE IF NOT EXISTS document_upload_grants (
  id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  document_id uuid NOT NULL REFERENCES contract_documents(id) ON DELETE RESTRICT,
  token_hash varchar(64) NOT NULL UNIQUE, expected_size_bytes bigint NOT NULL,
  expected_mime_type varchar(120) NOT NULL, expires_at timestamptz NOT NULL,
  consumed_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS document_chunks (
  id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  document_id uuid NOT NULL REFERENCES contract_documents(id) ON DELETE RESTRICT,
  chunk_index integer NOT NULL, page_number integer, section varchar(255),
  start_offset integer NOT NULL, end_offset integer NOT NULL, source_text text NOT NULL,
  content_hash varchar(64) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_document_chunk_index UNIQUE(document_id,chunk_index),
  CONSTRAINT ck_document_chunk_offsets CHECK(start_offset >= 0 AND end_offset >= start_offset)
);
CREATE INDEX IF NOT EXISTS ix_document_chunks_project ON document_chunks(tenant_id,project_id,document_id,chunk_index);

CREATE TABLE IF NOT EXISTS scope_candidates (
  id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  document_id uuid NOT NULL REFERENCES contract_documents(id) ON DELETE RESTRICT,
  source_chunk_id uuid NOT NULL REFERENCES document_chunks(id) ON DELETE RESTRICT,
  item_key varchar(160) NOT NULL, item_type varchar(40) NOT NULL, extracted_text text NOT NULL,
  corrected_text text, extractor_version varchar(120) NOT NULL, status varchar(32) NOT NULL DEFAULT 'CANDIDATE',
  correction_reason varchar(500), created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_scope_candidate_key UNIQUE(tenant_id,document_id,item_key),
  CONSTRAINT ck_scope_candidate_status CHECK(status IN ('CANDIDATE','CORRECTED','CONFIRMED','REJECTED'))
);

CREATE TABLE IF NOT EXISTS scope_versions (
  id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT, version integer NOT NULL,
  parent_version_id uuid, source_revision_id uuid, confirmation_actor varchar(255) NOT NULL,
  content_hash varchar(64) NOT NULL, confirmed_at timestamptz NOT NULL DEFAULT now(), created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_scope_version_number UNIQUE(tenant_id,project_id,version), CONSTRAINT uq_scope_version_tenant_id UNIQUE(tenant_id,id)
);
CREATE TABLE IF NOT EXISTS scope_items (
  id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  source_document_chunk_id uuid REFERENCES document_chunks(id) ON DELETE RESTRICT,
  source_revision_id uuid, item_type varchar(40) NOT NULL, item_key varchar(160) NOT NULL,
  text text NOT NULL, supersedes_item_id uuid, created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_scope_item_identity UNIQUE(tenant_id,project_id,item_key,created_at)
);
CREATE TABLE IF NOT EXISTS scope_version_items (
  id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  scope_version_id uuid NOT NULL REFERENCES scope_versions(id) ON DELETE RESTRICT,
  scope_item_id uuid NOT NULL REFERENCES scope_items(id) ON DELETE RESTRICT,
  CONSTRAINT uq_scope_version_item UNIQUE(scope_version_id,scope_item_id)
);
CREATE TABLE IF NOT EXISTS scope_amendments (
  id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT, accepted_revision_id uuid NOT NULL UNIQUE,
  previous_scope_version_id uuid NOT NULL REFERENCES scope_versions(id) ON DELETE RESTRICT,
  resulting_scope_version_id uuid NOT NULL UNIQUE REFERENCES scope_versions(id) ON DELETE RESTRICT,
  operations_json jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS integration_bindings (
  id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT, provider varchar(80) NOT NULL,
  connection_id uuid, resource_type varchar(80) NOT NULL, resource_id varchar(255) NOT NULL,
  alias varchar(160), priority integer NOT NULL DEFAULT 100, status varchar(32) NOT NULL DEFAULT 'ACTIVE', created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_integration_binding UNIQUE(tenant_id,project_id,provider,resource_type,resource_id)
);
CREATE INDEX IF NOT EXISTS ix_integration_binding_lookup ON integration_bindings(tenant_id,provider,resource_type,resource_id,status);

CREATE TABLE IF NOT EXISTS external_events (
  id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT, connection_id uuid,
  provider varchar(80) NOT NULL, provider_account_id varchar(255), environment varchar(32) NOT NULL,
  provider_event_id varchar(255) NOT NULL, payload_hash varchar(64) NOT NULL, payload_object_ref varchar(512),
  received_at timestamptz NOT NULL DEFAULT now(), occurred_at timestamptz NOT NULL, processing_status varchar(40) NOT NULL DEFAULT 'RECEIVED',
  correlation_id uuid NOT NULL, CONSTRAINT uq_external_event_delivery UNIQUE(tenant_id,connection_id,provider_event_id)
);
CREATE TABLE IF NOT EXISTS communication_events (
  id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT, project_id uuid REFERENCES projects(id) ON DELETE RESTRICT,
  connection_id uuid, external_event_id uuid NOT NULL REFERENCES external_events(id) ON DELETE RESTRICT,
  resource_type varchar(80) NOT NULL, resource_id varchar(255) NOT NULL, source_version varchar(255) NOT NULL,
  sender varchar(320), thread_id varchar(255), occurred_at timestamptz NOT NULL, content_ref varchar(512) NOT NULL, direction varchar(32) NOT NULL,
  CONSTRAINT uq_communication_source_version UNIQUE(tenant_id,connection_id,resource_type,resource_id,source_version)
);

CREATE TABLE IF NOT EXISTS request_records (
  id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT, project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  summary text NOT NULL, status varchar(40) NOT NULL DEFAULT 'OPEN', request_version integer NOT NULL DEFAULT 1,
  merged_into_id uuid, rejection_reason varchar(500), row_version bigint NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_request_record_status CHECK(status IN ('OPEN','CLARIFICATION_REQUIRED','COVERED','PROPOSAL_OPEN','WAIVED','DECLINED','MERGED','RESOLVED'))
);
CREATE INDEX IF NOT EXISTS ix_request_records_project_status ON request_records(tenant_id,project_id,status,created_at);
CREATE TABLE IF NOT EXISTS request_communications (
  id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT, project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  request_id uuid NOT NULL REFERENCES request_records(id) ON DELETE RESTRICT, communication_id uuid NOT NULL REFERENCES communication_events(id) ON DELETE RESTRICT,
  relationship_type varchar(40) NOT NULL DEFAULT 'SUPPORTS', created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_request_communication UNIQUE(request_id,communication_id)
);

CREATE TABLE IF NOT EXISTS evidence_bundles (
  id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT, project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  request_id uuid REFERENCES request_records(id) ON DELETE RESTRICT, snapshot_digest varchar(64) NOT NULL,
  searched_sources jsonb NOT NULL, cutoff timestamptz NOT NULL, completeness varchar(32) NOT NULL, stale_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS evidence_references (
  id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT, project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  bundle_id uuid NOT NULL REFERENCES evidence_bundles(id) ON DELETE RESTRICT, source_type varchar(80) NOT NULL, source_id varchar(255) NOT NULL,
  source_version varchar(255) NOT NULL, exact_excerpt_ref varchar(512) NOT NULL, content_hash varchar(64) NOT NULL,
  locator jsonb NOT NULL, fetched_at timestamptz NOT NULL, access_scope varchar(255) NOT NULL, relation varchar(32) NOT NULL,
  CONSTRAINT ck_evidence_reference_relation CHECK(relation IN ('SUPPORTS','CONTRADICTS','CONTEXT'))
);
CREATE TABLE IF NOT EXISTS routing_decisions (
  id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  external_event_id uuid NOT NULL REFERENCES external_events(id) ON DELETE RESTRICT, status varchar(32) NOT NULL DEFAULT 'OPEN',
  precedence varchar(40) NOT NULL, candidate_projects jsonb NOT NULL, evidence jsonb NOT NULL,
  selected_project_id uuid, resolved_by varchar(255), resolved_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_routing_decision_status CHECK(status IN ('OPEN','RESOLVED','DISMISSED'))
);
