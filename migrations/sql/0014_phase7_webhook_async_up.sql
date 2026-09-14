CREATE TABLE payment_webhook_ingress (
  id uuid PRIMARY KEY,
  provider_account_id varchar(255) NOT NULL,
  provider_environment varchar(32) NOT NULL DEFAULT 'test',
  provider_event_id varchar(255) NOT NULL,
  event_type varchar(120) NOT NULL,
  signature_verified boolean NOT NULL DEFAULT false,
  raw_payload jsonb NOT NULL,
  normalization_state varchar(32) NOT NULL DEFAULT 'PENDING',
  observation_id uuid REFERENCES payment_observations(id) ON DELETE RESTRICT,
  normalized_at timestamptz,
  last_error varchar(500),
  received_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_payment_webhook_ingress_event
    UNIQUE (provider_account_id, provider_environment, provider_event_id),
  CONSTRAINT ck_payment_webhook_ingress_environment
    CHECK (provider_environment = 'test'),
  CONSTRAINT ck_payment_webhook_ingress_state
    CHECK (normalization_state IN ('PENDING','NORMALIZED','REVIEW_REQUIRED'))
);
CREATE INDEX ix_payment_webhook_ingress_state
  ON payment_webhook_ingress(normalization_state, received_at);
