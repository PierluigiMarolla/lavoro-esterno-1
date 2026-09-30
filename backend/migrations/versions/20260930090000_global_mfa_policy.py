"""Add the application-wide, opt-in MFA policy.

Revision ID: 20260930090000
Revises: 20260925090000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260930090000"
down_revision: str | None = "20260925090000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "application_security_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("mfa_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mfa_required_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("id = 1", name="ck_application_security_settings_singleton"),
    )
    op.execute(
        "INSERT INTO application_security_settings "
        "(id, mfa_required, revision) VALUES (1, false, 1)"
    )


def downgrade() -> None:
    op.drop_table("application_security_settings")
