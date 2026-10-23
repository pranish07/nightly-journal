# Nightly Journal — Design Document

Status: **awaiting approval**. No application code has been written.
Date: 2026-10-23
Target stack: Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, PostgreSQL, Jinja2, vanilla JS, Chart.js, matplotlib.

---

## 1. Decision required: Render Free blocks Gmail SMTP

This is a real conflict in the hard constraints, verified against current provider documentation:

- Render Free web services have blocked **outbound TCP 25, 465, and 587** since 2025-09-26.
- Gmail SMTP only accepts submission on ports 25, 465, or 587.
- Therefore **Gmail SMTP via `smtplib` cannot work from a Render Free web service**, regardless of app-password correctness.

This must be resolved before the mailer milestone. Options:

| Option | Keeps Gmail? | Keeps `smtplib`? | Free? | Cost / complexity | Notes |
|---|---:|---:|---:|---|---|
| **A. Brevo SMTP relay on port 2525 (recommended)** | Sender can be verified Gmail address | Yes | Yes (300/day) | Low | Render documents blocking only 25/465/587; Brevo explicitly supports 2525 for this case. Not Gmail's server. Verify with the test-email command immediately after deploy. |
| B. Gmail API over HTTPS | Yes | No | Yes | Medium | OAuth refresh token, no app password. Must publish the OAuth app to Production or refresh tokens expire after 7 days. |
| C. Resend HTTPS API | No | No | Yes (100/day, 3,000/mo) | Low | Simplest and most reliable. Can send to the account's own address from `onboarding@resend.dev`. Supports CID inline images. |
| D. GitHub Actions Gmail SMTP sender | Yes | Yes | Yes for public repos | High | Render tick queues; a scheduled workflow sends. Adds a second runtime, 5-minute delay, and secret management. |
| E. Render paid instance | Yes | Yes | No ($7/mo) | Low | Removes the SMTP port block, but violates the free-tier requirement. |

**Approved: A (Brevo SMTP on 2525).** It preserves the intended SMTP/`smtplib` design and the single Render service with the smallest change. The `Mailer` protocol keeps the transport replaceable; a Resend HTTPS adapter must be a config-only switch and a small adapter, not a refactor of email building.

The test-email command sends a uniquely tagged message, then checks Gmail IMAP (when `IMAP_*` is configured) for that tag/Message-ID in the inbox for up to 90 seconds. It reports `accepted_by_relay` even when IMAP is not configured, and `delivered_to_inbox` or `not_found` when it is. IMAP credentials are separate from Brevo SMTP credentials and are never logged.

---

## 2. Architecture

One Docker web service on Render Free, one Neon Postgres database. No SPA, no separate worker, no in-process scheduler.

```
cron-job.org ──POST /cron/tick (X-Cron-Secret)──┐
                                                ▼
Browser ──signed form token──▶ FastAPI ──▶ Neon Postgres
                                   │
                                   ├──▶ Gemini REST (insight)
                                   ├──▶ SMTP/HTTPS mailer
                                   └──▶ matplotlib PNGs (weekly)
Dashboard ──password session──▶ server-rendered HTML + vendored Chart.js
```

- **Sync SQLAlchemy + `def` endpoints.** FastAPI runs them in its threadpool, so `smtplib`, matplotlib, and `httpx` calls are off the event loop. One user does not justify async ORM complexity.
- **No APScheduler / background loop.** The external tick is the only scheduler. FastAPI `BackgroundTasks` only carry one already-claimed send after the tick returns `202`.
- **Cold starts are expected.** `/cron/tick` does only time checks and a small atomic DB claim; it returns quickly. Heavy rendering/sending happens after the response.
- **`/healthz` is liveness-only and does not query Postgres.** A DB-checking health check would keep Neon from scaling to zero and burn its 100 CU-hours.
- **SQLAlchemy connection settings:** `pool_pre_ping=True`, small pool, recycle; Neon suspend/resume is handled by pre-ping.
- **Migrations** run from the Docker entrypoint (`alembic upgrade head`), which is idempotent for this single-instance service.

Suggested modules:

