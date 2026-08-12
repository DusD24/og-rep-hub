#!/usr/bin/env python3
"""Surface repeated mentions of bags that are not yet catalogued.

triage.py's vocabulary is built from data/bag_families.json and data/bags.json,
so a post about a model the catalog has never seen scores as "no catalogued
collection referenced" and is auto-rejected -- correctly, since there is nothing
in data/ for that evidence to attach to. That also means those posts are the only
signal for what to catalogue next, and triage.py discards them.

This script reads the same run directory's candidates.jsonl and groups the
posts that do NOT strongly match a specific catalogued model by the crawler's
own KNOWN_BAG_TERMS hits (already recorded per-candidate as bag_terms at
scrape time), so it needs no extra scraping or a new term list to maintain. A
brand-only match (e.g. "Chanel") is deliberately not enough to exclude a post
here -- it anchors the post to every family of that brand without confirming
which model it actually is, so "Chanel 25" still surfaces as its own signal
even though "Chanel" alone would have anchored the post to Classic Flap and
Vanity Slim. A term already covered by the catalog (as a family's model or
alias) is excluded outright -- that is a catalog vocabulary gap, not
new-collection signal, and belongs in triage.py's matching instead.

Per the "repeated posts by the same author count as one source" rule the rest
of the catalog follows (see model.py's evidence model), a term only clears the
default floor once at least two *distinct* authors have mentioned it -- unless
a single post is a high-confidence hit, in which case one is enough. Every
candidate here is already a Reddit *post*: comments are captured for context
but never turned into candidates (see candidate_from_post in scrape_reddit.py),
so that half of "one high-confidence post, not a comment" is structural, not
a filter this script has to apply. "High confidence" itself means: the post's
own evidence-type lane is a substantive, hands-on lane (QC, in-hand review,
factory comparison, long-term wear, or auth comparison -- not seller_context,
w2c, collection, discussion, or other); the post is not itself a generic
how-to/guide post (those routinely use real model names as examples, and
otherwise pass the lane check for the wrong reason); and the post names few
enough catalogued-vocabulary bag terms (at most two) that this term reads as
the subject of the post rather than one line item in a multi-brand haul.

This never writes to data/ or the ledger. It is a read-only report for a human
to act on through the normal contribution path (see CONTRIBUTING.md) -- adding
a bag_family record needs a category, summary, and tile image that only a
reviewer can supply.
"""

from __future__ import annotations

import argparse
import json
import unicodedata
from pathlib import Path
from typing import Any

from triage import build_vocabulary, load_candidates, score_candidate, build_gap_index


def _fold(value: str) -> str:
    """Casefold and strip accents, so 'Hermes' and 'Hermès' compare equal."""
    stripped = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in stripped if not unicodedata.combining(ch)).casefold()


def _catalogued_terms(vocabulary: dict[str, Any]) -> set[str]:
    return {
        _fold(item["term"])
        for group in ("families", "bags")
        for item in vocabulary[group]
    }


# Lanes that reflect a hands-on account of a specific bag, mirroring
# LANE_TO_EVIDENCE_TYPE's non-None entries in triage.py. seller_context is
# left out here even though it maps to an evidence type there: it is about the
# seller/transaction, not a confirmed look at the bag itself.
_STRONG_LANES = frozenset({"psp_qc", "in_hand_review", "factory_comparison", "long_term_wear", "auth_comparison"})

# How-to/guide posts routinely use real model names as illustrative examples
# ("QC for Kelly should look like...") and can otherwise pass the strong-lane
# check for the wrong reason, since they are full of the same QC/review words.
_META_POST_MARKERS = ("how to", "guide", "faq", "tips for", "before you")

# A post naming more than this many catalogued-vocabulary bag terms reads as a
# multi-brand haul, where any single term is a passing mention rather than the
# post's subject.
_MAX_TERMS_FOR_HIGH_CONFIDENCE = 2


def _is_high_confidence(candidate: dict[str, Any]) -> bool:
    if str(candidate.get("evidence_type") or "") not in _STRONG_LANES:
        return False
    title = str(candidate.get("title") or "").casefold()
    if any(marker in title for marker in _META_POST_MARKERS):
        return False
    if len(candidate.get("bag_terms") or []) > _MAX_TERMS_FOR_HIGH_CONFIDENCE:
        return False
    return True


def detect(candidates: list[dict[str, Any]], *, min_authors: int) -> dict[str, Any]:
    vocabulary = build_vocabulary()
    gap_index = build_gap_index()
    known_authors: set[str] = set()  # not used for scoring here, just satisfies score_candidate
    bag_to_family: dict[str, str] = {}
    catalogued = _catalogued_terms(vocabulary)

    groups: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        scored = score_candidate(candidate, vocabulary, gap_index, known_authors, bag_to_family)
        if scored["has_strong_collection_anchor"]:
            continue
        author = str(candidate.get("author") or "").strip()
        if not author:
            continue
        high_confidence = _is_high_confidence(candidate)
        for term in candidate.get("bag_terms") or []:
            if _fold(term) in catalogued:
                continue
            group = groups.setdefault(
                term,
                {"term": term, "authors": {}, "examples": [], "high_confidence_hit": False},
            )
            group["authors"].setdefault(author.casefold(), author)
            if high_confidence:
                group["high_confidence_hit"] = True
            if len(group["examples"]) < 5:
                group["examples"].append(
                    {
                        "candidate_id": candidate.get("candidate_id"),
                        "subreddit": candidate.get("subreddit"),
                        "author": author,
                        "url": candidate.get("url"),
                        "title": candidate.get("title"),
                        "high_confidence": high_confidence,
                    }
                )

    entries = []
    for group in groups.values():
        distinct_authors = sorted(group["authors"].values())
        entries.append(
            {
                "term": group["term"],
                "independent_author_count": len(distinct_authors),
                "authors": distinct_authors,
                "post_count": len(group["examples"]),
                "high_confidence_hit": group["high_confidence_hit"],
                "meets_floor": len(distinct_authors) >= min_authors or group["high_confidence_hit"],
                "examples": group["examples"],
            }
        )
    entries.sort(key=lambda e: (-e["independent_author_count"], e["term"].casefold()))

    return {
        "schema_version": "1.0.0",
        "min_authors": min_authors,
        "counts": {
            "candidates_in": len(candidates),
            "uncatalogued_terms": len(entries),
            "meeting_floor": sum(1 for e in entries if e["meets_floor"]),
        },
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True, help="crawl run directory to scan")
    parser.add_argument("--out", type=Path, default=None, help="defaults to <run-dir>/new-collection-candidates.json")
    parser.add_argument(
        "--min-authors",
        type=int,
        default=2,
        help="independent authors needed before a term is flagged as ready for review",
    )
    args = parser.parse_args()

    candidates = load_candidates(args.run_dir)
    report = detect(candidates, min_authors=args.min_authors)

    out_path = args.out or (args.run_dir / "new-collection-candidates.json")
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report["counts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
