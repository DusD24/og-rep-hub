"""Shared data loading, URL canonicalization, and deterministic score rules for OG Rep Hub."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# Mirrors of worker/src/index.js so ledger keys, worker submissions, and committed
# evidence URLs all canonicalize to the same string. Keep the two in sync.
EVIDENCE_HOSTS = frozenset({
    "reddit.com", "www.reddit.com", "old.reddit.com", "new.reddit.com", "np.reddit.com", "redd.it",
    "i.redd.it", "v.redd.it", "preview.redd.it", "external-preview.redd.it", "packaged-media.redd.it",
    "redditmedia.com", "www.redditmedia.com",
    "imgur.com", "www.imgur.com", "i.imgur.com",
})
REDDIT_PAGE_HOSTS = frozenset({"reddit.com", "www.reddit.com", "old.reddit.com", "new.reddit.com", "np.reddit.com"})
TRACKING_PARAMETERS = frozenset({"share_id", "rdt", "ref", "ref_source"})

_POST_ID_PATTERN = re.compile(r"/comments/([0-9a-z]+)", re.IGNORECASE)
_COMMENT_ID_PATTERN = re.compile(r"/comments/[0-9a-z]+/[^/]*/([0-9a-z]+)", re.IGNORECASE)


def load(name: str) -> Any:
    with (DATA / f"{name}.json").open(encoding="utf-8") as handle:
        return json.load(handle)


def normalize_evidence_url(value: Any) -> str | None:
    """Python port of the worker's normalizeEvidenceUrl. Returns None when unusable."""
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate or len(candidate) > 2048:
        return None
    try:
        parts = urlsplit(candidate)
    except ValueError:
        return None
    if parts.scheme != "https" or parts.username or parts.password:
        return None
    hostname = (parts.hostname or "").lower()
    if hostname not in EVIDENCE_HOSTS:
        return None
    if hostname in REDDIT_PAGE_HOSTS:
        hostname = "www.reddit.com"
    elif hostname == "www.imgur.com":
        hostname = "imgur.com"
    netloc = f"{hostname}:{parts.port}" if parts.port else hostname
    query = sorted(
        (key, val)
        for key, val in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMETERS
    )
    return urlunsplit((parts.scheme, netloc, parts.path, urlencode(query), ""))


def comparison_url(value: Any) -> str:
    """Canonical form used only for equality checks: no query, no trailing slash."""
    normalized = normalize_evidence_url(value)
    if not normalized:
        return ""
    parts = urlsplit(normalized)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def reddit_thing_id(value: Any) -> str | None:
    """Ledger key for a Reddit URL: t3_<post> for a post, t1_<comment> for a comment."""
    normalized = normalize_evidence_url(value)
    if not normalized:
        return None
    path = urlsplit(normalized).path
    comment_match = _COMMENT_ID_PATTERN.search(path)
    if comment_match:
        return f"t1_{comment_match.group(1).lower()}"
    # /comments/<id>/<slug>/comment/<cid>/ is the other permalink shape Reddit emits.
    if "/comment/" in path:
        tail = path.split("/comment/", 1)[1].strip("/").split("/")[0]
        if tail:
            return f"t1_{tail.lower()}"
    post_match = _POST_ID_PATTERN.search(path)
    if post_match:
        return f"t3_{post_match.group(1).lower()}"
    return None


def round_score(value: float) -> float:
    return round(value + 1e-9, 1)


def seller_reliability(metrics: dict[str, float]) -> float:
    return round_score(
        metrics["fulfillment"] * 0.30
        + metrics["service_communication"] * 0.25
        + metrics["qc_transparency"] * 0.20
        + metrics["shipping_consistency"] * 0.15
        + metrics["payment_risk_signals"] * 0.10
    )


def bag_confidence(metrics: dict[str, float]) -> float:
    return round_score(
        metrics["accuracy"] * 0.35
        + metrics["construction_materials"] * 0.25
        + metrics["exact_variant_availability"] * 0.20
        + metrics["independent_corroboration"] * 0.10
        + metrics["recency"] * 0.10
    )


def recommendation(bag_score: float, seller_score: float) -> float:
    return round_score(bag_score * 0.65 + seller_score * 0.35)


def tier_for(
    score: float,
    *,
    exact_variant: bool,
    independent_authors: int,
    unresolved_major_negative: bool,
    quality_evidence: bool,
) -> str | None:
    if not quality_evidence:
        return None
    if (
        score >= 80
        and exact_variant
        and independent_authors >= 2
        and not unresolved_major_negative
    ):
        return "A"
    if score >= 65 and exact_variant and not unresolved_major_negative:
        return "B"
    if score >= 50:
        return "C"
    return "Watchlist"

