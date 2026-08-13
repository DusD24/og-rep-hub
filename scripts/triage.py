#!/usr/bin/env python3
"""Rank crawl candidates deterministically so only a small shortlist needs a reader.

This is the cost gate for the whole pipeline. The crawler's output grows with the
number of communities; the number of candidates a person (or a model) reads each
day should not. Everything here is pure Python over already-captured data: no
network, no model calls, and identical inputs always produce an identical digest.

Two outputs:

  triage-digest.json   the shortlist, capped by --limit, each entry compact enough
                       that a full day's digest is a few thousand tokens
  triage-context.json  the catalog ids and enums a reviewer needs to write evidence
                       records, so the review step never re-reads all of data/

Candidates scoring below the floor are written back to the ledger as `rejected`
and are never presented again.

A candidate that references no catalogued collection is instead written back as
`deferred`. That is a fact about the catalog rather than about the post, and it stops
being true the moment the collection is added -- so it stays eligible, and
detect_new_collections.py reads exactly these posts to decide what to catalogue next.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable

from ledger import is_settled, load_ledger, record, save_ledger
from model import load, normalize_evidence_url, reddit_thing_id

# The crawler's keyword classifier emits ten lanes; validate.py accepts six.
# Anything mapping to None has no landing spot in evidence.json and is triage-only.
LANE_TO_EVIDENCE_TYPE: dict[str, str | None] = {
    "psp_qc": "psp_qc",
    "long_term_wear": "long_term_wear",
    "auth_comparison": "auth_comparison",
    "factory_comparison": "factory_comparison",
    "seller_context": "seller_context",
    "in_hand_review": "in_hand_review",
    "collection": None,
    "w2c": None,
    "discussion": None,
    "other": None,
}

# Reddit lane -> the source_type a reviewer will usually pick. Still a judgment
# field; this is a starting suggestion, not an assignment.
LANE_TO_SOURCE_TYPE: dict[str, str] = {
    "psp_qc": "reddit_qc",
    "in_hand_review": "reddit_review",
    "long_term_wear": "reddit_review",
    "auth_comparison": "reddit_review",
    "factory_comparison": "reddit_review",
    "seller_context": "reddit_discussion",
}

# Seller and factory rosters contain ordinary English words ("Angel", "Autumn",
# "God", "Emily"). Matching those alone is noise, so they score as weak signals
# and can never carry a candidate over the floor by themselves.
GENERIC_ENTITY_WORDS = frozenset({
    "angel", "autumn", "baker", "booker", "captain", "emily", "god", "heidi", "jing",
    "kata", "kendall", "lemon", "li", "moon", "spring", "summer", "sunny", "winter",
})
MIN_TERM_LENGTH = 3
# Evidence is an observation of a bag someone has, saw, or is inspecting. A post
# asking which seller to use, or hunting for a stockist, names all the same
# collections, sellers, and factories while reporting nothing about any of them --
# so it scores like a review without being one. These were most of one real
# shortlist. The penalty is sized to drop a post that is purely a request below the
# floor, while a review that happens to end with a question still clears it.
SOLICITATION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?<!\w)ISO(?!\w)",
        r"\bin search of\b",
        r"\bwhich (?:seller|ts|factory|one) (?:should|do|would)\b",
        r"\b(?:any|other) (?:suggestions|recommendations|recs)\b",
        r"\b(?:can|could) (?:anyone|someone|you) recommend\b",
        r"\brecommend(?:ed|ations?)? (?:ts|seller)\b",
        r"\blooking for a (?:seller|ts|trusted seller)\b",
        r"\bwhat should (?:my|i) (?:next )?\w+ be\b",
        r"\bdon'?t know which seller\b",
        r"\bdoes anyone (?:know|have) (?:a |any )?(?:seller|rec)\b",
        r"\bwho (?:do you|should i) (?:use|buy from)\b",
        r"\bwhere (?:can|do) i (?:buy|get)\b",
    )
)
SOLICITATION_PENALTY = 30
REDACTION_PENALTIES = {
    "private_message_present": 40,
    "secret_present": 40,
    "payment_present": 25,
    "contact_present": 15,
    "address_present": 15,
}


# Several model names are also ordinary modifiers, and a bare word-boundary match
# cannot tell "a Dior Saddle" from "Margaux 15 in saddle leather", or a Kelly bag
# from Kelly sandals. Both misreadings were observed in real drafts. When one of
# these nouns immediately follows the term, the term is describing that noun rather
# than naming a bag: either a material/technique, or a product that is not a bag.
NON_BAG_SUCCESSOR_PATTERN = re.compile(
    r"\s+(?:leather|calfskin|suede|canvas|stitch(?:ing|es|ed)?|"
    r"sandals?|mules?|slides?|shoes?|boots?|sneakers?|heels?|flats?|loafers?|"
    r"scarf|scarves|belts?|sunglasses|glasses|rings?|bracelets?|necklaces?|"
    r"earrings?|watch(?:es)?|perfumes?|fragrances?)(?!\w)",
    re.IGNORECASE,
)


def _term_pattern(term: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)


def _is_bag_reference(text: str, match: re.Match[str]) -> bool:
    """False when the matched term is modifying a non-bag noun rather than naming a bag."""
    return NON_BAG_SUCCESSOR_PATTERN.match(text, match.end()) is None


def build_vocabulary() -> dict[str, Any]:
    """Derive match terms from the live catalog rather than a frozen literal list.

    Adding a bag family or seller to data/ immediately improves triage, which is
    what keeps the crawler useful as the catalog grows.
    """
    families = load("bag_families")
    bags = load("bags")
    sellers = load("sellers")
    factories = load("factories")

    def entry(term: str, entity_id: str, strong: bool) -> dict[str, Any] | None:
        cleaned = str(term or "").strip()
        if len(cleaned) < MIN_TERM_LENGTH:
            return None
        multiword = " " in cleaned
        generic = cleaned.casefold() in GENERIC_ENTITY_WORDS
        return {
            "term": cleaned,
            "id": entity_id,
            "pattern": _term_pattern(cleaned),
            # A term is a strong signal when it is multi-word or distinctive enough
            # not to collide with ordinary review prose.
            "strong": strong and (multiword or (not generic and len(cleaned) >= 5)),
        }

    def collect(rows: Iterable[dict[str, Any]], fields: tuple[str, ...], strong: bool) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for row in rows:
            values: list[str] = []
            for field in fields:
                value = row.get(field)
                if isinstance(value, str):
                    values.append(value)
                elif isinstance(value, list):
                    values.extend(str(item) for item in value)
            for value in values:
                built = entry(value, row["id"], strong)
                if built and (built["term"].casefold(), row["id"]) not in seen:
                    seen.add((built["term"].casefold(), row["id"]))
                    out.append(built)
        return out

    family_terms = collect(families, ("model", "aliases"), strong=True)
    for row in families:
        # Brand alone is weak: half the catalog is Louis Vuitton.
        built = entry(row.get("brand", ""), row["id"], strong=False)
        if built:
            family_terms.append(built)
        # A model named for one size ("Birkin 25") must still match posts about
        # another ("Birkin 30"); the collection is the same. But when the model
        # itself is just "<Brand> <number>" ("Chanel 25"), stripping the number
        # collapses the head to the brand name alone -- that must stay weak like
        # any other brand-only mention, or every post naming the brand would
        # falsely register as a strong match for this one specific model.
        head = re.sub(r"\s+\d+\s*(?:cm)?$", "", str(row.get("model") or "")).strip()
        if head and head != row.get("model") and head.casefold() != str(row.get("brand") or "").casefold():
            built = entry(head, row["id"], strong=True)
            if built:
                family_terms.append(built)
    return {
        "families": family_terms,
        "bags": collect(bags, ("name",), strong=True),
        "sellers": collect(sellers, ("display_name", "aliases"), strong=True),
        "factories": collect(factories, ("display_name", "aliases"), strong=True),
    }


def _matches(
    text: str, terms: list[dict[str, Any]], *, require_bag_reference: bool = False
) -> tuple[list[str], bool]:
    """Return (all matched ids, whether any match was strong, strongly matched ids).

    The two id lists exist because a match is used for two different things. Ranking
    wants every match, including the weak brand terms every family of that brand
    carries -- a post saying "Dior" really is more likely to be about a Dior bag.
    Attribution must not: it would claim the post is evidence about the Book Tote and
    the Saddle purely because the word "Dior" appeared. Only a strong match names a
    specific model, so only strong ids may become a record's family_ids.

    With require_bag_reference, a term only counts where it actually names a bag --
    see NON_BAG_SUCCESSOR_PATTERN. Sellers and factories do not use this: "Kendall
    factory" is a real attribution, and those rosters are already guarded by
    GENERIC_ENTITY_WORDS.
    """
    ids: list[str] = []
    strong_ids: list[str] = []
    strong = False
    for item in terms:
        found = None
        for candidate_match in item["pattern"].finditer(text):
            if not require_bag_reference or _is_bag_reference(text, candidate_match):
                found = candidate_match
                break
        if found is None:
            continue
        if item["id"] not in ids:
            ids.append(item["id"])
        if item["strong"] and item["id"] not in strong_ids:
            strong_ids.append(item["id"])
        strong = strong or item["strong"]
    return ids, strong, strong_ids


def build_gap_index() -> dict[str, dict[str, Any]]:
    """Score how badly each family needs more coverage, using validate.py's own gates."""
    families = load("bag_families")
    index: dict[str, dict[str, Any]] = {}
    counts = [f.get("evidence_coverage", {}).get("source_count", 0) for f in families]
    busiest = max(counts) if counts else 0
    for family in families:
        coverage = family.get("evidence_coverage", {})
        authors = int(coverage.get("independent_author_count", 0) or 0)
        sources = int(coverage.get("source_count", 0) or 0)
        primary = set(coverage.get("primary_subreddit_coverage", []) or []) & {"RealRepLadies", "RepTherapy"}
        boost = 0
        reasons: list[str] = []
        if family.get("publication_status") == "research_queue":
            boost += 25
            reasons.append("family is still in the research queue")
        if authors < 2:
            # The exact gate that blocks publication in validate.py.
            boost += 20
            reasons.append(f"only {authors} independent author(s); 2 required to publish")
        if not primary:
            boost += 10
            reasons.append("no RealRepLadies or RepTherapy source yet")
        if not family.get("tile_media_id"):
            boost += 5
            reasons.append("no collection tile image yet")
        if busiest and sources >= busiest:
            # Diminishing returns: the most-covered family does not need more.
            boost -= 15
            reasons.append(f"already the best-covered family ({sources} receipts)")
        index[family["id"]] = {
            "boost": boost,
            "reasons": reasons,
            "source_count": sources,
            "status": family.get("publication_status"),
        }
    return index


