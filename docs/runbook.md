# Runbook

Purpose: Provide symptom-based troubleshooting for the current Nightly Journal deployment and local environment.

Last verified: 2026-10-23

## First checks

| Check | Command or location |
| --- | --- |
| App is alive | `curl -i https://<host>/healthz` |
| Current local time | The tick response includes `local_time` |
| Cron secret | Compare the scheduler header with `CRON_SECRET` |
| Recent email jobs | Query `email_log` in the Neon SQL editor |
| Render logs | Render Dashboard > service > Logs |
| Local tests | `python -m pytest -q` |

Useful SQL:

```sql
SELECT kind, local_date, status, attempts, last_error,
       lease_until, next_attempt_at, sent_at
FROM email_log
ORDER BY local_date DESC, kind
LIMIT 30;
```

```sql
SELECT id, local_date, mood, screen_minutes, created_at
FROM entries
ORDER BY local_date DESC
LIMIT 10;
```

## Symptom table

| Symptom | Likely cause | What to check / do |
| --- | --- | --- |
| No nightly email | Tick outside 21:00–23:00 NPT | Confirm the scheduler timezone and current Nepal time |
| No nightly email | Wrong `X-Cron-Secret` | Expect `403`; update the cron-job.org header |
| No nightly email | Render cold start or timeout | Check Render logs and cron-job.org execution history; add a `/healthz` warm-up |
| No nightly email | `email_log` row is `failed` | Read `last_error`; fix mail credentials or provider issue |
| No nightly email | Row is `sent` but no inbox mail | Check spam, Brevo/Resend logs, sender verification, recipient address |
| No nightly email | No row at all | The tick never reached the app or the window was wrong |
| Duplicate nightly email | Crash after provider accepted but before `sent` commit | Expected at-least-once behavior; see [Scheduling](./scheduling.md) |
| Duplicate nightly email | Two schedulers or overlapping jobs | Keep one scheduler; unique `(kind, local_date)` should limit claims |
| Weekly email missing | Not Saturday 06:00–12:00 NPT | Check scheduler timezone and weekly job history |
| Weekly email missing | Chart or insight failure | Search logs for `email_job_failed`; inspect `email_log.last_error` |
| Weekly email missing | Five failed attempts | Reset only after fixing the cause; see “Resetting a failed job” |
| Weekly email missing | Empty report | An empty week still sends a report with “not logged” days |
| Insight pending forever | Background task failed | Check logs; refresh `/thanks/{token}`; the entry is already saved |
| Insight always rule-based | Gemini key or model missing | Set `GEMINI_API_KEY` and `GEMINI_MODEL` |
| Insight always rule-based | Rate limit, timeout, auth, or invalid schema | Search logs for `gemini_insight_fallback reason=...` |
| Insight always rule-based | Model output rejected | Check the reason; fallback is expected for invalid JSON/schema |
| Insight email missing after submission | Insight mailer call failed | Check `email_log` for `kind='insight'`; there is no scheduler retry, but the insight remains on `/thanks/{token}` |
| Form link invalid or expired | Token older than 48 hours or tampered | Open the latest nightly email or send a new test email |
| Form says session expired | CSRF token expired | Reopen the form from the email |
| Form redirects to thanks | Entry already exists for that date | The app does not overwrite existing entries |
| “That date is not open yet” | Token date is in the future | Check server clock and token generation |
| “Add at least one goal…” | No goals and no no-goals toggle | Add a goal or select “No goals today” |
| Goal note error | A goal title is present without a note | Fill the note or remove the goal row |
| Database connection error | Neon suspended, quota reached, or bad URL | Check Neon status, CU-hours, storage, and `DATABASE_URL` |
| Database relation missing | Migrations not applied | Run `alembic upgrade head` |
| First request very slow | Render Free cold start | Expected; use a warm-up request |
| Cron job auto-disabled | Repeated failures | Re-enable it after fixing the URL/secret/timeout |
| Dashboard 404 or placeholder | Dashboard is not built | Expected; use the email form link |
| Test email says `send_failed` | SMTP/Resend auth or configuration | See “Test email” below |
| Test email says `not_found` | IMAP polling failed or mail not delivered | Check IMAP credentials, spam, and the 90-second timeout |

## Manual tick

Inside a valid window:

```bash
curl -i \
  -H "X-Cron-Secret: $CRON_SECRET" \
  https://<host>/cron/tick
```

Expected success:

```http
HTTP/2 202
```

