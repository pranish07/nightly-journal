# Testing

Purpose: Explain how Nightly Journal is tested, how to run the suite, and where to add coverage for new behavior.

Last verified: 2026-10-23

## Commands

```bash
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
alembic check
```

The current suite has **210 tests**. `pyproject.toml` sets `testpaths = ["tests"]` and targets Python 3.12 for Ruff.

## Test environment

- Most tests use in-memory SQLite: `make_engine("sqlite://")`.
- `Base.metadata.create_all()` creates the schema for model, service, route, and job tests.
- SQLite foreign keys are enabled through the engine event listener in `app/db.py`.
- Migration tests use a temporary SQLite file and Alembic.
- Time-dependent code accepts an injected clock. Tests use a fixed value such as:

```python
NOW = datetime(2026, 10, 23, 15, 15, tzinfo=UTC)
```

`create_app(..., clock=lambda: NOW)` and job/insight functions receive the same clock where relevant. This keeps windows, leases, and retry times deterministic.

There is no `tests/conftest.py`; fixtures are local to each test module.

## Module coverage

| Test module | Covers |
| --- | --- |
| `test_cli.py` | Test-email success/failure, relay output, IMAP polling, CLI dispatch |
| `test_config.py` | Production secret/HTTPS validation, Gemini model character validation |
| `test_email_builder.py` | Nightly email context, yesterday fallback, escaping, empty database |
| `test_forms.py` | Parsing, stripping, no-goals toggle, limits, validation errors |
| `test_gemini.py` | Valid JSON, bad output, rate limit, timeout, blocked/safety responses, fallback |
| `test_insights.py` | Payload shape/truncation, fallback persistence/reuse, insight email, failure handling |
| `test_jobs.py` | Claim insert, active lease, expired lease, backoff, max attempts, sent/failed, weekly charts |
| `test_mailer.py` | SMTP multipart, auth failure, retries, Resend payload/auth/transient/permanent errors, transport selection, CID images |
| `test_migrations.py` | Initial upgrade/downgrade and migrated-database check constraints |
| `test_models.py` | Normalization, ordering, cascade, check constraints, uniqueness, JSON round trip |
| `test_normalization.py` | NFKC, whitespace, case folding, trailing punctuation |
| `test_routes_cron.py` | Secret enforcement, window behavior, nightly/weekly sends, duplicate tick, failure recording |
| `test_routes_form.py` | Form render, invalid token/CSRF, planned goals, create/redirect, thanks, duplicate POST, future date, no-goals, escaping, headers |
| `test_scheduler.py` | Nightly/weekly boundaries and Saturday behavior |
| `test_services_entries.py` | Entry creation, no-goals, duplicate submit, next-day plan protection, metrics |
| `test_stats.py` | Gap filling, sleep calculation, no-goals neutrality, aggregates, validation |
| `test_streaks.py` | Status precedence, threshold, grace, no-goals bridging, historical maxima, range fill |
| `test_timeutils.py` | 18:00 anchor wrapping, sleep wrap, Nepal offset, naive datetime rejection |
| `test_tokens.py` | Form/CSRF round trip, tampering, wrong secret, expiry |
| `test_weekly.py` | Weekly range, goal ties, weekly payload, insight reuse/Gemini, PNG alt text, weekly email |

## What is not covered

- Dashboard, login, sessions, and login throttling do not exist.
- Gmail API/OAuth does not exist.
- There is no browser end-to-end test.
- There is no Postgres CI job; migration tests use SQLite.
- There is no CI workflow at all.
- There is no test for every possible Gemini model/rate-limit variant.

## Adding a streak edge case

`compute_streaks()` takes an iterable of `DayRecord` and an explicit `as_of`. Add a focused test in `tests/test_streaks.py`:

```python
from datetime import date

from app.streaks import DayRecord, DayStatus, compute_streaks, status_for


def test_new_edge_case() -> None:
    records = [
        DayRecord(date(2026, 10, 21), logged=True, no_goals=False, goals_total=1, goals_done=1),
        DayRecord(date(2026, 10, 22), logged=True, no_goals=False, goals_total=1, goals_done=0),
    ]
    stats = compute_streaks(records, as_of=date(2026, 10, 23), threshold=1.0)
    assert stats.current_goal == 0
    assert status_for(records[-1], 1.0) is DayStatus.MISSED
```

Prefer a table-driven test when the case is another status/threshold combination. Keep the fixed `as_of` explicit so the test does not depend on the real date.

## Adding a route test

Use the pattern in `tests/test_routes_form.py`:

1. Build an in-memory engine.
2. Create the schema with `Base.metadata.create_all(engine)`.
3. Inject a fake mailer and fixed clock into `create_app`.
4. Use `TestClient` to call the route.
5. Assert both the response and the database state.

Do not assert on real email delivery or real Gemini calls. Use the fake mailer and a fake Gemini client or fallback configuration.

## Adding a migration

1. Update `app/models.py`.
2. Generate a revision with Alembic.
3. Review the generated migration for SQLite/Postgres compatibility and named constraints.
4. Run `alembic upgrade head` and `alembic check`.
5. Add or update a migration test if the schema behavior changes.

## Known warning

The suite has been run successfully with only a Starlette/httpx deprecation warning. Treat new warnings as review items rather than silently accepting them.

`test_form_token_rejects_tampering` can intermittently fail because it changes only the final base64 character of the token. The unused padding bits can leave the decoded signature unchanged. Rerun the test before treating that failure as a regression; the test itself is the fragile part.

## Related docs

- [Architecture](./architecture.md)
- [Data model](./data-model.md)
- [Scheduling and idempotency](./scheduling.md)
- [Streaks and statuses](./streaks-and-status.md)
