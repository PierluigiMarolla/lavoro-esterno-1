from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from app.services.dashboard_range import resolve_dashboard_range


def test_dashboard_range_defaults_to_last_24_hours() -> None:
    before = datetime.now(UTC)
    result = resolve_dashboard_range(None, None)
    after = datetime.now(UTC)

    assert before <= result.end <= after
    assert result.duration == timedelta(hours=24)


def test_dashboard_range_normalizes_explicit_offsets_to_utc() -> None:
    result = resolve_dashboard_range(
        datetime(2026, 1, 1, 1, tzinfo=ZoneInfo("Europe/Rome")),
        datetime(2026, 1, 2, 1, tzinfo=ZoneInfo("Europe/Rome")),
    )

    assert result.start == datetime(2026, 1, 1, tzinfo=UTC)
    assert result.end == datetime(2026, 1, 2, tzinfo=UTC)
    assert result.previous_start == datetime(2025, 12, 31, tzinfo=UTC)


def test_dashboard_range_handles_rome_dst_transition() -> None:
    rome = ZoneInfo("Europe/Rome")
    result = resolve_dashboard_range(
        datetime(2026, 3, 28, 12, tzinfo=rome),
        datetime(2026, 3, 29, 12, tzinfo=rome),
    )

    assert result.duration == timedelta(hours=23)


@pytest.mark.parametrize(
    ("start", "end", "message"),
    [
        (datetime(2026, 1, 1, tzinfo=UTC), None, "Both start and end"),
        (
            datetime(2026, 2, 1, tzinfo=UTC),
            datetime(2026, 1, 1, tzinfo=UTC),
            "start must be earlier",
        ),
        (
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2025, 5, 1, tzinfo=UTC),
            "cannot exceed 90 days",
        ),
    ],
)
def test_dashboard_range_rejects_invalid_intervals(
    start: datetime | None, end: datetime | None, message: str
) -> None:
    with pytest.raises(HTTPException, match=message) as exc:
        resolve_dashboard_range(start, end)
    assert exc.value.status_code == 422


def test_dashboard_range_rejects_naive_and_future_timestamps() -> None:
    with pytest.raises(HTTPException, match="timezone offset"):
        resolve_dashboard_range(datetime(2026, 1, 1), datetime(2026, 1, 2))

    now = datetime.now(UTC)
    with pytest.raises(HTTPException, match="cannot be in the future"):
        resolve_dashboard_range(now, now + timedelta(minutes=1))
