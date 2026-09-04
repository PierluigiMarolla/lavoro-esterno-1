"""Validation shared by the time-filtered dashboard endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Query, status

DEFAULT_DASHBOARD_RANGE = timedelta(hours=24)
MAX_DASHBOARD_RANGE = timedelta(days=90)


@dataclass(frozen=True)
class DashboardRange:
    start: datetime
    end: datetime

    @property
    def duration(self) -> timedelta:
        return self.end - self.start

    @property
    def previous_start(self) -> datetime:
        return self.start - self.duration


def resolve_dashboard_range(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
) -> DashboardRange:
    """Return a bounded, timezone-aware UTC interval, defaulting to 24 hours."""
    now = datetime.now(UTC)
    if start is None and end is None:
        return DashboardRange(start=now - DEFAULT_DASHBOARD_RANGE, end=now)
    if start is None or end is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Both start and end are required",
        )
    if start.tzinfo is None or end.tzinfo is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Dashboard timestamps must include a timezone offset",
        )

    start_utc = start.astimezone(UTC)
    end_utc = end.astimezone(UTC)
    if start_utc >= end_utc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Dashboard start must be earlier than end",
        )
    if end_utc > now:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Dashboard end cannot be in the future",
        )
    if end_utc - start_utc > MAX_DASHBOARD_RANGE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Dashboard range cannot exceed 90 days",
        )
    return DashboardRange(start=start_utc, end=end_utc)
