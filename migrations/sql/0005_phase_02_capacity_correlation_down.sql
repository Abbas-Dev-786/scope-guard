DROP TABLE IF EXISTS analysis_capacity_reservations;
ALTER TABLE jobs DROP COLUMN IF EXISTS causation_id;
ALTER TABLE jobs DROP COLUMN IF EXISTS correlation_id;