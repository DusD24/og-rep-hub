#!/usr/bin/env python3
"""Turn a triage digest into evidence-record skeletons, then apply the reviewed ones.

The split is deliberate. Everything mechanical -- id, canonical url, subreddit,
author, dates, empty media -- is filled in here, for free. Everything that carries
judgment -- what the post actually claims, whether it matches the exact variant,
which seller/factory/collection it supports -- is left blank for a reviewer.

That keeps the expensive step to the part that genuinely needs reading, and it
means a reviewer writes a few short fields per record instead of a full object.

  --from-digest  emit drafts alongside the post context needed to fill them
  --apply        merge completed drafts into data/evidence.json, recompute the
                 affected collections' coverage counts, and mark the ledger

Applying always runs the same integrity rules validate.py enforces, so a
half-filled draft fails loudly here rather than producing an invalid catalog.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from ledger import load_ledger, record, save_ledger
from model import DATA, load, normalize_evidence_url, reddit_thing_id
from triage import LANE_TO_EVIDENCE_TYPE

EVIDENCE_PATH = DATA / "evidence.json"
FAMILIES_PATH = DATA / "bag_families.json"

VALID_EVIDENCE_TYPES = frozenset(value for value in LANE_TO_EVIDENCE_TYPE.values() if value)
VALID_SOURCE_TYPES = frozenset({"reddit_review", "reddit_qc", "reddit_discussion", "catalog", "official_reference"})
VALID_PRECISION = frozenset({"exact", "month_estimate", "relative_day_estimate"})

# Fields a reviewer must supply. Everything else the tool fills in.
JUDGMENT_FIELDS = (
    "source_type",
    "evidence_type",
    "exact_product_match",
    "paraphrase",
    "positive_observations",
    "negative_observations",
)
PLACEHOLDER = "TODO"


def _subreddit_slug(subreddit: str) -> str:
    """RepTherapy -> rt, RealRepLadies -> rll; falls back to the lowercased name."""
    initials = "".join(part[0] for part in re.findall(r"[A-Z][a-z0-9]*", subreddit or ""))
    return (initials or re.sub(r"[^a-z0-9]+", "", (subreddit or "x").casefold()))[:4].casefold()


def _slug(value: str, limit: int = 24) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-")
    return cleaned[:limit].strip("-")


def evidence_id_for(entry: dict[str, Any], taken: set[str]) -> str:
    """Deterministic, readable, and collision-checked against existing ids."""
    thing_id = entry.get("thing_id") or reddit_thing_id(entry.get("url")) or ""
    post_id = thing_id.split("_", 1)[-1]
    families = entry.get("matched", {}).get("family_ids", [])
    topic = _slug(families[0].replace("bag-family-", "")) if families else _slug(entry.get("title", ""))
    base = "-".join(part for part in ("ev-crawl", _subreddit_slug(entry.get("subreddit", "")), topic, post_id) if part)
    if base not in taken:
        return base
    for suffix in range(2, 100):
        alternative = f"{base}-{suffix}"
        if alternative not in taken:
            return alternative
    raise RuntimeError(f"could not allocate an unused evidence id for {base}")


def build_drafts(digest: dict[str, Any], existing_ids: set[str]) -> list[dict[str, Any]]:
    drafts: list[dict[str, Any]] = []
    taken = set(existing_ids)
    today = date.today().isoformat()
    for entry in digest.get("entries", []):
        evidence_id = evidence_id_for(entry, taken)
        taken.add(evidence_id)
        drafts.append({
            # --- filled in mechanically -------------------------------------
            "id": evidence_id,
            "title": entry.get("title") or "Untitled public post",
            "url": normalize_evidence_url(entry.get("url")) or entry.get("url"),
            "subreddit": entry.get("subreddit"),
            "author": entry.get("author"),
            "publication_date": entry.get("publication_date"),
            "publication_date_precision": "exact",
            "access_date": today,
            "price": None,
            "shipping_timeline": None,
            "media_ids": [],
            # --- suggested, still a reviewer's call --------------------------
            "source_type": entry.get("suggested_source_type") or PLACEHOLDER,
            "evidence_type": entry.get("suggested_evidence_type") or PLACEHOLDER,
            "family_ids": entry.get("matched", {}).get("family_ids", []),
            "bag_ids": entry.get("matched", {}).get("bag_ids", []),
            "seller_ids": entry.get("matched", {}).get("seller_ids", []),
            "factory_ids": entry.get("matched", {}).get("factory_ids", []),
            # --- must be written by a reviewer -------------------------------
            "exact_product_match": PLACEHOLDER,
            "paraphrase": PLACEHOLDER,
            "positive_observations": [],
            "negative_observations": [],
            "_review": {
                "note": "Replace every TODO. Delete this _review block or leave it; --apply strips it.",
                "excerpt": entry.get("excerpt", ""),
                "flair": entry.get("flair", ""),
                "gap_reason": entry.get("gap_reason", ""),
                "signals": entry.get("signals", []),
                "priority": entry.get("priority"),
            },
        })
    return drafts


def _incomplete(draft: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for field in JUDGMENT_FIELDS:
        value = draft.get(field)
        if value == PLACEHOLDER or value is None:
            problems.append(f"{field} is still {PLACEHOLDER}")
        elif isinstance(value, (list, str)) and not value:
            problems.append(f"{field} is empty")
    if draft.get("source_type") not in VALID_SOURCE_TYPES and draft.get("source_type") != PLACEHOLDER:
        problems.append(f"source_type {draft.get('source_type')!r} is not a valid enum value")
    if draft.get("evidence_type") not in VALID_EVIDENCE_TYPES and draft.get("evidence_type") != PLACEHOLDER:
        problems.append(f"evidence_type {draft.get('evidence_type')!r} is not a valid enum value")
    if draft.get("publication_date_precision") not in VALID_PRECISION:
        problems.append("publication_date_precision is not a valid enum value")
    if not isinstance(draft.get("exact_product_match"), bool):
        problems.append("exact_product_match must be true or false")
    if not draft.get("family_ids"):
        problems.append("family_ids must name at least one collection")
    if str(draft.get("source_type", "")).startswith("reddit_") and not (draft.get("subreddit") and draft.get("author")):
        problems.append("reddit sources need both subreddit and author")
    return problems


def recompute_coverage(families: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> None:
    """Keep evidence_coverage in step with evidence_ids, which validate.py cross-checks."""
    by_id = {row["id"]: row for row in evidence}
    for family in families:
        linked = [by_id[eid] for eid in family.get("evidence_ids", []) if eid in by_id]
        coverage = family.setdefault("evidence_coverage", {})
        coverage["source_count"] = len(linked)
        coverage["independent_author_count"] = len(
            {str(row.get("author") or "").casefold() for row in linked if row.get("author")}
        )
        coverage["primary_subreddit_coverage"] = sorted(
            {row["subreddit"] for row in linked if row.get("subreddit")}
        )
        coverage["evidence_types"] = sorted({row["evidence_type"] for row in linked if row.get("evidence_type")})
        coverage.setdefault("image_ready", bool(family.get("tile_media_id")))


def apply_drafts(drafts: list[dict[str, Any]], *, ledger: dict[str, Any] | None = None) -> dict[str, Any]:
    evidence = load("evidence")
    families = load("bag_families")
    family_by_id = {row["id"]: row for row in families}
    existing_ids = {row["id"] for row in evidence}
    existing_urls = {normalize_evidence_url(row.get("url")) for row in evidence}

    problems: list[str] = []
    accepted: list[dict[str, Any]] = []
    for index, draft in enumerate(drafts):
        where = f"draft[{index}] {draft.get('id', '?')}"
        issues = _incomplete(draft)
        if draft.get("id") in existing_ids:
            issues.append("id already exists in evidence.json")
        if normalize_evidence_url(draft.get("url")) in existing_urls:
            issues.append("url already cited by an existing record")
        for family_id in draft.get("family_ids", []):
            if family_id not in family_by_id:
                issues.append(f"unknown family_id {family_id}")
        if issues:
            problems.extend(f"{where}: {issue}" for issue in issues)
            continue
        clean = {key: value for key, value in draft.items() if not key.startswith("_")}
        clean["url"] = normalize_evidence_url(clean["url"]) or clean["url"]
        accepted.append(clean)
        existing_ids.add(clean["id"])
        existing_urls.add(clean["url"])

    if problems:
        return {"applied": 0, "problems": problems}

    for row in accepted:
        evidence.append(row)
        for family_id in row["family_ids"]:
            family = family_by_id[family_id]
            if row["id"] not in family.setdefault("evidence_ids", []):
                family["evidence_ids"].append(row["id"])
            family["last_updated"] = row["access_date"]
        if ledger is not None:
            record(
                ledger,
                reddit_thing_id(row["url"]),
                "promoted",
                evidence_ids=[row["id"]],
                subreddit=str(row.get("subreddit") or ""),
                reason="normalized from a triage shortlist",
            )

    recompute_coverage(families, evidence)
    EVIDENCE_PATH.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    FAMILIES_PATH.write_text(json.dumps(families, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "applied": len(accepted),
        "problems": [],
        "evidence_ids": [row["id"] for row in accepted],
        "families_touched": sorted({fid for row in accepted for fid in row["family_ids"]}),
    }


def decline_candidates(
    declines: list[dict[str, Any]], *, ledger: dict[str, Any]
) -> dict[str, Any]:
    """Record shortlisted posts a reviewer read and chose not to promote.

    Without this, a declined post stays `pending`, which is not settled, so it
    returns at the top of every later shortlist and the queue cannot advance. The
    disposition is `rejected` because the judgment is about the post itself -- it
    is a request for recommendations, a sales listing, or not about a bag -- and
    unlike a missing collection that is not a condition the catalog can grow out of.
    """
    problems: list[str] = []
    settled: list[str] = []
    for index, row in enumerate(declines):
        where = f"decline[{index}]"
        if not isinstance(row, dict):
            problems.append(f"{where}: expected an object")
            continue
        thing_id = row.get("thing_id") or reddit_thing_id(row.get("url"))
        if not thing_id:
            problems.append(f"{where}: needs a resolvable thing_id or url")
            continue
        reason = str(row.get("reason") or "").strip()
        if not reason:
            problems.append(f"{where} {thing_id}: a reason is required")
            continue
        settled.append(thing_id)
    if problems:
        return {"declined": 0, "problems": problems, "thing_ids": []}

    for row in declines:
        thing_id = row.get("thing_id") or reddit_thing_id(row.get("url"))
        record(
            ledger,
            thing_id,
            "rejected",
            subreddit=str(row.get("subreddit") or ""),
            reason=f"reviewed and not promoted: {row['reason']}",
        )
    return {"declined": len(settled), "problems": [], "thing_ids": settled}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--from-digest", type=Path, help="triage-digest.json to build drafts from")
    group.add_argument("--apply", type=Path, help="completed drafts file to merge into data/")
    group.add_argument(
        "--decline",
        type=Path,
        help="JSON array of {url|thing_id, reason} for shortlisted posts a reviewer read and did not promote",
    )
    parser.add_argument("--out", type=Path, default=None, help="draft output path (defaults next to the digest)")
    parser.add_argument("--ledger", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="with --apply, report problems without writing")
    args = parser.parse_args()

    if args.from_digest:
        digest = json.loads(args.from_digest.read_text(encoding="utf-8"))
        drafts = build_drafts(digest, {row["id"] for row in load("evidence")})
        out = args.out or args.from_digest.with_name("evidence-drafts.json")
        out.write_text(json.dumps(drafts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {len(drafts)} draft(s) to {out}")
        print(f"fill in: {', '.join(JUDGMENT_FIELDS)}")
        return 0

    if args.decline:
        declines = json.loads(args.decline.read_text(encoding="utf-8"))
        if not isinstance(declines, list):
            print("decline file must be a JSON array")
            return 1
        ledger = load_ledger(args.ledger)
        result = decline_candidates(declines, ledger=ledger)
        if result["problems"]:
            print("Nothing declined. Fix these first:")
            for problem in result["problems"]:
                print(f"- {problem}")
            return 1
        save_ledger(ledger, args.ledger)
        print(json.dumps(result, indent=2))
        return 0

    drafts = json.loads(args.apply.read_text(encoding="utf-8"))
    if not isinstance(drafts, list):
        print("drafts file must be a JSON array")
        return 1
    if args.dry_run:
        problems = [f"draft[{i}] {d.get('id', '?')}: {p}" for i, d in enumerate(drafts) for p in _incomplete(d)]
        print(json.dumps({"drafts": len(drafts), "problems": problems}, indent=2))
        return 1 if problems else 0

    ledger = load_ledger(args.ledger)
    result = apply_drafts(drafts, ledger=ledger)
    if result["problems"]:
        print("Nothing applied. Fix these first:")
        for problem in result["problems"]:
            print(f"- {problem}")
        return 1
    save_ledger(ledger, args.ledger)
    print(json.dumps(result, indent=2))
    print("Now run: python3 scripts/validate.py && python3 scripts/score.py --check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
