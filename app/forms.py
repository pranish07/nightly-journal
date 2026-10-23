from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from starlette.datastructures import FormData

from app.schemas import EntryForm

GOAL_FIELD = re.compile(r"goal_title_(\d+)$")
PLAN_FIELD = re.compile(r"plan_title_(\d+)$")

FIELD_LABELS = {
    "wake_time": "Wake time",
    "bedtime_time": "Bedtime",
    "screen_minutes": "Screen time",
    "top_apps": "Top apps",
    "day_summary": "Day summary",
    "went_well": "What went well",
    "improve_tomorrow": "What to improve",
    "key_takeaway": "Key takeaway",
    "mood": "Mood",
    "goals": "Goals",
    "plans": "Tomorrow's plans",
    "no_goals": "No goals",
}


@dataclass(frozen=True, slots=True)
class ParsedEntryForm:
    data: EntryForm | None
    raw: dict[str, Any]
    errors: dict[str, str]
    error_list: list[str]

    @property
    def ok(self) -> bool:
        return self.data is not None


def _text(form: FormData, key: str, default: str = "") -> str:
    value = form.get(key)
    return value if isinstance(value, str) else default


def _checkbox(form: FormData, key: str) -> bool:
    return _text(form, key).strip().lower() in {"1", "true", "yes", "on"}


def _indices(form: FormData, pattern: re.Pattern[str]) -> list[int]:
    found: set[int] = set()
    for key in form.keys():
        match = pattern.match(key)
        if match:
            found.add(int(match.group(1)))
    return sorted(found)


def _parse_goals(form: FormData) -> list[dict[str, str]]:
    goals: list[dict[str, str]] = []
    for index in _indices(form, GOAL_FIELD):
        title = _text(form, f"goal_title_{index}")
        if not title.strip():
            continue
        goals.append(
            {
                "title": title,
                "done": _text(form, f"goal_done_{index}", "no"),
                "difficulty": _text(form, f"goal_difficulty_{index}", "3"),
                "note": _text(form, f"goal_note_{index}"),
            }
        )
    return goals


def _parse_plans(form: FormData) -> list[str]:
    plans: list[str] = []
    for index in _indices(form, PLAN_FIELD):
        title = _text(form, f"plan_title_{index}")
        if title.strip():
            plans.append(title)
    return plans


def _friendly_message(error: dict[str, Any]) -> str:
    error_type = error.get("type")
    message = str(error.get("msg", "Invalid value."))
    if error_type == "missing":
        return "This field is required."
    if error_type == "string_too_short":
        return "This value is too short."
    if error_type == "string_too_long":
        return "This value is too long."
    if error_type in {"int_parsing", "int_type"}:
        return "Enter a whole number."
    if error_type == "time_parsing":
        return "Enter a valid time."
    if error_type == "value_error":
        return message.removeprefix("Value error, ")
    return message


def _format_errors(exc: ValidationError) -> tuple[dict[str, str], list[str]]:
    errors: dict[str, str] = {}
    error_list: list[str] = []
    for error in exc.errors():
        location = error.get("loc", ())
        message = _friendly_message(error)
        if not location:
            key = "__all__"
            label = None
        elif location[0] == "goals":
            if len(location) > 1 and isinstance(location[1], int):
                key = f"goal_{location[1]}"
                label = f"Goal {location[1] + 1}"
            else:
                key = "goals"
                label = FIELD_LABELS["goals"]
        elif location[0] == "plans":
            if len(location) > 1 and isinstance(location[1], int):
                key = f"plan_{location[1]}"
                label = f"Plan {location[1] + 1}"
            else:
                key = "plans"
                label = FIELD_LABELS["plans"]
        else:
            key = str(location[0])
            label = FIELD_LABELS.get(key, key.replace("_", " ").capitalize())
        errors.setdefault(key, message)
        error_list.append(message if label is None else f"{label}: {message}")
    return errors, error_list


def parse_entry_form(form: FormData) -> ParsedEntryForm:
    no_goals = _checkbox(form, "no_goals")
    raw: dict[str, Any] = {
        "wake_time": _text(form, "wake_time"),
        "bedtime_time": _text(form, "bedtime_time"),
        "screen_minutes": _text(form, "screen_minutes"),
        "top_apps": _text(form, "top_apps"),
        "no_goals": no_goals,
        "day_summary": _text(form, "day_summary"),
        "went_well": _text(form, "went_well"),
        "improve_tomorrow": _text(form, "improve_tomorrow"),
        "key_takeaway": _text(form, "key_takeaway"),
        "mood": _text(form, "mood"),
        "goals": [] if no_goals else _parse_goals(form),
        "plans": _parse_plans(form),
    }
    try:
        data = EntryForm.model_validate(raw)
    except ValidationError as exc:
        errors, error_list = _format_errors(exc)
        return ParsedEntryForm(data=None, raw=raw, errors=errors, error_list=error_list)
    return ParsedEntryForm(data=data, raw=raw, errors={}, error_list=[])
