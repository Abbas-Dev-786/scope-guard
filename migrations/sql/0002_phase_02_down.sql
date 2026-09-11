DROP TRIGGER IF EXISTS audit_events_immutable ON audit_events;
DROP FUNCTION IF EXISTS prevent_audit_mutation();
DROP TABLE IF EXISTS action_attempts;
DROP TABLE IF EXISTS external_actions;
DROP TABLE IF EXISTS workflow_instances;
DROP TABLE IF EXISTS consumer_receipts;
DROP TABLE IF EXISTS outbox_events;
DROP TABLE IF EXISTS jobs;