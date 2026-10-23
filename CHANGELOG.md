# Changelog

The project has no tagged releases yet. This file records completed implementation and documentation work.

## Unreleased

### Added

- Maintainer documentation under `docs/` covering architecture, data model, scheduling, streaks, AI insights, email, security, deployment, operations, testing, free-tier limits, roadmap, and decisions.
- Top-level README, contributing guide, and changelog.

### Changed

- No runtime behavior changed in the documentation pass.

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
