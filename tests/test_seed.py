from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.db import Base, make_engine, make_session_factory
from app.models import Entry
from scripts.seed import DAYS, MISSED_OFFSETS, SeedError, seed

TODAY = date(2026, 10, 23)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="test",
        database_url=f"sqlite:///{(tmp_path / 'seed.db').as_posix()}",
    )


def _create_schema(settings: Settings) -> None:
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    engine.dispose()


def test_seed_refuses_production(tmp_path: Path) -> None:
    settings = _settings(tmp_path).model_copy(update={"app_env": "production"})
    with pytest.raises(SeedError, match="production"):
        seed(settings, today=TODAY)


def test_seed_refuses_postgres(tmp_path: Path) -> None:
    settings = _settings(tmp_path).model_copy(
        update={"database_url": "postgresql+psycopg://user:pass@host/journal"}
    )
    with pytest.raises(SeedError, match="PostgreSQL"):
        seed(settings, today=TODAY)


def test_seed_refuses_in_memory_sqlite(tmp_path: Path) -> None:
    settings = _settings(tmp_path).model_copy(update={"database_url": "sqlite://"})
    with pytest.raises(SeedError, match="file-backed"):
        seed(settings, today=TODAY)


def test_seed_requires_schema(tmp_path: Path) -> None:
    with pytest.raises(SeedError, match="alembic upgrade head"):
        seed(_settings(tmp_path), today=TODAY)


def test_seed_populates_thirty_days_and_is_idempotent(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _create_schema(settings)

    result = seed(settings, today=TODAY)
    assert result.created == DAYS - len(MISSED_OFFSETS)
    assert result.skipped == 0
    assert result.missed == len(MISSED_OFFSETS)

    engine = make_engine(settings.database_url)
    with make_session_factory(engine)() as session:
        entries = list(session.scalars(select(Entry).options(selectinload(Entry.goals))).all())

    expected_dates = {
        TODAY - timedelta(days=offset)
        for offset in range(1, DAYS + 1)
        if offset not in MISSED_OFFSETS
    }
    assert {entry.local_date for entry in entries} == expected_dates
    assert len(entries) == DAYS - len(MISSED_OFFSETS)

    no_goals = [entry for entry in entries if entry.no_goals]
    assert len(no_goals) == 3
    assert all(not entry.goals for entry in no_goals)

    goals = [goal for entry in entries for goal in entry.goals]
    assert goals
    assert any(goal.done for goal in goals)
    assert not all(goal.done for goal in goals)

    assert {entry.mood for entry in entries} <= {1, 2, 3, 4, 5}
    assert all(0 <= entry.screen_minutes <= 1440 for entry in entries)
    assert any(entry.top_apps for entry in entries)
    for entry in entries:
        assert entry.day_summary
        assert entry.went_well
        assert entry.improve_tomorrow
        assert entry.key_takeaway
        assert entry.wake_time is not None
        assert entry.bedtime_time is not None

    engine.dispose()

    again = seed(settings, today=TODAY)
    assert again.created == 0
    assert again.skipped == DAYS - len(MISSED_OFFSETS)
    assert again.missed == len(MISSED_OFFSETS)
