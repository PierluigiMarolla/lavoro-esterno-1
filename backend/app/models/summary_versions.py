"""Modello `SummaryVersion`: versione di un riepilogo generato (da AI o da
template placeholder) per un Record. Versionato perché il riepilogo può
essere rigenerato quando arrivano nuovi annunci/fonti."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin, utcnow


class SummaryVersion(UUIDPKMixin, Base):
    __tablename__ = "summary_versions"

    record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    # Struttura attesa (vedi app/services/summary_generator.py e
    # app/schemas/records.py per lo schema Pydantic corrispondente):
    # {
    #   "summary": str,
    #   "advertisement_information": [...],
    #   "forum_information": [...],
    #   "unverified_claims": [...],
    #   "sources": [...],
    # }
    summary_json: Mapped[dict] = mapped_column(JSONB, nullable=False)

    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