def score_candidate(
    candidate: dict[str, Any],
    vocabulary: dict[str, Any],
    gap_index: dict[str, dict[str, Any]],
    known_authors: set[str],
    bag_to_family: dict[str, str],
) -> dict[str, Any]:
    """Deterministic 0-100 quality score plus an additive coverage-gap boost."""
    text = " ".join(str(candidate.get(field) or "") for field in ("title", "flair", "redacted_excerpt"))
    family_ids, family_strong, strong_family_ids = _matches(
        text, vocabulary["families"], require_bag_reference=True
    )
    bag_ids, bag_strong, strong_bag_ids = _matches(
        text, vocabulary["bags"], require_bag_reference=True
    )
    seller_ids, seller_strong, _ = _matches(text, vocabulary["sellers"])
    factory_ids, factory_strong, _ = _matches(text, vocabulary["factories"])

    # A bag variant implies its family even when the family name is not written out.
    for bag_id in bag_ids:
        family_id = bag_to_family.get(bag_id)
        if family_id and family_id not in family_ids:
            family_ids.append(family_id)

    lane = str(candidate.get("evidence_type") or "other")
    mapped_type = LANE_TO_EVIDENCE_TYPE.get(lane)

    score = 0
    signals: list[str] = []
    if family_strong or bag_strong:
        score += 30
        signals.append("names a catalogued collection")
    elif family_ids or bag_ids:
        score += 10
        signals.append("weak collection-name match only")
    if seller_ids:
        score += 15 if seller_strong else 4
        signals.append("names a known seller")
    if factory_ids:
        score += 12 if factory_strong else 4
        signals.append("names a known factory")
    if mapped_type:
        score += 20
        signals.append(f"lane maps to {mapped_type}")
    if candidate.get("flair"):
        score += 5
    if str(candidate.get("author") or "").casefold() in known_authors:
        score += 8
        signals.append("author already cited in the catalog")
    if any(pattern.search(text) for pattern in SOLICITATION_PATTERNS):
        score -= SOLICITATION_PENALTY
        signals.append("asks for a seller rather than reporting on a bag")
    excerpt = str(candidate.get("redacted_excerpt") or "")
    if len(excerpt) >= 240:
        score += 10
        signals.append("substantive post body")
    elif len(excerpt) < 60:
        score -= 10
        signals.append("very short post body")

    flags = candidate.get("redaction_flags") or {}
    for flag, penalty in REDACTION_PENALTIES.items():
        if flags.get(flag):
            score -= penalty
            signals.append(f"redaction flag: {flag}")

    score = max(0, min(100, score))

    gap_boost = 0
    gap_reasons: list[str] = []
    for family_id in family_ids:
        gap = gap_index.get(family_id)
        if not gap:
            continue
        if gap["boost"] > gap_boost:
            gap_boost = gap["boost"]
            gap_reasons = gap["reasons"]

    return {
        "score": score,
        "gap_boost": gap_boost,
        "priority": score + gap_boost,
        "signals": signals,
        "gap_reason": gap_reasons[0] if gap_reasons else "",
        "family_ids": family_ids,
        "bag_ids": bag_ids,
        # Attribution-safe subsets: only terms that named a specific model, never a
        # brand term. A record's family_ids must come from these, or a post saying
        # "Dior" becomes evidence about every Dior collection at once.
        "strong_family_ids": strong_family_ids,
        "strong_bag_ids": strong_bag_ids,
        "seller_ids": seller_ids,
        "factory_ids": factory_ids,
        "suggested_evidence_type": mapped_type,
        "suggested_source_type": LANE_TO_SOURCE_TYPE.get(lane, ""),
        # No catalogued collection means there is nothing to attach a receipt to,
        # regardless of how well the post reads.
        "has_collection_anchor": bool(family_ids or bag_ids),
        # A brand-only match (e.g. "Chanel") anchors a post to every family of
        # that brand without confirming which model it is actually about, so a
        # strong match is a stronger signal of a *specific* catalogued model.
        "has_strong_collection_anchor": bool(family_strong or bag_strong),
    }


