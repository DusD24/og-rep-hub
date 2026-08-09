#!/usr/bin/env python3
"""Write the immutable commit marker included in the Pages artifact."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args()

    sha = args.sha.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("--sha must be a full 40-character Git commit SHA")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"commit_sha": sha}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
