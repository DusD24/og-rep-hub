"""Durable cross-run memory for the evidence crawl.

Run directories are disposable, so their dedupe sets (RunStore.capture_keys,
RunStore.candidate_ids) only prevent re-work inside a single run. This ledger is
committed, so a post reviewed and rejected in March never resurfaces in August,
and an already-normalized post is never presented for triage twice.

It stores identifiers and dispositions only -- never post text -- so it stays
small and passes the forbidden-key / sensitive-pattern sweep in validate.py.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from model import DATA, load, reddit_thing_id

LEDGER_PATH = DATA / "scrape_ledger.json"
SCHEMA_VERSION = "1.0.0"

# promoted  -> a committed evidence record cites this post
# rejected  -> reviewed (by a human or the triage score floor) and declined
# deferred  -> plausible but not now; kept out of the daily digest
# pending   -> captured, awaiting triage
DISPOSITIONS = frozenset({"promoted", "rejected", "deferred", "pending"})
# Dispositions that permanently suppress a post. "pending" and "deferred" stay
# eligible so a deferred lead can be revisited by a deliberate sweep.
TERMINAL_DISPOSITIONS = frozenset({"promoted", "rejected"})


def empty_ledger() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "watermarks": {}, "seen": {}}


def load_ledger(path: Path | None = None) -> dict[str, Any]:
    target = Path(path) if path else LEDGER_PATH
    if not target.exists():
        return empty_ledger()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_ledger()
    if not isinstance(data, dict):
        return empty_ledger()
    data.setdefault("schema_version", SCHEMA_VERSION)
    data.setdefault("watermarks", {})
    data.setdefault("seen", {})
    return data


def save_ledger(ledger: dict[str, Any], path: Path | None = None) -> None:
    target = Path(path) if path else LEDGER_PATH
    payload = {
        "schema_version": ledger.get("schema_version", SCHEMA_VERSION),
        # Sorted so a nightly job produces a minimal, reviewable diff.
        "watermarks": {key: ledger["watermarks"][key] for key in sorted(ledger.get("watermarks", {}))},
        "seen": {key: ledger["seen"][key] for key in sorted(ledger.get("seen", {}))},
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def is_settled(ledger: dict[str, Any], thing_id: str | None) -> bool:
    """True when this post is already promoted or rejected and must not resurface."""
    if not thing_id:
        return False
    entry = ledger.get("seen", {}).get(thing_id)
    return bool(entry) and entry.get("disposition") in TERMINAL_DISPOSITIONS


def record(
    ledger: dict[str, Any],
    thing_id: str | None,
    disposition: str,
    *,
    evidence_ids: Iterable[str] = (),
    subreddit: str = "",
    decided_on: str | None = None,
    reason: str = "",
) -> bool:
    """Set a disposition. Returns True when the ledger changed."""
    if not thing_id:
        return False
    if disposition not in DISPOSITIONS:
        raise ValueError(f"unknown disposition {disposition!r}")
    seen = ledger.setdefault("seen", {})
    existing = seen.get(thing_id, {})
    # A settled post is never quietly downgraded; promotion is the only upgrade
    # allowed over a prior rejection, and it has to be explicit.
    if existing.get("disposition") in TERMINAL_DISPOSITIONS and disposition != "promoted":
        return False
    # Keep the original decision date when the disposition is unchanged, so
    # re-running a backfill on a later day is a genuine no-op.
    if existing.get("disposition") == disposition and existing.get("decided_on"):
        decided = existing["decided_on"]
    else:
        decided = decided_on or date.today().isoformat()
    entry = {"disposition": disposition, "decided_on": decided}
    merged_ids = sorted({*existing.get("evidence_ids", []), *evidence_ids})
    if merged_ids:
        entry["evidence_ids"] = merged_ids
    if subreddit or existing.get("subreddit"):
        entry["subreddit"] = subreddit or existing["subreddit"]
    if reason:
        entry["reason"] = reason
    if existing == entry:
        return False
    seen[thing_id] = entry
    return True


def watermark(ledger: dict[str, Any], subreddit: str) -> float:
    row = ledger.get("watermarks", {}).get(subreddit, {})
    try:
        return float(row.get("last_seen_utc") or 0)
    except (TypeError, ValueError):
        return 0.0


def set_watermark(
    ledger: dict[str, Any],
    subreddit: str,
    last_seen_utc: float,
    *,
    full_sweep: bool = False,
) -> None:
    row = ledger.setdefault("watermarks", {}).setdefault(subreddit, {})
    # Only ever advances. A partial or failed run must not rewind the window and
    # cause the next daily poll to re-present posts already dispositioned.
    row["last_seen_utc"] = max(float(last_seen_utc or 0), watermark(ledger, subreddit))
    if full_sweep:
        row["last_full_sweep"] = date.today().isoformat()


def backfill_from_evidence(ledger: dict[str, Any], evidence: list[dict[str, Any]] | None = None) -> int:
    """Mark every committed evidence source as promoted. Idempotent."""
    rows = evidence if evidence is not None else load("evidence")
    changed = 0
    by_thing: dict[str, dict[str, Any]] = {}
    for row in rows:
        thing_id = reddit_thing_id(row.get("url"))
        if not thing_id:
            continue
        # One post can back several records (a haul covering two bags), so
        # evidence ids accumulate per post rather than overwriting.
        bucket = by_thing.setdefault(thing_id, {"ids": set(), "subreddit": ""})
        bucket["ids"].add(row["id"])
        bucket["subreddit"] = bucket["subreddit"] or str(row.get("subreddit") or "")
    for thing_id, bucket in by_thing.items():
        if record(
            ledger,
            thing_id,
            "promoted",
            evidence_ids=bucket["ids"],
            subreddit=bucket["subreddit"],
            reason="backfilled from committed evidence",
        ):
            changed += 1
    return changed