```
app/
  main.py, config.py, db.py, models.py, schemas.py
  clock.py, scheduler.py, streaks.py, stats.py
  security.py, tokens.py, forms.py
  mailer.py, email_builder.py, charts.py, reports.py
  gemini.py, insights.py
  routes/{form,thanks,dashboard,auth,cron,health}.py
  templates/{form,thanks,dashboard,login,history,email/*}
  static/{app.css,form.js,dashboard.js,vendor/chart.umd.min.js}
alembic/, tests/, scripts/seed.py, .github/workflows/{ci,cron-fallback}.yml
Dockerfile, render.yaml, .env.example, README.md
```

---

## 3. Data model

All `*_date` columns are **Nepal local dates**. All `*_at` timestamps are **UTC** (`timezone=True`). Indexes cover every date lookup.

| Table | Columns and rules |
|---|---|
| `entries` | `id` PK; `local_date` date **unique, not null**; `wake_time` time; `bedtime_time` time; `screen_minutes` int 0–1440; `top_apps` text null; `no_goals` bool default false; `day_summary`, `went_well`, `improve_tomorrow`, `key_takeaway` text; `mood` smallint 1–5; `created_at`, `updated_at` UTC. One row per local date. |
| `goals` | `id` PK; `entry_id` FK → entries ON DELETE CASCADE, indexed; `position` int; `title` text; `normalized_title` text, indexed (for analytics); `done` bool; `difficulty` smallint 1–5; `note` text; unique `(entry_id, position)`. |
| `planned_goals` | `id` PK; `target_date` date, indexed; `position` int; `title` text; `normalized_title` text, indexed; `created_at`; unique `(target_date, position)`. These are proposals for the next form, not results. |
| `insights` | `id` PK; `kind` (`nightly`/`weekly`); `start_date`, `end_date`; `text` summary; `payload` JSON (wins, struggles, actions, pattern); `model_name`; `created_at`; unique `(kind, start_date, end_date)`. This makes weekly insight generation reusable across retries. |
| `email_log` | `id` PK; `kind` (`nightly`/`weekly`/`insight`); `local_date`; `status` (`sending`/`sent`/`failed`); `attempts`; `last_error` (truncated, no journal text); `lease_until`; `next_attempt_at`; `created_at`, `updated_at`, `sent_at`. **Unique `(kind, local_date)`**; index `(status, next_attempt_at)`. |

Goal titles get a stored `normalized_title` for analytics: Unicode NFKC, trim, collapse whitespace, casefold, strip trailing sentence punctuation. The original title is always displayed; normalization is only for grouping and duplicate checks (including "reuse yesterday's goals").

Constraints are enforced in the DB where possible and in pydantic/services for text lengths and cross-table rules. `JSON` (not Postgres-specific `JSONB`) keeps SQLite tests portable.

An entry is valid only if `no_goals = true` **or** it has at least one goal. The service enforces this; the pure status function rejects impossible rows rather than silently mis-scoring them.

---

## 4. Tick algorithm and scheduling

### Windows

| Job | Earliest | Hard cutoff | Dedupe key |
|---|---|---|---|
| Nightly | 21:00 NPT on date D | 23:00 NPT on D | `('nightly', D)` |
| Weekly | Saturday 06:00 NPT | Saturday 12:00 NPT | `('weekly', Saturday)` |

- Weekly report covers the **7 completed days before Saturday**: `Saturday - 7` through `Saturday - 1` inclusive (prior Saturday through Friday).
- No send occurs after the cutoff, so a 9 PM email cannot arrive at 3 AM.
- Saturday is not special-cased in form/streak logic; only the weekly report is Saturday-specific.

### Algorithm

1. Inject `Clock` (`now_utc()`), convert with `ZoneInfo("Asia/Kathmandu")`.
2. Pure functions `due_nightly(local_dt)` and `due_weekly(local_dt)` return a date or `None`. Windows are half-open: `start <= t < cutoff`.
3. For each due job, atomically **claim** `email_log`:
   - Try `INSERT (kind, local_date, status='sending', attempts=1, lease_until=now+5m)`.
   - On unique conflict, `UPDATE` a `failed` row, or an expired `sending` lease, only when `attempts < 5` and `next_attempt_at <= now`; set `sending`, bump attempts, renew lease.
   - If neither insert nor update affects a row, skip. This is the concurrency/double-ping guard.
