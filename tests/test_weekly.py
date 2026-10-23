from __future__ import annotations

from collections.abc import Iterator
from datetime import date, time, timedelta

import pytest
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import Base, make_engine, make_session_factory
from app.email_builder import build_weekly_email
from app.gemini import InsightOutput
from app.models import Entry, Goal
from app.weekly import (
    build_weekly_insight_payload,
    build_weekly_report,
    get_or_create_weekly_insight,
    weekly_range,
)

SATURDAY = date(2026, 10, 24)
START = date(2026, 10, 17)
END = date(2026, 10, 23)


class FakeGemini:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, _payload: object) -> InsightOutput:
        self.calls += 1
        return InsightOutput(
            summary="A weekly summary.",
            wins=["A weekly win."],
            struggles=[],
            actions=["One.", "Two.", "Three."],
            pattern="A weekly pattern.",
        )


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
        public_base_url="https://journal.example.com",
        form_token_secret="form-" + "x" * 40,
        csrf_secret="csrf-" + "y" * 40,
        cron_secret="cron-" + "z" * 40,
        gemini_model="gemini-test",
    )


def add_week(session: Session) -> None:
    difficulties = [1, 2, 3, 4, 5, 2, 1]
    for index, difficulty in enumerate(difficulties):
        local_date = START + timedelta(days=index)
        entry = Entry(
            local_date=local_date,
            wake_time=time(6, 30),
            bedtime_time=time(23, 0),
            screen_minutes=120,
            top_apps="Reading",
            day_summary=f"Day {index}.",
            went_well="Focused work.",
            improve_tomorrow="Start earlier.",
            key_takeaway="Small steps.",
            mood=4,
        )
        entry.goals.append(
            Goal(
                position=0,
                title=f"Goal {index}",
                done=index % 2 == 0,
                difficulty=difficulty,
                note=f"Note {index}.",
            )
        )
        session.add(entry)
    session.commit()


def test_weekly_range_covers_prior_saturday_through_friday() -> None:
    assert weekly_range(SATURDAY) == (START, END)


def test_weekly_report_uses_range_stats_and_recent_goal_ties(
    session: Session,
) -> None:
    add_week(session)

    report = build_weekly_report(session, settings(), SATURDAY)

    assert report.start == START
    assert report.end == END
    assert report.stats.logged_days == 7
    assert report.stats.goals_total == 7
    assert report.stats.goals_done == 4
    assert report.easiest is not None
    assert report.easiest.title == "Goal 6"
    assert report.easiest.difficulty == 1
    assert report.hardest is not None
    assert report.hardest.title == "Goal 4"
    assert report.hardest.difficulty == 5


def test_weekly_insight_payload_has_highlights_and_days(session: Session) -> None:
    add_week(session)

    payload = build_weekly_insight_payload(session, settings(), SATURDAY)

    assert payload["range"] == {"start": "2026-10-17", "end": "2026-10-23"}
    assert payload["summary"]["logged_days"] == 7
    assert len(payload["days"]) == 7
    assert payload["goal_highlights"]["easiest"]["title"] == "Goal 6"
    assert payload["goal_highlights"]["hardest"]["title"] == "Goal 4"
    assert payload["entries"][0]["goals"][0]["note"] == "Note 0."


def test_get_or_create_weekly_insight_reuses_saved_insight(
    session: Session,
) -> None:
    add_week(session)
    insight = get_or_create_weekly_insight(session, settings(), SATURDAY)

    assert insight.kind == "weekly"
    assert insight.start_date == START
    assert insight.end_date == END
    assert insight.model_name == "rule-based"
    assert insight.payload is not None

    client = FakeGemini()
    again = get_or_create_weekly_insight(
        session,
        settings(),
        SATURDAY,
        gemini_client=client,  # type: ignore[arg-type]
    )
    assert again.id == insight.id
    assert client.calls == 0


def test_get_or_create_weekly_insight_uses_gemini(session: Session) -> None:
    add_week(session)
    client = FakeGemini()
    insight = get_or_create_weekly_insight(
        session,
        settings(),
        SATURDAY,
        gemini_client=client,  # type: ignore[arg-type]
    )
    assert client.calls == 1
    assert insight.model_name == "gemini-test"
    assert insight.payload is not None
    assert insight.payload["summary"] == "A weekly summary."


def test_weekly_charts_are_png_with_alt_text(session: Session) -> None:
    add_week(session)

    report = build_weekly_report(
        session,
        settings(),
        SATURDAY,
        include_charts=True,
    )

    assert len(report.charts) == 4
    assert [chart.cid for chart in report.charts] == [
        "weekly-completion",
        "weekly-sleep",
        "weekly-screen",
        "weekly-mood",
    ]
    for chart in report.charts:
        assert chart.content.startswith(b"\x89PNG\r\n\x1a\n")
        assert chart.alt
        assert chart.filename.endswith(".png")


def test_build_weekly_email_includes_metrics_text_and_inline_images(
    session: Session,
) -> None:
    add_week(session)

    message = build_weekly_email(session, settings(), SATURDAY)

    assert message.subject == "Your week in review: Oct 17 - Oct 23, 2026"
    assert len(message.inline_images) == 4
    assert "cid:weekly-completion" in message.html
    assert "cid:weekly-sleep" in message.html
    assert "Goal completion by day" in message.html
    assert "7 / 7" in message.html
    assert "Goal 6" in message.html
    assert "Goal 4" in message.html
    assert "THE NUMBERS" in message.text
    assert "Goal 6" in message.text
    assert "Goal 4" in message.text
    assert "last 7 days" in message.text


def test_weekly_email_escapes_goal_text(session: Session) -> None:
    entry = Entry(
        local_date=END,
        wake_time=time(6, 30),
        bedtime_time=time(23, 0),
        screen_minutes=60,
        day_summary="A day.",
        went_well="Something.",
        improve_tomorrow="Something.",
        key_takeaway="Something.",
        mood=3,
    )
    entry.goals.append(
        Goal(
            position=0,
            title="<script>alert(1)</script>",
            done=False,
            difficulty=3,
            note="<b>note</b>",
        )
    )
    session.add(entry)
    session.commit()

    message = build_weekly_email(session, settings(), SATURDAY)

    assert "<script>alert(1)</script>" not in message.html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in message.html
    assert "<b>note</b>" not in message.html
    assert "<script>alert(1)</script>" in message.text
