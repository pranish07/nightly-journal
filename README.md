# Nightly Journal

A single-user journal with a nightly email check-in, goal and streak tracking, Gemini insights, and a Saturday weekly report.

## Status

The current version is **email-first**. There is no dashboard or login yet: `GET /` is a placeholder, and dashboard links in email intentionally land there.

Implemented:

- Signed, expiring nightly form links with CSRF protection.
- Entries with goals, planned goals, and no-goals days.
- Status and streak calculations with a one-day grace.
- Nightly, insight, and weekly email.
- Brevo SMTP on port 2525 or Resend over HTTPS.
- Gemini insights with a deterministic rule-based fallback.
- Weekly inline PNG charts.
- Durable email claims, retries, and backoff.

Not implemented:

- Dashboard and authentication.
- Gmail API/OAuth sending.
- Entry editing or deletion UI.
- Weekly preview CLI.
- Dockerfile.

## Requirements

- Python 3.12 (`.python-version`)
- SQLite for local smoke testing, or PostgreSQL/Neon
- A Brevo SMTP key or Resend API key for email
- Optional Gemini API key and model

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env   # optional; edit for real email, database, or Gemini
alembic upgrade head
uvicorn app.main:app --reload
```

The defaults use SQLite (`nightly-journal.db`), development secrets, and placeholder email addresses. For real email, edit the copied `.env` and see the variable list in [docs/deployment.md](docs/deployment.md). Do not use the development secrets in production.

Open `http://localhost:8000/` for the placeholder page and `http://localhost:8000/healthz` for health.

## Demo data

To fill the local SQLite database with 30 days of demo entries:

```bash
alembic upgrade head
python -m scripts.seed
```

The seed script creates varied goals, three no-goals days, four missed days, and realistic moods, sleep times, and screen time. It refuses to run when `APP_ENV=production` or when `DATABASE_URL` points at PostgreSQL, and it only writes to a file-backed SQLite database. Existing dates are left untouched, so re-running fills in missing days. `python scripts/seed.py` works too.

## Tests

```bash
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
alembic check
```

The current suite has 216 tests. See [docs/testing.md](docs/testing.md).

## Documentation

Start at [docs/README.md](docs/README.md).

Most useful pages:

- [Architecture](docs/architecture.md)
- [Data model](docs/data-model.md)
- [Scheduling and idempotency](docs/scheduling.md)
- [Email](docs/email.md)
- [Security](docs/security.md)
- [Deployment](docs/deployment.md)
- [Runbook](docs/runbook.md)
- [Roadmap](docs/roadmap.md)

`DESIGN.md` is the original design document and is not the current source of truth.

## Deployment summary

The reference deployment is Neon PostgreSQL, Brevo SMTP on port 2525, optional Gemini, Render Free, and cron-job.org. `render.yaml` defines the Render service and `.github/workflows/schedule.yml` can trigger `/cron/tick` instead of cron-job.org. Render Free blocks SMTP ports `25`, `465`, and `587`, which is why port `2525` is required. See [docs/deployment.md](docs/deployment.md) and [docs/free-tier-limits.md](docs/free-tier-limits.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). CI runs the same checks on pushes to `main` and on pull requests.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).
