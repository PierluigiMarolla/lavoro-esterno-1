"""Modello `Source`: una fonte/sito da cui vengono raccolti annunci."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin

SourcePriority = sa.Enum("high", "medium", "low", name="source_priority", create_type=True)
SourceStatus = sa.Enum("healthy", "degraded", "offline", name="source_status", create_type=True)


class Source(UUIDPKMixin, TimestampMixin, Base):
    """Fonte configurata (es. un sito di annunci). Lo `slug` collega la riga
    DB al connettore scraper concreto registrato in `app/scrapers/registry.py`.
    """

    __tablename__ = "sources"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)

    # Priorità usata come tie-break nella selezione dell'annuncio canonico
    # (vedi app/services/canonical.py): a parità di altri criteri, vince la
    # fonte con priorità più alta.
    priority: Mapped[str] = mapped_column(SourcePriority, default="medium", nullable=False)
    status: Mapped[str] = mapped_column(SourceStatus, default="healthy", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
