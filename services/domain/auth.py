from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from services.domain.errors import AuthorizationError


@dataclass(frozen=True, slots=True)
class TrustedContext:
    """Identity derived by the server, never from a request body."""

    tenant_id: UUID
    subject: str
    email: str
    email_verified: bool
    correlation_id: UUID

    def require_tenant(self, resource_tenant_id: UUID) -> None:
        if resource_tenant_id != self.tenant_id:
            raise AuthorizationError("Resource was not found")

    def require_project(self, resource_tenant_id: UUID, project_id: UUID) -> UUID:
        self.require_tenant(resource_tenant_id)
        return project_id
