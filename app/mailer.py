from __future__ import annotations

import smtplib
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass
from email.message import EmailMessage as MIMEMessage
from typing import Protocol

import httpx

from app.config import Settings


class MailerError(Exception):
    """A safe, loggable mailer failure."""


class MailerAuthError(MailerError):
    """Authentication/authorization failure; do not retry in-process."""


@dataclass(frozen=True, slots=True)
class OutboundEmail:
    subject: str
    html: str
    text: str


class Mailer(Protocol):
    def send(self, message: OutboundEmail) -> None: ...


def _build_mime(settings: Settings, message: OutboundEmail) -> MIMEMessage:
    mime = MIMEMessage()
    mime["From"] = settings.email_from
    mime["To"] = settings.email_to
    mime["Subject"] = message.subject
    mime.set_content(message.text)
    mime.add_alternative(message.html, subtype="html")
    return mime


class SmtpMailer:
    def __init__(
        self,
        settings: Settings,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._settings = settings
        self._sleep = sleep

    def _send_once(self, mime: MIMEMessage) -> None:
        settings = self._settings
        context = ssl.create_default_context()
        if settings.smtp_security == "ssl":
            client: smtplib.SMTP = smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout_seconds,
                context=context,
            )
        else:
            client = smtplib.SMTP(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout_seconds,
            )
        try:
            client.ehlo()
            if settings.smtp_security == "starttls":
                client.starttls(context=context)
                client.ehlo()
            if settings.smtp_user:
                try:
                    client.login(settings.smtp_user, settings.smtp_password)
                except smtplib.SMTPAuthenticationError as exc:
                    raise MailerAuthError("SMTP authentication failed") from exc
            client.send_message(mime)
        finally:
            try:
                client.quit()
            except (smtplib.SMTPException, OSError):
                pass

    def send(self, message: OutboundEmail) -> None:
        mime = _build_mime(self._settings, message)
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                self._send_once(mime)
                return
            except MailerAuthError:
                raise
            except (smtplib.SMTPException, OSError) as exc:
                last_error = exc
                if attempt < 2:
                    self._sleep(2**attempt)
        raise MailerError(
            f"SMTP send failed after retries: {type(last_error).__name__}"
        ) from last_error


class ResendMailer:
    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._settings = settings
        self._client = client or httpx.Client(
            timeout=settings.resend_timeout_seconds,
        )
        self._sleep = sleep

    def send(self, message: OutboundEmail) -> None:
        settings = self._settings
        if not settings.resend_api_key:
            raise MailerError("Resend API key is not configured")
        payload = {
            "from": settings.email_from,
            "to": [settings.email_to],
            "subject": message.subject,
            "html": message.html,
            "text": message.text,
        }
        headers = {
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self._client.post(
                    settings.resend_api_url,
                    headers=headers,
                    json=payload,
                )
            except httpx.HTTPError as exc:
                last_error = exc
            else:
                if 200 <= response.status_code < 300:
                    return
                if response.status_code in {401, 403}:
                    raise MailerAuthError(
                        f"Resend authorization failed: HTTP {response.status_code}"
                    )
                if response.status_code == 429 or response.status_code >= 500:
                    last_error = MailerError(
                        f"Resend transient failure: HTTP {response.status_code}"
                    )
                else:
                    raise MailerError(f"Resend rejected the message: HTTP {response.status_code}")
            if attempt < 2:
                self._sleep(2**attempt)
        raise MailerError(
            f"Resend send failed after retries: {type(last_error).__name__}"
        ) from last_error


def make_mailer(settings: Settings) -> Mailer:
    if settings.mail_transport == "resend":
        return ResendMailer(settings)
    return SmtpMailer(settings)
