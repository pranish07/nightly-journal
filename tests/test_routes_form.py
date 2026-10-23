from __future__ import annotations

from collections.abc import Iterator
from datetime import date, time, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import Base, make_engine
from app.mailer import OutboundEmail
from app.main import create_app
from app.models import EmailLog, Entry, Goal, PlannedGoal
from app.timeutils import local_date
from app.tokens import make_form_csrf, make_form_token

TODAY = local_date()
YESTERDAY = TODAY - timedelta(days=1)
TOMORROW = TODAY + timedelta(days=1)


class FakeMailer:
    def __init__(self) -> None:
        self.messages: list[OutboundEmail] = []

    def send(self, message: OutboundEmail) -> None:
        self.messages.append(message)


@pytest.fixture
def bundle() -> Iterator[SimpleNamespace]:
    settings = Settings(
        app_env="test",
        database_url="sqlite://",
        form_token_secret="form-" + "x" * 40,
        csrf_secret="csrf-" + "y" * 40,
    )
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    mailer = FakeMailer()
    app = create_app(settings, engine, mailer=mailer)
    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client,
            engine=engine,
            settings=settings,
            app=app,
            mailer=mailer,
        )
    engine.dispose()


def valid_data(settings: Settings, local_date: date = TODAY) -> dict[str, str]:
    return {
        "csrf_token": make_form_csrf(local_date, settings),
        "wake_time": "06:30",
        "bedtime_time": "23:00",
        "screen_minutes": "120",
        "top_apps": "Reading",
        "day_summary": "A steady day.",
        "went_well": "Focused work.",
        "improve_tomorrow": "Start earlier.",
        "key_takeaway": "Small steps.",
        "mood": "4",
        "goal_title_0": "Deep work",
        "goal_done_0": "yes",
        "goal_difficulty_0": "3",
        "goal_note_0": "Two focused hours.",
        "plan_title_0": "Walk",
    }


def test_form_get_renders(bundle: SimpleNamespace) -> None:
    token = make_form_token(TODAY, bundle.settings)
    response = bundle.client.get(f"/f/{token}")
    assert response.status_code == 200
    assert 'name="csrf_token"' in response.text
    assert f"/f/{token}" in response.text
    assert "No goals today" in response.text
    assert 'id="goal-list"' in response.text


def test_invalid_token_is_forbidden(bundle: SimpleNamespace) -> None:
    response = bundle.client.get("/f/not-a-token")
    assert response.status_code == 403
    assert "This link did not work" in response.text


def test_form_prefills_planned_goals(bundle: SimpleNamespace) -> None:
    with Session(bundle.engine) as session:
        session.add(PlannedGoal(target_date=TODAY, position=0, title="Read"))
        session.add(PlannedGoal(target_date=TOMORROW, position=0, title="Walk"))
        session.commit()

    token = make_form_token(TODAY, bundle.settings)
    response = bundle.client.get(f"/f/{token}")
    assert 'value="Read"' in response.text
    assert 'value="Walk"' in response.text


