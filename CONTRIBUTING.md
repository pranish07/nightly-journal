# Contributing

Purpose: Explain how to set up, test, and document changes in Nightly Journal.

Last verified: 2026-10-23

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
```

The defaults use SQLite and development secrets. Edit the copied `.env` for real email, database, or Gemini settings. Use the variable list in [docs/deployment.md](docs/deployment.md).

## Checks

CI runs these checks on pushes to `main` and on pull requests. Run them locally before pushing:

```bash
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
alembic check
```

Use `python -m ruff format .` only when you intend to reformat files.

## Code style

- Target Python 3.12.
- Keep the existing FastAPI, SQLAlchemy, Pydantic, and Jinja patterns.
- Use type hints and explicit timezone-aware datetimes.
- Do not add comments unless they explain non-obvious behavior.
- Do not add third-party runtime dependencies without a clear need.
- Keep secrets and personal data out of source and tests.

## Tests

- Put tests in `tests/` and follow the existing module naming.
- Use in-memory SQLite and an injected fixed clock for time-dependent behavior.
- Use the fake mailer and fake Gemini client instead of real network calls.
- Add a regression test for every bug fix.
- Add a route test when changing form, cron, or response behavior.
- Run the full suite, not only the changed module.

See [docs/testing.md](docs/testing.md) for the coverage map and examples.

## Migrations

1. Update `app/models.py`.
2. Generate a revision with Alembic.
3. Review named constraints and SQLite/Postgres compatibility.
4. Run `alembic upgrade head` and `alembic check`.
5. Update the migration tests if schema behavior changes.
6. Never edit an applied migration in a shared environment; add a new revision.

The initial revision is `9e95400cf356`. Its downgrade drops all application tables.

## Documentation

Update the relevant file in `docs/` when behavior changes. Keep `docs/README.md` as the index.

Before submitting docs:

- [ ] The document starts with a title, one-line purpose, and `Last verified: YYYY-MM-DD`.
- [ ] It describes current code, not an aspirational design.
- [ ] Missing features are labeled deferred and linked to the roadmap.
- [ ] Third-party limits have an official link and a re-check note.
- [ ] Commands and paths match the repository.
- [ ] No real secrets, personal email addresses, or journal text are included.
- [ ] Internal links resolve.
- [ ] The document stays focused and links to related docs instead of duplicating them.

Do not treat `DESIGN.md` as current behavior. Update the docs first, and change `DESIGN.md` only when the design itself changes.

## Commit and pull request checklist

- [ ] The change is scoped to one concern.
- [ ] Tests and lint pass.
- [ ] Migrations are included when the schema changes.
- [ ] Docs are updated for behavior, configuration, or operations changes.
- [ ] No `.env`, database file, build artifact, or secret is staged.
- [ ] The pull request explains the user-visible effect and any deployment steps.

## Secrets

- `.env` and `.env.*` are ignored except `.env.example`.
- Use placeholders in `.env.example`; never real credentials.
- Rotate any credential that is accidentally committed or logged.
- Do not paste journal entries into issues, pull requests, or test fixtures.

## Related docs

- [Documentation index](docs/README.md)
- [Testing](docs/testing.md)
- [Deployment](docs/deployment.md)
- [Security](docs/security.md)
