"""Add Phase 4 decisions, immutable drafts and evaluation reports."""
from pathlib import Path

from alembic import op

revision = "0009_phase4_decisions_evaluation"
down_revision = "0008_phase4_analysis_context"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).parents[1] / "sql" / name).read_text(encoding="utf-8")


def upgrade() -> None:
    op.execute(_sql("0009_phase4_decisions_evaluation_up.sql"))


def downgrade() -> None:
    op.execute(_sql("0009_phase4_decisions_evaluation_down.sql"))