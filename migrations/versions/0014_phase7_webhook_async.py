"""Persist Razorpay webhook ingress before asynchronous normalization."""

from pathlib import Path

from alembic import op

revision = "0014_payment_webhook_async"
down_revision = "0013_payment_reconcile"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).parents[1] / "sql" / name).read_text(encoding="utf-8")


def upgrade() -> None:
    op.execute(_sql("0014_phase7_webhook_async_up.sql"))


def downgrade() -> None:
    op.execute(_sql("0014_phase7_webhook_async_down.sql"))
