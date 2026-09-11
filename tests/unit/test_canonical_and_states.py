from decimal import Decimal
from uuid import UUID

import pytest

from services.api.schemas import EventEnvelope
from services.domain.canonical import canonical_json_bytes, canonical_sha256
from services.domain.enums import (
    CHANGE_ORDER_TRANSITIONS,
    PAYMENT_TRANSITIONS,
    REQUEST_TRANSITIONS,
    ChangeOrderStatus,
    EventType,
    PaymentStatus,
    RequestStatus,
)


def test_canonical_json_is_stable_and_decimal_safe() -> None:
    left = {"price": 1_500_000, "hours": Decimal("14.00"), "name": "Entra OIDC"}
    right = {"name": "Entra OIDC", "hours": Decimal("14.00"), "price": 1_500_000}
    assert canonical_json_bytes(left) == canonical_json_bytes(right)
    assert canonical_sha256(left) == canonical_sha256(right)
    assert b'"hours":"14.00"' in canonical_json_bytes(left)
    with pytest.raises(ValueError):
        canonical_json_bytes({"money": 15000.0})


def test_transition_registry_uses_only_canonical_states() -> None:
    assert (
        REQUEST_TRANSITIONS[(RequestStatus.OPEN, "evidence_missing")]
        is RequestStatus.CLARIFICATION_REQUIRED
    )
    assert (
        CHANGE_ORDER_TRANSITIONS[(ChangeOrderStatus.SEND_PENDING, "client_accepted")]
        is ChangeOrderStatus.CLIENT_APPROVED
    )
    assert (
        PAYMENT_TRANSITIONS[(PaymentStatus.EXPIRED, "full_capture_verified")] is PaymentStatus.PAID
    )
    assert (PaymentStatus.PAID, "provider_expired") not in PAYMENT_TRANSITIONS


def test_documented_event_envelope_validates_against_registry() -> None:
    envelope = EventEnvelope.model_validate(
        {
            "schema_version": 1,
            "event_id": "11111111-1111-4111-8111-111111111111",
            "event_type": "communication.created",
            "tenant_id": "22222222-2222-4222-8222-222222222222",
            "project_id": None,
            "connection_id": "33333333-3333-4333-8333-333333333333",
            "environment": "test",
            "provider": "gmail",
            "provider_account_id": "verified-account-reference",
            "provider_event_id": "provider-delivery-reference",
            "resource_type": "message",
            "resource_id": "provider-message-reference",
            "occurred_at": "2026-09-07T10:32:00Z",
            "received_at": "2026-09-07T10:32:01Z",
            "correlation_id": "44444444-4444-4444-8444-444444444444",
            "causation_id": None,
            "payload_ref": "authorized-database-or-object-reference",
        }
    )
    assert envelope.event_type is EventType.COMMUNICATION_CREATED
    assert envelope.tenant_id == UUID("22222222-2222-4222-8222-222222222222")
    with pytest.raises(ValueError):
        EventEnvelope.model_validate({**envelope.model_dump(), "event_type": "payment.captured"})
