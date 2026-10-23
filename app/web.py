from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse


def format_date(value: date) -> str:
    return f"{value.strftime('%A, %B')} {value.day}, {value.year}"


def render(
    request: Request,
    template_name: str,
    context: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
) -> HTMLResponse:
    values: dict[str, Any] = {"request": request}
    if context:
        values.update(context)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name=template_name,
        context=values,
        status_code=status_code,
    )


def token_error(
    request: Request,
    message: str,
    *,
    status_code: int = 403,
) -> HTMLResponse:
    return render(
        request,
        "token_error.html",
        {"message": message},
        status_code=status_code,
    )