4. Enqueue one background send per claimed row and return `202` with claimed job summary.
5. Background send builds/renders/sends, then marks `sent` (with `sent_at`) or `failed` (with a truncated error and exponential `next_attempt_at`). The next tick retries failed rows until the cutoff or 5 attempts.
6. Mailer itself retries transient SMTP/HTTP failures (3 attempts, 1/2/4s backoff). Auth failures fail fast.
7. Log every attempt with structured fields; never log the email body, journal text, tokens, or secrets.

**Exactly-once caveat:** the unique row makes duplicate *jobs* impossible under concurrency, retries, and double pings. SMTP/HTTP cannot guarantee exactly-once delivery if the process dies after the provider accepted the message but before `sent_at` commits. That window is tiny and unavoidable without provider idempotency keys; this design accepts at-least-once wire delivery in that crash case.

### External cron schedule

To stay far below Render's 750 free instance hours, cron-job.org runs **only in send windows**, every 5 minutes:

- Nightly: 20:40–23:00 NPT daily (the 20:40/20:45 ticks warm the cold instance).
- Weekly: Saturday 05:40–12:00 NPT.

This is still a 5-minute tick during every period that can send, but it does not keep Render awake 24/7 (~80h/month instead of ~744h). Cold starts are absorbed by the warm-up ticks. If cron-job.org is down for the whole window, the email is skipped by design; the next day/week is unaffected.

**cron-job.org cold-start failures:** its 30s request timeout is shorter than Render's ~1 minute cold start, so the very first tick after sleep can be recorded as a failure. This does not accumulate to the 25-consecutive-failure auto-disable threshold because the next 5-minute tick succeeds. To make this safer: create a separate warm-up job that only GETs `/healthz` 5–10 minutes before the window, keep the actual tick job on a separate schedule, and enable failure + auto-disable email notifications. If the warm-up job ever gets disabled, recreate it; the actual tick job still recovers on its second tick. The GitHub Actions fallback performs a warm-up request, waits 70 seconds, then ticks; it is documented as the more cold-start-tolerant fallback.

GitHub Actions fallback uses equivalent UTC windows, 5-minute minimum, and the same secret header. It is documented but not the primary trigger.

### Testability

- `Clock` is a dependency; tests use a frozen clock.
- Pure window tests: 20:59/21:00/22:59/23:00, midnight rollover, Saturday 05:59/06:00/11:59/12:00, Sunday, January and July (Nepal is fixed UTC+05:45, no DST).
- Idempotency tests: two ticks, duplicate insert, expired lease, failed retry with backoff, cutoff.
- Endpoint test: missing/wrong `X-Cron-Secret` → 401; valid secret → 202/200; no duplicate processing.

---

## 5. Status and streak rules

Pure functions in `streaks.py`, no DB or clock inside.

| Status | Rule |
|---|---|
| `ACHIEVED` | Entry logged, not `no_goals`, ≥1 goal, completion ratio ≥ `STREAK_MIN_COMPLETION` (default 1.0) |
| `PARTIAL` | Entry logged, goals exist, completion > 0 but below threshold |
| `MISSED` | Entry logged, goals exist, **0 done** |
| `NO_GOALS` | Entry logged with the toggle set. Neutral: does not extend or break the goal streak; does extend the logging streak. |
| `NOT_LOGGED` | No submission. Breaks both streaks. |

Precedence detail: zero done is `MISSED` even if the threshold is 0. A logged entry with no goals and no toggle is invalid.

- **Current goal streak:** consecutive `ACHIEVED` days ending at the latest relevant day, with `NO_GOALS` days skipped as neutral bridges. If today is not yet logged, start from yesterday (one-day grace); a second missing day breaks it. `NO_GOALS` alone does not end a live streak.
- **Longest goal streak:** same rules over all history; `PARTIAL`, `MISSED`, `NOT_LOGGED` reset.
- **Current logging streak:** consecutive submitted days, including `NO_GOALS`, with the same one-day grace for today.
- **Longest logging streak:** same over history.
- Missing calendar dates between records are filled as `NOT_LOGGED`.
- Threshold changes retroactively re-score stored goals because status is computed, never stored.

