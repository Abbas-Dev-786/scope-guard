ALTER TABLE payment_observations DROP CONSTRAINT IF EXISTS ck_payment_observation_association_state;
ALTER TABLE payment_observations
  DROP COLUMN IF EXISTS associated_at,
  DROP COLUMN IF EXISTS next_retry_at,
  DROP COLUMN IF EXISTS association_state;
ALTER TABLE payment_link_attempts DROP COLUMN IF EXISTS provider_order_id;