from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import Base, make_engine
from app.mailer import MailerError, OutboundEmail
from app.main import create_app
from app.models import EmailLog

NOW = datetime(2026, 10, 23, 15, 15, tzinfo=UTC)
SECRET = "cron-" + "z" * 40


class FakeMailer:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.messages: list[OutboundEmail] = []

    def send(self, message: OutboundEmail) -> None:
        self.messages.append(message)
        if self.error is not None:
            raise self.error


def settings() -> Settings:
    return Settings(
        app_env="test",
        database_url="sqlite://",
        public_base_url="https://journal.example.com",
        form_token_secret="form-" + "x" * 40,
        csrf_secret="csrf-" + "y" * 40,
        cron_secret=SECRET,
    )


@pytest.fixture
def bundle() -> Iterator[SimpleNamespace]:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    mailer = FakeMailer()
    app = create_app(settings(), engine, mailer=mailer, clock=lambda: NOW)
    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client,
            engine=engine,
            mailer=mailer,
            app=app,
        )
    engine.dispose()


def test_tick_requires_secret(bundle: SimpleNamespace) -> None:
    assert bundle.client.get("/cron/tick").status_code == 403
    assert (
        bundle.client.get(
            "/cron/tick",
            headers={"X-Cron-Secret": "wrong"},
        ).status_code
        == 403
    )
    with Session(bundle.engine) as session:
        assert session.scalars(select(EmailLog)).all() == []


def test_tick_outside_window_claims_nothing(bundle: SimpleNamespace) -> None:
    bundle.app.state.clock = lambda: datetime(2026, 10, 23, 14, 0, tzinfo=UTC)
    response = bundle.client.get(
        "/cron/tick",
        headers={"X-Cron-Secret": SECRET},
    )
    assert response.status_code == 202
    assert response.json()["claimed"] == []
    assert bundle.mailer.messages == []


def test_tick_sends_nightly_email(bundle: SimpleNamespace) -> None:
    response = bundle.client.get(
        "/cron/tick",
        headers={"X-Cron-Secret": SECRET},
    )

    assert response.status_code == 202
    assert response.json()["claimed"] == [
        {"kind": "nightly", "local_date": "2026-10-23", "attempts": 1}
    ]
    assert len(bundle.mailer.messages) == 1
    with Session(bundle.engine) as session:
        log = session.scalar(select(EmailLog))
        assert log is not None
        assert log.status == "sent"
        assert log.attempts == 1


def test_second_tick_does_not_resend(bundle: SimpleNamespace) -> None:
    headers = {"X-Cron-Secret": SECRET}
    assert bundle.client.get("/cron/tick", headers=headers).status_code == 202
    response = bundle.client.get("/cron/tick", headers=headers)

    assert response.status_code == 202
    assert response.json()["claimed"] == []
    assert len(bundle.mailer.messages) == 1


def test_tick_records_failure(bundle: SimpleNamespace) -> None:
    bundle.mailer.error = MailerError("relay rejected")
    headers = {"X-Cron-Secret": SECRET}

    first = bundle.client.get("/cron/tick", headers=headers)
    second = bundle.client.get("/cron/tick", headers=headers)

    assert first.status_code == 202
    assert first.json()["claimed"][0]["attempts"] == 1
    assert second.status_code == 202
    assert second.json()["claimed"] == []
    with Session(bundle.engine) as session:
        log = session.scalar(select(EmailLog))
        assert log is not None
        assert log.status == "failed"
        assert log.last_error == "relay rejected"


def test_tick_sends_weekly_email(bundle: SimpleNamespace) -> None:
    bundle.app.state.clock = lambda: datetime(2026, 10, 24, 1, 15, tzinfo=UTC)
    response = bundle.client.get(
        "/cron/tick",
        headers={"X-Cron-Secret": SECRET},
    )

    assert response.status_code == 202
    assert response.json()["claimed"] == [
        {"kind": "weekly", "local_date": "2026-10-24", "attempts": 1}
    ]
    assert len(bundle.mailer.messages) == 1
    assert len(bundle.mailer.messages[0].inline_images) == 4
    with Session(bundle.engine) as session:
        log = session.scalar(select(EmailLog))
        assert log is not None
        assert log.kind == "weekly"
        assert log.status == "sent"
