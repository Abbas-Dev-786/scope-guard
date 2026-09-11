"""Add durable analysis capacity reservations and job correlation identifiers."""

from pathlib import Path

from alembic import op

revision = "0005_phase2_capacity_corr"
down_revision = "0004_phase_02_job_fk"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).parents[1] / "sql" / name).read_text(encoding="utf-8")


def upgrade() -> None:
    op.execute(_sql("0005_phase_02_capacity_correlation.sql"))


def downgrade() -> None:
    op.execute(_sql("0005_phase_02_capacity_correlation_down.sql"))