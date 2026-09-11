import pytest

from services.connectors.policy import require_capability
from services.domain.errors import AuthorizationError


def test_read_and_deterministic_capabilities_are_separate() -> None:
    require_capability("gmail", "messages.get", actor="reader")
    require_capability("gmail", "messages.send", actor="deterministic")
    with pytest.raises(AuthorizationError):
        require_capability("gmail", "messages.send", actor="agent")
    with pytest.raises(AuthorizationError):
        require_capability("github", "update_issue", actor="agent")
