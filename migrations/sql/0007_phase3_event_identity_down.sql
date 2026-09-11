DROP TABLE IF EXISTS thread_assignments CASCADE;
ALTER TABLE external_events DROP COLUMN IF EXISTS content_ref;
ALTER TABLE external_events DROP COLUMN IF EXISTS source_version;
ALTER TABLE external_events DROP COLUMN IF EXISTS resource_id;
ALTER TABLE external_events DROP COLUMN IF EXISTS resource_type;
