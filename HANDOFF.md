# Session handoff

Last updated: 2026-10-23

Project: Nightly Journal  
Repository: `https://github.com/pranish07/nightly-journal`  
Branch: `main`  
Current status: documentation pass complete and pushed. No runtime code changed.

## Resume in a new session

```bash
cd C:\Users\DELL\Documents\projects\nightly-journal
git pull --ff-only
.venv\Scripts\activate
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
alembic check
```

Read [docs/README.md](docs/README.md) first. It is the documentation index.

## Completed this session

- Reconstructed the actual behavior from code, tests, `DESIGN.md`, and the migration.
- Created the `docs/` directory and wrote 14 documentation pages:
  - `architecture.md`
  - `data-model.md`
  - `scheduling.md`
  - `streaks-and-status.md`
  - `ai-insights.md`
  - `email.md`
  - `security.md`
  - `deployment.md`
  - `runbook.md`
  - `testing.md`
  - `free-tier-limits.md`
  - `roadmap.md`
  - `decisions.md`
  - `README.md` (documentation index)
- Added top-level `README.md`, `CHANGELOG.md`, and `CONTRIBUTING.md`.
- Documented the current email transport decision: Brevo SMTP on port 2525 first, Resend HTTPS optional.
- Documented that Gmail API/OAuth, the dashboard, and authentication are not implemented.
- Verified third-party limits against official provider pages on 2026-10-23.
- Verified `210 passed`, Ruff clean, `alembic check` clean, and all relative docs links valid.
- Commits pushed to `origin/main`:
  - `1396f96` `docs: add architecture, data model, and scheduling docs`
  - `822479b` `docs: add operations, email, security, and reference docs`
  - `7d80993` `docs: add docs index, changelog, readme, and contributing guide`

## What is left

### Immediate housekeeping

- [ ] Review the new docs on GitHub for wording or accuracy.
- [ ] Add `.env.example` with placeholders only, then link it from `README.md`, `docs/README.md`, and `docs/deployment.md`.
- [ ] Consider adding CI for Ruff, pytest, and `alembic check`.
- [ ] Fix the flaky token-tampering test or make it tamper with a byte that always changes the signature.
- [ ] Decide whether to add an automatic retry path for failed insight emails.

### Product work not started

These are planned in [docs/roadmap.md](docs/roadmap.md), not implemented:

- [ ] Dashboard and authentication.
- [ ] Entry editing and deletion.
- [ ] Weekly email preview CLI.
- [ ] Data export and delete-all.
- [ ] Delivery hardening and an admin retry view.
- [ ] Gmail API/OAuth sending (currently deferred).

### Deployment

- [ ] This session did not deploy or verify a live Render instance.
- [ ] Use [docs/deployment.md](docs/deployment.md) for Neon, Brevo/Resend, Gemini, Render, and cron-job.org.
- [ ] Set production environment variables in Render; never commit secrets.
- [ ] Run `alembic upgrade head`, send a test email, and verify one `/cron/tick` inside a window.

## Known issues and gaps

- `tests/test_tokens.py::test_form_token_rejects_tampering` is flaky because it changes only the final base64 character; unused padding bits can leave the decoded signature unchanged. It passed on the final full run. This is documented in [docs/testing.md](docs/testing.md).
- Failed insight emails are not retried by `/cron/tick`; that endpoint only claims nightly and weekly jobs. The insight remains stored and visible on `/thanks/{token}`.
- There is no dashboard or login. `GET /` is a placeholder.
- `TRUST_PROXY_HEADERS` exists in settings but is unused.
- There is no `.env.example`, `render.yaml`, `Dockerfile`, or CI workflow.
- There is no application-level encryption; security depends on Neon, Render, and the mail provider.
- Render Free blocks SMTP ports `25`, `465`, and `587`; use Brevo port `2525` or Resend HTTPS.
- Render Free is not intended for production applications and can cold-start in about a minute.

## Key files

- `docs/README.md` — documentation index.
- `docs/architecture.md` — components and request flows.
- `docs/scheduling.md` — windows, claims, leases, retries.
- `docs/deployment.md` — deploy procedure and environment variables.
- `docs/runbook.md` — troubleshooting and weekly preview snippet.
- `docs/testing.md` — test commands and coverage map.
- `app/main.py` — app factory and security headers.
- `app/config.py` — all settings and production validation.
- `app/models.py` — ORM schema.
- `app/jobs.py` — email claims and retries.
- `app/gemini.py` — Gemini client and fallback.
- `app/mailer.py` — SMTP and Resend adapters.

## Safety notes

- Do not commit `.env`, database files, SMTP keys, API keys, cron secrets, or real journal text.
- Use separate strong values for `FORM_TOKEN_SECRET`, `CSRF_SECRET`, and `CRON_SECRET`.
- Keep `PUBLIC_BASE_URL` on HTTPS in production.
- Review provider free-tier data-use terms before storing sensitive content.
