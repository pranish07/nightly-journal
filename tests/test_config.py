from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_production_requires_strong_secrets_and_https() -> None:
    with pytest.raises(ValidationError, match="strong secrets"):
        Settings(app_env="production")

    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(
            app_env="production",
            public_base_url="http://example.com",
            form_token_secret="f" * 40,
            csrf_secret="c" * 40,
            cron_secret="k" * 40,
        )


def test_production_accepts_valid_secrets() -> None:
    settings = Settings(
        app_env="production",
        public_base_url="https://example.com",
        form_token_secret="f" * 40,
        csrf_secret="c" * 40,
        cron_secret="k" * 40,
    )
    assert settings.app_env == "production"


def test_production_requires_strong_cron_secret() -> None:
    with pytest.raises(ValidationError, match="CRON_SECRET"):
        Settings(
            app_env="production",
            public_base_url="https://example.com",
            form_token_secret="f" * 40,
            csrf_secret="c" * 40,
            cron_secret="short",
        )


def test_gemini_model_rejects_path_characters() -> None:
    with pytest.raises(ValidationError):
        Settings(gemini_model="models/gemini-test")
