from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models import Entry, Goal, Insight, PlannedGoal
from app.schemas import EntryForm
from app.stats import DayMetrics
from app.streaks import StreakStats, compute_streaks


def get_entry_by_date(session: Session, local_date: date) -> Entry | None:
    return session.scalars(
        select(Entry).where(Entry.local_date == local_date).options(selectinload(Entry.goals))
    ).first()


def get_planned_goals(session: Session, target_date: date) -> list[PlannedGoal]:
    return list(
        session.scalars(
            select(PlannedGoal)
            .where(PlannedGoal.target_date == target_date)
            .order_by(PlannedGoal.position)
        )
    )


def get_yesterday_goals(session: Session, local_date: date) -> list[Goal]:
    entry = get_entry_by_date(session, local_date - timedelta(days=1))
    return list(entry.goals) if entry is not None else []


def get_nightly_insight(session: Session, local_date: date) -> Insight | None:
    return session.scalars(
        select(Insight).where(
            Insight.kind == "nightly",
            Insight.start_date == local_date,
            Insight.end_date == local_date,
        )
    ).first()


def get_yesterday_headline(session: Session, local_date: date) -> str:
    yesterday = local_date - timedelta(days=1)
    entry = get_entry_by_date(session, yesterday)
    if entry is None:
        return "No entry yesterday."
    insight = get_nightly_insight(session, yesterday)
    if insight is not None and insight.text.strip():
        return insight.text.strip()
    return entry.key_takeaway.strip()


def get_streak_stats(
    session: Session,
    as_of: date,
    threshold: float = 1.0,
) -> StreakStats:
    earliest = session.scalar(select(func.min(Entry.local_date)))
    if earliest is None:
        return compute_streaks([], as_of=as_of, threshold=threshold)
    metrics = load_day_metrics(session, earliest, as_of)
    return compute_streaks(
        [metric.record for metric in metrics],
        as_of=as_of,
        threshold=threshold,
    )


def load_day_metrics(session: Session, start: date, end: date) -> list[DayMetrics]:
    entries = session.scalars(
        select(Entry)
        .where(Entry.local_date.between(start, end))
        .options(selectinload(Entry.goals))
        .order_by(Entry.local_date)
    ).all()
    return [
        DayMetrics(
            local_date=entry.local_date,
            logged=True,
            no_goals=entry.no_goals,
            goals_total=len(entry.goals),
            goals_done=sum(1 for goal in entry.goals if goal.done),
            mood=entry.mood,
            screen_minutes=entry.screen_minutes,
            wake_time=entry.wake_time,
            bedtime_time=entry.bedtime_time,
        )
        for entry in entries
    ]


def submit_entry(
    session: Session,
    local_date: date,
    data: EntryForm,
) -> tuple[Entry, bool]:
    """Persist an entry atomically. Returns (entry, created)."""

    if not data.no_goals and not data.goals:
        raise ValueError("an entry needs goals or the no-goals toggle")

    existing = get_entry_by_date(session, local_date)
    if existing is not None:
        return existing, False

    entry = Entry(
        local_date=local_date,
        wake_time=data.wake_time,
        bedtime_time=data.bedtime_time,
        screen_minutes=data.screen_minutes,
        top_apps=data.top_apps,
        no_goals=data.no_goals,
        day_summary=data.day_summary,
        went_well=data.went_well,
        improve_tomorrow=data.improve_tomorrow,
        key_takeaway=data.key_takeaway,
        mood=data.mood,
    )
    if not data.no_goals:
        for position, goal in enumerate(data.goals):
            entry.goals.append(
                Goal(
                    position=position,
                    title=goal.title,
                    done=goal.done,
                    difficulty=goal.difficulty,
                    note=goal.note,
                )
            )

    next_date = local_date + timedelta(days=1)

    try:
        session.add(entry)
        session.execute(delete(PlannedGoal).where(PlannedGoal.target_date == local_date))

        next_entry_exists = (
            session.scalar(select(Entry.id).where(Entry.local_date == next_date)) is not None
        )
        if not next_entry_exists:
            session.execute(delete(PlannedGoal).where(PlannedGoal.target_date == next_date))
            for position, title in enumerate(data.plans):
                session.add(
                    PlannedGoal(
                        target_date=next_date,
                        position=position,
                        title=title,
                    )
                )
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = get_entry_by_date(session, local_date)
        if existing is not None:
            return existing, False
        raise

    return entry, True
