from __future__ import annotations

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

NEPAL_TZ = ZoneInfo("Asia/Kathmandu")


def utc_now() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""

    return datetime.now(UTC)


def to_nepal(value: datetime) -> datetime:
    """Convert an aware datetime to Asia/Kathmandu."""

    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(NEPAL_TZ)


def local_now(now: datetime | None = None) -> datetime:
    """Return Nepal local time for an injected UTC clock value."""

    return to_nepal(now or utc_now())


def local_date(now: datetime | None = None) -> date:
    return local_now(now).date()


def minutes_after_18(value: time) -> int:
    """Minutes after 18:00, wrapping at midnight.

    Used by the wake/bed chart so evening and early-morning values form one
    continuous anchored axis instead of jumping at midnight.
    """

    return (value.hour * 60 + value.minute - 18 * 60) % (24 * 60)


def sleep_duration_minutes(bedtime: time, wake: time) -> int:
    """Sleep duration in minutes: (wake - bed) mod 24h."""

    bedtime_minutes = bedtime.hour * 60 + bedtime.minute
    wake_minutes = wake.hour * 60 + wake.minute
    return (wake_minutes - bedtime_minutes) % (24 * 60)
