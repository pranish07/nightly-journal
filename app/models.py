from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db import Base
from app.normalization import normalize_goal_title
from app.timeutils import utc_now


def _normalized_title(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("goal title must be a string")
    normalized = normalize_goal_title(value)
    if not normalized:
        raise ValueError("goal title must not be blank")
    return normalized


class Entry(Base):
    __tablename__ = "entries"
    __table_args__ = (
        CheckConstraint("screen_minutes BETWEEN 0 AND 1440", name="screen_minutes_range"),
        CheckConstraint("mood BETWEEN 1 AND 5", name="mood_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    local_date: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    wake_time: Mapped[time] = mapped_column(Time, nullable=False)
    bedtime_time: Mapped[time] = mapped_column(Time, nullable=False)
    screen_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    top_apps: Mapped[str | None] = mapped_column(Text, nullable=True)
    no_goals: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    day_summary: Mapped[str] = mapped_column(Text, nullable=False)
    went_well: Mapped[str] = mapped_column(Text, nullable=False)
    improve_tomorrow: Mapped[str] = mapped_column(Text, nullable=False)
    key_takeaway: Mapped[str] = mapped_column(Text, nullable=False)
    mood: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )

    goals: Mapped[list[Goal]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="Goal.position",
        passive_deletes=True,
    )


class Goal(Base):
    __tablename__ = "goals"
    __table_args__ = (
        UniqueConstraint("entry_id", "position", name="uq_goals_entry_position"),
        CheckConstraint("position >= 0", name="position_non_negative"),
        CheckConstraint("difficulty BETWEEN 1 AND 5", name="difficulty_range"),
        CheckConstraint("length(trim(title)) > 0", name="title_not_blank"),
        CheckConstraint("length(normalized_title) > 0", name="normalized_title_not_blank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_title: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    done: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    difficulty: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)

    entry: Mapped[Entry] = relationship(back_populates="goals")

    @validates("title")
    def _set_normalized_title(self, _key: str, value: str) -> str:
        self.normalized_title = _normalized_title(value)
        return value.strip()


class PlannedGoal(Base):
    __tablename__ = "planned_goals"
    __table_args__ = (
        UniqueConstraint("target_date", "position", name="uq_planned_goals_target_position"),
        CheckConstraint("position >= 0", name="position_non_negative"),
        CheckConstraint("length(trim(title)) > 0", name="title_not_blank"),
        CheckConstraint("length(normalized_title) > 0", name="normalized_title_not_blank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_title: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )

    @validates("title")
    def _set_normalized_title(self, _key: str, value: str) -> str:
        self.normalized_title = _normalized_title(value)
        return value.strip()


class Insight(Base):
    __tablename__ = "insights"
    __table_args__ = (
        UniqueConstraint("kind", "start_date", "end_date", name="uq_insights_kind_start_end"),
        CheckConstraint("kind IN ('nightly', 'weekly')", name="kind_valid"),
        CheckConstraint("end_date >= start_date", name="date_range_valid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )


class EmailLog(Base):
    __tablename__ = "email_log"
    __table_args__ = (
        UniqueConstraint("kind", "local_date", name="uq_email_log_kind_local_date"),
        CheckConstraint("kind IN ('nightly', 'weekly', 'insight')", name="kind_valid"),
        CheckConstraint("status IN ('sending', 'sent', 'failed')", name="status_valid"),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        Index("ix_email_log_status_next_attempt_at", "status", "next_attempt_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
