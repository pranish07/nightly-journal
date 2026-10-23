from __future__ import annotations

import imaplib
from collections.abc import Iterator
from email.message import EmailMessage

import pytest
from sqlalchemy.engine import Engine

from app import cli
from app.config import Settings
from app.db import Base, make_engine
from app.mailer import MailerError, OutboundEmail


class FakeMailer:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.messages: list[OutboundEmail] = []

    def send(self, message: OutboundEmail) -> None:
        self.messages.append(message)
        if self.error is not None:
            raise self.error


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "test",
        "database_url": "sqlite://",
        "public_base_url": "https://journal.example.com",
        "form_token_secret": "form-" + "x" * 40,
        "csrf_secret": "csrf-" + "y" * 40,
        "cron_secret": "cron-" + "z" * 40,
        "imap_host": "imap.example.com",
        "imap_user": "me@example.com",
        "imap_password": "password",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


@pytest.fixture
def engine() -> Iterator[Engine]:
    db = make_engine("sqlite://")
    Base.metadata.create_all(db)
    yield db
    db.dispose()


def test_send_test_email_reports_relay_and_inbox(
    monkeypatch: pytest.MonkeyPatch,
    engine: Engine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mailer = FakeMailer()
    monkeypatch.setattr(cli, "make_engine", lambda _url: engine)
    monkeypatch.setattr(cli, "make_mailer", lambda _settings: mailer)
    monkeypatch.setattr(cli, "poll_imap", lambda _settings, _subject: True)

    assert cli.send_test_email(settings()) is True

    assert len(mailer.messages) == 1
    assert mailer.messages[0].subject.startswith("Nightly Journal test ")
    output = capsys.readouterr().out
    assert "relay_accepted" in output
    assert "delivered_to_inbox" in output


def test_send_test_email_reports_not_found(
    monkeypatch: pytest.MonkeyPatch,
    engine: Engine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "make_engine", lambda _url: engine)
    monkeypatch.setattr(cli, "make_mailer", lambda _settings: FakeMailer())
    monkeypatch.setattr(cli, "poll_imap", lambda _settings, _subject: False)

    assert cli.send_test_email(settings()) is True
    assert "not_found" in capsys.readouterr().out


def test_send_test_email_reports_mailer_failure(
    monkeypatch: pytest.MonkeyPatch,
    engine: Engine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "make_engine", lambda _url: engine)
    monkeypatch.setattr(
        cli,
        "make_mailer",
        lambda _settings: FakeMailer(MailerError("relay rejected")),
    )

    assert cli.send_test_email(settings()) is False
    captured = capsys.readouterr()
    assert "send_failed: relay rejected" in captured.err


class FakeIMAP:
    messages: list[bytes] = []
    login_error = False

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.logged_out = False

    def login(self, user: str, password: str) -> None:
        if FakeIMAP.login_error:
            raise imaplib.IMAP4.error("login failed")

    def select(self, mailbox: str) -> tuple[str, list[bytes]]:
        return "OK", [b"1"]

    def search(self, charset: str | None, *criteria: str) -> tuple[str, list[bytes]]:
        return "OK", [b"1" if FakeIMAP.messages else b""]

    def fetch(self, message_id: bytes, _parts: str) -> tuple[str, list[object]]:
        return "OK", [(b"1 (RFC822)", FakeIMAP.messages[0]), b")"]

    def logout(self) -> None:
        self.logged_out = True


def message_bytes(subject: str) -> bytes:
    message = EmailMessage()
    message["Subject"] = subject
    message.set_content("body")
    return message.as_bytes()


@pytest.fixture(autouse=True)
def reset_fake_imap() -> None:
    FakeIMAP.messages = []
    FakeIMAP.login_error = False


def test_poll_imap_finds_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeIMAP.messages = [message_bytes("Nightly Journal test")]
    monkeypatch.setattr(cli.imaplib, "IMAP4_SSL", FakeIMAP)

    assert cli.poll_imap(settings(), "Nightly Journal test", timeout_seconds=0) is True


def test_poll_imap_returns_false_without_configuration() -> None:
    assert cli.poll_imap(settings(imap_host=""), "subject") is False


def test_poll_imap_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.imaplib, "IMAP4_SSL", FakeIMAP)
    sleeps: list[float] = []

    assert (
        cli.poll_imap(
            settings(),
            "missing",
            timeout_seconds=0,
            sleep=sleeps.append,
            monotonic=lambda: 0.0,
        )
        is False
    )
    assert sleeps == []


def test_poll_imap_handles_login_error(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeIMAP.login_error = True
    monkeypatch.setattr(cli.imaplib, "IMAP4_SSL", FakeIMAP)

    assert cli.poll_imap(settings(), "subject", timeout_seconds=0) is False


def test_main_runs_send_test_email(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "get_settings", settings)
    monkeypatch.setattr(cli, "send_test_email", lambda _settings: True)

    assert cli.main(["send-test-email"]) == 0
