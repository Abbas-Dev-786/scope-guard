from __future__ import annotations

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SCOPEGUARD_", env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql+psycopg://scopeguard:scopeguard@localhost:5432/scopeguard"
    cognito_region: str = "us-east-1"
    cognito_user_pool_id: str = "replace-after-deployment"
    cognito_client_id: str = "replace-after-deployment"
    allow_dev_auth: bool = False
    dev_auth_sub: str = "00000000-0000-4000-8000-000000000001"
    dev_auth_email: str = "owner@example.test"
    aws_region: str = "us-east-1"
    contract_object_bucket: str = ""
    contract_object_kms_key_arn: str = ""
    contract_object_url_expiry_seconds: int = Field(default=900, ge=60, le=3600)
    bedrock_model_id: str = "replace-after-readiness-verification"
    contract_structure_model_timeout_seconds: int = Field(default=120, ge=1, le=120)
    max_model_cost_minor_per_day: int = Field(default=0, ge=0)
    tenant_token_limit_per_day: int = Field(default=250_000, gt=0)
    deployment_token_limit_per_day: int = Field(default=1_000_000, gt=0)
    capability_encryption_key: str = ""
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_authorization_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    gmail_token_url: str = "https://oauth2.googleapis.com/token"
    gmail_userinfo_url: str = "https://openidconnect.googleapis.com/v1/userinfo"
    gmail_redirect_uri: str = "http://localhost:8000/api/v1/integrations/gmail/callback"
    gmail_push_verification_secret: str = ""
    gmail_pubsub_topic: str = ""
    gmail_api_base_url: str = "https://gmail.googleapis.com/gmail/v1"
    client_review_base_url: str = "http://localhost:3000"
    ses_configuration_set: str = ""
    ses_from_email: str = ""
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    razorpay_account_id: str = ""
    razorpay_environment: str = "test"
    razorpay_api_base_url: str = "https://api.razorpay.com/v1"

    @model_validator(mode="after")
    def safe_development_auth(self) -> Settings:
        if self.allow_dev_auth and self.environment != "development":
            raise ValueError("Development authentication can only be enabled in development")
        return self

    @property
    def cognito_issuer(self) -> str:
        return (
            f"https://cognito-idp.{self.cognito_region}.amazonaws.com/{self.cognito_user_pool_id}"
        )

    @property
    def cognito_jwks_url(self) -> str:
        return f"{self.cognito_issuer}/.well-known/jwks.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