```json
{"claimed":[{"kind":"nightly","local_date":"2026-10-23","attempts":1}],"local_time":"2026-10-23T21:05:00+05:45"}
```

Outside the window:

```json
{"claimed":[],"local_time":"..."}
```

Wrong secret:

```json
{"detail":"forbidden"}
```

## Test email

From a machine with the production environment loaded:

```bash
python -m app.cli send-test-email
```

Expected output:

```text
relay_accepted
```

With IMAP configured:

```text
relay_accepted
checking inbox...
delivered_to_inbox
```

or:

```text
relay_accepted
checking inbox...
not_found
```

`relay_accepted` means the provider accepted the message. It does not guarantee inbox placement. Check spam and provider logs if IMAP is not configured.

Common causes:

- Brevo SMTP login is wrong (it is not the relay hostname).
- Brevo SMTP key was replaced by an API key.
- Sender/domain is not verified.
- Port/security mismatch: port `2525` with `starttls` is the reference configuration.
- Resend API key is missing or the domain is unverified.
- `EMAIL_TO` is wrong.

## Weekly preview without sending

There is no weekly preview CLI. Use the actual builder to render the HTML, text, and PNGs to `out/weekly-preview/`:

```python
from datetime import date
from pathlib import Path

from app.config import get_settings
from app.db import make_engine, make_session_factory
from app.email_builder import build_weekly_email

saturday = date(2026, 10, 24)
settings = get_settings()
engine = make_engine(settings.database_url)
factory = make_session_factory(engine)
out = Path("out/weekly-preview")
out.mkdir(parents=True, exist_ok=True)

try:
    with factory() as session:
        message = build_weekly_email(session, settings, saturday)
    (out / "weekly.html").write_text(message.html, encoding="utf-8")
    (out / "weekly.txt").write_text(message.text, encoding="utf-8")
    for image in message.inline_images:
        (out / image.filename).write_bytes(image.content)
    print(message.subject)
    print(f"wrote {len(message.inline_images)} images to {out}")
finally:
    engine.dispose()
```

Warning: `build_weekly_email()` calls `get_or_create_weekly_insight()`. If no weekly insight exists for that range, it generates and stores one, and may call Gemini. Do not run it against production if you do not want that side effect.

The snippet writes to `out/`, which is ignored by Git.

## Inspecting email jobs

`email_log` is the source of truth:

- `sending`: a worker holds a five-minute lease.
- `sent`: the mailer accepted the message.
- `failed`: see `last_error` and `next_attempt_at`.

Retry rules are in [Scheduling](./scheduling.md). A row with `attempts >= 5` will not be claimed again.

### Resetting a failed job

Only do this after fixing the underlying cause. Example for one weekly job:

```sql
UPDATE email_log
SET status = 'failed',
    attempts = 0,
    lease_until = NULL,
    next_attempt_at = NULL,
    last_error = NULL
WHERE kind = 'weekly'
  AND local_date = DATE '2026-10-24';
```

The next valid tick can claim it again. Do not reset a `sent` row to force a resend unless a duplicate is acceptable.

## Neon and database checks

- Confirm the project is not suspended for CU-hour or network-transfer limits.
- Confirm storage is below the free-plan cap.
- Confirm `DATABASE_URL` uses `postgresql+psycopg://` and includes SSL as required by Neon.
- Run `alembic current` and `alembic upgrade head`.
- Run `alembic check` to detect model/schema drift.
- Do not point production at `nightly-journal.db`; the Render filesystem is ephemeral.

## Render cold starts

Render Free spins down after 15 minutes without inbound traffic and takes about a minute to wake. If cron-job.org times out at 30 seconds:

1. Add a `GET /healthz` job a few minutes before the window.
2. Increase the scheduler timeout if the plan supports it.
3. Keep the nightly and weekly windows wide enough to allow several ticks.

The tick claims work before returning, but the HTTP request still has to reach a running instance.

## Cron-job.org disabled jobs

cron-job.org can disable a job after repeated failures. Check:

- The URL is correct and uses HTTPS.
- `X-Cron-Secret` matches.
- The service is awake.
- The response is not a timeout.
- The job is inside the intended Nepal-time window.

Re-enable it only after the failure cause is fixed.

## Dashboard and login

There is no dashboard login to troubleshoot. `GET /` is a placeholder. Email “dashboard” links intentionally land there. See [Roadmap](./roadmap.md).

## Related docs

- [Architecture](./architecture.md)
- [Scheduling and idempotency](./scheduling.md)
- [Email](./email.md)
- [Deployment](./deployment.md)
- [Security](./security.md)
