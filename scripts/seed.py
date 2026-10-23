"""Seed a local SQLite database with demo journal entries for development."""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass
from datetime import date, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect, select  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.config import Settings, get_settings  # noqa: E402
from app.db import make_engine, make_session_factory  # noqa: E402
from app.models import Entry, Goal  # noqa: E402
from app.timeutils import local_date  # noqa: E402

DAYS = 30
RNG_SEED = 20261023
MISSED_OFFSETS = frozenset({6, 13, 22, 27})
NO_GOALS_OFFSETS = frozenset({4, 17, 25})

GOAL_POOL = (
    ("Read 20 pages", 2),
    ("Walk 8,000 steps", 2),
    ("Ship the PR review", 3),
    ("Meditate for 10 minutes", 1),
    ("No phone before 9pm", 4),
    ("Cook dinner at home", 2),
    ("Finish the report draft", 3),
    ("Practice guitar for 30 minutes", 2),
    ("Drink 2 liters of water", 1),
    ("Inbox to zero", 3),
    ("Stretch for 15 minutes", 1),
    ("Call family", 1),
    ("Study Nepali for 20 minutes", 2),
    ("Write 500 words", 3),
    ("Clean the kitchen", 1),
    ("Run 5km", 4),
    ("Review the monthly budget", 2),
    ("Sleep before 11pm", 4),
    ("Plan tomorrow before logging off", 2),
    ("Take a 20-minute walk after lunch", 1),
)

DONE_NOTES = (
    "Done, and easier than expected once I started.",
    "Finished it without rushing.",
    "Small win, but it kept the day on track.",
    "Knocked it out before dinner.",
)

MISSED_NOTES = (
    "Ran out of time after work.",
    "Kept putting it off until it was too late.",
    "Started, but did not get far.",
    "Skipped it and felt it later.",
)

WENT_WELL = (
    "Kept the morning routine intact and started work on time.",
    "Handled one annoying task early instead of delaying it.",
    "Took real breaks instead of scrolling through lunch.",
    "Stayed patient in a meeting that could have gone badly.",
    "Cooked instead of ordering out, which saved money and time.",
    "Got outside for a bit even though the day was busy.",
)

IMPROVE = (
    "Start the most important task before opening chat.",
    "Put the phone in another room during deep work.",
    "Stop work at a reasonable hour instead of drifting late.",
    "Prepare tomorrow's clothes and bag tonight.",
    "Drink water earlier in the day.",
    "Leave one buffer block in the calendar.",
)

TAKEAWAYS = (
    "Consistency beats intensity on busy days.",
    "The first ten minutes are the hard part.",
    "Sleep quality drives the whole next day.",
    "A short walk resets my focus better than another coffee.",
    "I do better when the evening has a clear stopping point.",
    "Small, boring routines are doing a lot of heavy lifting.",
)

NO_GOALS_SUMMARIES = (
    "Deliberate no-goals day. I needed the reset and did not force productivity.",
    "Took the day off goals on purpose: long lunch, a walk, and an early night.",
    "Chose rest over targets today. No guilt, just recovery.",
)

NO_GOALS_WENT_WELL = (
    "Actually rested instead of squeezing in one more task.",
    "Kept the evening quiet and went to bed early.",
    "Said no to extra work and protected the downtime.",
)

TOP_APPS = (
    "YouTube 1h 10m, WhatsApp 35m",
    "Instagram 48m, Chrome 1h 05m",
    "Spotify 2h 05m, Slack 40m",
    "Chrome 1h 50m, Notion 25m",
    "YouTube 45m, Maps 20m",
    "Reddit 38m, Kindle 30m",
)

WAKE_TIMES = (time(5, 45), time(6, 10), time(6, 30), time(7, 0), time(7, 20), time(8, 0))
BED_TIMES = (time(22, 15), time(22, 45), time(23, 0), time(23, 30), time(0, 10), time(0, 45))

MOOD_WEIGHTS = (4, 16, 40, 30, 10)
MOOD_WORDS = {1: "low", 2: "flat", 3: "steady", 4: "good", 5: "great"}


class SeedError(RuntimeError):
    """Raised when the seed script refuses to run or cannot complete."""


@dataclass(frozen=True, slots=True)
class SeedResult:
    created: int
    skipped: int
    missed: int
    database: str


