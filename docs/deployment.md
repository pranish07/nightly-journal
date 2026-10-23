# Deployment

Purpose: Provide a first-deploy procedure for the current repository using Neon, Brevo or Resend, Gemini, Render, and cron-job.org.

Last verified: 2026-10-23

## What exists in the repository

Current deployment assets: `requirements.txt`, `requirements-dev.txt`, `.python-version` (`3.12`), `alembic.ini`, `alembic/`, and `app/main.py`.

Not present: `Dockerfile`, `render.yaml`, `.env.example`, a CI workflow, or a seed script.

Because there is no Docker entrypoint, migrations are not automatically run by a container start script. You must either configure the Render start command to run `alembic upgrade head` before Uvicorn or run migrations as a separate release step.

## Reference topology

```mermaid
flowchart LR
  U[Browser] --> R[Render Free web service]
  C[cron-job.org] -->|/cron/tick| R
  R --> N[(Neon PostgreSQL)]
  R --> B[Brevo SMTP 2525]
  R -. optional .-> X[Resend HTTPS]
  R -. optional .-> G[Gemini API]
  B --> I[Recipient inbox]
  X --> I
```

Render Free limitations that matter:

- 0.1 CPU / 512 MB RAM.
- Spins down after 15 minutes without inbound traffic; wake-up takes about a minute.
- Ephemeral filesystem; do not use local SQLite in production.
- Outbound TCP `25`, `465`, and `587` are blocked.
- Free instance hours: 750 per workspace per month.
- The service can be restarted at any time.
- Render's documentation says Free instances are not for production applications.

See [Free-tier limits](./free-tier-limits.md) for dated provider limits.

## 1. Create the database

1. Create a Neon project and database.
2. Copy a connection string.
3. Convert the scheme to SQLAlchemy's psycopg driver:

```text
postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require
```

Use the pooled or direct Neon connection string according to the Neon dashboard. The app creates a small pool (`pool_size=2`, `max_overflow=2`, `pool_recycle=300`, `pool_pre_ping=True`) and a 10-second connect timeout.

4. Keep the URL out of source control.

## 2. Prepare email

### Brevo SMTP (default)

1. Create a Brevo account and verify the sender address or domain used in `EMAIL_FROM`.
2. Open **Settings > SMTP & API**.
3. Copy the SMTP login and create/copy an SMTP key.
4. Use:

```text
MAIL_TRANSPORT=smtp
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=2525
SMTP_SECURITY=starttls
SMTP_USER=<Brevo SMTP login>
SMTP_PASSWORD=<Brevo SMTP key>
```

The SMTP login is not `smtp-relay.brevo.com`, and the SMTP key is not the Brevo API key. Port `2525` is the Render-compatible path.

### Resend HTTPS (optional)

Use this if SMTP is unavailable or you prefer an HTTPS API:

```text
MAIL_TRANSPORT=resend
RESEND_API_KEY=<Resend API key>
EMAIL_FROM=Nightly Journal <journal@your-verified-domain>
```

Verify the sending domain in Resend. The free plan has a daily and monthly quota; see [Free-tier limits](./free-tier-limits.md).

### Gmail API/OAuth

Not implemented. The current code has no Google OAuth client, refresh-token storage, Gmail API adapter, or Gmail scopes. Do not configure Google OAuth for this version.

### Gmail IMAP for test-email checks (optional)

This only checks whether a test message arrived:

```text
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USER=<Gmail address>
IMAP_PASSWORD=<Gmail app password>
IMAP_MAILBOX=INBOX
```

A Gmail app password requires 2-Step Verification. These credentials are separate from the SMTP credentials and are never logged by the app.

## 3. Prepare Gemini (optional)

1. Create a Gemini API key in Google AI Studio.
2. Set:

```text
GEMINI_API_KEY=<key>
GEMINI_MODEL=<model id shown in AI Studio>
```

`GEMINI_MODEL` is empty by default. If the key or model is empty, the app uses the deterministic rule-based fallback. The model ID is validated against `^[A-Za-z0-9._-]*$`.

The free tier's rate limits are model-dependent and content may be used to improve Google products. See [AI insights](./ai-insights.md).

## 4. Generate secrets

Generate independent random values:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Use separate values for:

- `FORM_TOKEN_SECRET`
- `CSRF_SECRET`
- `CRON_SECRET`

Production startup rejects empty values, the development defaults, or values shorter than 32 characters.

## 5. Environment variables

