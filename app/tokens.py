from __future__ import annotations

import secrets
from datetime import date

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import Settings

FORM_TOKEN_SALT = "nightly-journal-form"
FORM_CSRF_SALT = "nightly-journal-form-csrf"


class InvalidToken(Exception):
    """Raised when a signed token is missing, tampered with, or expired."""


def _serializer(secret: str, salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key=secret, salt=salt)


def make_form_token(local_date: date, settings: Settings) -> str:
    return _serializer(settings.form_token_secret, FORM_TOKEN_SALT).dumps(local_date.isoformat())


def read_form_token(token: str, settings: Settings) -> date:
    try:
        payload = _serializer(settings.form_token_secret, FORM_TOKEN_SALT).loads(
            token,
            max_age=settings.form_token_max_age_seconds,
        )
    except (BadSignature, SignatureExpired) as exc:
        raise InvalidToken("invalid form token") from exc
    if not isinstance(payload, str):
        raise InvalidToken("invalid form token payload")
    try:
        return date.fromisoformat(payload)
    except ValueError as exc:
        raise InvalidToken("invalid form token date") from exc


def make_form_csrf(local_date: date, settings: Settings) -> str:
    return _serializer(settings.csrf_secret, FORM_CSRF_SALT).dumps(local_date.isoformat())


def verify_form_csrf(token: str | None, local_date: date, settings: Settings) -> bool:
    if not token:
        return False
    try:
        payload = _serializer(settings.csrf_secret, FORM_CSRF_SALT).loads(
            token,
            max_age=settings.csrf_max_age_seconds,
        )
    except (BadSignature, SignatureExpired):
        return False
    if not isinstance(payload, str):
        return False
    return secrets.compare_digest(payload, local_date.isoformat())
