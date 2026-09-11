from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from services.domain.models import AnalysisCapacityReservation


class CapacityExceededError(RuntimeError):
    """No analysis capacity is available without starving protected work."""


@dataclass(frozen=True)
class CapacityPolicy:
    per_tenant: int = 1
    global_limit: int = 4
    lease_seconds: int = 60
    reserved_fraction: float = 0.30


DEFAULT_CAPACITY_POLICY = CapacityPolicy()

def _now(value: datetime | None) -> datetime:
    return value or datetime.now(UTC)


def reserve_analysis_slot(
    session: Session,
    *,
    tenant_id: UUID,
    reservation_key: str,
    worker_id: str,
    policy: CapacityPolicy = DEFAULT_CAPACITY_POLICY,
    now: datetime | None = None,
) -> AnalysisCapacityReservation:
    if not 0 < policy.per_tenant <= policy.global_limit:
        raise ValueError("Capacity policy limits are invalid")
    current = _now(now)
    active = session.scalars(
        select(AnalysisCapacityReservation)
        .where(
            AnalysisCapacityReservation.released_at.is_(None),
            AnalysisCapacityReservation.lease_until > current,
        )
        .with_for_update(skip_locked=True)
    ).all()
    existing = next(
        (
            item
            for item in active
            if item.tenant_id == tenant_id and item.reservation_key == reservation_key
        ),
        None,
    )
    if existing is not None:
        existing.lease_until = current + timedelta(seconds=policy.lease_seconds)
        existing.worker_id = worker_id
        session.flush()
        return existing
    tenant_count = sum(item.tenant_id == tenant_id for item in active)
    if tenant_count >= policy.per_tenant or len(active) >= policy.global_limit:
        raise CapacityExceededError("Analysis capacity is exhausted")
    reservation = AnalysisCapacityReservation(
        tenant_id=tenant_id,
        reservation_key=reservation_key,
        worker_id=worker_id,
        lease_until=current + timedelta(seconds=policy.lease_seconds),
    )
    session.add(reservation)
    session.flush()
    return reservation


def release_analysis_slot(
    session: Session,
    *,
    reservation_id: UUID,
    worker_id: str,
    now: datetime | None = None,
) -> None:
    reservation = session.get(AnalysisCapacityReservation, reservation_id, with_for_update=True)
    if reservation is None:
        raise CapacityExceededError("Capacity reservation does not exist")
    if reservation.released_at is None and reservation.worker_id != worker_id:
        raise CapacityExceededError("Capacity reservation belongs to another worker")
    reservation.released_at = _now(now)
    session.flush()


def recover_capacity_slots(session: Session, *, now: datetime | None = None) -> int:
    current = _now(now)
    expired = session.scalars(
        select(AnalysisCapacityReservation)
        .where(
            AnalysisCapacityReservation.released_at.is_(None),
            AnalysisCapacityReservation.lease_until <= current,
        )
        .with_for_update(skip_locked=True)
    ).all()
    for reservation in expired:
        reservation.released_at = current
    session.flush()
    return len(expired)


def active_capacity(session: Session, *, now: datetime | None = None) -> int:
    current = _now(now)
    return int(
        session.scalar(
            select(func.count())
            .select_from(AnalysisCapacityReservation)
            .where(
                AnalysisCapacityReservation.released_at.is_(None),
                AnalysisCapacityReservation.lease_until > current,
            )
        )
        or 0
    )