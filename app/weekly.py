from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.charts import weekly_charts
from app.config import Settings
from app.gemini import GeminiClient, generate_insight
from app.mailer import InlineImage
from app.models import Entry, Insight
from app.services.entries import load_day_metrics
from app.stats import RangeStats, range_stats
from app.streaks import StreakStats, compute_streaks

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WeeklyGoal:
    local_date: date
    position: int
    title: str
    difficulty: int
    note: str
    done: bool


@dataclass(frozen=True, slots=True)
class WeeklyReport:
    start: date
    end: date
    stats: RangeStats
    streak: StreakStats
    easiest: WeeklyGoal | None
    hardest: WeeklyGoal | None
    charts: tuple[InlineImage, ...] = ()


def weekly_range(saturday: date) -> tuple[date, date]:
    return saturday - timedelta(days=7), saturday - timedelta(days=1)


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


def _goal_payload(goal: WeeklyGoal | None) -> dict[str, Any] | None:
    if goal is None:
        return None
    return {
        "date": goal.local_date.isoformat(),
        "title": goal.title,
        "difficulty": goal.difficulty,
        "note": goal.note,
        "done": goal.done,
    }


def _goal_highlights(
    session: Session,
    start: date,
    end: date,
) -> tuple[WeeklyGoal | None, WeeklyGoal | None]:
    entries = session.scalars(
        select(Entry)
        .where(Entry.local_date.between(start, end))
        .options(selectinload(Entry.goals))
        .order_by(Entry.local_date)
    ).all()
    candidates = [
        WeeklyGoal(
            local_date=entry.local_date,
            position=goal.position,
            title=goal.title,
            difficulty=goal.difficulty,
            note=goal.note,
            done=goal.done,
        )
        for entry in entries
        for goal in entry.goals
    ]
    if not candidates:
        return None, None

    easiest_difficulty = min(goal.difficulty for goal in candidates)
    hardest_difficulty = max(goal.difficulty for goal in candidates)
    easiest = max(
        (goal for goal in candidates if goal.difficulty == easiest_difficulty),
        key=lambda goal: (goal.local_date, goal.position),
    )
    hardest = max(
        (goal for goal in candidates if goal.difficulty == hardest_difficulty),
        key=lambda goal: (goal.local_date, goal.position),
    )
    return easiest, hardest


def build_weekly_report(
    session: Session,
    settings: Settings,
    saturday: date,
    *,
    include_charts: bool = False,
) -> WeeklyReport:
    start, end = weekly_range(saturday)
    metrics = load_day_metrics(session, start, end)
    stats = range_stats(
        metrics,
        start=start,
        end=end,
        threshold=settings.streak_min_completion,
    )
    streak = compute_streaks(
        [metric.record for metric in metrics],
        as_of=end,
        threshold=settings.streak_min_completion,
    )
    easiest, hardest = _goal_highlights(session, start, end)
    charts = weekly_charts(stats.days) if include_charts else ()
    return WeeklyReport(
        start=start,
        end=end,
        stats=stats,
        streak=streak,
        easiest=easiest,
        hardest=hardest,
        charts=charts,
    )


