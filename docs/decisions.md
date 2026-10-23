# Decisions

Purpose: Record the architectural and product decisions that explain the current code, including alternatives that were rejected.

Last verified: 2026-10-23

## 0001 — Single-user journal, no account system

**Status:** Accepted for the current version.

**Context:** The product is a personal nightly journal with one owner. A full account system adds login, sessions, password reset, authorization, and a larger attack surface.

**Decision:** Treat the deployment as single-user. Use email form links as the write path. Do not build multi-user ownership or sharing.

**Consequences:**

- There is no dashboard login yet.
- `GET /` is a placeholder.
- Anyone with a valid form link can submit for that date until it expires or an entry exists.
- Adding multi-user support later requires schema and authorization changes.

## 0002 — PostgreSQL in production, SQLite in tests

**Status:** Accepted.

**Context:** The app needs a hosted relational database with reliable constraints. Tests need a fast, isolated database without external services.

**Decision:** Use PostgreSQL (Neon) in production and in-memory or temporary SQLite in tests. Use SQLAlchemy 2.x and Alembic.

**Consequences:**

- Production uses `postgresql+psycopg://`.
- SQLite tests do not prove every Postgres behavior, especially concurrency and constraint details.
- There is no Postgres CI job.
- The initial migration must remain portable enough for the test database.

## 0003 — Signed expiring form links plus CSRF

**Status:** Accepted.

**Context:** The nightly email must open a form without a login. A permanent link would remain usable forever.

**Decision:** Put the local date in an `itsdangerous` signed token with a 48-hour default lifetime. Use a separate signed CSRF token for the POST. Verify both server-side.

**Consequences:**

- Links expire and cannot be tampered with without the secret.
- The link is a bearer credential.
- Reopening an old email after 48 hours fails.
- There is no per-device session or revocation list.
- Secrets must be strong and rotated if exposed.

**Rejected:** A database-backed one-time link table. It would add cleanup and state for little benefit at this scale.

## 0004 — Compute statuses and streaks, do not store them

**Status:** Accepted.

**Context:** Status and streak values depend on the current date, the threshold, and historical gaps. Storing them would create consistency and backfill problems.

**Decision:** Derive statuses and streaks from entries, goals, and planned goals on read. Fill missing dates explicitly. Treat no-goals days as neutral and apply a one-day grace.

**Consequences:**

- The database has no status or streak columns.
- Changing `STREAK_MIN_COMPLETION` changes historical results.
- Range calculations can be more expensive but are simple at this scale.
- Tests can use fixed dates and explicit `DayRecord` values.

## 0005 — Durable email log with claims and at-least-once delivery

**Status:** Accepted.

**Context:** Cron ticks can overlap, retry, or arrive after a cold start. Sending an email is not transactional with the database.

**Decision:** Use `email_log` with a unique `(kind, local_date)` row, a `sending` lease, bounded attempts, and backoff. Claim work before sending. Mark `sent` only after the mailer accepts the message.

**Consequences:**

- Duplicate delivery is possible if the process crashes after provider acceptance and before the `sent` commit.
- Exactly-once delivery is not claimed.
- Stuck leases expire after five minutes.
- Authentication failures back off for a day.
- Five failed attempts require manual intervention.

## 0006 — External scheduler with wide windows

**Status:** Accepted.

**Context:** Render Free spins down and has no built-in cron for this service. Nightly and weekly jobs need a reliable trigger.

**Decision:** Use cron-job.org to call `/cron/tick` every five minutes inside wide Nepal-time windows. The app decides whether a job is due. Use a warm-up request to reduce cold-start timeouts.

**Consequences:**

- The scheduler needs the `X-Cron-Secret` header.
- The 30-second scheduler timeout can still fail during a cold start.
- The app tolerates repeated ticks through claims and unique rows.
- A GitHub Actions schedule is a possible fallback but is not configured.

## 0007 — Brevo SMTP on port 2525, Resend as HTTPS fallback

**Status:** Accepted.

**Context:** Render Free blocks outbound TCP `25`, `465`, and `587`. Gmail SMTP on `587` therefore cannot work from Render Free.

**Decision:** Use Brevo SMTP relay on port `2525` as the default. Keep a Resend HTTPS adapter behind the same `Mailer` interface as an alternative.

**Consequences:**

- The default transport is `smtp`.
- `SMTP_SECURITY=starttls` with port `2525` is the reference configuration.
- Brevo sender/domain verification is required.
- Resend requires a verified domain and its own quota.
- There is no Gmail API/OAuth adapter.

**Rejected:** Gmail API/OAuth for this version. It would add OAuth, token storage, Gmail scopes, and quota handling without solving a current requirement.

## 0008 — Gemini with strict schema and deterministic fallback

**Status:** Accepted.

**Context:** AI insights are optional. A failed AI call must not block the journal or the email flow.

