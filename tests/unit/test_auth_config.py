import pytest

from services.api.auth import CognitoTokenVerifier
from services.api.config import Settings
from services.domain.errors import AuthenticationError


def test_development_auth_cannot_be_enabled_outside_development() -> None:
    with pytest.raises(ValueError):
        Settings(environment="test", allow_dev_auth=True)


def test_development_token_is_exact_and_explicit() -> None:
    settings = Settings(
        environment="development",
        allow_dev_auth=True,
        dev_auth_sub="owner-sub",
        dev_auth_email="owner@example.com",
    )
    verifier = CognitoTokenVerifier(settings)
    principal = verifier.verify("dev:owner-sub")
    assert principal.subject == "owner-sub"
    assert principal.email_verified is True
    with pytest.raises(AuthenticationError):
        verifier.verify("dev:other")


def test_development_token_is_disabled_by_default() -> None:
    verifier = CognitoTokenVerifier(Settings())
    with pytest.raises(AuthenticationError):
        verifier.verify("dev:00000000-0000-4000-8000-000000000001")
