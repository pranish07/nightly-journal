from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

DAY = timedelta(days=1)


class DayStatus(StrEnum):
    ACHIEVED = "achieved"
    PARTIAL = "partial"
    MISSED = "missed"
    NO_GOALS = "no_goals"
    NOT_LOGGED = "not_logged"


@dataclass(frozen=True, slots=True)
class DayRecord:
    """One local day's scoring inputs.

    Missing days are represented by ``logged=False`` and zero goals.
    """

    local_date: date
    logged: bool
    no_goals: bool
    goals_total: int
    goals_done: int

    def __post_init__(self) -> None:
        if self.goals_total < 0:
            raise ValueError("goals_total must be >= 0")
        if self.goals_done < 0:
            raise ValueError("goals_done must be >= 0")
        if self.goals_done > self.goals_total:
            raise ValueError("goals_done cannot exceed goals_total")
        if not self.logged:
            if self.no_goals or self.goals_total or self.goals_done:
                raise ValueError("an unlogged day cannot carry goals")
            return
        if self.no_goals:
            if self.goals_total or self.goals_done:
                raise ValueError("a no-goals day cannot carry goals")
            return
        if self.goals_total == 0:
            raise ValueError("a logged day needs goals or the no-goals toggle")

    @property
    def completion_ratio(self) -> float:
        if self.goals_total == 0:
            return 0.0
        return self.goals_done / self.goals_total


@dataclass(frozen=True, slots=True)
class StreakStats:
    current_goal: int
    longest_goal: int
    current_logging: int
    longest_logging: int


def _validate_threshold(threshold: float) -> None:
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0.0 and 1.0")


def status_for(record: DayRecord, threshold: float = 1.0) -> DayStatus:
    """Classify one day. MISSED takes precedence over a zero threshold."""

    _validate_threshold(threshold)
    if not record.logged:
        return DayStatus.NOT_LOGGED
    if record.no_goals:
        return DayStatus.NO_GOALS
    if record.goals_done == 0:
        return DayStatus.MISSED
    if record.completion_ratio >= threshold:
        return DayStatus.ACHIEVED
    return DayStatus.PARTIAL


def _records_by_date(records: Iterable[DayRecord]) -> dict[date, DayRecord]:
    by_date: dict[date, DayRecord] = {}
    for record in records:
        if record.local_date in by_date:
            raise ValueError(f"duplicate day record for {record.local_date}")
        by_date[record.local_date] = record
    return by_date


def _status_on(by_date: dict[date, DayRecord], day: date, threshold: float) -> DayStatus:
    record = by_date.get(day)
    if record is None:
        return DayStatus.NOT_LOGGED
    return status_for(record, threshold)


def compute_streaks(
    records: Iterable[DayRecord],
    *,
    as_of: date,
    threshold: float = 1.0,
) -> StreakStats:
    """Compute current and longest goal/logging streaks.

    Current streaks include a one-day grace when ``as_of`` has not been logged
    yet. This keeps the displayed streak stable during the current day and
    breaks it once a full day has definitively been missed.
    """

    _validate_threshold(threshold)
    by_date = _records_by_date(records)
    eligible = [day for day in by_date if day <= as_of]
    if not eligible:
        return StreakStats(0, 0, 0, 0)

    earliest = min(eligible)

    if as_of in by_date and by_date[as_of].logged:
        current_anchor = as_of
    else:
        current_anchor = as_of - DAY

    current_goal = 0
    day = current_anchor
    while day >= earliest:
        status = _status_on(by_date, day, threshold)
        if status is DayStatus.NO_GOALS:
            day -= DAY
            continue
        if status is DayStatus.ACHIEVED:
            current_goal += 1
            day -= DAY
            continue
        break

    current_logging = 0
    day = current_anchor
    while day >= earliest:
        record = by_date.get(day)
        if record is None or not record.logged:
            break
        current_logging += 1
        day -= DAY

    longest_goal = 0
    running_goal = 0
    day = earliest
    while day <= as_of:
        status = _status_on(by_date, day, threshold)
        if status is DayStatus.ACHIEVED:
            running_goal += 1
            longest_goal = max(longest_goal, running_goal)
        elif status is DayStatus.NO_GOALS:
            pass
        else:
            running_goal = 0
        day += DAY

    longest_logging = 0
    running_logging = 0
    day = earliest
    while day <= as_of:
        record = by_date.get(day)
        if record is not None and record.logged:
            running_logging += 1
            longest_logging = max(longest_logging, running_logging)
        else:
            running_logging = 0
        day += DAY

    return StreakStats(
        current_goal=current_goal,
        longest_goal=longest_goal,
        current_logging=current_logging,
        longest_logging=longest_logging,
    )


def statuses_for_range(
    records: Iterable[DayRecord],
    *,
    start: date,
    end: date,
    threshold: float = 1.0,
) -> list[tuple[date, DayStatus]]:
    """Return a contiguous, gap-filled status list for calendars/trends."""

    if end < start:
        raise ValueError("end must be on or after start")
    _validate_threshold(threshold)
    by_date = _records_by_date(records)
    result: list[tuple[date, DayStatus]] = []
    day = start
    while day <= end:
        result.append((day, _status_on(by_date, day, threshold)))
        day += DAY
    return result
