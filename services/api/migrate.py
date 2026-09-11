"""Lambda entrypoint for running database migrations inside the VPC."""

from __future__ import annotations

from typing import Any

from alembic import command
from alembic.config import Config

from services.api.config import get_settings


def handler(event: dict[str, Any], context: Any) -> dict[str, str]:
    """Upgrade the staging database to the latest migration revision."""
    del event, context

    config = Config("/var/task/alembic.ini")
    # Alembic's ConfigParser treats percent signs as interpolation markers.
    config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))
    command.upgrade(config, "head")
    return {"status": "migrated", "revision": "head"}