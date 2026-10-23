# Nightly Journal documentation

Purpose: Index the maintainer documentation for the current Nightly Journal codebase.

Last verified: 2026-10-23

These docs describe **what the repository actually does**, not only what was originally designed. Features that are missing are labeled as deferred. `DESIGN.md` remains a historical design document and is not the current source of truth.

## Start here

| Document | Read it for |
| --- | --- |
| [Architecture](./architecture.md) | System context, components, request flows, module map |
| [Data model](./data-model.md) | Tables, relationships, constraints, time conventions |
| [Scheduling and idempotency](./scheduling.md) | Nightly/weekly windows, claims, leases, retries, cron setup |
| [Streaks and statuses](./streaks-and-status.md) | Status precedence, thresholds, grace, logging vs goal streaks |
| [AI insights](./ai-insights.md) | Gemini prompt/schema, fallback, privacy, failure handling |
| [Email](./email.md) | Transports, MIME structure, templates, charts, delivery flow |
| [Security](./security.md) | Threat model, tokens, CSRF, cron auth, headers, accepted risks |
| [Deployment](./deployment.md) | Neon, Brevo/Resend, Gemini, Render, cron-job.org, verification |
| [Runbook](./runbook.md) | Symptom-based troubleshooting and manual checks |
| [Testing](./testing.md) | Test commands, coverage map, how to add tests |
| [Free-tier limits](./free-tier-limits.md) | Dated provider limits and official links |
| [Roadmap](./roadmap.md) | Shipped, next, deferred, and out-of-scope work |
| [Decisions](./decisions.md) | Why the current design looks the way it does |

## Current status at a glance

Implemented:

- Email-first entry form with signed links and CSRF.
- Goals, planned goals, no-goals days, statuses, and streaks.
- Nightly, insight, and weekly emails.
- Brevo SMTP on port 2525 and Resend HTTPS.
- Gemini insights with deterministic fallback.
- Weekly PNG charts.
- Durable email claims, retries, and backoff.

Not implemented:

- Dashboard and authentication.
- Gmail API/OAuth sending.
- Entry editing/deletion UI.
- Weekly preview CLI.
- Dockerfile.

## Documentation conventions

- Start each document with a title, a one-line purpose, and `Last verified: YYYY-MM-DD`.
- Describe current behavior; put future work in [Roadmap](./roadmap.md).
- Use exact code names and paths.
- Put third-party limits in [Free-tier limits](./free-tier-limits.md) and include official links and a re-check note.
- Do not include real secrets, personal email addresses, or journal text.
- Prefer Mermaid for flows and tables for exact values.
- Keep one source of truth per topic and link to it elsewhere.

## Related

- [Project README](../README.md)
- [Contributing](../CONTRIBUTING.md)
- [Changelog](../CHANGELOG.md)
