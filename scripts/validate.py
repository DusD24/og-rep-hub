#!/usr/bin/env python3
"""Validate normalized data, references, safety constraints, and media hashes."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

from model import DATA, ROOT, load

COLLECTIONS = ("bag_families", "bags", "sellers", "factories", "offerings", "evidence", "contacts", "media")
STATUSES = {"seller_confirmed", "catalog_seen", "historically_ordered", "inferred", "unavailable", "unknown"}
SOURCE_TYPES = {"reddit_review", "reddit_qc", "reddit_discussion", "catalog", "official_reference"}
EVIDENCE_TYPES = {"auth_comparison", "factory_comparison", "in_hand_review", "long_term_wear", "psp_qc", "seller_context"}
FAMILY_STATUSES = {"published", "research_queue"}
PRIMARY_SUBREDDITS = {"RealRepLadies", "RepTherapy"}
CONTACT_TYPES = {"whatsapp", "wechat", "email", "website", "instagram", "telegram", "phone", "other"}
FORBIDDEN_KEYS = {"payment", "address", "private_message", "buyer_conversation", "password", "secret", "token"}
SENSITIVE_PATTERNS = [
    re.compile(r"\b(?:sk_live|sk_test)_[A-Za-z0-9]+\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:routing|account)\s*(?:number|#)\b", re.I),
]


class Validation:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def required(self, row: dict, keys: tuple[str, ...], where: str) -> None:
        for key in keys:
            if key not in row or row[key] in (None, ""):
                self.error(f"{where}: missing {key}")


def valid_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except (TypeError, ValueError):
        return False


def valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def reddit_url(value: str) -> bool:
    return valid_url(value) and urlparse(value).hostname in {"reddit.com", "www.reddit.com"}


def flatten(value, path="$"):
    if isinstance(value, dict):
        for key, child in value.items():
            yield f"{path}.{key}", key, child
            yield from flatten(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from flatten(child, f"{path}[{index}]")


def validate() -> list[str]:
    v = Validation()
    records = {name: load(name) for name in COLLECTIONS}
    ids: dict[str, set[str]] = {}

    for name, rows in records.items():
        if not isinstance(rows, list):
            v.error(f"{name}.json: top level must be an array")
            continue
        seen: set[str] = set()
        for index, row in enumerate(rows):
            where = f"{name}[{index}]"
            if not isinstance(row, dict):
                v.error(f"{where}: must be an object")
                continue
            v.required(row, ("id",), where)
            item_id = row.get("id")
            if item_id in seen:
                v.error(f"{where}: duplicate id {item_id}")
            if item_id:
                seen.add(item_id)
        ids[name] = seen

    family_rows = records["bag_families"]
    if len(family_rows) != 12:
        v.error(f"bag_families.json: expected exactly 12 launch families, found {len(family_rows)}")
    family_slugs: set[str] = set()
    for index, row in enumerate(family_rows):
        where = f"bag_families[{index}]"
        v.required(row, ("slug", "brand", "model", "aliases", "category", "summary", "publication_status", "documented_variant_ids", "evidence_ids", "evidence_coverage", "last_updated", "research_gaps"), where)
        slug = row.get("slug")
        if slug in family_slugs:
            v.error(f"{where}: duplicate slug {slug}")
        if slug:
            family_slugs.add(slug)
        if row.get("publication_status") not in FAMILY_STATUSES:
            v.error(f"{where}: invalid publication_status {row.get('publication_status')}")
        if row.get("last_updated") and not valid_date(row["last_updated"]):
            v.error(f"{where}: invalid last_updated")
        for variant_id in row.get("documented_variant_ids", []):
            if variant_id not in ids["bags"]:
                v.error(f"{where}: unknown documented_variant_id {variant_id}")
        for evidence_id in row.get("evidence_ids", []):
            if evidence_id not in ids["evidence"]:
                v.error(f"{where}: unknown evidence_id {evidence_id}")
        coverage = row.get("evidence_coverage", {})
        v.required(coverage, ("source_count", "independent_author_count", "primary_subreddit_coverage", "image_ready", "evidence_types"), f"{where}.evidence_coverage")
        linked_evidence = [item for item in records["evidence"] if item.get("id") in set(row.get("evidence_ids", []))]
        authors = {item.get("author", "").casefold() for item in linked_evidence if item.get("author")}
        subreddits = {item.get("subreddit") for item in linked_evidence if item.get("subreddit")}
        if coverage.get("source_count") != len(linked_evidence):
            v.error(f"{where}: evidence_coverage.source_count does not match evidence_ids")
        if coverage.get("independent_author_count") != len(authors):
            v.error(f"{where}: evidence_coverage.independent_author_count does not match linked authors")
        if len(authors) < 2:
            v.error(f"{where}: two independent Reddit authors are required")
        if not subreddits & PRIMARY_SUBREDDITS:
            v.error(f"{where}: a RealRepLadies or RepTherapy source is required")
        candidate = row.get("candidate_tile")
        if row.get("publication_status") == "published" and not row.get("tile_media_id"):
            v.error(f"{where}: published family needs a Reddit tile_media_id")
        if row.get("publication_status") == "research_queue" and not candidate:
            v.error(f"{where}: research_queue family needs a candidate_tile provenance record")
        if candidate:
            v.required(candidate, ("status", "post_url", "author", "subreddit", "capture_date", "alt_text"), f"{where}.candidate_tile")
            if not reddit_url(candidate.get("post_url")):
                v.error(f"{where}.candidate_tile: post_url must be a public Reddit URL")
            if not valid_date(candidate.get("capture_date")):
                v.error(f"{where}.candidate_tile: invalid capture_date")
            if candidate.get("status") != "candidate_not_archived":
                v.error(f"{where}.candidate_tile: status must disclose that local archival is pending")

    for index, row in enumerate(records["bags"]):
        v.required(row, ("name", "size", "pattern", "colorway", "priority", "family_id", "material", "hardware", "official_reference_url"), f"bags[{index}]")
        if row.get("family_id") not in ids["bag_families"]:
            v.error(f"bags[{index}]: unknown family_id {row.get('family_id')}")
        if row.get("official_reference_url") and not valid_url(row["official_reference_url"]):
            v.error(f"bags[{index}]: official_reference_url must be https")
        if row.get("tile_media_id") and row["tile_media_id"] not in ids["media"]:
            v.error(f"bags[{index}]: unknown tile_media_id {row['tile_media_id']}")

    for index, row in enumerate(records["sellers"]):
        where = f"sellers[{index}]"
        v.required(row, ("display_name", "last_verified"), where)
        if "reliability_metrics" not in row:
            v.error(f"{where}: missing reliability_metrics (use null when evidence is insufficient)")
        if row.get("last_verified") and not valid_date(row["last_verified"]):
            v.error(f"{where}: invalid last_verified")
        metrics = row.get("reliability_metrics")
        if metrics is not None:
            for key in ("fulfillment", "service_communication", "qc_transparency", "shipping_consistency", "payment_risk_signals"):
                if key not in metrics or not isinstance(metrics[key], (int, float)) or not 0 <= metrics[key] <= 100:
                    v.error(f"{where}: reliability metric {key} must be 0..100")

    for index, row in enumerate(records["offerings"]):
        where = f"offerings[{index}]"
        v.required(row, ("seller_id", "bag_id", "variant_id", "family_id", "factory_id", "status", "last_verified", "evidence_ids"), where)
        for field, target in (("seller_id", "sellers"), ("bag_id", "bags"), ("variant_id", "bags"), ("family_id", "bag_families"), ("factory_id", "factories")):
            if row.get(field) not in ids[target]:
                v.error(f"{where}: unknown {field} {row.get(field)}")
        if row.get("variant_id") != row.get("bag_id"):
            v.error(f"{where}: variant_id must match the exact bag_id for backward-compatible references")
        variant = next((item for item in records["bags"] if item.get("id") == row.get("variant_id")), None)
        if variant and variant.get("family_id") != row.get("family_id"):
            v.error(f"{where}: family_id does not match the referenced exact variant")
        if row.get("status") not in STATUSES:
            v.error(f"{where}: invalid status {row.get('status')}")
        if row.get("last_verified") and not valid_date(row["last_verified"]):
            v.error(f"{where}: invalid last_verified")
        for evidence_id in row.get("evidence_ids", []):
            if evidence_id not in ids["evidence"]:
                v.error(f"{where}: unknown evidence_id {evidence_id}")
        if row.get("status") == "catalog_seen" and row.get("current_stock") is True:
            v.error(f"{where}: catalog_seen cannot claim current stock")
        metrics = row.get("bag_metrics")
        if metrics is not None:
            for key in ("accuracy", "construction_materials", "exact_variant_availability", "independent_corroboration", "recency"):
                if key not in metrics or not isinstance(metrics[key], (int, float)) or not 0 <= metrics[key] <= 100:
                    v.error(f"{where}: bag metric {key} must be 0..100")

    for index, row in enumerate(records["evidence"]):
        where = f"evidence[{index}]"
        v.required(row, ("source_type", "evidence_type", "url", "publication_date", "access_date", "exact_product_match", "paraphrase", "positive_observations", "negative_observations", "media_ids"), where)
        if row.get("source_type") not in SOURCE_TYPES:
            v.error(f"{where}: invalid source_type")
        if row.get("evidence_type") not in EVIDENCE_TYPES:
            v.error(f"{where}: invalid evidence_type")
        if row.get("url") and not valid_url(row["url"]):
            v.error(f"{where}: URL must be https")
        for field in ("publication_date", "access_date"):
            if row.get(field) and not valid_date(row[field]):
                v.error(f"{where}: invalid {field}")
        for field, target in (("seller_ids", "sellers"), ("factory_ids", "factories"), ("bag_ids", "bags"), ("family_ids", "bag_families"), ("media_ids", "media")):
            for ref in row.get(field, []):
                if ref not in ids[target]:
                    v.error(f"{where}: unknown {field} reference {ref}")
        if row.get("source_type", "").startswith("reddit_"):
            v.required(row, ("subreddit", "author"), where)
        if row.get("publication_date_precision") not in {"exact", "month_estimate", "relative_day_estimate"}:
            v.error(f"{where}: publication_date_precision must disclose date certainty")

    for index, row in enumerate(records["contacts"]):
        where = f"contacts[{index}]"
        v.required(row, ("seller_id", "channel", "value", "public_source_url", "last_verified"), where)
        if row.get("seller_id") not in ids["sellers"]:
            v.error(f"{where}: unknown seller_id")
        if row.get("channel") not in CONTACT_TYPES:
            v.error(f"{where}: invalid channel")
        if row.get("public_source_url") and not valid_url(row["public_source_url"]):
            v.error(f"{where}: public_source_url must be https")
        if row.get("last_verified") and not valid_date(row["last_verified"]):
            v.error(f"{where}: invalid last_verified")
        if row.get("provenance") not in {"seller_public_catalog", "seller_public_profile", "reddit_public_post", "reddit_public_wiki"}:
            v.error(f"{where}: public provenance is required")
        if row.get("link_url") and not valid_url(row["link_url"]):
            v.error(f"{where}: link_url must be https")

    for index, row in enumerate(records["media"]):
        where = f"media[{index}]"
        v.required(row, ("path", "attribution", "source_url", "post_url", "author", "subreddit", "capture_date", "sha256", "research_purpose"), where)
        path = ROOT / row.get("path", "")
        if not path.is_file():
            v.error(f"{where}: missing media file {row.get('path')}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != row.get("sha256"):
            v.error(f"{where}: SHA-256 mismatch")
        if row.get("source_url") and not valid_url(row["source_url"]):
            v.error(f"{where}: source_url must be https")
        if row.get("post_url") and not reddit_url(row["post_url"]):
            v.error(f"{where}: post_url must be a public Reddit URL")
        if row.get("usage_scope") == "target_tile" and not reddit_url(row.get("source_url")):
            v.error(f"{where}: target tile source must be a public Reddit post")
        if row.get("capture_date") and not valid_date(row["capture_date"]):
            v.error(f"{where}: invalid capture_date")

    all_public = {name: records[name] for name in COLLECTIONS}
    for path, key, value in flatten(all_public):
        if key.casefold() in FORBIDDEN_KEYS:
            v.error(f"{path}: forbidden sensitive/private field")
        if isinstance(value, str):
            for pattern in SENSITIVE_PATTERNS:
                if pattern.search(value):
                    v.error(f"{path}: possible secret or payment data")

    # Unproven allegations must not be represented as settled facts.
    for index, row in enumerate(records["evidence"]):
        if row.get("major_negative") and not row.get("negative_observations"):
            v.error(f"evidence[{index}]: major_negative needs a sourced observation")
        if row.get("allegation") and row.get("language") != "attributed_claim":
            v.error(f"evidence[{index}]: allegations must be explicitly attributed")

    # Every published family must point at a locally hashed Reddit-only tile.
    media_by_id = {row["id"]: row for row in records["media"]}
    for index, family in enumerate(records["bag_families"]):
        if family.get("publication_status") != "published":
            continue
        media = media_by_id.get(family.get("tile_media_id"))
        if not media:
            v.error(f"bag_families[{index}]: published family tile media is missing")
            continue
        if media.get("usage_scope") != "target_tile" or not reddit_url(media.get("post_url")):
            v.error(f"bag_families[{index}]: published family tile must be a Reddit-only target tile")
        if not media.get("sha256"):
            v.error(f"bag_families[{index}]: published family tile needs a SHA-256 hash")

    return v.errors


def main() -> int:
    errors = validate()
    if errors:
        print("Validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Validated normalized data, references, URLs, dates, contacts, media, and public-data safety.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
