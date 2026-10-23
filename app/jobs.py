from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import and_, insert, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.email_builder import build_nightly_email, build_weekly_email
from app.gemini import GeminiClient
from app.mailer import Mailer, MailerAuthError, MailerError
from app.models import EmailLog
from app.timeutils import utc_now

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
LEASE = timedelta(minutes=5)
MAX_BACKOFF_MINUTES = 30


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    kind: str
    local_date: date
    attempts: int


def _get_log(session: Session, kind: str, local_date: date) -> EmailLog | None:
    return session.scalars(
        select(EmailLog).where(
            EmailLog.kind == kind,
            EmailLog.local_date == local_date,
        )
    ).first()


def claim_job(
    session: Session,
    kind: str,
    local_date: date,
    now: datetime,
) -> ClaimedJob | None:
    """Atomically claim one due email job for this kind/date."""

    try:
        with session.begin_nested():
            session.execute(
                insert(EmailLog).values(
                    kind=kind,
                    local_date=local_date,
                    status="sending",
                    attempts=1,
                    lease_until=now + LEASE,
                )
            )
    except IntegrityError:
        pass
    else:
        session.commit()
        return ClaimedJob(kind=kind, local_date=local_date, attempts=1)

    result = session.execute(
        update(EmailLog)
        .where(
            EmailLog.kind == kind,
            EmailLog.local_date == local_date,
            EmailLog.attempts < MAX_ATTEMPTS,
            or_(
                EmailLog.status == "failed",
                and_(
                    EmailLog.status == "sending",
                    EmailLog.lease_until.is_not(None),
                    EmailLog.lease_until < now,
                ),
            ),
            or_(
                EmailLog.next_attempt_at.is_(None),
                EmailLog.next_attempt_at <= now,
            ),
        )
        .values(
            status="sending",
            attempts=EmailLog.attempts + 1,
            lease_until=now + LEASE,
            next_attempt_at=None,
            last_error=None,
            sent_at=None,
        )
        .execution_options(synchronize_session=False)
    )
    claimed = result.rowcount
    session.commit()
    if claimed != 1:
        return None
    log = _get_log(session, kind, local_date)
    if log is None:
        return None
    return ClaimedJob(kind=kind, local_date=local_date, attempts=log.attempts)


def _safe_error(exc: Exception) -> str:
    detail = str(exc) if isinstance(exc, MailerError) else type(exc).__name__
    return detail[:500]


def _mark_failed(log: EmailLog, exc: Exception, now: datetime) -> None:
    log.status = "failed"
    log.lease_until = None
    log.last_error = _safe_error(exc)
    if isinstance(exc, MailerAuthError):
        log.next_attempt_at = now + timedelta(days=1)
        return
    delay = min(2 ** max(log.attempts - 1, 0), MAX_BACKOFF_MINUTES)
    log.next_attempt_at = now + timedelta(minutes=delay)


def mark_job_failed(
    session: Session,
    kind: str,
    local_date: date,
    exc: Exception,
    now: datetime,
) -> EmailLog | None:
    log = _get_log(session, kind, local_date)
    if log is None or log.status != "sending":
        return None
    _mark_failed(log, exc, now)
    return log


def mark_job_sent(
    session: Session,
    kind: str,
    local_date: date,
    now: datetime,
) -> EmailLog | None:
    log = _get_log(session, kind, local_date)
    if log is None or log.status != "sending":
        return None
    log.status = "sent"
    log.sent_at = now
    log.lease_until = None
    log.next_attempt_at = None
    log.last_error = None
    return log


def run_claimed_job(
    session_factory: sessionmaker[Session],
    settings: Settings,
    mailer: Mailer,
    kind: str,
    local_date: date,
    clock: Callable[[], datetime] = utc_now,
    gemini_client: GeminiClient | None = None,
) -> None:
    now = clock()
    with session_factory() as session:
        log = _get_log(session, kind, local_date)
        if log is None or log.status != "sending":
            return
        try:
            if kind == "nightly":
                outbound = build_nightly_email(session, settings, local_date)
            elif kind == "weekly":
                outbound = build_weekly_email(
                    session,
                    settings,
                    local_date,
                    gemini_client=gemini_client,
                )
            else:
                raise MailerError(f"unsupported email job kind: {kind}")
            mailer.send(outbound)
        except Exception as exc:
            session.rollback()
            log = _get_log(session, kind, local_date)
            if log is not None:
                _mark_failed(log, exc, now)
                session.commit()
                logger.warning(
                    "email_job_failed kind=%s date=%s attempts=%s error=%s",
                    kind,
                    local_date,
                    log.attempts,
                    log.last_error,
                )
            return
        log.status = "sent"
        log.sent_at = now
        log.lease_until = None
        log.next_attempt_at = None
        log.last_error = None
        session.commit()
        logger.info(
            "email_job_sent kind=%s date=%s attempts=%s",
            kind,
            local_date,
            log.attempts,
        )
