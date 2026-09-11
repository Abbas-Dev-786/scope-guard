DROP TABLE IF EXISTS notifications;
DROP TABLE IF EXISTS approved_revenue_facts;
DROP TABLE IF EXISTS payment_requests;
DROP TABLE IF EXISTS client_sessions;
DROP TABLE IF EXISTS client_capabilities;
DROP TABLE IF EXISTS approvals;
ALTER TABLE change_orders DROP CONSTRAINT IF EXISTS fk_change_order_current_revision;
DROP TABLE IF EXISTS proposal_revisions;
DROP TABLE IF EXISTS change_orders;
