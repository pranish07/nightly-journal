# Security

Purpose: Describe the current threat model and the controls actually implemented in Nightly Journal, including known gaps.

Last verified: 2026-10-23

## Threat model

Nightly Journal is a single-user journal. The primary assets are:

- Journal entries and derived insights.
- The ability to submit an entry.
- The ability to trigger scheduled email jobs.
- Email, database, and Gemini credentials.

The main risks are:

- Someone with a leaked form link submits or reads a day's entry.
- Someone triggers cron jobs or causes email spam.
- A forged cross-site form submits data.
- Secrets leak through logs, source control, or error messages.
- A compromised email or AI provider sees journal content.
- A malicious payload attempts prompt injection against Gemini.

There is no multi-user isolation because there is no user account system.

## Authentication and sessions

**Not implemented:** password login, session cookies, logout, login throttling, protected dashboard pages, and trusted-proxy client-IP handling.

`GET /` is a public placeholder page. The current access control for writing an entry is possession of a valid signed form token in the email link.

`TRUST_PROXY_HEADERS` exists in `Settings` but is not read anywhere. Do not document or rely on it as active behavior.

If a dashboard is added later, it needs its own authentication and authorization design. See [Roadmap](./roadmap.md).

## Form tokens

Form links use `itsdangerous.URLSafeTimedSerializer`.

- Secret: `FORM_TOKEN_SECRET`.
- Salt: `nightly-journal-form`.
- Payload: the local date in ISO format.
- Maximum age: `FORM_TOKEN_MAX_AGE_SECONDS`, default 48 hours.
- Tampering, wrong secret, malformed payload, or expiry raises `InvalidToken`.

The token is a bearer credential. Anyone who obtains the link can open the form for that date until it expires or an entry already exists. The app does not bind the token to an IP address or user agent.

## CSRF protection

The form uses a second signed token:

- Secret: `CSRF_SECRET`.
- Salt: `nightly-journal-form-csrf`.
- Payload: the same local date.
- Maximum age: `CSRF_MAX_AGE_SECONDS`, default 48 hours.
- Verification uses `secrets.compare_digest` against the date.

A POST without a valid CSRF token returns the token-error page with status `403`. The CSRF token is rendered into the form by `make_form_csrf()`.

The cron endpoint does not use CSRF. It uses a shared secret header instead.

## Cron authentication

`GET` and `POST /cron/tick` require:

```http
X-Cron-Secret: <CRON_SECRET>
```

The comparison uses `secrets.compare_digest`. Missing or wrong values return `403`.

The cron secret is a bearer secret. The endpoint has no IP allowlist, HMAC timestamp, or replay window. Use a long random value, keep it out of URLs and logs, and rotate it if exposed.

## Production configuration validation

When `APP_ENV=production`, `Settings` rejects startup if:

- `FORM_TOKEN_SECRET` is empty, the development default, or shorter than 32 characters.
- `CSRF_SECRET` is empty, the development default, or shorter than 32 characters.
- `CRON_SECRET` is empty, the development default, or shorter than 32 characters.
- `PUBLIC_BASE_URL` does not start with `https://`.

The development defaults are intentionally recognizable and must not be used in production.

## Response headers

`app/main.py` sets these headers on every response:

| Header | Value |
| --- | --- |
| `Content-Security-Policy` | `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'` |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `no-referrer` |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` |
| `X-Robots-Tag` | `noindex, nofollow` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` only when `APP_ENV=production` |

The CSP allows only same-origin scripts/styles and same-origin or `data:` images. There are no CDN assets. Chart.js is not currently bundled because the dashboard is not built.

## Output encoding and input validation

- Jinja2 templates use autoescape for HTML and XML.
- Email templates use a Jinja environment with `select_autoescape(["html", "xml"])` and `StrictUndefined`.
- Form input is parsed into Pydantic models with length, range, and type constraints.
- Goal titles and notes are stripped and length-limited.
- Database access uses SQLAlchemy parameter binding.
- The OpenAPI schema, Swagger UI, and ReDoc are disabled (`docs_url=None`, `redoc_url=None`, `openapi_url=None`).

User text is escaped in HTML and email HTML. It is not stripped of all markup before storage, so treat stored text as untrusted when rendering it in any future surface.

## Secrets

Secrets are loaded from environment variables or `.env` through `pydantic-settings`.

- `.env` and `.env.*` are ignored by Git, except `.env.example`.
- `.env.example` contains placeholders only; copy it to `.env` and fill in local values.
- Do not commit real secrets, API keys, SMTP keys, IMAP passwords, or database URLs with credentials.
- Use the provider dashboards to rotate leaked credentials.
- `EMAIL_FROM` and `EMAIL_TO` are configuration, not secrets, but they are personal data and should not be committed as real values.

## Logging and error handling

- Mailer errors are reduced to safe text: `MailerError` messages or the exception class name, truncated to 500 characters.
- Gemini logs include the fallback reason and latency, not the journal payload.
- Job logs include `kind`, `local_date`, attempts, and safe error text.
- `LOG_LEVEL` is read by `app/cli.py` through `logging.basicConfig`. The web app does not configure logging centrally, so framework defaults apply unless the runtime configures them.
- Do not enable debug mode or verbose SQL echo in production.

## Accepted risks

- A leaked form link is usable until expiry or until an entry exists for that date.
- There is no rate limiting on form GET/POST or `/cron/tick`.
- There is no login, session revocation, or dashboard authorization because there is no dashboard.
- There is no CSRF protection on the cron endpoint; it uses a shared secret instead.
- There is no encryption at the application layer. Database and transport security depend on Neon, Render, and the mail provider.
- Journal text is sent to Gemini when AI insights are enabled. Google's free tier may use content to improve products.
- Nightly and weekly email delivery is at-least-once and can duplicate after a crash. Insight email has no scheduler retry.
- There is no dependency vulnerability scanning or CI security check.

## Operational guidance

- Use long random values for `FORM_TOKEN_SECRET`, `CSRF_SECRET`, and `CRON_SECRET`.
- Keep `PUBLIC_BASE_URL` on HTTPS in production.
- Use a dedicated Brevo SMTP key, not the account password or API key.
- Use a Gmail app password for IMAP test polling only, and only with 2-Step Verification enabled.
- Rotate secrets after any suspected exposure.
- Do not put the cron secret in a URL, commit it, or paste it into logs.
- Review provider access and free-tier data-use terms before storing sensitive journal content.

## Related docs

- [Architecture](./architecture.md)
- [Scheduling and idempotency](./scheduling.md)
- [Email](./email.md)
- [Deployment](./deployment.md)
- [AI insights](./ai-insights.md)
