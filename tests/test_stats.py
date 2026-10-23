from __future__ import annotations

from datetime import date, time, timedelta

import pytest

from app.stats import DayMetrics, daily_stats, range_stats, summarize
from app.streaks import DayStatus

START = date(2026, 10, 1)


def day(offset: int) -> date:
    return START + timedelta(days=offset)


def metrics(offset: int, **overrides: object) -> DayMetrics:
    values: dict[str, object] = {
        "local_date": day(offset),
        "logged": True,
        "no_goals": False,
        "goals_total": 2,
        "goals_done": 1,
        "mood": 4,
        "screen_minutes": 120,
        "wake_time": time(6, 30),
        "bedtime_time": time(23, 0),
    }
    values.update(overrides)
    return DayMetrics(**values)  # type: ignore[arg-type]


def missing(offset: int) -> DayMetrics:
    return DayMetrics(
        local_date=day(offset),
        logged=False,
        no_goals=False,
        goals_total=0,
        goals_done=0,
    )


def test_daily_stats_fills_gaps_and_computes_sleep() -> None:
    days = daily_stats(
        [metrics(0), metrics(2, goals_done=2)],
        start=day(0),
        end=day(2),
    )
    assert [item.status for item in days] == [
        DayStatus.PARTIAL,
        DayStatus.NOT_LOGGED,
        DayStatus.ACHIEVED,
    ]
    assert days[0].sleep_minutes == 450
    assert days[1].mood is None
    assert days[2].completion_percent == 100.0


def test_no_goals_day_is_neutral_and_logged() -> None:
    days = daily_stats(
        [
            metrics(
                0,
                no_goals=True,
                goals_total=0,
                goals_done=0,
            )
        ],
        start=day(0),
        end=day(0),
    )
    assert days[0].status is DayStatus.NO_GOALS
    assert days[0].logged is True
    assert days[0].completion_ratio == 0.0


def test_range_stats_aggregates_only_available_metrics() -> None:
    stats = range_stats(
        [
            metrics(0, mood=2, screen_minutes=60, goals_done=1),
            metrics(1, mood=4, screen_minutes=180, goals_done=0),
            metrics(2, mood=3, screen_minutes=120, goals_done=2, goals_total=2),
        ],
        start=day(0),
        end=day(3),
    )
    assert stats.logged_days == 3
    assert stats.goal_days == 3
    assert stats.goals_total == 6
    assert stats.goals_done == 3
    assert stats.completion_ratio == 0.5
    assert stats.avg_mood == 3.0
    assert stats.avg_screen_minutes == 120.0
    assert stats.avg_sleep_minutes == 450.0


def test_summarize_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="at least one"):
        summarize([])


def test_daily_stats_rejects_duplicates() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        daily_stats([metrics(0), metrics(0)], start=day(0), end=day(0))


def test_daily_stats_rejects_reversed_range() -> None:
    with pytest.raises(ValueError, match="end"):
        daily_stats([], start=day(2), end=day(1))


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"mood": 0}, "mood"),
        ({"mood": 6}, "mood"),
        ({"screen_minutes": -1}, "screen_minutes"),
        ({"screen_minutes": 1441}, "screen_minutes"),
        ({"wake_time": None}, "together"),
        ({"mood": None}, "missing"),
    ],
)
def test_day_metrics_validation(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        metrics(0, **overrides)


def test_unlogged_day_cannot_carry_metrics() -> None:
    with pytest.raises(ValueError, match="unlogged"):
        DayMetrics(
            local_date=day(0),
            logged=False,
            no_goals=False,
            goals_total=0,
            goals_done=0,
            mood=3,
        )
