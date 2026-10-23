from __future__ import annotations

import argparse
import json
import sys

import httpx

from app.config import get_settings


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Call the authenticated /cron/tick endpoint.")
    parser.add_argument(
        "--url", default=settings.public_base_url, help="Base URL (default: PUBLIC_BASE_URL)"
    )
    parser.add_argument(
        "--secret", default=settings.cron_secret, help="Cron secret (default: CRON_SECRET)"
    )
    parser.add_argument("--timeout", type=float, default=180.0, help="Request timeout in seconds")
    args = parser.parse_args()

    endpoint = args.url.rstrip("/") + "/cron/tick"
    try:
        response = httpx.post(
            endpoint,
            headers={"X-Cron-Secret": args.secret},
            timeout=args.timeout,
        )
    except httpx.HTTPError as exc:
        print(f"request failed: {exc}", file=sys.stderr)
        return 1

    print(f"{response.status_code} {response.reason_phrase}")
    try:
        print(json.dumps(response.json(), indent=2))
    except ValueError:
        print(response.text)
    return 0 if response.is_success else 1


if __name__ == "__main__":
    raise SystemExit(main())