Tests: all-achieved, partial/missed, mixed, gaps, no-goals neutral bridge, no-goals-only, Saturday skip (both skipped and no-goals), today-not-yet-logged grace, threshold 0/0.5/1.0, empty history, current vs longest, logging streak with no-goals.

---

## 6. Form, planning, and submit flow

### Links and tokens

- Form URL: `/f/{token}`. Token is `itsdangerous.URLSafeTimedSerializer` with `FORM_TOKEN_SECRET`; payload is the local date. Max age **48h**. No sequential IDs in any URL.
- Thank-you URL: `/thanks/{token}`, same token. Dashboard/history use dates, not IDs.
- Form CSRF: stateless signed token tied to the form date, valid **48h** (aligned with the form token), verified with constant-time comparison. Login/logout CSRF uses the session.
- Token errors show a friendly page with a dashboard link; expired/tampered tokens are 403, not 500.

### GET form for date D

- If an entry exists for D, redirect to `/thanks/{token}`. (No editing; see trade-offs.)
- Otherwise prefill goals from `planned_goals` for D. If none, the dynamic list starts empty and the user can add goals.
- If yesterday (D-1) had goals, show a **"Reuse yesterday's goals"** button that appends those titles to today's goal list. It skips titles already present by `normalized_title`; the user still fills in today's done/difficulty/note.
- Planning section pre-fills from `planned_goals` for D+1, if any.
- "No goals today" checkbox is available every day, including Saturday.
- Dynamic goal/plan lists are plain `<template>` + vanilla JS; names are indexed (`goal_title_0`, `plan_title_1`, etc.) so the server can parse without JSON payloads. JS reindexes on add/remove; `<noscript>` explains the limitation. Done is a Yes/No select, avoiding unchecked-checkbox array problems.

### POST `/f/{token}`

1. Validate token, CSRF, date not in the future, and all fields with pydantic.
2. If `no_goals` is false: 1–10 goals; each title 1–120 chars, difficulty 1–5, note 1–280 chars. If true: ignore goal fields.
3. Screen minutes 0–1440; mood 1–5; text limits: summary 2,000, well/improve 1,000, takeaway 500, top apps 200. Planning: 0–10 titles, 1–120 chars.
4. Write **entry + goals + planned-goal consumption** in one transaction. Delete consumed `planned_goals` for D; insert `planned_goals` for D+1 only if D+1 has no entry yet. The user's answers are durable before any external API call.
5. Unique `entries.local_date` makes a duplicate/race submission harmless: on `IntegrityError`, fetch the existing entry and redirect to thanks.
6. Enqueue a background task with its own DB session and redirect 303 to `/thanks/{token}` (PRG) so refresh does not resubmit.
7. The background task: read the last 14 days of computed data, generate the AI insight with a 20s timeout + rule-based fallback, insert the insight (unique range key), then send the insight email with retries. Any failure is logged with safe fields; the entry is never rolled back.

### Thank-you page

- If the entry exists but the insight does not yet exist, show an **"Insight pending"** state with a short meta-refresh (or a Refresh link) and no fake content. The same page later shows the saved insight.
- When ready: status, streak summary, summary, wins, struggles with likely causes, exactly three actions, pattern, model label. All user/AI text is escaped. Link to the protected dashboard.
- A process restart in the tiny window between the entry commit and the background insight insert can leave an entry permanently pending. This is accepted for now; the entry is never lost, and a "regenerate insight" action is deferred.

### Insight email

`kind='insight'`, `local_date=D`, unique. HTML table layout with inline CSS and a plain-text alternative. No charts. If sending fails, the entry and insight remain saved and the thank-you page still shows the insight.

---

## 7. AI insights

