# Email

Purpose: Document the actual email transports, message structure, templates, and operational constraints.

Last verified: 2026-10-23

## Actual transport choice

The code supports two transports selected by `MAIL_TRANSPORT`:

| Value | Adapter | Transport |
| --- | --- | --- |
| `smtp` (default) | `SmtpMailer` | SMTP via `smtplib` |
| `resend` | `ResendMailer` | HTTPS POST to Resend |

The approved SMTP path is **Brevo SMTP relay on port 2525** at `smtp-relay.brevo.com`. Render Free blocks outbound TCP `25`, `465`, and `587`, but Brevo supports port `2525`.

There is **no Gmail API/OAuth adapter** in the current code. Gmail SMTP on ports `25`, `465`, or `587` cannot work from a Render Free web service. Gmail API remains a rejected/deferred option; see [Decisions](./decisions.md) and [Roadmap](./roadmap.md).

`IMAP_*` settings are only used by the CLI test-email command to check whether a message arrived. IMAP does not send mail.

## Configuration

| Variable | Default | Notes |
| --- | --- | --- |
| `MAIL_TRANSPORT` | `smtp` | `smtp` or `resend` |
| `EMAIL_FROM` | `Nightly Journal <journal@example.com>` | Must be a verified sender/domain with the provider |
| `EMAIL_TO` | `you@example.com` | Single recipient |
| `SMTP_HOST` | `smtp-relay.brevo.com` | Brevo relay |
| `SMTP_PORT` | `2525` | Brevo alternative submission port |
| `SMTP_USER` | empty | Brevo SMTP login, not the relay hostname |
| `SMTP_PASSWORD` | empty | Brevo SMTP key, not an API key |
| `SMTP_SECURITY` | `starttls` | `starttls`, `ssl`, or `none` |
| `SMTP_TIMEOUT_SECONDS` | `20` | Socket timeout |
| `RESEND_API_KEY` | empty | Required when `MAIL_TRANSPORT=resend` |
| `RESEND_API_URL` | `https://api.resend.com/emails` | Override for testing/proxy |
| `RESEND_TIMEOUT_SECONDS` | `20` | HTTP timeout |

`EMAIL_FROM` and `EMAIL_TO` are used by both transports. The app does not support multiple recipients or per-message reply-to headers.

## Mailer protocol

`app/mailer.py` defines:

```python
class Mailer(Protocol):
    def send(self, message: OutboundEmail) -> None: ...
```

`OutboundEmail` contains:

- `subject`
- `html`
- `text`
- `inline_images: tuple[InlineImage, ...]`

`InlineImage` contains `cid`, `filename`, `content`, `content_type` (default `image/png`), and `alt`.

`make_mailer(settings)` returns `ResendMailer` when `MAIL_TRANSPORT=resend`; otherwise it returns `SmtpMailer`.

## MIME structure

`_build_mime()` creates:

```text
multipart/alternative
├── text/plain
└── multipart/related
    ├── text/html
    ├── image/png (Content-ID: <weekly-completion>)
    ├── image/png (Content-ID: <weekly-sleep>)
    ├── image/png (Content-ID: <weekly-screen>)
    └── image/png (Content-ID: <weekly-mood>)
```

The HTML part uses `src="cid:weekly-completion"` and similar references. Images are inline, not external URLs.

For Resend, inline images are sent as base64 attachments with `content_type` and `content_id`. The HTML still references the same `cid:` values.

## SMTP adapter

`SmtpMailer`:

- Creates a default SSL context.
- Uses `SMTP_SSL` for `SMTP_SECURITY=ssl`.
- Uses `SMTP` plus `starttls()` for `starttls`.
- Uses plain `SMTP` for `none`.
- Calls `ehlo()`, optionally `starttls()` and a second `ehlo()`.
- Calls `login()` only when `SMTP_USER` is non-empty.
- Calls `send_message(mime)`.
- Always attempts `quit()` and suppresses quit errors.

Retry behavior:

- Up to 3 attempts.
- Transient `SMTPException`/`OSError` waits 1 second, then 2 seconds.
- `SMTPAuthenticationError` raises `MailerAuthError` immediately; no in-process retry.
- Exhausted retries raise a safe `MailerError` with the exception class name, not the full SMTP transcript.

