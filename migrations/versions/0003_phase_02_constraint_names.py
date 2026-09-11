"""Normalize legacy Phase 01 constraint names for schema drift-free checks."""

from pathlib import Path

from alembic import op

revision = "0003_phase_02_constraint_names"
down_revision = "0002_phase_02"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).parents[1] / "sql" / name).read_text(encoding="utf-8")


def upgrade() -> None:
    op.execute(_sql("0003_phase_02_constraint_names_up.sql"))


def downgrade() -> None:
    op.execute(_sql("0003_phase_02_constraint_names_down.sql"))