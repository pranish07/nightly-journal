from __future__ import annotations

import smtplib
from email.message import EmailMessage

import httpx
import pytest

from app.config import Settings
from app.mailer import (
    MailerAuthError,
    MailerError,
    OutboundEmail,
    ResendMailer,
    SmtpMailer,
    make_mailer,
)


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "test",
        "smtp_host": "smtp.example.com",
        "smtp_port": 2525,
        "smtp_user": "user",
        "smtp_password": "password",
        "email_from": "Journal <journal@example.com>",
        "email_to": "me@example.com",
        "resend_api_key": "re_test",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def outbound() -> OutboundEmail:
    return OutboundEmail(subject="Subject", html="<p>Hello</p>", text="Hello")


class FakeSMTP:
    instances: list[FakeSMTP] = []
    send_failures = 0

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.starttls_used = False
        self.logged_in: tuple[str, str] | None = None
        self.message: EmailMessage | None = None
        self.quit_called = False
        FakeSMTP.instances.append(self)

    def ehlo(self) -> None:
        pass

    def starttls(self, context: object) -> None:
        self.starttls_used = True

    def login(self, user: str, password: str) -> None:
        self.logged_in = (user, password)

    def send_message(self, message: EmailMessage) -> None:
        if FakeSMTP.send_failures > 0:
            FakeSMTP.send_failures -= 1
            raise smtplib.SMTPServerDisconnected("temporary")
        self.message = message

    def quit(self) -> None:
        self.quit_called = True


@pytest.fixture(autouse=True)
def reset_fake_smtp() -> None:
    FakeSMTP.instances = []
    FakeSMTP.send_failures = 0


def test_smtp_mailer_sends_multipart_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.mailer.smtplib.SMTP", FakeSMTP)
    sleeps: list[float] = []
    mailer = SmtpMailer(settings(), sleep=sleeps.append)

    mailer.send(outbound())

    assert sleeps == []
    assert len(FakeSMTP.instances) == 1
    smtp = FakeSMTP.instances[0]
    assert (smtp.host, smtp.port) == ("smtp.example.com", 2525)
    assert smtp.starttls_used is True
    assert smtp.logged_in == ("user", "password")
    assert smtp.quit_called is True
    assert smtp.message is not None
    assert smtp.message["From"] == "Journal <journal@example.com>"
    assert smtp.message["To"] == "me@example.com"
    assert smtp.message["Subject"] == "Subject"
    assert smtp.message.get_body(preferencelist=("plain",)).get_content().strip() == "Hello"
    assert "<p>Hello</p>" in smtp.message.get_body(preferencelist=("html",)).get_content()


def test_smtp_auth_failure_does_not_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    class AuthFailingSMTP(FakeSMTP):
        def login(self, user: str, password: str) -> None:
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    monkeypatch.setattr("app.mailer.smtplib.SMTP", AuthFailingSMTP)
    sleeps: list[float] = []
    mailer = SmtpMailer(settings(), sleep=sleeps.append)

    with pytest.raises(MailerAuthError, match="authentication failed"):
        mailer.send(outbound())

    assert len(AuthFailingSMTP.instances) == 1
    assert sleeps == []


def test_smtp_transient_failure_retries_with_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.mailer.smtplib.SMTP", FakeSMTP)
    FakeSMTP.send_failures = 2
    sleeps: list[float] = []
    mailer = SmtpMailer(settings(), sleep=sleeps.append)

    mailer.send(outbound())

    assert len(FakeSMTP.instances) == 3
    assert sleeps == [1, 2]
    assert FakeSMTP.instances[-1].message is not None


def test_smtp_exhausted_retries_raise_safe_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.mailer.smtplib.SMTP", FakeSMTP)
    FakeSMTP.send_failures = 3
    sleeps: list[float] = []
    mailer = SmtpMailer(settings(), sleep=sleeps.append)

    with pytest.raises(MailerError, match="after retries: SMTPServerDisconnected"):
        mailer.send(outbound())

    assert len(FakeSMTP.instances) == 3
    assert sleeps == [1, 2]


def test_resend_mailer_sends_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "email_1"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        mailer = ResendMailer(settings(mail_transport="resend"), client=client)
        mailer.send(outbound())
    finally:
        client.close()

    assert len(requests) == 1
    request = requests[0]
    assert request.url == "https://api.resend.com/emails"
    assert request.headers["authorization"] == "Bearer re_test"
    payload = request.read().decode()
    assert '"subject":"Subject"' in payload
    assert '"to":["me@example.com"]' in payload


def test_resend_auth_failure_does_not_retry() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(401)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        mailer = ResendMailer(settings(mail_transport="resend"), client=client)
        with pytest.raises(MailerAuthError, match="authorization failed"):
            mailer.send(outbound())
    finally:
        client.close()
    assert len(requests) == 1


def test_resend_transient_failure_retries() -> None:
    requests: list[httpx.Request] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"id": "email_1"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        mailer = ResendMailer(
            settings(mail_transport="resend"),
            client=client,
            sleep=sleeps.append,
        )
        mailer.send(outbound())
    finally:
        client.close()

    assert len(requests) == 3
    assert sleeps == [1, 2]


def test_resend_rejects_permanent_error_without_retry() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(400)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        mailer = ResendMailer(settings(mail_transport="resend"), client=client)
        with pytest.raises(MailerError, match="HTTP 400"):
            mailer.send(outbound())
    finally:
        client.close()
    assert len(requests) == 1


def test_make_mailer_selects_transport() -> None:
    assert isinstance(make_mailer(settings()), SmtpMailer)
    assert isinstance(
        make_mailer(settings(mail_transport="resend")),
        ResendMailer,
    )
