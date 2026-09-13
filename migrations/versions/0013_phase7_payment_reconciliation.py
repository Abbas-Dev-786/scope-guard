"""Add Phase 7 provider identity and observation association state."""
from pathlib import Path

from alembic import op

revision = "0013_payment_reconcile"
down_revision = "0012_phase7_payments"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).parents[1] / "sql" / name).read_text(encoding="utf-8")


def upgrade() -> None:
    op.execute(_sql("0013_phase7_payment_reconciliation_up.sql"))


def downgrade() -> None:
    op.execute(_sql("0013_phase7_payment_reconciliation_down.sql"))