- Plain REST `httpx` call to Gemini `generateContent`; `GEMINI_MODEL`, `GEMINI_API_KEY` from env. Model name is validated and never hardcoded. Key sent as `x-goog-api-key` header, not in a loggable URL.
- Input: a compact JSON payload of **last 14 days of computed stats** (statuses, goals, mood, screen, wake/bedtime, sleep duration) plus truncated free-text fields and goal notes. Stats are computed in Python; the prompt says the model must not calculate or invent numbers.
- Prompt injection: journal text lives only inside JSON data, never in the system instruction. System prompt explicitly says all payload strings are untrusted data, not instructions; no tools; output JSON only. Inputs are length-capped.
- Output: strict JSON validated by pydantic:

```json
{
  "summary": "string",
  "wins": ["string"],
  "struggles": [{"struggle": "string", "likely_cause": "string"}],
  "actions": ["string", "string", "string"],
  "pattern": "string"
}
```

- Validation: 1–5 wins, 0–5 struggles, **exactly 3 actions**, bounded lengths, no extra fields. Any HTTP error, 429, timeout, blocked response, malformed JSON, or schema failure falls back to a deterministic rule-based insight built from the same stats. Fallback `model_name = "rule-based"`.
- Weekly narrative uses the same schema but asks for actions for the coming week. It is stored once per Saturday range and reused if email retry occurs.
- Logging: kind, date, success/fallback, latency, HTTP status, error type. Never prompt or response bodies.
- README states that Gemini Free-tier inputs may be used by Google to improve products; prompts are intentionally minimal and journal text is truncated.

---

## 8. Email and weekly report

### Mailer

`Mailer` protocol with adapters: `SmtpMailer` (`smtplib`, STARTTLS/SSL, timeout, 3 transient retries) for Brevo on port 2525, plus a thin `ResendMailer` HTTP adapter behind the same `send(message)` interface. Switching is env-only (`MAIL_TRANSPORT=smtp|resend`) and must not touch email builders. Scheduled sends run in `BackgroundTasks`; insight emails run in the submit background task. Failures are logged, never swallowed silently.

The test-email CLI (`python -m app.cli send-test-email`) sends a uniquely tagged message and reports relay acceptance; with `IMAP_*` configured it polls Gmail IMAP INBOX for up to 90s and reports whether the message reached the inbox or was not found.

### Nightly email (21:00 NPT)

Short and warm: greeting, form link, current goal streak (with a gentle "start one tonight" fallback), **today's planned goals** (up to 10; "Nothing planned—add goals in tonight's form" when empty), yesterday's headline (insight summary, else key takeaway, else "No entry yesterday"), dashboard footer. No AI call at send time. Token generated at send time with 48h expiry.

### Weekly email (Saturday 06:00 NPT)

- 7-day range: prior Saturday through Friday.
- Metric cards: logged days, goal completion, current/longest goal streak, logging streak, average mood, average sleep, average screen time.
- Four inline CID PNG charts, each with one axis and alt text:
  1. Goal completion per day (0–100%; no-goals/not-logged bars visually distinct and explained).
  2. Wake and bedtime on an **anchored axis**: minutes after 18:00 local (`(hour*60+minute - 18*60) mod 1440`), y 0–1440 with labels 18:00, 21:00, 00:00, 03:00, 06:00, 09:00, 12:00, 15:00, 18:00. Two series, legend. Sleep duration uses `(wake - bed) mod 24h`.
  3. Screen time (minutes; one series).
  4. Mood (1–5; one series).
- Easiest and hardest goal with difficulty and the note (reason). Ties break by most recent date/position.
- AI narrative (summary, wins, struggles, actions, pattern), with rule-based fallback.
- Plain-text alternative with all numbers and text; no reliance on images.
- Gmail-safe HTML: table layout, inline CSS, dark text on light background, no external assets, CID images, preheader, descriptive image alt text. PNGs are small and optimized; matplotlib uses `Agg` and `Figure` directly.

### Charting and accessibility

- Okabe–Ito colorblind-safe palette. Status colors are paired with labels/symbols, never color alone.
- Dashboard charts: one axis per chart, legend for ≥2 series, `<canvas>` with `aria-label`, and a hidden data table for screen readers. Dark mode reads CSS variables and re-renders charts on `prefers-color-scheme` change.
- Chart.js is vendored under `static/vendor` (no CDN, no external dependency, CSP-friendly).

