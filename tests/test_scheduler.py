from __future__ import annotations

from datetime import date, datetime

from app.scheduler import DueJob, due_jobs, due_nightly, due_weekly
from app.timeutils import NEPAL_TZ

FRIDAY = date(2026, 10, 23)
SATURDAY = date(2026, 10, 24)


def npt(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=NEPAL_TZ)


def test_nightly_window_boundaries() -> None:
    assert due_nightly(npt(FRIDAY, 20, 59)) is None
    assert due_nightly(npt(FRIDAY, 21, 0)) == FRIDAY
    assert due_nightly(npt(FRIDAY, 22, 59)) == FRIDAY
    assert due_nightly(npt(FRIDAY, 23, 0)) is None


def test_weekly_window_is_saturday_only() -> None:
    assert due_weekly(npt(SATURDAY, 5, 59)) is None
    assert due_weekly(npt(SATURDAY, 6, 0)) == SATURDAY
    assert due_weekly(npt(SATURDAY, 11, 59)) == SATURDAY
    assert due_weekly(npt(SATURDAY, 12, 0)) is None
    assert due_weekly(npt(FRIDAY, 7, 0)) is None


def test_due_jobs_returns_nightly_on_friday() -> None:
    assert due_jobs(npt(FRIDAY, 21, 30)) == (DueJob(kind="nightly", local_date=FRIDAY),)


def test_due_jobs_returns_weekly_on_saturday_morning() -> None:
    assert due_jobs(npt(SATURDAY, 7, 0)) == (DueJob(kind="weekly", local_date=SATURDAY),)


def test_due_jobs_returns_nightly_on_saturday_evening() -> None:
    assert due_jobs(npt(SATURDAY, 21, 30)) == (DueJob(kind="nightly", local_date=SATURDAY),)
