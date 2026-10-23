from __future__ import annotations

from collections.abc import Iterator
from datetime import date, time

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import Base, make_engine, make_session_factory
from app.models import EmailLog, Entry, Goal, Insight, PlannedGoal

TODAY = date(2026, 10, 23)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    with factory() as db:
        yield db
    engine.dispose()


def make_entry(session: Session, local_date: date = TODAY, **overrides: object) -> Entry:
    values: dict[str, object] = {
        "local_date": local_date,
        "wake_time": time(6, 30),
        "bedtime_time": time(23, 0),
        "screen_minutes": 120,
        "top_apps": "Reading",
        "no_goals": False,
        "day_summary": "A steady day.",
        "went_well": "Focused work.",
        "improve_tomorrow": "Start earlier.",
        "key_takeaway": "Small steps compound.",
        "mood": 4,
    }
    values.update(overrides)
    entry = Entry(**values)  # type: ignore[arg-type]
    session.add(entry)
    session.flush()
    return entry


def make_goal(session: Session, entry: Entry, **overrides: object) -> Goal:
    values: dict[str, object] = {
        "entry_id": entry.id,
        "position": 0,
        "title": "Deep work",
        "done": True,
        "difficulty": 3,
        "note": "Two focused hours.",
    }
    values.update(overrides)
    goal = Goal(**values)  # type: ignore[arg-type]
    session.add(goal)
    session.flush()
    return goal


def test_goal_title_normalizes_but_display_keeps_spacing(session: Session) -> None:
    entry = make_entry(session)
    goal = make_goal(session, entry, title="  Deep   Work.  ")
    assert goal.title == "Deep   Work."
    assert goal.normalized_title == "deep work"


def test_planned_goal_title_normalizes(session: Session) -> None:
    planned = PlannedGoal(
        target_date=TODAY,
        position=0,
        title="  Read 20 Pages! ",
    )
    session.add(planned)
    session.flush()
    assert planned.title == "Read 20 Pages!"
    assert planned.normalized_title == "read 20 pages"


def test_blank_goal_title_rejected_before_database(session: Session) -> None:
    entry = make_entry(session)
    with pytest.raises(ValueError, match="blank"):
        Goal(
            entry_id=entry.id,
            position=0,
            title="   ",
            done=False,
            difficulty=3,
            note="note",
        )


def test_no_goals_defaults_false(session: Session) -> None:
    entry = Entry(
        local_date=TODAY,
        wake_time=time(6, 30),
        bedtime_time=time(23, 0),
        screen_minutes=30,
        day_summary="summary",
        went_well="well",
        improve_tomorrow="improve",
        key_takeaway="takeaway",
        mood=3,
    )
    session.add(entry)
    session.flush()
    assert entry.no_goals is False


def test_goals_are_ordered_by_position(session: Session) -> None:
    entry = make_entry(session)
    make_goal(session, entry, position=1, title="Second")
    make_goal(session, entry, position=0, title="First")
    session.expire(entry)
    assert [goal.position for goal in entry.goals] == [0, 1]


def test_deleting_entry_cascades_to_goals(session: Session) -> None:
    entry = make_entry(session)
    make_goal(session, entry)
    entry_id = entry.id
    session.execute(delete(Entry).where(Entry.id == entry_id))
    session.flush()
    assert session.scalar(select(func.count()).select_from(Goal)) == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"screen_minutes": -1},
        {"screen_minutes": 1441},
        {"mood": 0},
        {"mood": 6},
    ],
)
def test_entry_check_constraints(session: Session, overrides: dict[str, object]) -> None:
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            make_entry(session, **overrides)


@pytest.mark.parametrize("difficulty", [0, 6])
def test_goal_difficulty_range(session: Session, difficulty: int) -> None:
    entry = make_entry(session)
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            make_goal(session, entry, difficulty=difficulty)


def test_goal_position_cannot_be_negative(session: Session) -> None:
    entry = make_entry(session)
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            make_goal(session, entry, position=-1)


def test_goal_position_unique_per_entry(session: Session) -> None:
    entry = make_entry(session)
    make_goal(session, entry, position=0)
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            make_goal(session, entry, position=0, title="Duplicate")


def test_database_rejects_blank_goal_title_bypassing_validator(session: Session) -> None:
    entry = make_entry(session)
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.execute(
                Goal.__table__.insert().values(
                    entry_id=entry.id,
                    position=0,
                    title="   ",
                    normalized_title="valid",
                    done=False,
                    difficulty=3,
                    note="note",
                )
            )


def test_database_rejects_blank_normalized_goal_title(session: Session) -> None:
    entry = make_entry(session)
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.execute(
                Goal.__table__.insert().values(
                    entry_id=entry.id,
                    position=0,
                    title="Valid",
                    normalized_title="",
                    done=False,
                    difficulty=3,
                    note="note",
                )
            )


def test_entry_local_date_is_unique(session: Session) -> None:
    make_entry(session)
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            make_entry(session)


def test_planned_goal_position_unique_per_date(session: Session) -> None:
    session.add(PlannedGoal(target_date=TODAY, position=0, title="Read"))
    session.flush()
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(PlannedGoal(target_date=TODAY, position=0, title="Write"))
            session.flush()


def test_planned_goal_database_rejects_blank_title(session: Session) -> None:
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.execute(
                PlannedGoal.__table__.insert().values(
                    target_date=TODAY,
                    position=0,
                    title="   ",
                    normalized_title="valid",
                )
            )


def test_insight_payload_round_trips(session: Session) -> None:
    insight = Insight(
        kind="nightly",
        start_date=TODAY,
        end_date=TODAY,
        text="You slept well.",
        payload={"wins": ["deep work"], "score": 3},
        model_name="gemini-test",
    )
    session.add(insight)
    session.commit()
    session.expire(insight)
    assert insight.payload == {"wins": ["deep work"], "score": 3}


def test_insight_is_unique_per_kind_and_range(session: Session) -> None:
    session.add(
        Insight(
            kind="weekly",
            start_date=date(2026, 10, 17),
            end_date=TODAY,
            text="Week summary",
            model_name="gemini-test",
        )
    )
    session.flush()
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(
                Insight(
                    kind="weekly",
                    start_date=date(2026, 10, 17),
                    end_date=TODAY,
                    text="Duplicate",
                    model_name="gemini-test",
                )
            )
            session.flush()


@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "other"},
        {"end_date": date(2026, 10, 22)},
    ],
)
def test_insight_check_constraints(session: Session, overrides: dict[str, object]) -> None:
    values: dict[str, object] = {
        "kind": "nightly",
        "start_date": TODAY,
        "end_date": TODAY,
        "text": "Insight",
        "model_name": "gemini-test",
    }
    values.update(overrides)
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(Insight(**values))  # type: ignore[arg-type]
            session.flush()


def test_email_log_is_unique_per_kind_and_date(session: Session) -> None:
    session.add(EmailLog(kind="nightly", local_date=TODAY, status="sent"))
    session.flush()
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(EmailLog(kind="nightly", local_date=TODAY, status="failed"))
            session.flush()


@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "other"},
        {"status": "unknown"},
        {"attempts": -1},
    ],
)
def test_email_log_check_constraints(session: Session, overrides: dict[str, object]) -> None:
    values: dict[str, object] = {
        "kind": "nightly",
        "local_date": TODAY,
        "status": "sending",
        "attempts": 0,
    }
    values.update(overrides)
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(EmailLog(**values))  # type: ignore[arg-type]
            session.flush()
