"""Persist original external resource identity for replay and explicit assignment."""
from pathlib import Path

from alembic import op

revision = "0007_phase3_event_identity"
down_revision = "0006_phase3_contracts"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).parents[1] / "sql" / name).read_text(encoding="utf-8")


def upgrade() -> None:
    op.execute(_sql("0007_phase3_event_identity_up.sql"))


def downgrade() -> None:
    op.execute(_sql("0007_phase3_event_identity_down.sql"))