def load_candidates(run_dir: Path) -> list[dict[str, Any]]:
    jsonl = run_dir / "candidates.jsonl"
    if jsonl.exists():
        rows = []
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
        return rows
    legacy = run_dir / "candidates.json"
    if legacy.exists():
        try:
            rows = json.loads(legacy.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        return [row for row in rows if isinstance(row, dict)]
    return []


def digest_entry(candidate: dict[str, Any], scored: dict[str, Any], excerpt_chars: int) -> dict[str, Any]:
    """Compact review payload. Everything here is redacted, public post context."""
    return {
        "candidate_id": candidate.get("candidate_id"),
        "thing_id": reddit_thing_id(candidate.get("url")),
        "url": normalize_evidence_url(candidate.get("url")) or candidate.get("url"),
        "subreddit": candidate.get("subreddit"),
        "author": candidate.get("author"),
        "publication_date": candidate.get("publication_date"),
        "flair": candidate.get("flair") or "",
        "title": candidate.get("title"),
        "excerpt": str(candidate.get("redacted_excerpt") or "")[:excerpt_chars],
        "priority": scored["priority"],
        "score": scored["score"],
        "gap_boost": scored["gap_boost"],
        "gap_reason": scored["gap_reason"],
        "signals": scored["signals"],
        "matched": {
            # Attribution uses the strong subsets so a draft never claims a post is
            # about every collection of a brand it merely mentioned. The full lists
            # stay available for a reviewer weighing whether a match was missed.
            "family_ids": scored["strong_family_ids"],
            "bag_ids": scored["strong_bag_ids"],
            "brand_only_family_ids": [
                family_id
                for family_id in scored["family_ids"]
                if family_id not in scored["strong_family_ids"]
            ],
            "seller_ids": scored["seller_ids"],
            "factory_ids": scored["factory_ids"],
        },
        "suggested_evidence_type": scored["suggested_evidence_type"],
        "suggested_source_type": scored["suggested_source_type"],
    }


def build_context() -> dict[str, Any]:
    """The slim catalog reference a reviewer needs, instead of re-reading all of data/."""
    return {
        "note": "Ids and enums for writing evidence records. Judgment fields are never pre-filled.",
        "evidence_types": sorted({value for value in LANE_TO_EVIDENCE_TYPE.values() if value}),
        "source_types": ["reddit_review", "reddit_qc", "reddit_discussion", "catalog", "official_reference"],
        "publication_date_precision": ["exact", "month_estimate", "relative_day_estimate"],
        "families": [
            {"id": row["id"], "brand": row.get("brand"), "model": row.get("model"), "status": row.get("publication_status")}
            for row in load("bag_families")
        ],
        "bags": [{"id": row["id"], "name": row.get("name"), "family_id": row.get("family_id")} for row in load("bags")],
        "sellers": [{"id": row["id"], "name": row.get("display_name")} for row in load("sellers")],
        "factories": [{"id": row["id"], "name": row.get("display_name")} for row in load("factories")],
    }


def triage(
    candidates: list[dict[str, Any]],
    ledger: dict[str, Any],
    *,
    limit: int,
    floor: int,
    excerpt_chars: int,
    per_family_cap: int = 3,
) -> dict[str, Any]:
    vocabulary = build_vocabulary()
    gap_index = build_gap_index()
    bag_to_family = {row["id"]: row.get("family_id") for row in load("bags")}
    known_authors = {
        str(row.get("author") or "").casefold() for row in load("evidence") if row.get("author")
    }

    reviewed: list[tuple[dict[str, Any], dict[str, Any]]] = []
    rejected: list[tuple[dict[str, Any], dict[str, Any]]] = []
    unanchored: list[tuple[dict[str, Any], dict[str, Any]]] = []
    settled = 0
    for candidate in candidates:
        thing_id = reddit_thing_id(candidate.get("url")) or f"t3_{candidate.get('source_id', '').split(':')[-1]}"
        if is_settled(ledger, thing_id):
            settled += 1
            continue
        scored = score_candidate(candidate, vocabulary, gap_index, known_authors, bag_to_family)
        # Anchoring is checked before the floor, and the two get different
        # dispositions, because they are different kinds of statement. A score below
        # the floor judges the post. A missing anchor judges the *catalog* -- the post
        # names a bag data/ has never heard of -- and that is a condition which
        # changes as collections are added. Scoring makes the distinction sharper
        # still: naming a catalogued collection is worth 30 of 100 points, so an
        # unanchored post is docked for the very thing being tested and its low score
        # is not independent evidence of low quality.
        # The strong anchor, not the weak one: a post that only mentions a brand has
        # no specific collection to attach a receipt to, so it is in exactly the same
        # position as one naming a bag the catalog has never seen. detect_new_collections
        # reads both. Using the weak anchor here also shortlisted posts that
        # draft_evidence.py then refused, since a draft's family_ids are strong-only.
        if not scored["has_strong_collection_anchor"]:
            unanchored.append((candidate, scored))
        elif scored["score"] < floor:
            rejected.append((candidate, scored))
        else:
            reviewed.append((candidate, scored))

    # Deterministic ordering: priority first, then candidate_id so equal scores
    # never reshuffle between runs.
    reviewed.sort(key=lambda pair: (-pair[1]["priority"], str(pair[0].get("candidate_id") or "")))

    # The gap boost is a per-family constant, so without a diversity cap the
    # neediest family takes the whole shortlist. Closing its gap needs a couple of
    # independent authors, not a full day of slots.
    shortlist: list[tuple[dict[str, Any], dict[str, Any]]] = []
    deferred: list[tuple[dict[str, Any], dict[str, Any]]] = []
    per_family: dict[str, int] = {}
    for pair in reviewed:
        if len(shortlist) >= limit:
            deferred.append(pair)
            continue
        families = pair[1]["family_ids"] or ["__unmatched__"]
        if per_family_cap and all(per_family.get(family, 0) >= per_family_cap for family in families):
            deferred.append(pair)
            continue
        for family in families:
            per_family[family] = per_family.get(family, 0) + 1
        shortlist.append(pair)

    for candidate, scored in rejected:
        record(
            ledger,
            reddit_thing_id(candidate.get("url")),
            "rejected",
            subreddit=str(candidate.get("subreddit") or ""),
            reason=f"triage score {scored['score']} below floor {floor}",
        )
    # Deferred, never rejected: cataloguing the collection this post names is exactly
    # what makes it reviewable, and detect_new_collections.py reads these posts to
    # decide what to catalogue next. Rejecting them terminally would let the pipeline
    # discard its own roadmap -- and permanently, since a rejection never resurfaces.
    for candidate, _ in unanchored:
        record(
            ledger,
            reddit_thing_id(candidate.get("url")),
            "deferred",
            subreddit=str(candidate.get("subreddit") or ""),
            reason="no catalogued collection referenced; revisit as the catalog grows",
        )
    for candidate, scored in deferred:
        record(
            ledger,
            reddit_thing_id(candidate.get("url")),
            "deferred",
            subreddit=str(candidate.get("subreddit") or ""),
            reason=f"above floor but outside the daily cap (priority {scored['priority']})",
        )
    for candidate, _ in shortlist:
        record(
            ledger,
            reddit_thing_id(candidate.get("url")),
            "pending",
            subreddit=str(candidate.get("subreddit") or ""),
            reason="on the review shortlist",
        )

    return {
        "schema_version": "1.0.0",
        "counts": {
            "candidates_in": len(candidates),
            "already_settled": settled,
            "auto_rejected": len(rejected),
            "awaiting_catalog": len(unanchored),
            "deferred": len(deferred),
            "shortlisted": len(shortlist),
        },
        "floor": floor,
        "limit": limit,
        "per_family_cap": per_family_cap,
        "families_represented": sorted(per_family),
        "entries": [digest_entry(candidate, scored, excerpt_chars) for candidate, scored in shortlist],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True, help="crawl run directory to triage")
    parser.add_argument("--out-dir", type=Path, default=None, help="where to write the digest (defaults to --run-dir)")
    parser.add_argument("--ledger", type=Path, default=None, help="crawl ledger path (defaults to data/scrape_ledger.json)")
    parser.add_argument("--limit", type=int, default=25, help="hard cap on shortlisted candidates")
    parser.add_argument("--floor", type=int, default=30, help="score below which a candidate is auto-rejected")
    parser.add_argument(
        "--per-family-cap",
        type=int,
        default=3,
        help="max shortlist slots one collection may take per run (0 disables)",
    )
    parser.add_argument("--excerpt-chars", type=int, default=400)
    parser.add_argument("--dry-run", action="store_true", help="write the digest but leave the ledger untouched")
    args = parser.parse_args()

    out_dir = args.out_dir or args.run_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    ledger = load_ledger(args.ledger)
    digest = triage(
        load_candidates(args.run_dir),
        ledger,
        limit=args.limit,
        floor=args.floor,
        excerpt_chars=args.excerpt_chars,
        per_family_cap=args.per_family_cap,
    )
    (out_dir / "triage-digest.json").write_text(
        json.dumps(digest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "triage-context.json").write_text(
        json.dumps(build_context(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if not args.dry_run:
        save_ledger(ledger, args.ledger)
    print(json.dumps(digest["counts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
