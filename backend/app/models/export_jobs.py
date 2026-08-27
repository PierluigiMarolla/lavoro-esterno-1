"""Modello `ExportJob`: richiesta asincrona di esportazione (testo, media
completi, o solo media "safe"), eseguita da un worker Celery dedicato."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin, utcnow

ExportType = sa.Enum(
    "text_only", "complete_media", "safe_complete", name="export_type", create_type=True
)
ExportStatus = sa.Enum(
    "pending", "processing", "ready", "failed", name="export_status", create_type=True
)


class ExportJob(UUIDPKMixin, Base):
    __tablename__ = "export_jobs"

    # Nullable: un export può riguardare un singolo record oppure essere bulk
    # (es. tutti i record che soddisfano un certo filtro), nel qual caso il
    # dettaglio è nel manifest_json piuttosto che in una FK singola.
    record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("records.id", ondelete="CASCADE"), nullable=True, index=True
    )

    type: Mapped[str] = mapped_column(ExportType, nullable=False)
    status: Mapped[str] = mapped_column(ExportStatus, default="pending", nullable=False)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    manifest_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
