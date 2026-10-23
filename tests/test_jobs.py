from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db import Base, make_engine, make_session_factory
from app.jobs import MAX_ATTEMPTS, claim_job, run_claimed_job
from app.mailer import MailerAuthError, MailerError, OutboundEmail
from app.models import EmailLog

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
    )


def get_log(factory: sessionmaker[Session]) -> EmailLog:
    with factory() as session:
        log = session.scalar(select(EmailLog))
        assert log is not None
        return log


def test_claim_job_creates_sending_row(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        claim = claim_job(session, "nightly", TODAY, NOW)

    assert claim is not None
    assert claim.attempts == 1
    log = get_log(factory)
    assert log.status == "sending"
    assert log.attempts == 1
    assert log.lease_until is not None


def test_second_claim_is_refused_while_lease_active(
    factory: sessionmaker[Session],
) -> None:
    with factory() as session:
        assert claim_job(session, "nightly", TODAY, NOW) is not None
    with factory() as session:
        assert claim_job(session, "nightly", TODAY, NOW) is None


def test_expired_lease_can_be_reclaimed(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        claim_job(session, "nightly", TODAY, NOW)
    with factory() as session:
        log = session.scalar(select(EmailLog))
        assert log is not None
        log.lease_until = NOW - timedelta(minutes=1)
        session.commit()
    with factory() as session:
        claim = claim_job(session, "nightly", TODAY, NOW)
    assert claim is not None
    assert claim.attempts == 2


def test_failed_job_respects_next_attempt(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        claim_job(session, "nightly", TODAY, NOW)
    with factory() as session:
        log = session.scalar(select(EmailLog))
        assert log is not None
        log.status = "failed"
        log.lease_until = None
        log.next_attempt_at = NOW + timedelta(minutes=1)
        session.commit()
    with factory() as session:
        assert claim_job(session, "nightly", TODAY, NOW) is None
    with factory() as session:
        assert claim_job(session, "nightly", TODAY, NOW + timedelta(minutes=2))


def test_max_attempts_stops_claiming(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        session.add(
            EmailLog(
                kind="nightly",
                local_date=TODAY,
                status="failed",
                attempts=MAX_ATTEMPTS,
                next_attempt_at=NOW - timedelta(minutes=1),
            )
        )
        session.commit()
    with factory() as session:
        assert claim_job(session, "nightly", TODAY, NOW) is None


def test_run_claimed_job_sends_and_marks_sent(
    factory: sessionmaker[Session],
) -> None:
    mailer = FakeMailer()
    with factory() as session:
        claim_job(session, "nightly", TODAY, NOW)

    run_claimed_job(factory, settings(), mailer, "nightly", TODAY, clock=lambda: NOW)

    assert len(mailer.messages) == 1
    assert "Tonight's check-in" in mailer.messages[0].subject
    log = get_log(factory)
    assert log.status == "sent"
    assert log.attempts == 1
    assert log.sent_at is not None
    assert log.last_error is None


def test_run_claimed_job_marks_failure_and_backs_off(
    factory: sessionmaker[Session],
) -> None:
    mailer = FakeMailer(MailerError("relay rejected"))
    with factory() as session:
        claim_job(session, "nightly", TODAY, NOW)

    run_claimed_job(factory, settings(), mailer, "nightly", TODAY, clock=lambda: NOW)

    log = get_log(factory)
    assert log.status == "failed"
    assert log.last_error == "relay rejected"
    assert log.next_attempt_at is not None
    assert log.lease_until is None


def test_auth_failure_backs_off_for_a_day(factory: sessionmaker[Session]) -> None:
    mailer = FakeMailer(MailerAuthError("bad credentials"))
    with factory() as session:
        claim_job(session, "nightly", TODAY, NOW)

    run_claimed_job(factory, settings(), mailer, "nightly", TODAY, clock=lambda: NOW)

    log = get_log(factory)
    assert log.status == "failed"
    assert log.last_error == "bad credentials"
    assert log.next_attempt_at is not None
    assert log.next_attempt_at.replace(tzinfo=UTC) >= NOW + timedelta(hours=23)


def test_run_skips_job_that_is_not_sending(
    factory: sessionmaker[Session],
) -> None:
    mailer = FakeMailer()
    with factory() as session:
        session.add(
            EmailLog(
                kind="nightly",
                local_date=TODAY,
                status="sent",
                attempts=1,
            )
        )
        session.commit()

    run_claimed_job(factory, settings(), mailer, "nightly", TODAY, clock=lambda: NOW)

    assert mailer.messages == []


def test_run_claimed_weekly_job_sends_inline_charts(
    factory: sessionmaker[Session],
) -> None:
    mailer = FakeMailer()
    saturday = date(2026, 10, 24)
    with factory() as session:
        claim_job(session, "weekly", saturday, NOW)

    run_claimed_job(factory, settings(), mailer, "weekly", saturday, clock=lambda: NOW)

    assert len(mailer.messages) == 1
    assert "week in review" in mailer.messages[0].subject
    assert len(mailer.messages[0].inline_images) == 4
    log = get_log(factory)
    assert log.kind == "weekly"
    assert log.status == "sent"
