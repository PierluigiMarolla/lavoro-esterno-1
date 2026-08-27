"""Modello `Advertisement`: un singolo annuncio scaricato da una fonte."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPKMixin, utcnow

if TYPE_CHECKING:
    from app.models.record import Record
    from app.models.sources import Source

AdvertisementStatus = sa.Enum(
    "active", "removed", "invalid", name="advertisement_status", create_type=True
)


class Advertisement(UUIDPKMixin, Base):
    """Annuncio raccolto da una fonte esterna, associato a un `Record`."""

    __tablename__ = "advertisements"

    record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # SHA-256 del contenuto normalizzato (title+description+...), usato dal
    # servizio di dedup per rilevare ri-pubblicazioni identiche senza dover
    # ricalcolare/confrontare il testo intero.
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Confidenza (0..1) che questo annuncio appartenga davvero al Record a cui è
    # associato (utile quando l'associazione deriva da euristiche di matching
    # più deboli del solo numero di telefono, es. testo/immagini simili).
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    status: Mapped[str] = mapped_column(AdvertisementStatus, default="active", nullable=False)

    record: Mapped[Record] = relationship(
        "Record", back_populates="advertisements", foreign_keys=[record_id]
    )
    source: Mapped[Source] = relationship("Source")
