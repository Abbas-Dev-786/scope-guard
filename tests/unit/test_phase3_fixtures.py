from __future__ import annotations

import json
from pathlib import Path


def test_acme_fixture_pack_is_self_consistent() -> None:
    root = Path(__file__).parents[2] / "fixtures" / "acme-demo"
    source = (root / "sow.md").read_text()
    expected = json.loads((root / "expected_scope.json").read_text())
    requests = json.loads((root / "requests.json").read_text())
    assert expected["source_version"] == "sow-v1"
    assert len(expected["items"]) >= 5
    assert all(item["text"] in source for item in expected["items"])
    assert {item["request_key"] for item in requests} == {"REQ-001", "REQ-002"}
    for variant in (root / "variants").glob("*.json"):
        assert json.loads(variant.read_text())["description"]