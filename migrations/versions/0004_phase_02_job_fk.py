"""Keep workflow job references tenant-safe during job retention."""

from pathlib import Path

from alembic import op

revision = "0004_phase_02_job_fk"
down_revision = "0003_phase_02_constraint_names"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).parents[1] / "sql" / name).read_text(encoding="utf-8")


def upgrade() -> None:
    op.execute(_sql("0004_phase_02_job_fk.sql"))


def downgrade() -> None:
    op.execute(_sql("0004_phase_02_job_fk_down.sql"))