# Changelog

The project has no tagged releases yet. This file records completed implementation and documentation work.

## Unreleased

### Added

- Maintainer documentation under `docs/` covering architecture, data model, scheduling, streaks, AI insights, email, security, deployment, operations, testing, free-tier limits, roadmap, and decisions.
- Top-level README, contributing guide, and changelog.
- `.env.example` with placeholders for every supported setting.
- GitHub Actions CI running Ruff, pytest, and Alembic migration checks.
- `scripts/seed.py` for 30 days of local demo entries; it refuses production and PostgreSQL targets.
- `render.yaml` for a repeatable Render web service.
- `.github/workflows/schedule.yml` as an optional scheduler for `/cron/tick`.
- `scripts/trigger_cron.py` to call the authenticated tick endpoint using local settings.

### Changed

- No runtime behavior changed in the documentation pass.
- Token-tampering test now mutates the first token character, so it fails deterministically when a signed token is altered.
- Pytest resolves the project root via `pythonpath = ["."]`, so both `pytest` and `python -m pytest` work.
- Gemini 3 models request low thinking to avoid long insight generations and timeouts.
- Tests ignore the local `.env` so developer settings cannot change test behavior.
- Deployment docs now cover the Render Blueprint, cron-job.org, and the GitHub Actions scheduler.

## Initial implementation

### Added

- SQLAlchemy models for entries, goals, planned goals, insights, and email logs.
- Initial Alembic migration.
- Signed, expiring form links and CSRF protection.
- Entry form, thanks page, health endpoint, and cron endpoint.
- Goal and logging status calculations with a configurable completion threshold and one-day grace.
- Nightly and weekly scheduling windows in Nepal time.
- Durable email claims with leases, bounded attempts, and backoff.
- Brevo SMTP and Resend HTTPS mail adapters.
- Nightly email, insight email, and weekly report email.
- Weekly inline PNG charts for completion, sleep, screen time, and mood.
- Gemini insight generation with a strict schema and deterministic fallback.
- CLI test email and optional Gmail IMAP delivery check.
- Security headers, production configuration validation, and tests.
