from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.db import make_engine

ROOT = Path(__file__).resolve().parents[1]
APP_TABLES = {"entries", "goals", "planned_goals", "insights", "email_log"}


@pytest.fixture
def alembic_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    url = f"sqlite:///{(tmp_path / 'migration.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    yield config
    get_settings.cache_clear()


def test_initial_migration_upgrades_and_downgrades(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")

    engine = make_engine(get_settings().database_url)
    inspector = inspect(engine)
    assert APP_TABLES <= set(inspector.get_table_names())
    assert {index["name"] for index in inspector.get_indexes("goals")} >= {
        "ix_goals_entry_id",
        "ix_goals_normalized_title",
    }
    assert {fk["name"] for fk in inspector.get_foreign_keys("goals")} == {
        "fk_goals_entry_id_entries"
    }
    assert {check["name"] for check in inspector.get_check_constraints("entries")} == {
        "ck_entries_mood_range",
        "ck_entries_screen_minutes_range",
    }
    engine.dispose()

    command.downgrade(alembic_config, "base")

    engine = make_engine(get_settings().database_url)
    remaining = set(inspect(engine).get_table_names())
    assert APP_TABLES.isdisjoint(remaining)
    engine.dispose()


def test_migrated_database_enforces_checks(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")

    engine = make_engine(get_settings().database_url)
    with engine.begin() as connection:
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    """
                    INSERT INTO entries (
                        local_date, wake_time, bedtime_time, screen_minutes,
                        day_summary, went_well, improve_tomorrow,
                        key_takeaway, mood
                    ) VALUES (
                        '2026-10-23', '06:30:00', '23:00:00', 1441,
                        's', 'w', 'i', 'k', 4
                    )
                    """
                )
            )
    engine.dispose()
