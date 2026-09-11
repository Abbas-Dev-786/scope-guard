ALTER TABLE projects DROP CONSTRAINT IF EXISTS fk_project_current_calendar_owner;
DROP TABLE IF EXISTS audit_events;
DROP TABLE IF EXISTS api_idempotency;
DROP TABLE IF EXISTS calendar_versions;
DROP TABLE IF EXISTS projects;
DROP TABLE IF EXISTS client_contacts;
DROP TABLE IF EXISTS clients;
DROP TABLE IF EXISTS preference_versions;
DROP TABLE IF EXISTS users;
