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

COLLECTIONS = ("bags", "sellers", "factories", "offerings", "evidence", "contacts", "media")
STATUSES = {"seller_confirmed", "catalog_seen", "historically_ordered", "inferred", "unavailable", "unknown"}
SOURCE_TYPES = {"reddit_review", "reddit_qc", "reddit_discussion", "catalog", "official_reference"}
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

    for index, row in enumerate(records["bags"]):
        v.required(row, ("name", "size", "pattern", "colorway", "priority", "official_reference_url"), f"bags[{index}]")
        if row.get("official_reference_url") and not valid_url(row["official_reference_url"]):
            v.error(f"bags[{index}]: official_reference_url must be https")

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
        v.required(row, ("seller_id", "bag_id", "factory_id", "status", "last_verified", "evidence_ids"), where)
        for field, target in (("seller_id", "sellers"), ("bag_id", "bags"), ("factory_id", "factories")):
            if row.get(field) not in ids[target]:
                v.error(f"{where}: unknown {field} {row.get(field)}")
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
        v.required(row, ("source_type", "url", "publication_date", "access_date", "exact_product_match", "paraphrase", "positive_observations", "negative_observations", "media_ids"), where)
        if row.get("source_type") not in SOURCE_TYPES:
            v.error(f"{where}: invalid source_type")
        if row.get("url") and not valid_url(row["url"]):
            v.error(f"{where}: URL must be https")
        for field in ("publication_date", "access_date"):
            if row.get(field) and not valid_date(row[field]):
                v.error(f"{where}: invalid {field}")
        for field, target in (("seller_ids", "sellers"), ("factory_ids", "factories"), ("bag_ids", "bags"), ("media_ids", "media")):
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
        if row.get("provenance") not in {"seller_public_catalog", "seller_public_profile", "reddit_public_post"}:
            v.error(f"{where}: public provenance is required")

    for index, row in enumerate(records["media"]):
        where = f"media[{index}]"
        v.required(row, ("path", "attribution", "source_url", "capture_date", "sha256", "research_purpose"), where)
        path = ROOT / row.get("path", "")
        if not path.is_file():
            v.error(f"{where}: missing media file {row.get('path')}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != row.get("sha256"):
            v.error(f"{where}: SHA-256 mismatch")
        if row.get("source_url") and not valid_url(row["source_url"]):
            v.error(f"{where}: source_url must be https")
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
