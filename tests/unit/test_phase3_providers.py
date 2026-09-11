from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from services.contracts.storage import ObjectStoreVerificationError, fetch_private_object
from services.contracts.structure import (
    BedrockStructureProvider,
    StructureProviderUnavailable,
    extract_scope_candidates,
)


def test_structure_provider_validates_fake_provider_output() -> None:
    chunk_id = uuid4()
    chunk = SimpleNamespace(id=chunk_id, start_offset=0, end_offset=8, source_text="Included")

    class FixtureProvider:
        extractor_version = "fixture:scope-structure-v1"

        def extract(self, chunks: list[object]) -> list[dict[str, object]]:
            assert chunks == [chunk]
            return [{"item_key": "included", "item_type": "INCLUDED", "text": "Included", "source_chunk_id": chunk_id, "start_offset": 0, "end_offset": 8}]

    result = extract_scope_candidates(FixtureProvider(), [chunk])
    assert result.status == "READY"
    assert result.reason == "fixture:scope-structure-v1"
    assert result.candidates[0].item_key == "included"


def test_structure_provider_unavailable_is_pending() -> None:
    class UnavailableProvider:
        extractor_version = "fixture:unavailable"

        def extract(self, chunks: list[object]) -> list[dict[str, object]]:
            raise StructureProviderUnavailable("model access is not configured")

    result = extract_scope_candidates(UnavailableProvider(), [])
    assert result.status == "PENDING"
    assert result.reason == "model access is not configured"


def test_bedrock_provider_requires_verified_model_id() -> None:
    with pytest.raises(StructureProviderUnavailable, match="verified Bedrock model ID"):
        BedrockStructureProvider(model_id="replace-after-readiness-verification", region_name="us-east-1")


def test_private_object_fetch_verifies_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    import services.contracts.storage as storage

    class Body:
        def read(self, limit: int) -> bytes:
            assert limit == 6
            return b"hello"

    class Client:
        def head_object(self, **kwargs: object) -> dict[str, object]:
            return {"ContentLength": 5, "ContentType": "text/plain", "Metadata": {"sha256": "abc"}}

        def get_object(self, **kwargs: object) -> dict[str, object]:
            return {"Body": Body(), "ContentType": "text/plain"}

    monkeypatch.setattr(storage, "get_settings", lambda: SimpleNamespace(contract_object_bucket="private", aws_region="us-east-1"))
    monkeypatch.setattr(storage, "_client", lambda: Client())
    assert fetch_private_object(object_key="contracts/a.txt", expected_size_bytes=5, expected_mime_type="text/plain", expected_sha256="abc") == b"hello"

    with pytest.raises(ObjectStoreVerificationError, match="size"):
        fetch_private_object(object_key="contracts/a.txt", expected_size_bytes=4, expected_mime_type="text/plain")