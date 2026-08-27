"""Modello `Media`: file (immagine/video) collegato a un annuncio."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin, utcnow

MediaClassification = sa.Enum(
    "explicit", "safe", "unclassified", name="media_classification", create_type=True
)


class Media(UUIDPKMixin, Base):
    """File media associato a un `Advertisement`, con relativa classificazione."""

    __tablename__ = "media"

    advertisement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("advertisements.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Chiave oggetto in MinIO/S3 per il file originale così come scaricato.
    original_object_key: Mapped[str] = mapped_column(Text, nullable=False)
    # Chiave oggetto per una eventuale variante derivata (es. thumbnail, versione
    # "safe" con blur, transcodifica video via FFmpeg). Nullable finché non generata.
    derived_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)

    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Perceptual hash (pHash) per il rilevamento di duplicati "quasi identici"
    # (stesso soggetto, ricompressione/resize diversi). Nullable per i video o
    # finché non calcolato in background.
    perceptual_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)

    classification: Mapped[str] = mapped_column(
        MediaClassification, default="unclassified", nullable=False
    )
    classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    classifier_version: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
