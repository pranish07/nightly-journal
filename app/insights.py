from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.config import Settings
from app.email_builder import build_insight_email
from app.gemini import GeminiClient, generate_insight
from app.jobs import claim_job, mark_job_failed, mark_job_sent
from app.mailer import Mailer
from app.models import Entry, Insight
from app.services.entries import (
    get_nightly_insight,
    load_day_metrics,
)
from app.stats import range_stats
from app.streaks import compute_streaks
from app.timeutils import utc_now

logger = logging.getLogger(__name__)


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _time_text(value: object) -> str | None:
    return value.isoformat(timespec="minutes") if hasattr(value, "isoformat") else None


def _entry_payload(entry: Entry) -> dict[str, Any]:
    return {
        "date": entry.local_date.isoformat(),
        "summary": _truncate(entry.day_summary, 600),
        "went_well": _truncate(entry.went_well, 400),
        "improve_tomorrow": _truncate(entry.improve_tomorrow, 400),
        "key_takeaway": _truncate(entry.key_takeaway, 300),
        "top_apps": _truncate(entry.top_apps, 150),
        "goals": [
            {
                "title": _truncate(goal.title, 120),
                "done": goal.done,
                "difficulty": goal.difficulty,
                "note": _truncate(goal.note, 200),
            }
            for goal in entry.goals
        ],
    }


def build_insight_payload(
    session: Session,
    settings: Settings,
    local_date: date,
) -> dict[str, Any]:
    start = local_date - timedelta(days=13)
    metrics = load_day_metrics(session, start, local_date)
    stats = range_stats(
        metrics,
        start=start,
        end=local_date,
        threshold=settings.streak_min_completion,
    )
    streaks = compute_streaks(
        [metric.record for metric in metrics],
        as_of=local_date,
        threshold=settings.streak_min_completion,
    )
    entries = session.scalars(
        select(Entry)
        .where(Entry.local_date.between(start, local_date))
        .options(selectinload(Entry.goals))
        .order_by(Entry.local_date)
    ).all()
    return {
        "range": {"start": start.isoformat(), "end": local_date.isoformat()},
        "summary": {
            "logged_days": stats.logged_days,
            "no_goals_days": stats.no_goals_days,
            "goal_days": stats.goal_days,
            "goals_total": stats.goals_total,
            "goals_done": stats.goals_done,
            "completion_ratio": round(stats.completion_ratio, 3),
            "completion_percent": round(stats.completion_ratio * 100, 1),
            "avg_mood": stats.avg_mood,
            "avg_screen_minutes": stats.avg_screen_minutes,
            "avg_sleep_minutes": stats.avg_sleep_minutes,
        },
        "streaks": {
            "current_goal": streaks.current_goal,
            "longest_goal": streaks.longest_goal,
            "current_logging": streaks.current_logging,
            "longest_logging": streaks.longest_logging,
        },
        "days": [
            {
                "date": item.local_date.isoformat(),
                "status": item.status.value,
                "goals_total": item.goals_total,
                "goals_done": item.goals_done,
                "completion_percent": item.completion_percent,
                "mood": item.mood,
                "screen_minutes": item.screen_minutes,
                "wake_time": _time_text(item.wake_time),
                "bedtime_time": _time_text(item.bedtime_time),
                "sleep_minutes": item.sleep_minutes,
            }
            for item in stats.days
        ],
        "entries": [_entry_payload(entry) for entry in entries],
    }


def get_or_create_nightly_insight(
    session: Session,
    settings: Settings,
    local_date: date,
    *,
    gemini_client: GeminiClient | None = None,
) -> Insight:
    existing = get_nightly_insight(session, local_date)
    if existing is not None:
        return existing

    payload = build_insight_payload(session, settings, local_date)
    result = generate_insight(payload, settings, client=gemini_client)
    insight = Insight(
        kind="nightly",
        start_date=local_date,
        end_date=local_date,
        text=result.output.summary,
        payload=result.output.model_dump(),
        model_name=result.model_name,
    )
    session.add(insight)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = get_nightly_insight(session, local_date)
        if existing is not None:
            return existing
        raise
    if result.fallback_reason is None:
        logger.info(
            "nightly_insight_generated date=%s model=%s",
            local_date,
            result.model_name,
        )
    else:
        logger.info(
            "nightly_insight_fallback date=%s reason=%s",
            local_date,
            result.fallback_reason,
        )
    return insight


def process_entry_insight(
    entry_id: int,
    session_factory: sessionmaker[Session],
    settings: Settings,
    mailer: Mailer,
    gemini_client: GeminiClient | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> None:
    now = clock()
    with session_factory() as session:
        entry = session.get(Entry, entry_id)
        if entry is None:
            return
        local_date = entry.local_date
        insight = get_or_create_nightly_insight(
            session,
            settings,
            local_date,
            gemini_client=gemini_client,
        )
        claim = claim_job(session, "insight", local_date, now)
        if claim is None:
            return
        try:
            message = build_insight_email(session, settings, insight, entry)
            mailer.send(message)
        except Exception as exc:
            session.rollback()
            log = mark_job_failed(session, "insight", local_date, exc, now)
            if log is not None:
                session.commit()
            logger.warning(
                "insight_email_failed entry_id=%s date=%s error=%s",
                entry_id,
                local_date,
                type(exc).__name__,
            )
            return
        log = mark_job_sent(session, "insight", local_date, now)
        if log is not None:
            session.commit()
        logger.info(
            "insight_email_sent entry_id=%s date=%s",
            entry_id,
            local_date,
        )
