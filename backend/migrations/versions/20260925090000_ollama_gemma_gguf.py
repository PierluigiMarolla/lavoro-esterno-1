"""Use the quantized Italian Gemma GGUF as the Ollama default.

Revision ID: 20260925090000
Revises: 20260923150000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260925090000"
down_revision: str | None = "20260923150000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_MODEL = "gemma4:e2b"
NEW_MODEL = "hf.co/unsloth/gemma-4-E2B-it-GGUF:UD-Q4_K_XL"


def upgrade() -> None:
    # Preserve administrators' custom Ollama choices: only migrate the old
    # project default and bump the revision used to invalidate queued jobs.
    op.execute(
        "UPDATE ai_provider_configs "
        f"SET model_name='{NEW_MODEL}', revision=revision+1, updated_at=now() "
        f"WHERE provider='ollama' AND model_name='{OLD_MODEL}'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE ai_provider_configs "
        f"SET model_name='{OLD_MODEL}', revision=revision+1, updated_at=now() "
        f"WHERE provider='ollama' AND model_name='{NEW_MODEL}'"
    )
