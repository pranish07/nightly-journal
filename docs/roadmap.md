# Roadmap

Purpose: Separate what the current repository actually implements from planned, deferred, and out-of-scope work.

Last verified: 2026-10-23

This roadmap is directional. It contains no dates or delivery commitments.

## Shipped

The current codebase includes:

- SQLAlchemy models and an initial Alembic migration.
- Signed, expiring nightly form links and CSRF protection.
- Entry creation with goals, planned goals, no-goals days, and validation.
- Status, streak, and range-stat calculations.
- Nightly and weekly scheduling windows in Nepal time.
- Durable `email_log` claims, leases, retries, and backoff.
- Brevo SMTP and Resend HTTPS mail adapters.
- Nightly email, insight email, and weekly email with inline PNG charts.
- Gemini insights with a strict schema and deterministic fallback.
- CLI test email and optional Gmail IMAP delivery check.
- Security headers, production config validation, and tests.

The dashboard is **not** shipped. `GET /` is a placeholder, and “dashboard” links in email intentionally land there.

## Next

### 1. Dashboard and authentication

**Problem:** The only way to read history and charts is email. `/` is a placeholder, and there is no login.

**Scope:**

- Password-based single-user login.
- Server-side sessions or signed session cookies with rotation.
- Login throttling and a logout action.
- Protected dashboard routes.
- History list, entry detail, streak/status summary, and charts.
- Chart.js or a server-rendered chart approach that fits the existing CSP.

**Acceptance criteria:**

- Unauthenticated requests to dashboard routes redirect to login or return `401`.
- Login failures are rate-limited.
- Session cookies are `HttpOnly`, `Secure` in production, and `SameSite=Lax` or stricter.
- CSRF protection exists on state-changing dashboard requests.
- Tests cover login, logout, unauthorized access, and session expiry.
- The existing email form flow still works.

### 2. Entry editing and deletion

**Problem:** Entries are immutable from the app. A typo requires direct database access.

**Scope:**

- Edit an existing entry from the dashboard.
- Preserve the one-entry-per-date rule.
- Recompute insights or mark them stale when entry content changes.
- Delete an entry with confirmation.
- Define whether deletion also removes linked insights.

**Acceptance criteria:**

- Editing cannot create a second entry for the same date.
- Updated values are reflected in status, streaks, and charts.
- Deletion behavior for insights is explicit and tested.
- Form-token access remains read-only or is intentionally limited.

### 3. Weekly preview CLI

**Problem:** There is no supported way to preview a weekly email without sending it. The runbook uses an inline Python snippet.

**Scope:**

- A CLI command such as `python -m app.cli preview-weekly --date YYYY-MM-DD`.
- Write HTML, text, and PNGs to a chosen directory.
- Read-only mode that does not create a weekly insight.
- Optional `--send` flag with an explicit confirmation.

**Acceptance criteria:**

- Preview does not send email.
- Read-only preview does not write to `insights`.
- Output paths are documented.
- Tests cover both read-only and insight-generating modes.

### 4. Operational manifests and examples

**Problem:** There is no `.env.example`, `render.yaml`, `Dockerfile`, or CI workflow.

**Scope:**

- `.env.example` with placeholders only.
- Optional `render.yaml` for a repeatable Render service.
- Optional Dockerfile if a non-Render host is needed.
- CI for Ruff, pytest, and `alembic check`.
- A docs link checker if it can run without secrets.

**Acceptance criteria:**

- No real secrets or personal addresses are committed.
- A new contributor can copy `.env.example` and run the app.
- CI runs on pull requests and does not require production credentials.
- Deployment docs match the manifests.

### 5. Data portability and privacy controls

**Problem:** There is no export or delete-all flow.

**Scope:**

- JSON export of entries, goals, planned goals, and insights.
- Delete-all with confirmation and a clear backup warning.
- Document what is sent to Gemini and the mail provider.

**Acceptance criteria:**

- Export includes stable field names and dates.
- Delete-all is authenticated and CSRF-protected.
- Docs explain provider retention and free-tier data use.

### 6. Delivery hardening

**Problem:** Nightly and weekly delivery is at-least-once, insight email has no scheduler retry, and there is no admin UI for failed jobs.

**Scope:**

- A small admin view for `email_log` and retry actions.
- Optional bounce/complaint handling if the provider exposes webhooks.
- A documented retention policy for old email logs.
- Alerting for repeated cron failures.

**Acceptance criteria:**

- Retrying a failed job is auditable.
- A `sent` job cannot be resent without an explicit override.
- Logs do not contain journal text or secrets.

## Deferred

### Gmail API/OAuth sending

Not implemented. The project currently sends through Brevo SMTP on port 2525 or Resend over HTTPS. A Gmail API adapter would require Google OAuth, refresh-token storage, Gmail scopes, quota handling, and a new security review. It is not needed to work around Render's SMTP port block.

### Multi-user support

Not planned. The data model, tokens, and access model assume one journal owner. Multi-user support would require ownership columns, authorization checks, per-user settings, and a much larger test matrix.

### Mobile app and public API

Not planned. The email form is the mobile-friendly input path. A public API would need authentication, versioning, rate limits, and abuse controls.

### Payments and subscriptions

Out of scope. This is a personal journal, not a commercial product.

## Explicit non-goals for the current version

- No dashboard until authentication is designed.
- No Gmail API or Google OAuth.
- No Docker/Render manifest in the repository.
- No CI workflow.
- No weekly preview CLI.
- No entry editing or deletion UI.
- No multi-user or sharing features.
- No public API.
- No guarantee of exactly-once email delivery.

## Related docs

- [Architecture](./architecture.md)
- [Security](./security.md)
- [Deployment](./deployment.md)
- [Testing](./testing.md)
- [Decisions](./decisions.md)
