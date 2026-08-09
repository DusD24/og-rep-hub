#!/usr/bin/env python3
"""Build the public runtime configuration used by the static site."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def normalized_https_origin(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("ISSUE_INTAKE_URL must be an absolute HTTPS URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("ISSUE_INTAKE_URL must not contain credentials, a query, or a fragment")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    endpoint = normalized_https_origin(os.environ.get("ISSUE_INTAKE_URL", ""))
    site_key = os.environ.get("TURNSTILE_SITE_KEY", "").strip()
    if not site_key:
        raise ValueError("TURNSTILE_SITE_KEY is required")

    payload = {
        "issue_intake_url": endpoint,
        "turnstile_site_key": site_key,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
