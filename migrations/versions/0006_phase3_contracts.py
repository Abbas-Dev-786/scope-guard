"""Add Phase 3 contract, scope, evidence and routing records."""
from pathlib import Path

from alembic import op

revision = "0006_phase3_contracts"
down_revision = "0005_phase2_capacity_corr"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).parents[1] / "sql" / name).read_text(encoding="utf-8")


def upgrade() -> None:
    op.execute(_sql("0006_phase3_contracts_up.sql"))


def downgrade() -> None:
    op.execute(_sql("0006_phase3_contracts_down.sql"))