def validate_environment(settings: Settings) -> None:
    if settings.app_env == "production":
        raise SeedError("refusing to seed: APP_ENV is production")

    raw_url = settings.database_url.lower()
    if raw_url.startswith(("postgres://", "postgresql://", "postgresql+", "postgres+")):
        raise SeedError("refusing to seed: DATABASE_URL points at PostgreSQL")

    try:
        url = make_url(settings.database_url)
    except Exception as exc:
        raise SeedError("refusing to seed: DATABASE_URL is not a valid URL") from exc

    backend = url.get_backend_name()
    if backend == "postgresql":
        raise SeedError("refusing to seed: DATABASE_URL points at PostgreSQL")
    if backend != "sqlite":
        raise SeedError(f"refusing to seed: DATABASE_URL uses {backend}, not SQLite")
    if not url.database or url.database == ":memory:":
        raise SeedError("refusing to seed: DATABASE_URL must be a file-backed SQLite database")


def seed(
    settings: Settings,
    *,
    today: date | None = None,
    rng_seed: int = RNG_SEED,
) -> SeedResult:
    validate_environment(settings)
    rng = random.Random(rng_seed)
    engine = make_engine(settings.database_url)
    try:
        if not inspect(engine).has_table("entries"):
            raise SeedError("refusing to seed: schema is missing; run `alembic upgrade head` first")
        factory = make_session_factory(engine)
        end = today or local_date()
        created = 0
        skipped = 0
        missed = 0
        with factory() as session:
            for offset in range(DAYS, 0, -1):
                day = end - timedelta(days=offset)
                if offset in MISSED_OFFSETS:
                    missed += 1
                    continue
                if session.scalar(select(Entry.id).where(Entry.local_date == day)) is not None:
                    skipped += 1
                    continue
                session.add(_build_entry(day, offset, rng))
                created += 1
            session.commit()
        return SeedResult(
            created=created,
            skipped=skipped,
            missed=missed,
            database=settings.database_url,
        )
    finally:
        engine.dispose()


def _build_entry(day: date, offset: int, rng: random.Random) -> Entry:
    no_goals = offset in NO_GOALS_OFFSETS
    mood = rng.choices((1, 2, 3, 4, 5), weights=MOOD_WEIGHTS)[0]
    weekend = day.weekday() >= 5
    wake_time = rng.choice(WAKE_TIMES)
    bedtime_time = rng.choice(BED_TIMES)
    screen_minutes = rng.randint(180, 620) if weekend else rng.randint(90, 430)
    if no_goals:
        screen_minutes = rng.randint(240, 620)

    entry = Entry(
        local_date=day,
        wake_time=wake_time,
        bedtime_time=bedtime_time,
        screen_minutes=screen_minutes,
        top_apps=rng.choice(TOP_APPS) if rng.random() < 0.7 else None,
        no_goals=no_goals,
        mood=mood,
    )

    if no_goals:
        entry.day_summary = rng.choice(NO_GOALS_SUMMARIES)
        entry.went_well = rng.choice(NO_GOALS_WENT_WELL)
        entry.improve_tomorrow = "Pick one small goal for tomorrow and keep the evening calm."
        entry.key_takeaway = "Rest is part of the routine, not a failure."
        return entry

    goal_count = rng.randint(1, 4)
    for position, (title, difficulty) in enumerate(rng.sample(GOAL_POOL, goal_count)):
        done = rng.random() < _done_probability(mood, difficulty)
        entry.goals.append(
            Goal(
                position=position,
                title=title,
                done=done,
                difficulty=difficulty,
                note=rng.choice(DONE_NOTES if done else MISSED_NOTES),
            )
        )

    focus = _join_titles([goal.title for goal in entry.goals])
    energy = MOOD_WORDS[mood]
    entry.day_summary = rng.choice(
        (
            f"Mostly heads-down on {focus}. Energy was {energy} and the day moved fast.",
            f"A steady day built around {focus}. Nothing dramatic, just consistent progress.",
            f"Started slow, then found a rhythm with {focus}. Ended the evening calm.",
            f"Balanced work with {focus}. Energy stayed {energy} for most of the day.",
        )
    )
    entry.went_well = rng.choice(WENT_WELL)
    entry.improve_tomorrow = rng.choice(IMPROVE)
    entry.key_takeaway = rng.choice(TAKEAWAYS)
    return entry


def _done_probability(mood: int, difficulty: int) -> float:
    base = {1: 0.15, 2: 0.35, 3: 0.6, 4: 0.8, 5: 0.9}[mood]
    return max(0.05, min(0.95, base - 0.08 * (difficulty - 1)))


def _join_titles(titles: list[str]) -> str:
    if len(titles) == 1:
        return titles[0]
    if len(titles) == 2:
        return f"{titles[0]} and {titles[1]}"
    return ", ".join(titles[:-1]) + f", and {titles[-1]}"


def main() -> int:
    settings = get_settings()
    try:
        result = seed(settings)
    except SeedError as exc:
        print(f"seed_failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"seeded {result.created} entries, skipped {result.skipped} existing, "
        f"left {result.missed} days empty"
    )
    print(f"database: {result.database}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