**Decision:** Request JSON only, validate with a strict Pydantic model, use a 20-second timeout, and fall back to deterministic rules for missing credentials, rate limits, timeouts, invalid JSON, schema errors, or blocked responses. Store the result and reuse it.

**Consequences:**

- The app works without a Gemini key.
- Free-tier journal text may be used by Google to improve products.
- The fallback is less personalized than Gemini.
- The app does not retry Gemini in a loop.
- Prompt injection is reduced by treating journal text as data and not giving the model tools.

## 0009 — Weekly report on Saturday morning

**Status:** Accepted.

**Context:** The user wants a weekly review before the weekend. The report should cover the completed week, not a partial current day.

**Decision:** Run weekly jobs on Saturday from 06:00 to 12:00 Nepal time. Report the prior Saturday through Friday (`D-7` to `D-1`). Render four inline PNG charts and a weekly insight.

**Consequences:**

- The weekly job is separate from the nightly window.
- Saturday's own entry is not included.
- Charts are inline CIDs, not remote images.
- Weekly insight rows use `kind="weekly"` with a start and end date.
- There is no weekly preview CLI; the runbook uses a builder snippet.

## 0010 — Documentation describes current code, not the design document

**Status:** Accepted.

**Context:** `DESIGN.md` contains stale status, module maps, and test claims. The user approved a docs-only scope based on the actual implementation.

**Decision:** Create `docs/` as the maintainer reference. Describe current behavior, label missing features as deferred, and do not edit `DESIGN.md` in this pass.

**Consequences:**

- The docs are the source of truth for current behavior.
- `DESIGN.md` remains a historical design artifact.
- Documentation changes do not alter runtime behavior.
- Missing deployment assets are documented rather than invented.

## 0011 — Defer dashboard, Gmail API, manifests, CI, and preview CLI

**Status:** Accepted.

**Context:** The current code is complete for the email-first flow. Adding these features would require code, tests, and new security decisions.

**Decision:** Do not implement them in the documentation pass. Record them in the roadmap.

**Consequences:**

- `/` remains a placeholder.
- There is no login.
- There is no Gmail API/OAuth.
- There is no Dockerfile or `render.yaml`.
- There is no CI workflow.
- There is no weekly preview command.

## 0012 — No-goals days are neutral

**Status:** Accepted.

**Context:** A day with no goals is not a failure, but it also should not inflate a streak.

**Decision:** Represent no-goals days explicitly with `no_goals=True`. Exclude them from goal streaks and treat them as neutral. Logging streaks count logged days, including no-goals days.

**Consequences:**

- Goal streaks can bridge a no-goals day.
- Logging streaks do not require goals.
- The form must make the no-goals choice explicit.
- Status precedence is documented in [Streaks and statuses](./streaks-and-status.md).

## 0013 — Nepal local dates, UTC timestamps

**Status:** Accepted.

**Context:** The user’s day is defined in Nepal time, while servers and databases commonly store UTC.

**Decision:** Store entry dates as Nepal local dates. Store timestamps as UTC `DateTime(timezone=True)`. Convert at the boundaries. Reject naive datetimes.

**Consequences:**

- Scheduling windows are expressed in `Asia/Kathmandu`.
- `local_date` is not derived from a UTC timestamp at read time.
- Sleep duration wraps across midnight with modulo 24 hours.
- Chart axes use the 18:00 anchor.

## 0014 — Strict CSP and same-origin assets

**Status:** Accepted.

**Context:** Journal content is sensitive, and the app has no need for third-party scripts.

**Decision:** Serve scripts, styles, and fonts from the same origin. Allow images from the same origin or `data:`. Set `frame-ancestors 'none'`, `X-Frame-Options: DENY`, and `Referrer-Policy: no-referrer`.

**Consequences:**

- No CDN scripts or styles.
- Chart.js must be bundled or served locally if a dashboard is added.
- Inline scripts require a nonce or hash, or must be avoided.
- Email HTML is separate from the web CSP.

## 0015 — Accept the residual risks of an email-first personal app

**Status:** Accepted.

**Context:** A personal journal does not justify a full identity platform, but it still holds sensitive text.

**Decision:** Accept bearer-link access, no login, no application-layer encryption, and provider-dependent data handling. Document these risks and require strong secrets, HTTPS, and provider review.

**Consequences:**

- A leaked link is usable until expiry or submission.
- There is no rate limiting.
- Journal text is visible to the mail provider and, if enabled, Gemini.
- The deployment is not suitable for multi-user or high-assurance use without further work.

## Related docs

- [Architecture](./architecture.md)
- [Security](./security.md)
- [Scheduling and idempotency](./scheduling.md)
- [Email](./email.md)
- [AI insights](./ai-insights.md)
- [Roadmap](./roadmap.md)
