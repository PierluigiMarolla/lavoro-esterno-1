"""Reusable proxy pools and safe operational history for scraper runs."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class ProxyPool(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "proxy_pools"

    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ProxyEndpoint(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "proxy_endpoints"

    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    scheme: Mapped[str] = mapped_column(String(10), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    credentials_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProxyPoolMember(Base):
    __tablename__ = "proxy_pool_members"

    pool_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("proxy_pools.id", ondelete="CASCADE"), primary_key=True
    )
    proxy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("proxy_endpoints.id", ondelete="RESTRICT"), primary_key=True
    )


class ScrapeRunProxyAttempt(UUIDPKMixin, Base):
    __tablename__ = "scrape_run_proxy_attempts"
    __table_args__ = (
        UniqueConstraint("scrape_run_id", "attempt_number", name="uq_proxy_attempt_run_number"),
    )

    scrape_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scrape_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    proxy_endpoint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("proxy_endpoints.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    operation: Mapped[str] = mapped_column(String(30), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_category: Mapped[str | None] = mapped_column(String(40), nullable=True)
