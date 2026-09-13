"""Add Phase 7 payment links, attempts, and observations."""
from pathlib import Path

from alembic import op

revision = "0012_phase7_payments"
down_revision = "0011_phase6_gmail_sync"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).parents[1] / "sql" / name).read_text(encoding="utf-8")


def upgrade() -> None:
    op.execute(_sql("0012_phase7_payments_up.sql"))


def downgrade() -> None:
    op.execute(_sql("0012_phase7_payments_down.sql"))