| Variable | Required | Default | Notes |
| --- | --- | --- | --- |
| `APP_ENV` | yes | `development` | Set `production` on Render |
| `DATABASE_URL` | yes | local SQLite | Use `postgresql+psycopg://...` in production |
| `PUBLIC_BASE_URL` | yes | `http://localhost:8000` | Must be HTTPS in production; no trailing slash needed |
| `FORM_TOKEN_SECRET` | yes | dev default | Strong random value in production |
| `CSRF_SECRET` | yes | dev default | Strong random value in production |
| `CRON_SECRET` | yes | dev default | Strong random value in production |
| `STREAK_MIN_COMPLETION` | no | `1.0` | `0.0..1.0` |
| `TRUST_PROXY_HEADERS` | no | `true` | Defined but unused in current code |
| `FORM_TOKEN_MAX_AGE_SECONDS` | no | `172800` | 48 hours |
| `CSRF_MAX_AGE_SECONDS` | no | `172800` | 48 hours |
| `LOG_LEVEL` | no | `INFO` | Used by the CLI logging setup; web logging is not centrally configured |
| `MAIL_TRANSPORT` | no | `smtp` | `smtp` or `resend` |
| `EMAIL_FROM` | yes | placeholder | Verified sender/domain |
| `EMAIL_TO` | yes | placeholder | Single recipient |
| `SMTP_HOST` | for SMTP | `smtp-relay.brevo.com` | Brevo relay |
| `SMTP_PORT` | for SMTP | `2525` | Render-compatible |
| `SMTP_USER` | for SMTP | empty | Brevo SMTP login |
| `SMTP_PASSWORD` | for SMTP | empty | Brevo SMTP key |
| `SMTP_SECURITY` | no | `starttls` | `starttls`, `ssl`, or `none` |
| `SMTP_TIMEOUT_SECONDS` | no | `20` | Socket timeout |
| `RESEND_API_KEY` | for Resend | empty | Resend API key |
| `RESEND_API_URL` | no | `https://api.resend.com/emails` | Override for testing |
| `RESEND_TIMEOUT_SECONDS` | no | `20` | HTTP timeout |
| `IMAP_HOST` | optional | empty | Test-email inbox check only |
| `IMAP_PORT` | no | `993` | IMAP SSL |
| `IMAP_USER` | optional | empty | Gmail address |
| `IMAP_PASSWORD` | optional | empty | Gmail app password |
| `IMAP_MAILBOX` | no | `INBOX` | Mailbox to search |
| `GEMINI_API_KEY` | optional | empty | Empty means fallback |
| `GEMINI_MODEL` | optional | empty | Empty means fallback |
| `GEMINI_API_BASE_URL` | no | Google v1beta URL | Override for tests/proxy |
| `GEMINI_TIMEOUT_SECONDS` | no | `20` | HTTP timeout |

For local development, put the same names in `.env`. There is no `.env.example` in the repository yet.

## 6. Create the Render service

Because there is no `render.yaml`, create the service manually:

1. Create a **Web Service** from the GitHub repository.
2. Runtime: Python.
3. Python version: `3.12` (from `.python-version`).
4. Build command:

```bash
pip install -r requirements.txt
```

5. Start command:

```bash
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

The `alembic upgrade head` portion is a manual deployment choice, not an application entrypoint. It makes migrations run on each start. For stricter release control, run migrations separately and use only:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

6. Health check path: `/healthz`.
7. Add all environment variables from the table above.
8. Deploy.

The service must bind to `0.0.0.0` and the port in `$PORT`. Render handles TLS for the public hostname.

## 7. Configure cron-job.org

Create two jobs:

### Nightly

- URL: `https://<your-host>/cron/tick`
- Method: `GET` or `POST`
- Schedule: every 5 minutes from 20:40 through 23:00 NPT
- Timezone: `Asia/Kathmandu`
- Header: `X-Cron-Secret: <CRON_SECRET>`

### Weekly

- URL: `https://<your-host>/cron/tick`
- Method: `GET` or `POST`
- Schedule: every 5 minutes Saturday 05:40 through 12:00 NPT
- Timezone: `Asia/Kathmandu`
- Header: `X-Cron-Secret: <CRON_SECRET>`

Optionally add a warm-up job:

- URL: `https://<your-host>/healthz`
- Schedule: a few minutes before each window.

cron-job.org has a default 30-second request timeout and may auto-disable a job after repeated failures. A Render cold start can exceed 30 seconds; the warm-up request reduces that risk. See [Scheduling](./scheduling.md).

## 8. First-deploy verification

1. Open `https://<your-host>/healthz`; expect `{"status":"ok"}`.
2. Open `/`; expect the placeholder page saying the dashboard is not part of this build.
3. Run the test email from a machine with the production environment:

```bash
python -m app.cli send-test-email
```

4. Confirm the output includes `relay_accepted`.
5. If IMAP is configured, confirm `delivered_to_inbox`.
6. Trigger a manual tick inside a window:

```bash
curl -i -H "X-Cron-Secret: $CRON_SECRET" https://<your-host>/cron/tick
```

Expect `202` and a `claimed` list. Outside the window, expect an empty `claimed` list.
7. Open the form link from a nightly email, submit an entry, and confirm `/thanks/{token}` shows the entry and insight (or “Insight pending”).
8. Check the `email_log` table for `nightly`, `insight`, and `weekly` rows as applicable.

## 9. Migrations and rollback

Apply migrations:

```bash
alembic upgrade head
```

Check schema drift:

```bash
alembic check
```

The initial migration revision is `9e95400cf356`. Its downgrade drops all application tables. Use downgrade only when you intend to remove data:

```bash
alembic downgrade -1
```

Render supports rollback to the two most recent previous deploys on Free. A code rollback does not automatically roll back the database. Keep migrations backward-compatible where possible.

## 10. Post-deploy checklist

- [ ] `APP_ENV=production`
- [ ] `PUBLIC_BASE_URL` is HTTPS
- [ ] Secrets are strong and unique
- [ ] `DATABASE_URL` points to Neon, not SQLite
- [ ] Migrations are applied
- [ ] Brevo sender/domain is verified
- [ ] `EMAIL_FROM` and `EMAIL_TO` are correct
- [ ] Test email reaches the inbox
- [ ] Cron jobs send `X-Cron-Secret`
- [ ] Cron schedules use `Asia/Kathmandu`
- [ ] Warm-up job exists or the scheduler timeout is sufficient
- [ ] `/healthz` succeeds
- [ ] A test entry submits and stores correctly
- [ ] Gemini key/model are set, or fallback is acceptable
- [ ] Logs do not contain secrets or journal text
- [ ] Provider free-tier usage is monitored

## Related docs

- [Architecture](./architecture.md)
- [Scheduling and idempotency](./scheduling.md)
- [Email](./email.md)
- [Security](./security.md)
- [Runbook](./runbook.md)
- [Free-tier limits](./free-tier-limits.md)
