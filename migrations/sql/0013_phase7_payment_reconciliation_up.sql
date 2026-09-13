ALTER TABLE payment_link_attempts
  ADD COLUMN IF NOT EXISTS provider_order_id varchar(255);

ALTER TABLE payment_observations
  ADD COLUMN IF NOT EXISTS association_state varchar(32) NOT NULL DEFAULT 'UNMATCHED',
  ADD COLUMN IF NOT EXISTS next_retry_at timestamptz,
  ADD COLUMN IF NOT EXISTS associated_at timestamptz;

ALTER TABLE payment_observations
  DROP CONSTRAINT IF EXISTS ck_payment_observation_association_state;
ALTER TABLE payment_observations
  ADD CONSTRAINT ck_payment_observation_association_state
  CHECK (association_state IN ('UNMATCHED','ASSOCIATED','MANUAL_REVIEW'));