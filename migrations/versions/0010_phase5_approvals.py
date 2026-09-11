"""Add Phase 5 approvals, client review and accepted payment intents."""
from pathlib import Path

from alembic import op

revision = "0010_phase5_approvals"
down_revision = "0009_phase4_decisions_evaluation"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).parents[1] / "sql" / name).read_text(encoding="utf-8")


def upgrade() -> None:
    op.execute(_sql("0010_phase5_approvals_up.sql"))


def downgrade() -> None:
    op.execute(_sql("0010_phase5_approvals_down.sql"))
