from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest

from app.timeutils import local_date, local_now, minutes_after_18, sleep_duration_minutes


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (time(18, 0), 0),
        (time(18, 1), 1),
        (time(23, 30), 330),
        (time(0, 0), 360),
        (time(5, 59), 719),
        (time(17, 59), 1439),
    ],
)
def test_minutes_after_18_wraps_at_midnight(value: time, expected: int) -> None:
    assert minutes_after_18(value) == expected


@pytest.mark.parametrize(
    ("bedtime", "wake", "expected"),
    [
        (time(23, 30), time(6, 30), 420),
        (time(1, 0), time(8, 0), 420),
        (time(22, 0), time(6, 0), 480),
        (time(0, 0), time(0, 0), 0),
        (time(6, 0), time(6, 0), 0),
        (time(23, 0), time(22, 0), 1380),
    ],
)
def test_sleep_duration_uses_24_hour_wrap(bedtime: time, wake: time, expected: int) -> None:
    assert sleep_duration_minutes(bedtime, wake) == expected


def test_local_time_and_date_use_nepal_offset() -> None:
    now = datetime(2026, 10, 23, 18, 30, tzinfo=UTC)
    assert local_now(now).isoformat() == "2026-10-24T00:15:00+05:45"
    assert local_date(now) == date(2026, 10, 24)


def test_local_now_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        local_now(datetime(2026, 10, 23, 18, 30))
