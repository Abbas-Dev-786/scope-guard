DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'api_idempotency_actor_scope_route_key_key') THEN
    ALTER TABLE api_idempotency RENAME CONSTRAINT api_idempotency_actor_scope_route_key_key TO uq_api_idempotency_scope_route_key;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'audit_events_tenant_id_id_key') THEN
    ALTER TABLE audit_events RENAME CONSTRAINT audit_events_tenant_id_id_key TO uq_audit_tenant_id;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'calendar_versions_tenant_id_project_id_id_key') THEN
    ALTER TABLE calendar_versions RENAME CONSTRAINT calendar_versions_tenant_id_project_id_id_key TO uq_calendar_project_id;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'calendar_versions_tenant_id_project_id_version_key') THEN
    ALTER TABLE calendar_versions RENAME CONSTRAINT calendar_versions_tenant_id_project_id_version_key TO uq_calendar_project_version;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'client_contacts_tenant_id_client_id_normalized_email_key') THEN
    ALTER TABLE client_contacts RENAME CONSTRAINT client_contacts_tenant_id_client_id_normalized_email_key TO uq_contact_email_per_client;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'client_contacts_tenant_id_id_key') THEN
    ALTER TABLE client_contacts RENAME CONSTRAINT client_contacts_tenant_id_id_key TO uq_contacts_tenant_id;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'clients_tenant_id_id_key') THEN
    ALTER TABLE clients RENAME CONSTRAINT clients_tenant_id_id_key TO uq_clients_tenant_id;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'preference_versions_tenant_id_id_key') THEN
    ALTER TABLE preference_versions RENAME CONSTRAINT preference_versions_tenant_id_id_key TO uq_preference_tenant_id;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'preference_versions_tenant_id_version_key') THEN
    ALTER TABLE preference_versions RENAME CONSTRAINT preference_versions_tenant_id_version_key TO uq_preference_tenant_version;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'projects_tenant_id_id_key') THEN
    ALTER TABLE projects RENAME CONSTRAINT projects_tenant_id_id_key TO uq_projects_tenant_id;
  END IF;
END
$$;