---

## 9. Dashboard

- Password login (`DASHBOARD_PASSWORD`), constant-time compare, session cookie signed by Starlette `SessionMiddleware` (HttpOnly, SameSite=Lax, Secure in production), CSRF on login/logout, in-memory sliding-window throttle (5 per IP / 15 min, plus a global cap). With `TRUST_PROXY_HEADERS=true` (Render), the client IP comes from the trusted `X-Forwarded-For` hop; the global cap still prevents header spoofing from fully bypassing throttling. Reset on restart is accepted for a single-user, single-instance app.
- Home shows **today's planned goals** (or today's goals if already submitted) at the top, then the calendar heatmap: last 12 weeks, weekday rows/week columns, status in text/`aria-label`, legend, links to logged entries.
- Trends: completion, mood, screen time, wake/bedtime (last 30 days); streaks; goal difficulty breakdown (stacked done/not-done, legend); history by month and entry detail.
- All server-rendered. No extra data API; chart data is embedded as escaped JSON read by `dashboard.js`.
- Responsive CSS, horizontal heatmap scroll on phones, focus styles, semantic headings/labels, and dark mode via `prefers-color-scheme`.

---

## 10. Security

- Signed, expiring form tokens; no sequential IDs.
- Dashboard session + CSRF; constant-time password comparison; login throttling.
- `X-Cron-Secret` required on `/cron/*`, constant-time compared.
- Jinja autoescape for HTML and email HTML; plain-text email templates do not HTML-escape; all text is treated as text.
- Secrets only via env; `.env.example` with placeholders; `.gitignore` excludes `.env`.
- CSP (`self` only), `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`.
- No secrets, tokens, email bodies, or full journal text in logs. Error logs record type/date/counts, not payloads.
- SQLAlchemy parameterized queries only.
- `PUBLIC_BASE_URL` validated; production requires HTTPS and strong secrets at startup.

---

## 11. Verified free-tier limits (2026-10-23)

These will be repeated with links and a "re-check before deploy" note in the README.

| Service | Current limits used / relevant |
|---|---|
| **Render Free web** | 750 instance hours/workspace/month; 512 MB RAM, 0.1 CPU; spins down after 15 min idle, ~1 min cold start; ephemeral disk; **outbound 25/465/587 blocked**; free Postgres expires after 30 days (not used). |
| **Neon Free** | 1 GB storage/project (increased from 0.5 GB on 2026-10-02); 100 CU-hours/project/month; scales to zero after 5 min idle; 5 GB public egress; 100 projects. |
| **cron-job.org** | Free; 1-minute minimum interval; 30s execution timeout; 64 KB response cap; fair use; auto-disables after >25 consecutive failures. We use every 5 min in send windows; a separate warm-up job absorbs cold-start timeouts. |
| **Gmail (if applicable)** | App password requires 2-Step Verification; personal Gmail sending limit is ~500 messages/recipients per day (far above need). SMTP ports are the blocker on Render Free. |
| **Gemini API Free** | Model availability and RPM/RPD limits vary by model and change; check AI Studio for the active model. Free-tier inputs may be used for product improvement. Model/key are env vars; failure falls back. |
| **GitHub Actions fallback** | Free for public repos; private free plan 2,000 min/month; scheduled workflows have a 5-minute minimum and may be delayed. |
| **Brevo (option A)** | Free 300 emails/day, SMTP ports 587/465/2525. |
| **Resend (option C)** | Free 3,000/month, 100/day; CID inline images supported. |

---

## 12. Testing and CI