def build_weekly_insight_payload(
    session: Session,
    settings: Settings,
    saturday: date,
) -> dict[str, Any]:
    report = build_weekly_report(session, settings, saturday)
    entries = session.scalars(
        select(Entry)
        .where(Entry.local_date.between(report.start, report.end))
        .options(selectinload(Entry.goals))
        .order_by(Entry.local_date)
    ).all()
    stats = report.stats
    return {
        "range": {"start": report.start.isoformat(), "end": report.end.isoformat()},
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
            "current_goal": report.streak.current_goal,
            "longest_goal": report.streak.longest_goal,
            "current_logging": report.streak.current_logging,
            "longest_logging": report.streak.longest_logging,
        },
        "goal_highlights": {
            "easiest": _goal_payload(report.easiest),
            "hardest": _goal_payload(report.hardest),
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


def get_weekly_insight(
    session: Session,
    start: date,
    end: date,
) -> Insight | None:
    return session.scalars(
        select(Insight).where(
            Insight.kind == "weekly",
            Insight.start_date == start,
            Insight.end_date == end,
        )
    ).first()


def get_or_create_weekly_insight(
    session: Session,
    settings: Settings,
    saturday: date,
    *,
    gemini_client: GeminiClient | None = None,
) -> Insight:
    start, end = weekly_range(saturday)
    existing = get_weekly_insight(session, start, end)
    if existing is not None:
        return existing

    payload = build_weekly_insight_payload(session, settings, saturday)
    result = generate_insight(payload, settings, client=gemini_client)
    insight = Insight(
        kind="weekly",
        start_date=start,
        end_date=end,
        text=result.output.summary,
        payload=result.output.model_dump(),
        model_name=result.model_name,
    )
    session.add(insight)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = get_weekly_insight(session, start, end)
        if existing is not None:
            return existing
        raise
    if result.fallback_reason is None:
        logger.info(
            "weekly_insight_generated start=%s end=%s model=%s",
            start,
            end,
            result.model_name,
        )
    else:
        logger.info(
            "weekly_insight_fallback start=%s end=%s reason=%s",
            start,
            end,
            result.fallback_reason,
        )
    return insight


def _goal_for_template(goal: WeeklyGoal | None) -> dict[str, Any] | None:
    if goal is None:
        return None
    return {
        "date": goal.local_date,
        "date_label": goal.local_date.strftime("%a, %b %d"),
        "title": goal.title,
        "difficulty": goal.difficulty,
        "note": goal.note,
        "done": goal.done,
    }


def weekly_email_context(
    report: WeeklyReport,
    insight: Insight,
) -> dict[str, Any]:
    payload = insight.payload or {}
    return {
        "start": report.start,
        "end": report.end,
        "stats": report.stats,
        "streak": report.streak,
        "easiest": _goal_for_template(report.easiest),
        "hardest": _goal_for_template(report.hardest),
        "payload": payload,
        "summary": payload.get("summary") or insight.text,
        "model_name": insight.model_name,
        "charts": report.charts,
        "day_rows": weekly_day_rows(report),
    }


def _format_minutes(value: float | None) -> str:
    if value is None:
        return "—"
    total = round(value)
    hours, minutes = divmod(total, 60)
    return f"{hours}h {minutes:02d}m"


def weekly_day_rows(report: WeeklyReport) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for day in report.stats.days:
        rows.append(
            {
                "date": day.local_date.strftime("%a %b %d"),
                "status": day.status.value,
                "goals": f"{day.goals_done}/{day.goals_total}",
                "mood": str(day.mood) if day.mood is not None else "—",
                "screen": (
                    _format_minutes(day.screen_minutes) if day.screen_minutes is not None else "—"
                ),
                "sleep": (
                    _format_minutes(day.sleep_minutes) if day.sleep_minutes is not None else "—"
                ),
            }
        )
    return rows


def _day_count(value: int) -> str:
    return f"{value} day" if value == 1 else f"{value} days"


def weekly_metric_rows(report: WeeklyReport) -> list[tuple[str, str]]:
    stats = report.stats
    streak = report.streak
    return [
        ("Logged days", f"{stats.logged_days} / 7"),
        (
            "Goal completion",
            f"{round(stats.completion_ratio * 100)}% ({stats.goals_done}/{stats.goals_total})",
        ),
        ("Current goal streak", _day_count(streak.current_goal)),
        ("Longest goal streak", _day_count(streak.longest_goal)),
        ("Current logging streak", _day_count(streak.current_logging)),
        ("Average mood", f"{stats.avg_mood:.1f} / 5" if stats.avg_mood is not None else "—"),
        ("Average sleep", _format_minutes(stats.avg_sleep_minutes)),
        ("Average screen time", _format_minutes(stats.avg_screen_minutes)),
    ]
