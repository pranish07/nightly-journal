from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.web import render

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return render(request, "home.html")