## Resend adapter

`ResendMailer`:

- Requires `RESEND_API_KEY`; otherwise raises `MailerError`.
- Sends `from`, `to` (one address), `subject`, `html`, and `text`.
- Adds `attachments` with `filename`, base64 `content`, `content_type`, and `content_id` when inline images exist.
- Uses `Authorization: Bearer <key>`.
- Retries up to 3 times with 1s/2s backoff for network errors, HTTP 429, and HTTP 5xx.
- Raises `MailerAuthError` immediately for HTTP 401/403.
- Raises `MailerError` immediately for other HTTP 4xx responses.

## Nightly email

Builder: `build_nightly_email()`.

Subject:

```text
Tonight's check-in: <Weekday, Month D, YYYY>
```

Contents:

- Preheader: “A quiet check-in for <date>.”
- “Open tonight's check-in” link to `PUBLIC_BASE_URL/f/<signed-token>`.
- Current goal streak, or a prompt to start one.
- Planned goals for the day from `planned_goals`.
- Yesterday's headline: the previous nightly insight summary if present, otherwise the previous entry's key takeaway, otherwise “No entry yesterday.”
- Footer link to `PUBLIC_BASE_URL/` (currently the placeholder home page).

The form token is signed for the local date and expires after `FORM_TOKEN_MAX_AGE_SECONDS`.

## Nightly insight email

Builder: `build_insight_email()`.

Subject:

```text
Your nightly insight: <Weekday, Month D, YYYY>
```

Contents:

- The insight summary.
- Wins, struggles, three actions, and pattern when present.
- Current goal streak.
- Model name (`Gemini model` or `rule-based`).
- Footer dashboard link.

This email is sent only after a new entry is created. It is not part of the nightly reminder.

## Weekly email

Builder: `build_weekly_email()`.

Subject:

```text
Your week in review: <Mon D> - <Mon D>, <YYYY>
```

Range: prior Saturday through Friday.

Contents:

- Summary from the weekly insight.
- Metric rows: logged days, goal completion, current/longest goal streak, current logging streak, average mood, average sleep, average screen time.
- Four inline charts:
  - `weekly-completion`
  - `weekly-sleep`
  - `weekly-screen`
  - `weekly-mood`
- Easiest and hardest goals with date, difficulty, done state, and note.
- Wins, struggles, three actions for next week, and pattern.
- Model name and footer dashboard link.

Charts are generated with matplotlib using the `Agg` backend. The palette is Okabe-Ito inspired. Each chart has descriptive alt text. The sleep chart uses an 18:00-to-18:00 anchored axis.

## Gmail-safe HTML

The templates use:

- Table-based layout.
- Inline CSS.
- Dark text on a light background.
- No external images, fonts, or scripts.
- A hidden preheader.
- Descriptive image alt text.
- A single-column layout with a maximum width.

These choices improve rendering in Gmail and other clients. They do not make Gmail API a supported transport.

## Delivery state

Email delivery is tracked in `email_log`, not in the mailer. The mailer only reports success or raises. Retry and idempotency behavior is in [Scheduling](./scheduling.md).

## Operational checks

Use:

```bash
python -m app.cli send-test-email
```

The command sends a nightly-style message with a unique subject and prints `relay_accepted`. If `IMAP_HOST` and `IMAP_USER` are configured, it polls the inbox for up to 90 seconds and prints `delivered_to_inbox` or `not_found`.

## Known limitations

- A failed insight email is not retried by the scheduler; `/cron/tick` only handles nightly and weekly jobs.
- No Gmail API/OAuth adapter.
- No weekly report preview CLI; see [Runbook](./runbook.md) for a Python snippet.
- No unsubscribe or preference management; this is a single-recipient app.
- No attachment beyond the four inline weekly PNGs.
- Dashboard links currently land on the placeholder page.
- No delivery webhooks or bounce processing.

## Related docs

- [Architecture](./architecture.md)
- [Scheduling and idempotency](./scheduling.md)
- [AI insights](./ai-insights.md)
- [Deployment](./deployment.md)
- [Free-tier limits](./free-tier-limits.md)
