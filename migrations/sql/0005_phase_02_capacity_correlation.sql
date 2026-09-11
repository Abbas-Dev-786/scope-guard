ALTER TABLE jobs ADD COLUMN IF NOT EXISTS correlation_id uuid;
UPDATE jobs SET correlation_id = id WHERE correlation_id IS NULL;
ALTER TABLE jobs ALTER COLUMN correlation_id SET NOT NULL;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS causation_id uuid;

CREATE TABLE IF NOT EXISTS analysis_capacity_reservations (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  reservation_key varchar(160) NOT NULL,
  worker_id varchar(255) NOT NULL,
  lease_until timestamptz NOT NULL,
  released_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_analysis_reservation_key UNIQUE (tenant_id, reservation_key)
);
CREATE INDEX IF NOT EXISTS ix_analysis_capacity_active
  ON analysis_capacity_reservations(released_at, lease_until);
CREATE INDEX IF NOT EXISTS ix_analysis_capacity_tenant
  ON analysis_capacity_reservations(tenant_id, released_at);