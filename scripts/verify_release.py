#!/usr/bin/env python3
"""Poll Pages and the receipt-intake Worker until both report a release SHA."""

from __future__ import annotations

import argparse
import json
import re
import time
from collections.abc import Callable
from typing import Any
from urllib.request import Request, urlopen


def request_json(url: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "User-Agent": "og-rep-hub-release-verifier",
        },
    )
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def poll_for_sha(
    pages_url: str,
    worker_url: str,
    sha: str,
    *,
    attempts: int = 36,
    interval: float = 5,
    fetch_json: Callable[[str], dict[str, Any]] = request_json,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    pages_marker = f"{pages_url.rstrip('/')}/build-meta.json"
    worker_health = f"{worker_url.rstrip('/')}/health"

    for attempt in range(1, attempts + 1):
        pages_payload: dict[str, Any] = {}
        worker_payload: dict[str, Any] = {}
        try:
            pages_payload = fetch_json(pages_marker)
        except Exception as error:  # pragma: no cover - diagnostic branch
            print(f"Attempt {attempt}: Pages marker unavailable: {error}")
        try:
            worker_payload = fetch_json(worker_health)
        except Exception as error:  # pragma: no cover - diagnostic branch
            print(f"Attempt {attempt}: Worker health unavailable: {error}")

        pages_sha = pages_payload.get("commit_sha")
        worker_sha = worker_payload.get("buildSha")
        print(f"Attempt {attempt}: Pages={pages_sha!r}, Worker={worker_sha!r}, expected={sha!r}")
        if pages_sha == sha and worker_payload.get("ok") is True and worker_sha == sha:
            return True
        if attempt < attempts:
            sleep(interval)
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages-url", required=True)
    parser.add_argument("--worker-url", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--attempts", type=int, default=36)
    parser.add_argument("--interval", type=float, default=5)
    args = parser.parse_args()

    sha = args.sha.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("--sha must be a full 40-character Git commit SHA")
    if args.attempts < 1 or args.interval < 0:
        raise ValueError("attempts must be positive and interval cannot be negative")
    if not poll_for_sha(
        args.pages_url,
        args.worker_url,
        sha,
        attempts=args.attempts,
        interval=args.interval,
    ):
        raise SystemExit("Release endpoints did not converge on the expected commit SHA")


if __name__ == "__main__":
    main()
