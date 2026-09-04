"""Modello `ScrapeRun`: esecuzione di uno scraping per una fonte."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin, utcnow

ScrapeRunStatus = sa.Enum(
    "running", "completed", "failed", name="scrape_run_status", create_type=True
)


class ScrapeRun(UUIDPKMixin, Base):
    __tablename__ = "scrape_runs"
    __table_args__ = (Index("ix_scrape_runs_started_at", "started_at"),)

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[str] = mapped_column(ScrapeRunStatus, default="running", nullable=False)
    items_found: Mapped[int] = mapped_column(Integer, default=0)
    items_new: Mapped[int] = mapped_column(Integer, default=0)
    errors_count: Mapped[int] = mapped_column(Integer, default=0)
