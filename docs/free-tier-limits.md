# Free-tier limits

Purpose: Record the third-party free-tier limits that affect Nightly Journal and link to the official sources.

Last verified: 2026-10-23

Free tiers change without notice. Re-check the linked pages before relying on a limit or making a capacity decision.

## Current services

| Service | Role in this project | Free-tier limits that matter | Official source |
| --- | --- | --- | --- |
| Render | Web service host | 750 instance hours per workspace per month; 0.1 CPU; 512 MB RAM; spins down after 15 minutes without traffic; ~1 minute cold start; ephemeral disk; outbound SMTP ports `25`, `465`, and `587` blocked; service may restart at any time | [Render Free](https://render.com/docs/free) · [SMTP block changelog](https://render.com/changelog/free-web-services-will-no-longer-allow-outbound-traffic-to-smtp-ports) |
| Neon | PostgreSQL database | 100 projects; 10 branches per project; 100 CU-hours per project per month; 1 GB storage per project (up to 20 GB per account); 5 GB public network transfer per project per month; scale-to-zero after 5 minutes; 6-hour restore window; 1 snapshot; 1 day of monitoring; community support | [Neon plans](https://neon.com/docs/introduction/plans) |
| cron-job.org | External scheduler | Free plan; 1-minute minimum interval; 60 executions per hour; 30-second request timeout; 64 KB response limit; job auto-disabled after more than 25 consecutive failures; last 50 executions visible; response bodies stored for 2 days | [cron-job.org FAQ](https://cron-job.org/en/faq/) |
| Brevo | SMTP relay on port 2525 | 300 email sends per day; up to 100,000 contacts; free forever; a transactional retry queue of up to 1,000 messages after the daily limit; SMTP ports `587`, `465`, and `2525` | [Brevo free-plan limits](https://help.brevo.com/hc/en-us/articles/208580669-FAQs-What-are-the-limits-of-the-Free-plan) · [SMTP ports](https://help.brevo.com/hc/en-us/articles/10905415650322-Which-SMTP-port-should-I-use-Port-587-465-or-2525) |
| Resend | Optional HTTPS mail adapter | 3,000 emails per month; 100 emails per day; 3 verified domains; 3 email inboxes; 30-day email retention; sent and received messages count toward the quota | [Resend pricing](https://resend.com/pricing) · [Sending limits](https://resend.com/docs/knowledge-base/resend-sending-limits) |
| Gemini API | Optional AI insight generation | Free tier is rate-limited per model and project; limits are expressed as RPM, TPM, and RPD; free-tier content may be used to improve Google products; daily quotas reset at midnight Pacific | [Gemini rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) · [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing) |
| Gmail IMAP | Optional test-email inbox check | Personal Gmail has daily sending/recipient limits; app passwords require 2-Step Verification; IMAP access must be enabled | [Gmail sending limits](https://support.google.com/mail/answer/22839) · [App passwords](https://support.google.com/mail/answer/185833) |
| GitHub Actions | Optional fallback scheduler | Public repositories use free standard runners; private repositories consume plan minutes (GitHub Free includes 2,000 minutes per month); the optional scheduler uses about 100 minutes per month | [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions) |

## What this project actually uses

- **Render Free** for the web process.
- **Neon Free** for PostgreSQL.
- **cron-job.org** or the optional GitHub Actions workflow for `/cron/tick`.
- **Brevo SMTP on port 2525** for nightly, insight, and weekly email.
- **Resend** only if `MAIL_TRANSPORT=resend`.
- **Gemini** only if `GEMINI_API_KEY` and `GEMINI_MODEL` are set.
- **Gmail IMAP** only for `python -m app.cli send-test-email` delivery checks.
- **GitHub Actions** runs CI and the optional scheduler workflow; neither is required for local development.

## Practical implications

### Render

The nightly and weekly windows are deliberately wider than the exact send time because the service may be asleep. A warm-up request to `/healthz` before each window reduces cold-start timeouts. Do not use the Render filesystem for the database or uploaded files.

### Neon

Nightly Journal opens a small SQLAlchemy pool and closes connections when the process exits. Scale-to-zero is acceptable because cron ticks are infrequent. If CU-hours or network transfer are exhausted, compute is suspended until the quota resets; if storage is exhausted, writes fail.

### cron-job.org

The 30-second timeout is the main operational constraint. A Render cold start can exceed it. The job can also be disabled after repeated failures, so monitor the scheduler's execution history. The app's five-minute lease and retry logic assume multiple ticks are available.

### Brevo

A few emails per night is well below 300/day. Free-plan messages include “Sent with Brevo” branding. The limit matters mainly during retries or manual testing. A hard bounce or provider rejection is recorded in `email_log`; the app does not retry authentication failures for a day.

### Resend

The 100/day limit is comfortable for normal use but can be reached by repeated tests. Resend requires a verified domain for production sending. It is an HTTPS fallback, not the default.

### Gemini

Free-tier limits vary by model. The app treats rate limits, timeouts, blocked responses, invalid JSON, and schema failures as fallback conditions. It does not retry Gemini in a loop. Journal text sent to the free tier may be used by Google to improve products.

### Gmail

Gmail is not used for sending. The IMAP check is a convenience for confirming that a test message arrived. A Gmail app password is not the account password.

## Capacity estimate

A normal week is approximately:

- 7 nightly emails
- 7 insight emails
- 1 weekly email
- occasional retries and test messages

That is about 15 messages per week, well below every mail quota listed above. The real risks are cold starts, provider auth failures, and scheduler disablement, not volume.

## Related docs

- [Deployment](./deployment.md)
- [Scheduling and idempotency](./scheduling.md)
- [Email](./email.md)
- [Runbook](./runbook.md)
- [AI insights](./ai-insights.md)
