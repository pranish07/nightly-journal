from __future__ import annotations

from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from sqlalchemy.orm import Session

from app.config import Settings
from app.mailer import OutboundEmail
from app.models import Entry, Insight
from app.services.entries import (
    get_planned_goals,
    get_streak_stats,
    get_yesterday_headline,
)
from app.tokens import make_form_token
from app.web import format_date

EMAIL_DIR = Path(__file__).resolve().parent / "templates" / "email"

_env = Environment(
    loader=FileSystemLoader(str(EMAIL_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    undefined=StrictUndefined,
    trim_blocks=False,
    lstrip_blocks=True,
)


def build_nightly_email(
    session: Session,
    settings: Settings,
    local_date: date,
) -> OutboundEmail:
    base_url = settings.public_base_url.rstrip("/")
    token = make_form_token(local_date, settings)
    context = {
        "date_label": format_date(local_date),
        "form_url": f"{base_url}/f/{token}",
        "dashboard_url": f"{base_url}/",
        "planned_goals": get_planned_goals(session, local_date),
        "yesterday_headline": get_yesterday_headline(session, local_date),
        "streak": get_streak_stats(
            session,
            local_date,
            settings.streak_min_completion,
        ),
    }
    return OutboundEmail(
        subject=f"Tonight's check-in: {context['date_label']}",
        html=_env.get_template("nightly.html").render(**context),
        text=_env.get_template("nightly.txt").render(**context),
    )


def build_insight_email(
    session: Session,
    settings: Settings,
    insight: Insight,
    entry: Entry,
) -> OutboundEmail:
    base_url = settings.public_base_url.rstrip("/")
    context = {
        "date_label": format_date(entry.local_date),
        "dashboard_url": f"{base_url}/",
        "payload": insight.payload or {},
        "summary": (insight.payload or {}).get("summary") or insight.text,
        "model_name": insight.model_name,
        "streak": get_streak_stats(
            session,
            entry.local_date,
            settings.streak_min_completion,
        ),
    }
    return OutboundEmail(
        subject=f"Your nightly insight: {context['date_label']}",
        html=_env.get_template("insight.html").render(**context),
        text=_env.get_template("insight.txt").render(**context),
    )
