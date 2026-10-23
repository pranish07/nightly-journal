from __future__ import annotations

from collections.abc import Iterator
from datetime import date, time, timedelta

import pytest
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import Base, make_engine, make_session_factory
from app.email_builder import build_nightly_email
from app.models import Entry, Goal, Insight, PlannedGoal
from app.services.entries import get_streak_stats

TODAY = date(2026, 10, 23)
YESTERDAY = TODAY - timedelta(days=1)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    with factory() as db:
        yield db
    engine.dispose()


def settings() -> Settings:
    return Settings(
        app_env="test",
        public_base_url="https://journal.example.com/",
        form_token_secret="form-" + "x" * 40,
        csrf_secret="csrf-" + "y" * 40,
        cron_secret="cron-" + "z" * 40,
        email_from="Journal <journal@example.com>",
        email_to="me@example.com",
    )


def add_entry(session: Session, local_date: date, takeaway: str) -> Entry:
    entry = Entry(
        local_date=local_date,
        wake_time=time(6, 30),
        bedtime_time=time(23, 0),
        screen_minutes=120,
        day_summary="A steady day.",
        went_well="Focused work.",
        improve_tomorrow="Start earlier.",
        key_takeaway=takeaway,
        mood=4,
    )
    entry.goals.append(Goal(position=0, title="Deep work", done=True, difficulty=3, note=""))
    session.add(entry)
    return entry


def test_build_nightly_email_includes_context(session: Session) -> None:
    add_entry(session, YESTERDAY, "Keep going.")
    session.add(
        Insight(
            kind="nightly",
            start_date=YESTERDAY,
            end_date=YESTERDAY,
            text="You protected your focus.",
            model_name="test",
        )
    )
    session.add(PlannedGoal(target_date=TODAY, position=0, title="Walk"))
    session.commit()

    message = build_nightly_email(session, settings(), TODAY)

    assert message.subject == "Tonight's check-in: Friday, October 23, 2026"
    assert "https://journal.example.com/f/" in message.html
    assert "You protected your focus." in message.html
    assert "Walk" in message.html
    assert "1 day" in message.html
    assert "https://journal.example.com/f/" in message.text
    assert "You protected your focus." in message.text
    assert "Walk" in message.text
    assert "1 day" in message.text


def test_build_nightly_email_falls_back_to_takeaway(session: Session) -> None:
    add_entry(session, YESTERDAY, "Small steps count.")
    session.commit()

    message = build_nightly_email(session, settings(), TODAY)

    assert "Small steps count." in message.html
    assert "Small steps count." in message.text


def test_build_nightly_email_handles_missing_yesterday(session: Session) -> None:
    message = build_nightly_email(session, settings(), TODAY)

    assert "No entry yesterday." in message.html
    assert "No entry yesterday." in message.text
    assert "No active goal streak yet" in message.text


def test_build_nightly_email_escapes_user_text(session: Session) -> None:
    add_entry(session, YESTERDAY, "<script>alert(1)</script>")
    session.commit()

    message = build_nightly_email(session, settings(), TODAY)

    assert "<script>alert(1)</script>" not in message.html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in message.html
    assert "<script>alert(1)</script>" in message.text


def test_get_streak_stats_empty_database(session: Session) -> None:
    stats = get_streak_stats(session, TODAY)
    assert stats.current_goal == 0
    assert stats.longest_goal == 0
