"""Razorpay Test Mode transport boundary.

The domain layer owns payment intent validation and state transitions. This module only
performs provider I/O and verifies webhook authenticity; it never decides whether money
is collected.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

import httpx

from services.api.config import get_settings
from services.domain.errors import ConflictError


class RazorpayProviderError(RuntimeError):
    """A definite provider-side failure or malformed response."""


class RazorpayProviderRetryable(RazorpayProviderError):
    """A provider failure that may be retried without changing the approved intent."""


@dataclass(frozen=True, slots=True)
class RazorpayProvider:
    key_id: str
    key_secret: str
    api_base_url: str
    account_id: str
    environment: str = "test"
    timeout_seconds: float = 20.0

    @classmethod
    def from_settings(cls) -> RazorpayProvider:
        settings = get_settings()
        if str(settings.razorpay_environment).strip().lower() != "test":
            raise ConflictError("Only Razorpay Test Mode is enabled")
        key_id = str(settings.razorpay_key_id or "").strip()
        key_secret = str(settings.razorpay_key_secret or "").strip()
        if not key_id or not key_secret:
            raise ConflictError("Razorpay Test Mode credentials are not configured")
        account_id = str(settings.razorpay_account_id or "").strip()
        if not account_id:
            raise ConflictError("Razorpay Test Mode account identity is not configured")
        return cls(
            key_id=key_id,
            key_secret=key_secret,
            api_base_url=str(settings.razorpay_api_base_url).rstrip("/"),
            account_id=account_id,
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, object]:
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["Accept"] = "application/json"
        headers["Content-Type"] = "application/json"
        headers["X-Razorpay-Account"] = self.account_id
        try:
            response = httpx.request(
                method,
                f"{self.api_base_url}/{path.lstrip('/')}",
                auth=(self.key_id, self.key_secret),
                headers=headers,
                timeout=self.timeout_seconds,
                **kwargs,
            )
        except httpx.RequestError as exc:
            raise RazorpayProviderRetryable("razorpay_request_failed") from exc
        if response.status_code == 429 or response.status_code >= 500:
            raise RazorpayProviderRetryable(f"razorpay_http_{response.status_code}")
        if response.status_code >= 400:
            raise RazorpayProviderError(f"razorpay_http_{response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise RazorpayProviderError("razorpay_invalid_json") from exc
        if not isinstance(payload, dict):
            raise RazorpayProviderError("razorpay_invalid_object")
        return {str(key): value for key, value in payload.items()}

    def create_payment_link(self, payload: dict[str, object]) -> dict[str, object]:
        return self._request("POST", "/payment_links", json=payload)

    def fetch_payment_link(self, provider_link_id: str) -> dict[str, object]:
        return self._request("GET", f"/payment_links/{provider_link_id}")

    def list_payment_links(self, *, reference_id: str) -> list[dict[str, object]]:
        payload = self._request("GET", "/payment_links", params={"reference_id": reference_id})
        items = payload.get("items", [])
        return [dict(item) for item in items if isinstance(item, dict)] if isinstance(items, list) else []

    def cancel_payment_link(self, provider_link_id: str) -> dict[str, object]:
        return self._request("POST", f"/payment_links/{provider_link_id}/cancel")

    def fetch_payment(self, provider_payment_id: str) -> dict[str, object]:
        return self._request("GET", f"/payments/{provider_payment_id}")

    def verify_webhook_signature(self, raw_body: bytes, signature: str) -> bool:
        secret = str(get_settings().razorpay_webhook_secret or "").strip()
        if not secret or not signature:
            return False
        expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature.strip())