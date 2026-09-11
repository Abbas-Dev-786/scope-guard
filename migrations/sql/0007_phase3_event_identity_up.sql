ALTER TABLE external_events ADD COLUMN IF NOT EXISTS resource_type varchar(80);
ALTER TABLE external_events ADD COLUMN IF NOT EXISTS resource_id varchar(255);
ALTER TABLE external_events ADD COLUMN IF NOT EXISTS source_version varchar(255);
ALTER TABLE external_events ADD COLUMN IF NOT EXISTS content_ref varchar(512);
CREATE TABLE IF NOT EXISTS thread_assignments (
  id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT, connection_id uuid,
  thread_id varchar(255) NOT NULL, assigned_by varchar(255) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_thread_assignment UNIQUE(tenant_id,connection_id,thread_id)
);
