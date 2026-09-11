"""Add Phase 4 analysis context, agent runs and durable budgets."""
from pathlib import Path

from alembic import op

revision = "0008_phase4_analysis_context"
down_revision = "0007_phase3_event_identity"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).parents[1] / "sql" / name).read_text(encoding="utf-8")


def upgrade() -> None:
    op.execute(_sql("0008_phase4_analysis_context_up.sql"))


def downgrade() -> None:
    op.execute(_sql("0008_phase4_analysis_context_down.sql"))