from __future__ import annotations

import argparse
import imaplib
import logging
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import timedelta
from email import message_from_bytes

from app.config import Settings, get_settings
from app.db import make_engine, make_session_factory
from app.email_builder import build_nightly_email
from app.mailer import MailerError, make_mailer
from app.timeutils import local_date, utc_now

logger = logging.getLogger(__name__)

IMAP_TIMEOUT_SECONDS = 90
IMAP_POLL_SECONDS = 5


def _find_subject(client: imaplib.IMAP4, mailbox: str, subject: str) -> bool:
    status, _ = client.select(mailbox)
    if status != "OK":
        return False
    since = (utc_now() - timedelta(days=1)).strftime("%d-%b-%Y")
    status, data = client.search(None, "SINCE", since)
    if status != "OK" or not data or not data[0]:
        return False
    for message_id in reversed(data[0].split()[-50:]):
        status, parts = client.fetch(message_id, "(RFC822)")
        if status != "OK":
            continue
        for part in parts:
            if not isinstance(part, tuple) or len(part) < 2:
                continue
            message = message_from_bytes(part[1])
            if message.get("Subject") == subject:
                return True
    return False


def poll_imap(
    settings: Settings,
    subject: str,
    *,
    timeout_seconds: float = IMAP_TIMEOUT_SECONDS,
    interval: float = IMAP_POLL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> bool:
    if not settings.imap_host or not settings.imap_user:
        return False
    client: imaplib.IMAP4 | None = None
    try:
        client = imaplib.IMAP4_SSL(
            settings.imap_host,
            settings.imap_port,
            timeout=20,
        )
        client.login(settings.imap_user, settings.imap_password)
        deadline = monotonic() + timeout_seconds
        while True:
            if _find_subject(client, settings.imap_mailbox, subject):
                return True
            remaining = deadline - monotonic()
            if remaining <= 0:
                return False
            sleep(min(interval, remaining))
    except (OSError, imaplib.IMAP4.error) as exc:
        logger.warning("imap_poll_failed error=%s", type(exc).__name__)
        return False
    finally:
        if client is not None:
            try:
                client.logout()
            except (OSError, imaplib.IMAP4.error):
                pass


def send_test_email(settings: Settings) -> bool:
    mailer = make_mailer(settings)
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    try:
        with factory() as session:
            message = build_nightly_email(session, settings, local_date())
        subject = f"Nightly Journal test {utc_now().isoformat(timespec='seconds')}"
        mailer.send(replace(message, subject=subject))
        print("relay_accepted")
        if settings.imap_host and settings.imap_user:
            print("checking inbox...")
            if poll_imap(settings, subject):
                print("delivered_to_inbox")
            else:
                print("not_found")
        return True
    except MailerError as exc:
        print(f"send_failed: {exc}", file=sys.stderr)
        return False
    finally:
        engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nightly-journal")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("send-test-email")
    args = parser.parse_args(argv)
    logging.basicConfig(level=get_settings().log_level)
    if args.command == "send-test-email":
        return 0 if send_test_email(get_settings()) else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
