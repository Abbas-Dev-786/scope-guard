from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.domain.auth import TrustedContext
from services.domain.errors import AuthorizationError, ValidationError
from services.domain.models import EvidenceReference, Project

ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class ValidationAttempt(Generic[ModelT]):
    value: ModelT | None
    errors: tuple[str, ...]
    repaired: bool


class StructuredOutputError(ValidationError):
    """A model response could not be validated within the single repair allowance."""


def parse_with_one_repair(
    model: type[ModelT],
    payload: object,
    *,
    repair: Callable[[object], object] | None = None,
) -> ValidationAttempt[ModelT]:
    """Parse strict output once, then permit one bounded repair of the same payload."""
    attempts: list[object] = [payload]
    if repair is not None:
        try:
            attempts.append(repair(payload))
        except Exception as exc:
            raise StructuredOutputError("Structured-output repair failed") from exc
    errors: list[str] = []
    for index, candidate in enumerate(attempts):
        try:
            return ValidationAttempt(model.model_validate(candidate), tuple(errors), index == 1)
        except PydanticValidationError as exc:
            errors.extend(error.get("msg", "invalid output") for error in exc.errors())
    raise StructuredOutputError("Structured output failed validation after one repair")


def require_project_context(session: Session, context: TrustedContext, project_id: UUID) -> Project:
    project = session.scalar(select(Project).where(Project.id == project_id, Project.tenant_id == context.tenant_id))
    if project is None:
        raise AuthorizationError("Analysis project is outside the trusted tenant")
    return project


def validate_reference_ids(
    session: Session,
    context: TrustedContext,
    *,
    project_id: UUID,
    reference_ids: list[UUID],
    bundle_id: UUID | None = None,
) -> list[EvidenceReference]:
    """Validate every cited evidence ID and its tenant/project/bundle ownership."""
    require_project_context(session, context, project_id)
    if len(reference_ids) != len(set(reference_ids)):
        raise StructuredOutputError("Evidence references must be unique")
    if not reference_ids:
        raise StructuredOutputError("A proposal requires at least one evidence reference")
    rows = list(session.scalars(select(EvidenceReference).where(EvidenceReference.id.in_(reference_ids), EvidenceReference.tenant_id == context.tenant_id, EvidenceReference.project_id == project_id)).all())
    found = {row.id: row for row in rows}
    if len(found) != len(reference_ids):
        raise AuthorizationError("Structured output cited an unknown or unauthorized evidence reference")
    if bundle_id is not None and any(row.bundle_id != bundle_id for row in rows):
        raise AuthorizationError("Structured output cited evidence outside the workflow bundle")
    return [found[item] for item in reference_ids]


def validate_safe_summary(value: str, *, limit: int = 1000) -> str:
    if not value.strip() or len(value) > limit:
        raise ValidationError("Safe summary is empty or exceeds its limit")
    lowered = value.lower()
    if any(secret in lowered for secret in ("authorization:", "bearer ", "access_key", "refresh_token", "private_key")):
        raise ValidationError("Safe summary contains secret-bearing content")
    return value.strip()