def test_post_creates_entry_and_redirects(bundle: SimpleNamespace) -> None:
    token = make_form_token(TODAY, bundle.settings)
    response = bundle.client.post(
        f"/f/{token}",
        data=valid_data(bundle.settings),
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/thanks/")

    with Session(bundle.engine) as session:
        entry = session.scalar(select(Entry).where(Entry.local_date == TODAY))
        assert entry is not None
        assert entry.day_summary == "A steady day."
        assert entry.goals[0].normalized_title == "deep work"
        plans = session.scalars(
            select(PlannedGoal).where(PlannedGoal.target_date == TOMORROW)
        ).all()
        assert [plan.title for plan in plans] == ["Walk"]


def test_post_then_thanks_shows_fallback_insight(bundle: SimpleNamespace) -> None:
    token = make_form_token(TODAY, bundle.settings)
    response = bundle.client.post(
        f"/f/{token}",
        data=valid_data(bundle.settings),
        follow_redirects=False,
    )
    thanks = bundle.client.get(response.headers["location"])
    assert thanks.status_code == 200
    assert "Nightly insight" in thanks.text
    assert "rule-based" in thanks.text
    assert "Insight pending" not in thanks.text
    assert "Deep work" in thanks.text
    assert len(bundle.mailer.messages) == 1
    with Session(bundle.engine) as session:
        log = session.scalar(select(EmailLog).where(EmailLog.kind == "insight"))
        assert log is not None
        assert log.status == "sent"


def test_thanks_pending_without_insight(bundle: SimpleNamespace) -> None:
    with Session(bundle.engine) as session:
        session.add(
            Entry(
                local_date=TODAY,
                wake_time=time(6, 30),
                bedtime_time=time(23, 0),
                screen_minutes=120,
                no_goals=True,
                day_summary="A steady day.",
                went_well="Focused work.",
                improve_tomorrow="Start earlier.",
                key_takeaway="Small steps.",
                mood=4,
            )
        )
        session.commit()
    token = make_form_token(TODAY, bundle.settings)
    thanks = bundle.client.get(f"/thanks/{token}")
    assert thanks.status_code == 200
    assert "Insight pending" in thanks.text


def test_duplicate_post_keeps_single_entry(bundle: SimpleNamespace) -> None:
    token = make_form_token(TODAY, bundle.settings)
    data = valid_data(bundle.settings)
    first = bundle.client.post(f"/f/{token}", data=data, follow_redirects=False)
    second = bundle.client.post(
        f"/f/{token}",
        data={**data, "day_summary": "A second summary."},
        follow_redirects=False,
    )
    assert first.status_code == 303
    assert second.status_code == 303
    with Session(bundle.engine) as session:
        count = session.scalar(select(func.count()).select_from(Entry))
        assert count == 1
        entry = session.scalar(select(Entry))
        assert entry is not None
        assert entry.day_summary == "A steady day."


def test_get_existing_entry_redirects_to_thanks(bundle: SimpleNamespace) -> None:
    token = make_form_token(TODAY, bundle.settings)
    bundle.client.post(
        f"/f/{token}",
        data=valid_data(bundle.settings),
        follow_redirects=False,
    )
    response = bundle.client.get(f"/f/{token}", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == f"/thanks/{token}"


def test_validation_error_rerenders_with_values(bundle: SimpleNamespace) -> None:
    token = make_form_token(TODAY, bundle.settings)
    data = valid_data(bundle.settings)
    data["day_summary"] = ""
    data["goal_note_0"] = ""
    response = bundle.client.post(f"/f/{token}", data=data)
    assert response.status_code == 422
    assert "Please fix the following" in response.text
    assert "Deep work" in response.text
    assert "Day summary" in response.text


def test_invalid_csrf_is_forbidden(bundle: SimpleNamespace) -> None:
    token = make_form_token(TODAY, bundle.settings)
    data = {**valid_data(bundle.settings), "csrf_token": "bad"}
    response = bundle.client.post(f"/f/{token}", data=data)
    assert response.status_code == 403
    assert "form session expired" in response.text


def test_future_date_is_forbidden(bundle: SimpleNamespace) -> None:
    token = make_form_token(TOMORROW, bundle.settings)
    response = bundle.client.post(
        f"/f/{token}",
        data=valid_data(bundle.settings, TOMORROW),
    )
    assert response.status_code == 403
    assert "not open yet" in response.text


def test_no_goals_submission(bundle: SimpleNamespace) -> None:
    token = make_form_token(TODAY, bundle.settings)
    data = {
        key: value
        for key, value in valid_data(bundle.settings).items()
        if not key.startswith("goal_")
    }
    data["no_goals"] = "on"
    response = bundle.client.post(f"/f/{token}", data=data, follow_redirects=False)
    assert response.status_code == 303
    with Session(bundle.engine) as session:
        entry = session.scalar(select(Entry))
        assert entry is not None
        assert entry.no_goals is True
        assert session.scalar(select(func.count()).select_from(Goal)) == 0


def test_reuse_yesterday_goals_data_is_rendered(bundle: SimpleNamespace) -> None:
    with Session(bundle.engine) as session:
        entry = Entry(
            local_date=YESTERDAY,
            wake_time=time(6, 0),
            bedtime_time=time(22, 30),
            screen_minutes=60,
            no_goals=False,
            day_summary="Yesterday.",
            went_well="Well.",
            improve_tomorrow="Improve.",
            key_takeaway="Takeaway.",
            mood=3,
        )
        entry.goals.append(
            Goal(
                position=0,
                title="Deep work.",
                done=True,
                difficulty=3,
                note="Focused.",
            )
        )
        session.add(entry)
        session.commit()

    token = make_form_token(TODAY, bundle.settings)
    response = bundle.client.get(f"/f/{token}")
    assert "Reuse yesterday's goals" in response.text
    assert "Deep work." in response.text
    assert "deep work" in response.text


def test_user_text_is_escaped(bundle: SimpleNamespace) -> None:
    token = make_form_token(TODAY, bundle.settings)
    data = {
        **valid_data(bundle.settings),
        "goal_title_0": "<script>alert(1)</script>",
    }
    response = bundle.client.post(f"/f/{token}", data=data, follow_redirects=False)
    thanks = bundle.client.get(response.headers["location"])
    assert "<script>alert(1)</script>" not in thanks.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in thanks.text


def test_thanks_missing_entry_is_not_found(bundle: SimpleNamespace) -> None:
    token = make_form_token(TODAY, bundle.settings)
    response = bundle.client.get(f"/thanks/{token}")
    assert response.status_code == 404
    assert "not found" in response.text


def test_security_headers(bundle: SimpleNamespace) -> None:
    response = bundle.client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
