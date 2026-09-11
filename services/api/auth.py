from __future__ import annotations

import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, Header
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.api.config import Settings, get_settings
from services.api.database import get_session
from services.domain.auth import TrustedContext
from services.domain.errors import AuthenticationError
from services.domain.models import User


@dataclass(frozen=True, slots=True)
class VerifiedPrincipal:
    subject: str
    email: str | None
    email_verified: bool | None


class CognitoTokenVerifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.jwks = PyJWKClient(settings.cognito_jwks_url, cache_keys=True, lifespan=300)

    def verify(self, token: str) -> VerifiedPrincipal:
        if token.startswith("dev:"):
            if not self.settings.allow_dev_auth or self.settings.environment != "development":
                raise AuthenticationError("Development authentication is disabled")
            if token != f"dev:{self.settings.dev_auth_sub}":
                raise AuthenticationError("Invalid development token")
            return VerifiedPrincipal(self.settings.dev_auth_sub, self.settings.dev_auth_email, True)
        try:
            signing_key = self.jwks.get_signing_key_from_jwt(token)
            unverified = jwt.decode(token, options={"verify_signature": False})
            token_use = unverified.get("token_use")
            if token_use == "id":
                claims = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256"],
                    audience=self.settings.cognito_client_id,
                    issuer=self.settings.cognito_issuer,
                )
            elif token_use == "access":
                claims = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256"],
                    issuer=self.settings.cognito_issuer,
                    options={"verify_aud": False},
                )
                if claims.get("client_id") != self.settings.cognito_client_id:
                    raise AuthenticationError("Token client is not accepted")
            else:
                raise AuthenticationError("Unsupported token type")
        except AuthenticationError:
            raise
        except Exception as exc:
            raise AuthenticationError("Invalid or expired authentication token") from exc
        subject = claims.get("sub")
        email = claims.get("email")
        verified = claims.get("email_verified") in (True, "true")
        if not isinstance(subject, str):
            raise AuthenticationError("Token subject is missing")
        return VerifiedPrincipal(subject, email if isinstance(email, str) else None, verified)


@lru_cache
def get_verifier() -> CognitoTokenVerifier:
    return CognitoTokenVerifier(get_settings())


def get_verified_principal(
    verifier: Annotated[CognitoTokenVerifier, Depends(get_verifier)],
    authorization: Annotated[str | None, Header()] = None,
) -> VerifiedPrincipal:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("Bearer authentication is required")
    return verifier.verify(authorization[7:])


def get_current_context(
    session: Annotated[Session, Depends(get_session)],
    principal: Annotated[VerifiedPrincipal, Depends(get_verified_principal)],
    x_request_id: Annotated[str | None, Header()] = None,
) -> TrustedContext:
    user = session.scalar(
        select(User).where(User.cognito_sub == principal.subject, User.status == "ACTIVE")
    )
    if user is None:
        raise AuthenticationError("Account is not provisioned or active")
    return TrustedContext(
        tenant_id=user.id,
        subject=principal.subject,
        email=user.verified_email,
        email_verified=True,
        correlation_id=_request_uuid(x_request_id),
    )


def _request_uuid(value: str | None) -> uuid.UUID:
    try:
        return uuid.UUID(value) if value else uuid.uuid4()
    except ValueError:
        return uuid.uuid4()


VerifiedIdentity = Annotated[VerifiedPrincipal, Depends(get_verified_principal)]
CurrentContext = Annotated[TrustedContext, Depends(get_current_context)]
DbSession = Annotated[Session, Depends(get_session)]
