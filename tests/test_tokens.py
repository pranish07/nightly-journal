from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.config import Settings
from app.tokens import (
    InvalidToken,
    make_form_csrf,
    make_form_token,
    read_form_token,
    verify_form_csrf,
)

DAY = date(2026, 10, 23)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="test",
        form_token_secret="form-secret-" + "x" * 40,
        csrf_secret="csrf-secret-" + "y" * 40,
    )


def test_form_token_round_trip(settings: Settings) -> None:
    token = make_form_token(DAY, settings)
    assert read_form_token(token, settings) == DAY
    assert "." in token


def test_form_token_rejects_tampering(settings: Settings) -> None:
    token = make_form_token(DAY, settings)
    tampered = ("A" if token[0] != "A" else "B") + token[1:]
    with pytest.raises(InvalidToken):
        read_form_token(tampered, settings)


def test_form_token_rejects_wrong_secret(settings: Settings) -> None:
    token = make_form_token(DAY, settings)
    other = settings.model_copy(update={"form_token_secret": "other-" + "z" * 40})
    with pytest.raises(InvalidToken):
        read_form_token(token, other)


def test_form_token_expires(settings: Settings) -> None:
    token = make_form_token(DAY, settings)
    expired = settings.model_copy(update={"form_token_max_age_seconds": -1})
    with pytest.raises(InvalidToken):
        read_form_token(token, expired)


def test_form_csrf_round_trip(settings: Settings) -> None:
    token = make_form_csrf(DAY, settings)
    assert verify_form_csrf(token, DAY, settings) is True
    assert verify_form_csrf(token, DAY + timedelta(days=1), settings) is False
    assert verify_form_csrf(None, DAY, settings) is False
    assert verify_form_csrf("", DAY, settings) is False


def test_form_csrf_rejects_tampering(settings: Settings) -> None:
    token = make_form_csrf(DAY, settings)
    with pytest.raises(InvalidToken):
        read_form_token(token, settings)
    tampered = ("A" if token[0] != "A" else "B") + token[1:]
    assert verify_form_csrf(tampered, DAY, settings) is False


def test_form_csrf_expires(settings: Settings) -> None:
    token = make_form_csrf(DAY, settings)
    expired = settings.model_copy(update={"csrf_max_age_seconds": -1})
    assert verify_form_csrf(token, DAY, expired) is False
