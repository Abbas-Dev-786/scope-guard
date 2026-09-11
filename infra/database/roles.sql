-- Run as the database owner after creating these NOLOGIN group roles through infrastructure.
GRANT USAGE ON SCHEMA public TO scopeguard_app, scopeguard_lifecycle;
GRANT SELECT, INSERT, UPDATE ON users, clients, client_contacts, projects TO scopeguard_app;
GRANT SELECT, INSERT ON preference_versions, calendar_versions, audit_events TO scopeguard_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON api_idempotency TO scopeguard_app;
REVOKE UPDATE, DELETE ON preference_versions, calendar_versions, audit_events FROM scopeguard_app;

GRANT SELECT ON ALL TABLES IN SCHEMA public TO scopeguard_lifecycle;
GRANT DELETE ON preference_versions, calendar_versions, audit_events TO scopeguard_lifecycle;
-- Lifecycle access is assumed only by a separately audited deletion worker in Phase 08.
