"""Phase 01 tenant, commercial, client and project foundation."""

from pathlib import Path

from alembic import op

revision = "0001_phase_01"
down_revision = None
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).parents[1] / "sql" / name).read_text(encoding="utf-8")


def upgrade() -> None:
    op.execute(_sql("0001_phase_01_up.sql"))


def downgrade() -> None:
    op.execute(_sql("0001_phase_01_down.sql"))
