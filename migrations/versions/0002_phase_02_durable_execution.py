"""Phase 02 durable execution, outbox and external-action foundation."""

from pathlib import Path

from alembic import op

revision = "0002_phase_02"
down_revision = "0001_phase_01"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).parents[1] / "sql" / name).read_text(encoding="utf-8")


def upgrade() -> None:
    op.execute(_sql("0002_phase_02_up.sql"))


def downgrade() -> None:
    op.execute(_sql("0002_phase_02_down.sql"))