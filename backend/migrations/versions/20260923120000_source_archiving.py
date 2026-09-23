"""Archiviazione reversibile delle fonti.

Revision ID: 20260923120000
Revises: 20260917090000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260923120000"
down_revision: str | None = "20260917090000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sources", sa.Column("archived_by_user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_sources_archived_by_user_id",
        "sources",
        "users",
        ["archived_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_sources_archived_at", "sources", ["archived_at"])


def downgrade() -> None:
    op.drop_index("ix_sources_archived_at", table_name="sources")
    op.drop_constraint("fk_sources_archived_by_user_id", "sources", type_="foreignkey")
    op.drop_column("sources", "archived_by_user_id")
    op.drop_column("sources", "archived_at")
