from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session, sessionmaker
from starlette.concurrency import run_in_threadpool

from app.config import Settings
from app.dependencies import SessionDep
from app.forms import parse_entry_form
from app.insights import process_entry_insight
from app.models import Goal, PlannedGoal
from app.schemas import EntryForm
from app.services.entries import (
    get_entry_by_date,
    get_planned_goals,
    get_yesterday_goals,
    submit_entry,
)
from app.timeutils import local_date as today
from app.tokens import InvalidToken, make_form_csrf, read_form_token, verify_form_csrf
from app.web import format_date, render, token_error

router = APIRouter()


def _empty_raw() -> dict[str, Any]:
    return {
        "wake_time": "",
        "bedtime_time": "",
        "screen_minutes": "",
        "top_apps": "",
        "no_goals": False,
        "day_summary": "",
        "went_well": "",
        "improve_tomorrow": "",
        "key_takeaway": "",
        "mood": "",
        "goals": [],
        "plans": [],
    }


def _planned_goal_rows(planned: Iterable[PlannedGoal]) -> list[dict[str, str]]:
    return [
        {
            "title": goal.title,
            "done": "no",
            "difficulty": "3",
            "note": "",
        }
        for goal in planned
    ]


def _goal_rows(goals: Iterable[Goal]) -> list[dict[str, str]]:
    return [{"title": goal.title, "normalized": goal.normalized_title} for goal in goals]


def _form_context(
    settings: Settings,
    token: str,
    local_date: date,
    raw: dict[str, Any],
    *,
    errors: dict[str, str] | None = None,
    error_list: list[str] | None = None,
    yesterday_goals: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "token": token,
        "local_date": local_date,
        "date_label": format_date(local_date),
        "csrf_token": make_form_csrf(local_date, settings),
        "form": raw,
        "errors": errors or {},
        "error_list": error_list or [],
        "yesterday_goals": yesterday_goals or [],
        "max_goals": 10,
        "max_plans": 10,
    }


def _yesterday_goals_in_thread(
    session_factory: sessionmaker[Session],
    local_date: date,
) -> list[dict[str, str]]:
    with session_factory() as session:
        return _goal_rows(get_yesterday_goals(session, local_date))


def _submit_in_thread(
    session_factory: sessionmaker[Session],
    local_date: date,
    data: EntryForm,
) -> tuple[int, bool]:
    with session_factory() as session:
        entry, created = submit_entry(session, local_date, data)
        return entry.id, created


@router.get("/f/{token}", response_class=HTMLResponse)
def show_form(
    token: str,
    request: Request,
    session: SessionDep,
) -> Response:
    settings = request.app.state.settings
    try:
        local_date = read_form_token(token, settings)
    except InvalidToken:
        return token_error(
            request,
            "This form link is invalid or has expired. Open the latest link from your email.",
        )

    entry = get_entry_by_date(session, local_date)
    if entry is not None:
        return RedirectResponse(
            url=request.app.url_path_for("thanks", token=token),
            status_code=303,
        )

    raw = _empty_raw()
    raw["goals"] = _planned_goal_rows(get_planned_goals(session, local_date))
    raw["plans"] = [
        goal.title for goal in get_planned_goals(session, local_date + timedelta(days=1))
    ]

    return render(
        request,
        "form.html",
        _form_context(
            settings,
            token,
            local_date,
            raw,
            yesterday_goals=_goal_rows(get_yesterday_goals(session, local_date)),
        ),
    )


@router.post("/f/{token}", response_class=HTMLResponse)
async def submit_form(
    token: str,
    request: Request,
    background_tasks: BackgroundTasks,
) -> Response:
    settings = request.app.state.settings
    try:
        local_date = read_form_token(token, settings)
    except InvalidToken:
        return token_error(
            request,
            "This form link is invalid or has expired. Open the latest link from your email.",
        )

    if local_date > today():
        return token_error(request, "That date is not open yet.", status_code=403)

    form = await request.form()
    csrf = form.get("csrf_token")
    if not isinstance(csrf, str) or not verify_form_csrf(csrf, local_date, settings):
        return token_error(
            request,
            "Your form session expired. Open the latest link from your email and try again.",
        )

    parsed = parse_entry_form(form)
    if not parsed.ok:
        yesterday_goals = await run_in_threadpool(
            _yesterday_goals_in_thread,
            request.app.state.session_factory,
            local_date,
        )
        return render(
            request,
            "form.html",
            _form_context(
                settings,
                token,
                local_date,
                parsed.raw,
                errors=parsed.errors,
                error_list=parsed.error_list,
                yesterday_goals=yesterday_goals,
            ),
            status_code=422,
        )

    data = parsed.data
    assert data is not None
    entry_id, created = await run_in_threadpool(
        _submit_in_thread,
        request.app.state.session_factory,
        local_date,
        data,
    )
    if created:
        background_tasks.add_task(
            process_entry_insight,
            entry_id,
            request.app.state.session_factory,
            settings,
            request.app.state.mailer,
            request.app.state.gemini_client,
        )

    return RedirectResponse(
        url=request.app.url_path_for("thanks", token=token),
        status_code=303,
    )
