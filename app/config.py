from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_FORM_SECRET = "dev-form-token-secret-change-me-000000"
_DEV_CSRF_SECRET = "dev-csrf-secret-change-me-00000000"
_DEV_CRON_SECRET = "dev-cron-secret-change-me-0000000000"


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = Field(default="sqlite:///./nightly-journal.db", min_length=1)
    public_base_url: str = "http://localhost:8000"
    form_token_secret: str = _DEV_FORM_SECRET
    csrf_secret: str = _DEV_CSRF_SECRET
    cron_secret: str = _DEV_CRON_SECRET
    streak_min_completion: float = Field(default=1.0, ge=0.0, le=1.0)
    trust_proxy_headers: bool = True
    form_token_max_age_seconds: int = Field(default=48 * 60 * 60, gt=0)
    csrf_max_age_seconds: int = Field(default=48 * 60 * 60, gt=0)
    log_level: str = "INFO"

    mail_transport: Literal["smtp", "resend"] = "smtp"
    email_from: str = "Nightly Journal <journal@example.com>"
    email_to: str = "you@example.com"
    smtp_host: str = "smtp-relay.brevo.com"
    smtp_port: int = Field(default=2525, gt=0, le=65535)
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_timeout_seconds: float = Field(default=20.0, gt=0)
    resend_api_key: str = ""
    resend_api_url: str = "https://api.resend.com/emails"
    resend_timeout_seconds: float = Field(default=20.0, gt=0)
    imap_host: str = ""
    imap_port: int = Field(default=993, gt=0, le=65535)
    imap_user: str = ""
    imap_password: str = ""
    imap_mailbox: str = "INBOX"

    gemini_api_key: str = ""
    gemini_model: str = Field(default="", max_length=100, pattern=r"^[A-Za-z0-9._-]*$")
    gemini_api_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_timeout_seconds: float = Field(default=20.0, gt=0)

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> Settings:
        if self.app_env != "production":
            return self
        weak = []
        if self.form_token_secret in {_DEV_FORM_SECRET, ""} or len(self.form_token_secret) < 32:
            weak.append("FORM_TOKEN_SECRET")
        if self.csrf_secret in {_DEV_CSRF_SECRET, ""} or len(self.csrf_secret) < 32:
            weak.append("CSRF_SECRET")
        if self.cron_secret in {_DEV_CRON_SECRET, ""} or len(self.cron_secret) < 32:
            weak.append("CRON_SECRET")
        if weak:
            raise ValueError(f"production requires strong secrets: {', '.join(weak)}")
        if not self.public_base_url.startswith("https://"):
            raise ValueError("PUBLIC_BASE_URL must use HTTPS in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
