from __future__ import annotations

from datetime import time

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class GoalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)
    done: bool
    difficulty: int = Field(ge=1, le=5)
    note: str = Field(min_length=1, max_length=280)

    @field_validator("title", "note", mode="before")
    @classmethod
    def _strip_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class EntryForm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wake_time: time
    bedtime_time: time
    screen_minutes: int = Field(ge=0, le=1440)
    top_apps: str | None = Field(default=None, max_length=200)
    no_goals: bool = False
    day_summary: str = Field(min_length=2, max_length=2000)
    went_well: str = Field(min_length=1, max_length=1000)
    improve_tomorrow: str = Field(min_length=1, max_length=1000)
    key_takeaway: str = Field(min_length=1, max_length=500)
    mood: int = Field(ge=1, le=5)
    goals: list[GoalInput] = Field(default_factory=list, max_length=10)
    plans: list[str] = Field(default_factory=list, max_length=10)

    @field_validator(
        "day_summary",
        "went_well",
        "improve_tomorrow",
        "key_takeaway",
        mode="before",
    )
    @classmethod
    def _strip_required_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("top_apps", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("plans", mode="before")
    @classmethod
    def _clean_plans(cls, value: object) -> object:
        if isinstance(value, list):
            return [item.strip() for item in value if isinstance(item, str) and item.strip()]
        return value

    @model_validator(mode="after")
    def _goals_or_toggle(self) -> EntryForm:
        if not self.no_goals and not self.goals:
            raise ValueError("Add at least one goal, or choose “No goals today”.")
        return self
