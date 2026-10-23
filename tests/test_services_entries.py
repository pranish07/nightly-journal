from __future__ import annotations

from collections.abc import Iterator
from datetime import date, time, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base, make_engine, make_session_factory
from app.models import Entry, PlannedGoal
from app.schemas import EntryForm, GoalInput
from app.services.entries import (
    get_entry_by_date,
    get_planned_goals,
    get_yesterday_goals,
    load_day_metrics,
    submit_entry,
)

TODAY = date(2026, 10, 23)
TOMORROW = TODAY + timedelta(days=1)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    with factory() as db:
        yield db
    engine.dispose()


def entry_form(**overrides: object) -> EntryForm:
    values: dict[str, object] = {
        "wake_time": time(6, 30),
        "bedtime_time": time(23, 0),
        "screen_minutes": 120,
        "top_apps": "Reading",
        "no_goals": False,
        "day_summary": "A steady day.",
        "went_well": "Focused work.",
        "improve_tomorrow": "Start earlier.",
        "key_takeaway": "Small steps.",
        "mood": 4,
        "goals": [
            GoalInput(
                title="  Deep   Work.  ",
                done=True,
                difficulty=3,
                note="Two focused hours.",
            )
        ],
        "plans": ["Walk"],
    }
    values.update(overrides)
    return EntryForm(**values)  # type: ignore[arg-type]


def test_submit_creates_entry_goals_and_plans(session: Session) -> None:
    session.add(PlannedGoal(target_date=TODAY, position=0, title="Old plan"))
    session.add(PlannedGoal(target_date=TOMORROW, position=0, title="Old tomorrow"))
    session.commit()

    entry, created = submit_entry(session, TODAY, entry_form())

    assert created is True
    assert entry.local_date == TODAY
    assert len(entry.goals) == 1
    assert entry.goals[0].title == "Deep   Work."
    assert entry.goals[0].normalized_title == "deep work"
    assert get_planned_goals(session, TODAY) == []
    tomorrow = get_planned_goals(session, TOMORROW)
    assert [goal.title for goal in tomorrow] == ["Walk"]


def test_submit_no_goals_entry(session: Session) -> None:
    entry, created = submit_entry(
        session,
        TODAY,
        entry_form(no_goals=True, goals=[]),
    )
    assert created is True
    assert entry.no_goals is True
    assert entry.goals == []


def test_duplicate_submit_returns_existing_without_overwrite(session: Session) -> None:
    first, created = submit_entry(session, TODAY, entry_form())
    assert created is True
    second, created_again = submit_entry(
        session,
        TODAY,
        entry_form(day_summary="A different summary."),
    )
    assert created_again is False
    assert second.id == first.id
    assert second.day_summary == "A steady day."


def test_next_day_entry_blocks_new_planned_goals(session: Session) -> None:
    session.add(
        Entry(
            local_date=TOMORROW,
            wake_time=time(6, 0),
            bedtime_time=time(22, 30),
            screen_minutes=60,
            no_goals=True,
            day_summary="Tomorrow already logged.",
            went_well="Well.",
            improve_tomorrow="Improve.",
            key_takeaway="Takeaway.",
            mood=3,
        )
    )
    session.add(PlannedGoal(target_date=TOMORROW, position=0, title="Existing"))
    session.commit()

    submit_entry(session, TODAY, entry_form(plans=["New plan"]))

    tomorrow = get_planned_goals(session, TOMORROW)
    assert [goal.title for goal in tomorrow] == ["Existing"]


def test_get_yesterday_goals(session: Session) -> None:
    submit_entry(
        session,
        TODAY - timedelta(days=1),
        entry_form(plans=[]),
    )
    goals = get_yesterday_goals(session, TODAY)
    assert [goal.title for goal in goals] == ["Deep   Work."]


def test_load_day_metrics(session: Session) -> None:
    submit_entry(session, TODAY, entry_form(plans=[]))
    metrics = load_day_metrics(session, TODAY, TODAY)
    assert len(metrics) == 1
    assert metrics[0].logged is True
    assert metrics[0].goals_total == 1
    assert metrics[0].goals_done == 1
    assert metrics[0].mood == 4
    assert metrics[0].screen_minutes == 120


def test_get_entry_by_date_returns_none_for_missing(session: Session) -> None:
    assert get_entry_by_date(session, TODAY) is None


def test_submit_entry_persists_goal_positions(session: Session) -> None:
    form = entry_form(
        goals=[
            GoalInput(title="First", done=False, difficulty=2, note="One."),
            GoalInput(title="Second", done=True, difficulty=4, note="Two."),
        ],
        plans=[],
    )
    submit_entry(session, TODAY, form)
    entry = get_entry_by_date(session, TODAY)
    assert entry is not None
    assert [goal.position for goal in entry.goals] == [0, 1]
    assert session.scalar(select(Entry).where(Entry.local_date == TODAY)) is not None
