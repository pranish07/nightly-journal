from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Literal

JobKind = Literal["nightly", "weekly"]

NIGHTLY_START = time(21, 0)
NIGHTLY_CUTOFF = time(23, 0)
WEEKLY_START = time(6, 0)
WEEKLY_CUTOFF = time(12, 0)


@dataclass(frozen=True, slots=True)
class DueJob:
    kind: JobKind
    local_date: date


def _clock_time(local_dt: datetime) -> time:
    return local_dt.time().replace(tzinfo=None)


def due_nightly(local_dt: datetime) -> date | None:
    current = _clock_time(local_dt)
    if NIGHTLY_START <= current < NIGHTLY_CUTOFF:
        return local_dt.date()
    return None


def due_weekly(local_dt: datetime) -> date | None:
    current = _clock_time(local_dt)
    if local_dt.weekday() == 5 and WEEKLY_START <= current < WEEKLY_CUTOFF:
        return local_dt.date()
    return None


def due_jobs(local_dt: datetime) -> tuple[DueJob, ...]:
    jobs: list[DueJob] = []
    nightly = due_nightly(local_dt)
    if nightly is not None:
        jobs.append(DueJob(kind="nightly", local_date=nightly))
    weekly = due_weekly(local_dt)
    if weekly is not None:
        jobs.append(DueJob(kind="weekly", local_date=weekly))
    return tuple(jobs)
