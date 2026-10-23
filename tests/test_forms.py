from __future__ import annotations

from starlette.datastructures import FormData

from app.forms import parse_entry_form


def base_items() -> list[tuple[str, str]]:
    return [
        ("wake_time", "06:30"),
        ("bedtime_time", "23:00"),
        ("screen_minutes", "120"),
        ("top_apps", "Reading"),
        ("day_summary", "A steady day."),
        ("went_well", "Focused work."),
        ("improve_tomorrow", "Start earlier."),
        ("key_takeaway", "Small steps."),
        ("mood", "4"),
        ("goal_title_0", "Deep work"),
        ("goal_done_0", "yes"),
        ("goal_difficulty_0", "3"),
        ("goal_note_0", "Two focused hours."),
        ("plan_title_0", "Walk"),
    ]


def parse(items: list[tuple[str, str]]) -> object:
    return parse_entry_form(FormData(items))


def test_valid_form_parses() -> None:
    parsed = parse(base_items())
    assert parsed.ok is True
    assert parsed.data is not None
    assert parsed.data.wake_time.isoformat() == "06:30:00"
    assert parsed.data.goals[0].title == "Deep work"
    assert parsed.data.goals[0].done is True
    assert parsed.data.plans == ["Walk"]
    assert parsed.data.top_apps == "Reading"


def test_text_is_stripped() -> None:
    text_keys = {
        "top_apps",
        "day_summary",
        "went_well",
        "improve_tomorrow",
        "key_takeaway",
        "goal_title_0",
        "goal_note_0",
        "plan_title_0",
    }
    items = [(key, f"  {value}  " if key in text_keys else value) for key, value in base_items()]
    parsed = parse(items)
    assert parsed.ok is True
    assert parsed.data is not None
    assert parsed.data.day_summary == "A steady day."
    assert parsed.data.goals[0].title == "Deep work"
    assert parsed.data.plans == ["Walk"]


def test_blank_optional_apps_becomes_none() -> None:
    items = [(key, "" if key == "top_apps" else value) for key, value in base_items()]
    parsed = parse(items)
    assert parsed.ok is True
    assert parsed.data is not None
    assert parsed.data.top_apps is None


def test_no_goals_ignores_goal_fields() -> None:
    items = base_items()
    items.append(("no_goals", "on"))
    items = [
        (key, "99" if key == "goal_difficulty_0" else value)
        for key, value in items
        if key != "goal_note_0"
    ]
    parsed = parse(items)
    assert parsed.ok is True
    assert parsed.data is not None
    assert parsed.data.no_goals is True
    assert parsed.data.goals == []


def test_requires_goals_or_toggle() -> None:
    items = [(key, value) for key, value in base_items() if not key.startswith("goal_")]
    parsed = parse(items)
    assert parsed.ok is False
    assert "No goals today" in " ".join(parsed.error_list)


def test_blank_goal_rows_are_skipped() -> None:
    items = base_items() + [
        ("goal_title_1", "   "),
        ("goal_done_1", "yes"),
        ("goal_difficulty_1", "1"),
        ("goal_note_1", "ignored"),
    ]
    parsed = parse(items)
    assert parsed.ok is True
    assert parsed.data is not None
    assert len(parsed.data.goals) == 1


def test_goal_note_is_required_when_title_present() -> None:
    items = [(key, value) for key, value in base_items() if key != "goal_note_0"]
    parsed = parse(items)
    assert parsed.ok is False
    assert "goal_0" in parsed.errors
    assert "Goal 1" in " ".join(parsed.error_list)


def test_goal_limit_is_ten() -> None:
    items = [(key, value) for key, value in base_items() if not key.startswith("goal_")]
    for index in range(11):
        items.extend(
            [
                (f"goal_title_{index}", f"Goal {index}"),
                (f"goal_done_{index}", "no"),
                (f"goal_difficulty_{index}", "3"),
                (f"goal_note_{index}", "Reason"),
            ]
        )
    parsed = parse(items)
    assert parsed.ok is False
    assert "goals" in parsed.errors


def test_plan_limit_is_ten() -> None:
    items = [(key, value) for key, value in base_items() if not key.startswith("plan_")]
    for index in range(11):
        items.append((f"plan_title_{index}", f"Plan {index}"))
    parsed = parse(items)
    assert parsed.ok is False
    assert "plans" in parsed.errors


def test_invalid_values_report_field_errors() -> None:
    items = [
        (key, "not-a-number" if key == "screen_minutes" else value) for key, value in base_items()
    ]
    parsed = parse(items)
    assert parsed.ok is False
    assert "screen_minutes" in parsed.errors


def test_blank_required_text_fails_after_strip() -> None:
    items = [(key, "   " if key == "went_well" else value) for key, value in base_items()]
    parsed = parse(items)
    assert parsed.ok is False
    assert "went_well" in parsed.errors
