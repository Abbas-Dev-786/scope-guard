DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_api_idempotency_scope_route_key') THEN
    ALTER TABLE api_idempotency RENAME CONSTRAINT uq_api_idempotency_scope_route_key TO api_idempotency_actor_scope_route_key_key;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_audit_tenant_id') THEN
    ALTER TABLE audit_events RENAME CONSTRAINT uq_audit_tenant_id TO audit_events_tenant_id_id_key;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_calendar_project_id') THEN
    ALTER TABLE calendar_versions RENAME CONSTRAINT uq_calendar_project_id TO calendar_versions_tenant_id_project_id_id_key;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_calendar_project_version') THEN
    ALTER TABLE calendar_versions RENAME CONSTRAINT uq_calendar_project_version TO calendar_versions_tenant_id_project_id_version_key;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_contact_email_per_client') THEN
    ALTER TABLE client_contacts RENAME CONSTRAINT uq_contact_email_per_client TO client_contacts_tenant_id_client_id_normalized_email_key;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_contacts_tenant_id') THEN
    ALTER TABLE client_contacts RENAME CONSTRAINT uq_contacts_tenant_id TO client_contacts_tenant_id_id_key;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_clients_tenant_id') THEN
    ALTER TABLE clients RENAME CONSTRAINT uq_clients_tenant_id TO clients_tenant_id_id_key;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_preference_tenant_id') THEN
    ALTER TABLE preference_versions RENAME CONSTRAINT uq_preference_tenant_id TO preference_versions_tenant_id_id_key;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_preference_tenant_version') THEN
    ALTER TABLE preference_versions RENAME CONSTRAINT uq_preference_tenant_version TO preference_versions_tenant_id_version_key;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_projects_tenant_id') THEN
    ALTER TABLE projects RENAME CONSTRAINT uq_projects_tenant_id TO projects_tenant_id_id_key;
  END IF;
END
$$;