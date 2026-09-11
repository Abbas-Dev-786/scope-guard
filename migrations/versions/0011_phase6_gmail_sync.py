"""Add Phase 6 Gmail integration and mailbox synchronization persistence."""
from pathlib import Path

from alembic import op

revision = "0011_phase6_gmail_sync"
down_revision = "0010_phase5_approvals"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).parents[1] / "sql" / name).read_text(encoding="utf-8")


def upgrade() -> None:
    op.execute(_sql("0011_phase6_gmail_sync_up.sql"))


def downgrade() -> None:
    op.execute(_sql("0011_phase6_gmail_sync_down.sql"))
