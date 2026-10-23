from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.engine import Engine

from app.config import Settings, get_settings
from app.db import make_engine, make_session_factory
from app.gemini import GeminiClient
from app.mailer import Mailer, make_mailer
from app.routes import cron, form, health, home, thanks
from app.timeutils import utc_now

APP_DIR = Path(__file__).resolve().parent
CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "form-action 'self'; "
    "base-uri 'none'; "
    "object-src 'none'; "
    "frame-ancestors 'none'"
)


def create_app(
    settings: Settings | None = None,
    engine: Engine | None = None,
    mailer: Mailer | None = None,
    clock: Callable[[], datetime] | None = None,
    gemini_client: GeminiClient | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    app_engine = engine or make_engine(app_settings.database_url)
    session_factory = make_session_factory(app_engine)
    templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        app_engine.dispose()

    app = FastAPI(
        title="Nightly Journal",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = app_settings
    app.state.engine = app_engine
    app.state.session_factory = session_factory
    app.state.templates = templates
    app.state.mailer = mailer or make_mailer(app_settings)
    app.state.clock = clock or utc_now
    app.state.gemini_client = gemini_client

    app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

    @app.middleware("http")
    async def security_headers(request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        if request.url.path.startswith(("/f/", "/thanks/")):
            response.headers["Cache-Control"] = "no-store"
        elif request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        if app_settings.app_env == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    app.include_router(home.router)
    app.include_router(health.router)
    app.include_router(form.router)
    app.include_router(thanks.router)
    app.include_router(cron.router)
    return app


app = create_app()