- `ruff check` + `ruff format --check`; `pytest`.
- SQLite in-memory for unit/integration tests; a Postgres CI job runs `alembic upgrade head` and (optionally) the migration smoke tests.
- Tests:
  - Streak/status matrix and all edge cases listed in §5.
  - Scheduler windows, midnight, Saturday, cutoff, retries, idempotency, unique constraint, cron auth.
  - Email builders without sending: subject/body, escaping, plain text, CID images, 7-day range.
  - Gemini client with mocked `httpx`: valid JSON, malformed JSON, 429, timeout, blocked response, fallback, injection-like text treated as data.
  - Form GET/POST with TestClient: token validation, CSRF, validation errors, no-goals, planned prefill, next-day planning, duplicate submit, AI/email failure not losing the entry, XSS escaping.
  - Auth: login, throttling, CSRF, protected pages.
  - Chart generation produces valid non-empty PNGs.
- GitHub Actions CI runs lint/tests on every push/PR. A separate `cron-fallback.yml` is documented as a fallback; it is not the primary scheduler.

---

## 13. Milestones (each ends with tests green)

1. **Core:** config, DB, models, Alembic initial migration, pure status/streak functions, stats.
2. **Form/planning:** signed tokens, form GET/POST, validation, planned goals, thank-you page, insight-email stub.
3. **Mailer/tick:** `Mailer`, nightly email builder, tick endpoint, `email_log` claim/retry, cron auth, test-email CLI.
4. **AI:** Gemini client, strict validation, fallback, insight persistence, insight email.
5. **Weekly:** 7-day report, matplotlib charts, CID email, weekly insight, tick integration.
6. **Dashboard:** auth, heatmap, trends, difficulty, history, accessibility/dark mode.
7. **Ops:** Dockerfile, `render.yaml`, `.env.example`, README, seed script, CI, troubleshooting.

---

## 14. Trade-offs and deferred work

- **No entry editing** after submit. Keeps planning/streak semantics simple; users can view history but cannot correct an entry. A future edit feature would need an audit/updated-at policy.
- **In-memory login throttle** resets on restart. Adequate for one user/one instance; a DB-backed throttle is deferred.
- **Background task + DB lease, not a durable queue.** No extra service; at-least-once wire delivery is possible in a crash-after-provider-accept window.
- **Windowed cron, not 24/7.** Preserves free instance hours at the cost of cold starts outside windows. Warm-up ticks protect the 21:00/06:00 sends.
- **Background AI on submit.** The entry is durable immediately and the thank-you page handles "insight pending"; the cost is a small crash window between entry commit and insight insert, accepted for this single-user app.
- **Form tokens valid 48h.** Late entries are possible but do not trigger retroactive emails.
- **Weekly catch-up cutoff 12:00 Saturday.** A report missed past noon is skipped rather than arriving late.
- Deferred: multiple users, OAuth/accounts, entry editing, data export, custom domains, push notifications, configurable timezone, attachments, PDF reports.
- **Risk to call out in README:** Brevo 2525 egress on Render must be verified with the test-email command; if blocked, switch to an HTTPS transport. Limits and model names change; re-check before deploy.

---

## 15. Assumptions

- Single user, English UI, one recipient (`EMAIL_TO`, may equal sender).
- All reflection dates are Nepal local dates; display in NPT; storage timestamps UTC.
- No goals without the toggle is invalid; Saturday is ordinary for status/streak purposes.
- One submission per local date; no editing.
- Weekly report is generated from already-submitted data only.
- Dashboard is password-only; no usernames or multi-factor.
- Chart.js is vendored; no CDN or external asset dependency.
- A manual test-email command and an `.eml` weekly-report preview are sufficient for operational previews; no admin UI.

---

## 16. Approval status

Approved with changes on 2026-10-23:

1. Email transport: **A, Brevo SMTP on 2525**, with a thin Resend adapter kept behind the same interface.
2. Submit flow: entry/goals commit first; insight generation and insight email run in a background task; thank-you page handles "insight pending".
3. Login throttle trusts the Render `X-Forwarded-For` hop, plus a global cap.
4. Wake/bed chart uses an anchored axis in minutes after 18:00; sleep duration is `(wake - bed) mod 24h`.
5. Goal titles are normalized for analytics; "reuse yesterday's goals" is added; today's planned goals appear in the nightly email and dashboard home.
6. Form CSRF lifetime is 48h, aligned with the form token.
7. README will explain cron-job.org's 30s cold-start timeout, separate warm-up job, and auto-disable notifications.
