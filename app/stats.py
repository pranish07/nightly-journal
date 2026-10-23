from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, time, timedelta
from statistics import fmean

from app.streaks import DayRecord, DayStatus, status_for
from app.timeutils import sleep_duration_minutes

DAY = timedelta(days=1)


@dataclass(frozen=True, slots=True)
class DayMetrics:
    """One day's raw values, independent of SQLAlchemy models."""

    local_date: date
    logged: bool
    no_goals: bool
    goals_total: int
    goals_done: int
    mood: int | None = None
    screen_minutes: int | None = None
    wake_time: time | None = None
    bedtime_time: time | None = None

    def __post_init__(self) -> None:
        DayRecord(
            local_date=self.local_date,
            logged=self.logged,
            no_goals=self.no_goals,
            goals_total=self.goals_total,
            goals_done=self.goals_done,
        )
        if self.mood is not None and not 1 <= self.mood <= 5:
            raise ValueError("mood must be between 1 and 5")
        if self.screen_minutes is not None and not 0 <= self.screen_minutes <= 1440:
            raise ValueError("screen_minutes must be between 0 and 1440")
        if (self.wake_time is None) != (self.bedtime_time is None):
            raise ValueError("wake_time and bedtime_time must be provided together")
        if self.logged:
            missing = [
                name
                for name, value in (
                    ("mood", self.mood),
                    ("screen_minutes", self.screen_minutes),
                    ("wake_time", self.wake_time),
                    ("bedtime_time", self.bedtime_time),
                )
                if value is None
            ]
            if missing:
                raise ValueError(f"logged day is missing: {', '.join(missing)}")
        elif any(
            value is not None
            for value in (
                self.mood,
                self.screen_minutes,
                self.wake_time,
                self.bedtime_time,
            )
        ):
            raise ValueError("an unlogged day cannot carry metrics")

    @property
    def record(self) -> DayRecord:
        return DayRecord(
            local_date=self.local_date,
            logged=self.logged,
            no_goals=self.no_goals,
            goals_total=self.goals_total,
            goals_done=self.goals_done,
        )


@dataclass(frozen=True, slots=True)
class DailyStats:
    local_date: date
    logged: bool
    status: DayStatus
    goals_total: int
    goals_done: int
    completion_ratio: float
    mood: int | None
    screen_minutes: int | None
    wake_time: time | None
    bedtime_time: time | None
    sleep_minutes: int | None

    @property
    def completion_percent(self) -> float:
        return round(self.completion_ratio * 100, 1)


@dataclass(frozen=True, slots=True)
class RangeStats:
    start: date
    end: date
    days: tuple[DailyStats, ...]
    logged_days: int
    no_goals_days: int
    goal_days: int
    goals_total: int
    goals_done: int
    completion_ratio: float
    avg_mood: float | None
    avg_screen_minutes: float | None
    avg_sleep_minutes: float | None


def _mean(values: Iterable[int]) -> float | None:
    materialized = list(values)
    if not materialized:
        return None
    return round(fmean(materialized), 1)


def daily_stats(
    metrics: Iterable[DayMetrics],
    *,
    start: date,
    end: date,
    threshold: float = 1.0,
) -> tuple[DailyStats, ...]:
    """Return one gap-filled DailyStats per date in the inclusive range."""

    if end < start:
        raise ValueError("end must be on or after start")
    by_date: dict[date, DayMetrics] = {}
    for item in metrics:
        if item.local_date in by_date:
            raise ValueError(f"duplicate day metrics for {item.local_date}")
        by_date[item.local_date] = item

    result: list[DailyStats] = []
    day = start
    while day <= end:
        item = by_date.get(day)
        if item is None:
            result.append(
                DailyStats(
                    local_date=day,
                    logged=False,
                    status=DayStatus.NOT_LOGGED,
                    goals_total=0,
                    goals_done=0,
                    completion_ratio=0.0,
                    mood=None,
                    screen_minutes=None,
                    wake_time=None,
                    bedtime_time=None,
                    sleep_minutes=None,
                )
            )
        else:
            record = item.record
            status = status_for(record, threshold)
            sleep_minutes = (
                sleep_duration_minutes(item.bedtime_time, item.wake_time)
                if item.bedtime_time is not None and item.wake_time is not None
                else None
            )
            result.append(
                DailyStats(
                    local_date=day,
                    logged=item.logged,
                    status=status,
                    goals_total=item.goals_total,
                    goals_done=item.goals_done,
                    completion_ratio=record.completion_ratio,
                    mood=item.mood,
                    screen_minutes=item.screen_minutes,
                    wake_time=item.wake_time,
                    bedtime_time=item.bedtime_time,
                    sleep_minutes=sleep_minutes,
                )
            )
        day += DAY
    return tuple(result)


def summarize(days: Iterable[DailyStats]) -> RangeStats:
    materialized = tuple(days)
    if not materialized:
        raise ValueError("at least one day is required")
    logged = [item for item in materialized if item.logged]
    goals_total = sum(item.goals_total for item in materialized)
    goals_done = sum(item.goals_done for item in materialized)
    completion_ratio = goals_done / goals_total if goals_total else 0.0
    return RangeStats(
        start=materialized[0].local_date,
        end=materialized[-1].local_date,
        days=materialized,
        logged_days=len(logged),
        no_goals_days=sum(1 for item in materialized if item.status is DayStatus.NO_GOALS),
        goal_days=sum(1 for item in materialized if item.goals_total > 0),
        goals_total=goals_total,
        goals_done=goals_done,
        completion_ratio=completion_ratio,
        avg_mood=_mean(item.mood for item in logged if item.mood is not None),
        avg_screen_minutes=_mean(
            item.screen_minutes for item in logged if item.screen_minutes is not None
        ),
        avg_sleep_minutes=_mean(
            item.sleep_minutes for item in logged if item.sleep_minutes is not None
        ),
    )


def range_stats(
    metrics: Iterable[DayMetrics],
    *,
    start: date,
    end: date,
    threshold: float = 1.0,
) -> RangeStats:
    return summarize(daily_stats(metrics, start=start, end=end, threshold=threshold))
