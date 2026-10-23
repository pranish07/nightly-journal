from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from app.dependencies import SessionDep
from app.services.entries import get_entry_by_date, get_nightly_insight
from app.tokens import InvalidToken, read_form_token
from app.web import format_date, render, token_error

router = APIRouter()


@router.get("/thanks/{token}", response_class=HTMLResponse)
def thanks(
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
            "This link is invalid or has expired. Open the latest link from your email.",
        )

    entry = get_entry_by_date(session, local_date)
    if entry is None:
        return token_error(
            request,
            "That entry was not found. Submit the form first, then open this page again.",
            status_code=404,
        )

    goals_total = len(entry.goals)
    goals_done = sum(1 for goal in entry.goals if goal.done)
    completion_percent = round((goals_done / goals_total) * 100, 1) if goals_total else None

    return render(
        request,
        "thanks.html",
        {
            "token": token,
            "local_date": local_date,
            "date_label": format_date(local_date),
            "entry": entry,
            "insight": get_nightly_insight(session, local_date),
            "goals_total": goals_total,
            "goals_done": goals_done,
            "completion_percent": completion_percent,
        },
    )
