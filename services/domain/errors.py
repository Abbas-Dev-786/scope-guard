from __future__ import annotations


class DomainError(Exception):
    """Base class for expected, sanitized domain failures."""

    code = "domain_error"
    status_code = 400

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class AuthenticationError(DomainError):
    code = "authentication_required"
    status_code = 401


class AuthorizationError(DomainError):
    code = "resource_not_found"
    status_code = 404


class ConflictError(DomainError):
    code = "conflict"
    status_code = 409


class NotFoundError(DomainError):
    code = "resource_not_found"
    status_code = 404


class UnsupportedTermsError(DomainError):
    code = "manual_handling_required"
    status_code = 422


class ValidationError(DomainError):
    code = "validation_error"
    status_code = 422
