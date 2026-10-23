from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, time

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db import Base, make_engine, make_session_factory
from app.email_builder import build_insight_email
from app.gemini import InsightOutput
from app.insights import (
    build_insight_payload,
    get_or_create_nightly_insight,
    process_entry_insight,
)
from app.mailer import MailerError, OutboundEmail
from app.models import EmailLog, Entry, Goal, Insight

TODAY = date(2026, 10, 23)
NOW = datetime(2026, 10, 23, 15, 15, tzinfo=UTC)


class FakeMailer:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.messages: list[OutboundEmail] = []

    def send(self, message: OutboundEmail) -> None:
        self.messages.append(message)
        if self.error is not None:
            raise self.error


class FakeGemini:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, _payload: object) -> InsightOutput:
        self.calls += 1
        return InsightOutput(
            summary="A specific summary.",
            wins=["A win."],
            struggles=[],
            actions=["One.", "Two.", "Three."],
            pattern="A pattern.",
        )


@pytest.fixture
def factory() -> Iterator[sessionmaker[Session]]:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield make_session_factory(engine)
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


def add_entry(factory: sessionmaker[Session], text: str = "A steady day.") -> int:
    with factory() as session:
        entry = Entry(
            local_date=TODAY,
            wake_time=time(6, 30),
            bedtime_time=time(23, 0),
            screen_minutes=120,
            top_apps="Reading",
            day_summary=text,
            went_well="Focused work.",
            improve_tomorrow="Start earlier.",
            key_takeaway="Small steps.",
            mood=4,
        )
        entry.goals.append(
            Goal(
                position=0,
                title="Deep work",
                done=True,
                difficulty=3,
                note="Two focused hours.",
            )
        )
        session.add(entry)
        session.commit()
        return entry.id


def test_build_insight_payload_has_stats_and_truncated_text(
    factory: sessionmaker[Session],
) -> None:
    entry_id = add_entry(factory, "x" * 800)
    with factory() as session:
        entry = session.get(Entry, entry_id)
        assert entry is not None
        payload = build_insight_payload(session, settings(), TODAY)

    assert payload["range"] == {"start": "2026-10-10", "end": "2026-10-23"}
    assert payload["summary"]["logged_days"] == 1
    assert payload["summary"]["goal_days"] == 1
    assert payload["summary"]["goals_done"] == 1
    assert payload["streaks"]["current_goal"] == 1
    assert len(payload["days"]) == 14
    assert payload["days"][-1]["date"] == "2026-10-23"
    assert payload["days"][-1]["wake_time"] == "06:30"
    assert payload["days"][-1]["sleep_minutes"] == 450
    assert len(payload["entries"][0]["summary"]) <= 600
    assert payload["entries"][0]["summary"].endswith("...")
    assert payload["entries"][0]["goals"][0]["note"] == "Two focused hours."


def test_get_or_create_persists_fallback_and_reuses_it(
    factory: sessionmaker[Session],
) -> None:
    entry_id = add_entry(factory)
    with factory() as session:
        entry = session.get(Entry, entry_id)
        assert entry is not None
        insight = get_or_create_nightly_insight(session, settings(), TODAY)

    assert insight.model_name == "rule-based"
    assert insight.payload is not None
    assert set(insight.payload) == {"summary", "wins", "struggles", "actions", "pattern"}
    assert insight.text == insight.payload["summary"]

    client = FakeGemini()
    with factory() as session:
        again = get_or_create_nightly_insight(
            session,
            settings(),
            TODAY,
            gemini_client=client,  # type: ignore[arg-type]
        )
    assert again.id == insight.id
    assert client.calls == 0


def test_get_or_create_uses_gemini_client(factory: sessionmaker[Session]) -> None:
    add_entry(factory)
    client = FakeGemini()
    with factory() as session:
        insight = get_or_create_nightly_insight(
            session,
            settings(),
            TODAY,
            gemini_client=client,  # type: ignore[arg-type]
        )
    assert client.calls == 1
    assert insight.model_name == "gemini-test"
    assert insight.payload is not None
    assert insight.payload["summary"] == "A specific summary."


def test_process_entry_insight_saves_and_sends(
    factory: sessionmaker[Session],
) -> None:
    entry_id = add_entry(factory)
    mailer = FakeMailer()

    process_entry_insight(
        entry_id,
        factory,
        settings(),
        mailer,
        clock=lambda: NOW,
    )

    assert len(mailer.messages) == 1
    assert "Your nightly insight" in mailer.messages[0].subject
    assert "A specific summary." not in mailer.messages[0].text
    assert "rule-based" in mailer.messages[0].text
    with factory() as session:
        insight = session.scalar(select(Insight))
        assert insight is not None
        log = session.scalar(select(EmailLog))
        assert log is not None
        assert log.kind == "insight"
        assert log.status == "sent"

    process_entry_insight(
        entry_id,
        factory,
        settings(),
        mailer,
        clock=lambda: NOW,
    )
    assert len(mailer.messages) == 1


def test_process_entry_insight_keeps_insight_when_email_fails(
    factory: sessionmaker[Session],
) -> None:
    entry_id = add_entry(factory)
    mailer = FakeMailer(MailerError("relay rejected"))

    process_entry_insight(
        entry_id,
        factory,
        settings(),
        mailer,
        clock=lambda: NOW,
    )

    with factory() as session:
        assert session.scalar(select(Insight)) is not None
        log = session.scalar(select(EmailLog))
        assert log is not None
        assert log.status == "failed"
        assert log.last_error == "relay rejected"


def test_process_entry_insight_ignores_missing_entry(
    factory: sessionmaker[Session],
) -> None:
    mailer = FakeMailer()
    process_entry_insight(999, factory, settings(), mailer, clock=lambda: NOW)
    assert mailer.messages == []


def test_insight_email_escapes_payload_text(factory: sessionmaker[Session]) -> None:
    entry_id = add_entry(factory)
    with factory() as session:
        entry = session.get(Entry, entry_id)
        assert entry is not None
        insight = Insight(
            kind="nightly",
            start_date=TODAY,
            end_date=TODAY,
            text="fallback",
            payload={
                "summary": "<script>alert(1)</script>",
                "wins": ["<b>win</b>"],
                "struggles": [],
                "actions": ["one", "two", "three"],
                "pattern": "<i>pattern</i>",
            },
            model_name="test",
        )
        session.add(insight)
        session.commit()
        message = build_insight_email(session, settings(), insight, entry)

    assert "<script>alert(1)</script>" not in message.html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in message.html
    assert "<b>win</b>" not in message.html
    assert "<script>alert(1)</script>" in message.text
