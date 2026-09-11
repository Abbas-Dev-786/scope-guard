from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from services.api import database


def _session_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[MagicMock, Generator[Session, None, None]]:
    session = MagicMock()
    context = MagicMock()
    context.__enter__.return_value = session
    context.__exit__.return_value = False
    monkeypatch.setattr(database, "SessionLocal", lambda: context)
    return session, database.get_session()


def test_get_session_commits_after_success(monkeypatch: pytest.MonkeyPatch) -> None:
    session, dependency = _session_dependency(monkeypatch)

    assert next(dependency) is session
    with pytest.raises(StopIteration):
        next(dependency)

    session.commit.assert_called_once_with()
    session.rollback.assert_not_called()


def test_get_session_rolls_back_after_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    session, dependency = _session_dependency(monkeypatch)

    assert next(dependency) is session
    with pytest.raises(RuntimeError, match="request failed"):
        dependency.throw(RuntimeError("request failed"))

    session.rollback.assert_called_once_with()
    session.commit.assert_not_called()