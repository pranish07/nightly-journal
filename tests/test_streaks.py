from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.streaks import (
    DayRecord,
    DayStatus,
    compute_streaks,
    status_for,
    statuses_for_range,
)

START = date(2026, 10, 1)


def day(offset: int) -> date:
    return START + timedelta(days=offset)


def logged(
    offset: int,
    *,
    total: int = 1,
    done: int = 1,
    no_goals: bool = False,
) -> DayRecord:
    if no_goals:
        total = 0
        done = 0
    return DayRecord(
        local_date=day(offset),
        logged=True,
        no_goals=no_goals,
        goals_total=total,
        goals_done=done,
    )


def unlogged(offset: int) -> DayRecord:
    return DayRecord(
        local_date=day(offset),
        logged=False,
        no_goals=False,
        goals_total=0,
        goals_done=0,
    )


@pytest.mark.parametrize(
    ("record", "threshold", "expected"),
    [
        (logged(0), 1.0, DayStatus.ACHIEVED),
        (logged(0, total=4, done=2), 0.5, DayStatus.ACHIEVED),
        (logged(0, total=4, done=2), 1.0, DayStatus.PARTIAL),
        (logged(0, total=4, done=0), 0.0, DayStatus.MISSED),
        (logged(0, no_goals=True), 1.0, DayStatus.NO_GOALS),
        (unlogged(0), 1.0, DayStatus.NOT_LOGGED),
    ],
)
def test_status_for(record: DayRecord, threshold: float, expected: DayStatus) -> None:
    assert status_for(record, threshold) == expected


def test_missed_takes_precedence_over_zero_threshold() -> None:
    assert status_for(logged(0, total=3, done=0), 0.0) is DayStatus.MISSED


@pytest.mark.parametrize("threshold", [-0.1, 1.1])
def test_invalid_threshold_rejected(threshold: float) -> None:
    with pytest.raises(ValueError, match="threshold"):
        status_for(logged(0), threshold)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"goals_total": -1, "goals_done": 0}, "goals_total"),
        ({"goals_total": 1, "goals_done": 2}, "cannot exceed"),
        ({"goals_total": 0, "goals_done": 0}, "needs goals"),
        ({"goals_total": 1, "goals_done": 1, "no_goals": True}, "no-goals"),
    ],
)
def test_impossible_logged_records_rejected(kwargs: dict[str, int | bool], message: str) -> None:
    values: dict[str, object] = {
        "local_date": START,
        "logged": True,
        "no_goals": False,
        "goals_total": 1,
        "goals_done": 1,
    }
    values.update(kwargs)
    with pytest.raises(ValueError, match=message):
        DayRecord(**values)  # type: ignore[arg-type]


def test_unlogged_record_cannot_carry_goals() -> None:
    with pytest.raises(ValueError, match="unlogged"):
        DayRecord(
            local_date=START,
            logged=False,
            no_goals=False,
            goals_total=1,
            goals_done=0,
        )


def test_current_goal_streak_has_one_day_grace() -> None:
    records = [logged(0), logged(1), logged(2)]
    stats = compute_streaks(records, as_of=day(3))
    assert stats.current_goal == 3
    assert stats.current_logging == 3


def test_current_goal_streak_breaks_after_full_missed_day() -> None:
    records = [logged(0), logged(1), logged(2)]
    stats = compute_streaks(records, as_of=day(4))
    assert stats.current_goal == 0
    assert stats.current_logging == 0


def test_today_missed_breaks_current_streak() -> None:
    records = [logged(0), logged(1), logged(2, done=0)]
    stats = compute_streaks(records, as_of=day(2))
    assert stats.current_goal == 0
    assert stats.current_logging == 3


def test_no_goals_day_bridges_but_does_not_increment() -> None:
    records = [logged(0), logged(1, no_goals=True), logged(2)]
    stats = compute_streaks(records, as_of=day(2))
    assert stats.current_goal == 2
    assert stats.longest_goal == 2
    assert stats.current_logging == 3
    assert stats.longest_logging == 3


def test_unlogged_day_breaks_goal_and_logging_streaks() -> None:
    records = [logged(0), unlogged(1), logged(2)]
    stats = compute_streaks(records, as_of=day(2))
    assert stats.current_goal == 1
    assert stats.current_logging == 1
    assert stats.longest_goal == 1
    assert stats.longest_logging == 1


def test_partial_day_breaks_goal_streak_but_not_logging_streak() -> None:
    records = [logged(0), logged(1, total=3, done=2), logged(2)]
    stats = compute_streaks(records, as_of=day(2))
    assert stats.current_goal == 1
    assert stats.longest_goal == 1
    assert stats.current_logging == 3
    assert stats.longest_logging == 3


def test_longest_streaks_are_historical_maxima() -> None:
    records = [
        logged(0),
        logged(1),
        logged(2),
        unlogged(3),
        logged(4),
        logged(5),
    ]
    stats = compute_streaks(records, as_of=day(5))
    assert stats.current_goal == 2
    assert stats.longest_goal == 3
    assert stats.current_logging == 2
    assert stats.longest_logging == 3


def test_no_records_returns_zeroes() -> None:
    assert compute_streaks([], as_of=START).current_goal == 0
    assert compute_streaks([], as_of=START).longest_goal == 0


def test_as_of_before_records_returns_zeroes() -> None:
    stats = compute_streaks([logged(1), logged(2)], as_of=day(0))
    assert stats == type(stats)(0, 0, 0, 0)


def test_duplicate_records_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        compute_streaks([logged(0), logged(0)], as_of=day(0))


def test_statuses_for_range_fills_gaps() -> None:
    records = [logged(1), logged(3, no_goals=True)]
    statuses = statuses_for_range(records, start=day(0), end=day(3))
    assert statuses == [
        (day(0), DayStatus.NOT_LOGGED),
        (day(1), DayStatus.ACHIEVED),
        (day(2), DayStatus.NOT_LOGGED),
        (day(3), DayStatus.NO_GOALS),
    ]


def test_statuses_for_range_rejects_reversed_range() -> None:
    with pytest.raises(ValueError, match="end"):
        statuses_for_range([], start=day(2), end=day(1))
