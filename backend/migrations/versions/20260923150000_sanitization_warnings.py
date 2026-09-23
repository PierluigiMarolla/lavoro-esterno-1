"""Avvisi non bloccanti per la sanitizzazione dei contenuti.

Revision ID: 20260923150000
Revises: 20260923120000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260923150000"
down_revision: str | None = "20260923120000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scrape_runs",
        sa.Column("warnings_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "scrape_errors",
        sa.Column("severity", sa.String(length=10), nullable=False, server_default="error"),
    )
    op.create_check_constraint(
        "ck_scrape_errors_severity",
        "scrape_errors",
        "severity IN ('warning', 'error')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_scrape_errors_severity", "scrape_errors", type_="check")
    op.drop_column("scrape_errors", "severity")
    op.drop_column("scrape_runs", "warnings_count")
