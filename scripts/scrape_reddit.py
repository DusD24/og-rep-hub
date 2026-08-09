#!/usr/bin/env python3
"""Privacy-safe, resumable discovery helpers for public Reddit research."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse


HREF_PATTERN = re.compile(r"href\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
ABSOLUTE_SUBREDDIT_PATTERN = re.compile(
    r"https://(?:www\.)?reddit\.com/r/([A-Za-z0-9_]+)(?:/|[?#]|$)",
    re.IGNORECASE,
)
PHONE_PATTERN = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")
EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
CONTACT_URL_PATTERN = re.compile(
    r"https?://(?:wa\.me|api\.whatsapp\.com|t\.me|telegram\.me)/[^\s)]+",
    re.IGNORECASE,
)
PAYMENT_KEYWORD_PATTERN = re.compile(
    r"\b(?:paid|payment|paypal|ppff|transferwise|wise|venmo|cashapp|zelle|bank transfer)\b",
    re.IGNORECASE,
)
CURRENCY_PATTERN = re.compile(
    r"(?<!\w)(?:[$€£]\s?\d[\d,.]*|(?:USD|CAD|AUD|GBP|CNY)\s?\d[\d,.]*)(?!\w)",
    re.IGNORECASE,
)
ADDRESS_PATTERN = re.compile(
    r"\b\d{1,5}\s+[A-Za-z][A-Za-z.'-]*(?:\s+[A-Za-z][A-Za-z.'-]*){0,4}\s+"
    r"(?:street|st\.?|avenue|ave\.?|road|rd\.?|lane|ln\.?|drive|dr\.?|boulevard|blvd\.?)\b[^\n]*",
    re.IGNORECASE,
)
PRIVATE_MESSAGE_PATTERN = re.compile(
    r"\b(?:dm|pm|private message|direct message|message me|whatsapp me|telegram me)\b",
    re.IGNORECASE,
)
SECRET_PATTERN = re.compile(
    r"\b(?:sk_(?:live|test)_[A-Za-z0-9]+|password|passcode|secret|api[_ -]?key|access token)\b"
    r"(?:\s*[:=]\s*\S+)?",
    re.IGNORECASE,
)


def load_registry(path: Path) -> dict:
    """Load the committed source registry and reject malformed top-level data."""
    with path.open(encoding="utf-8") as handle:
        registry = json.load(handle)
    if not isinstance(registry, dict) or not isinstance(registry.get("sources"), list):
        raise ValueError("research source registry must contain a sources array")
    return registry


def sanitize_text(value: str) -> tuple[str, dict[str, bool]]:
    """Redact sensitive material while preserving research-relevant prose."""
    text = str(value or "")
    flags = {
        "contact_present": bool(CONTACT_URL_PATTERN.search(text) or EMAIL_PATTERN.search(text) or PHONE_PATTERN.search(text)),
        "payment_present": bool(PAYMENT_KEYWORD_PATTERN.search(text) or CURRENCY_PATTERN.search(text)),
        "address_present": bool(ADDRESS_PATTERN.search(text)),
        "private_message_present": bool(PRIVATE_MESSAGE_PATTERN.search(text)),
        "secret_present": bool(SECRET_PATTERN.search(text)),
    }
    text = CONTACT_URL_PATTERN.sub("[contact link redacted]", text)
    text = EMAIL_PATTERN.sub("[email redacted]", text)
    text = PHONE_PATTERN.sub("[phone redacted]", text)
    text = ADDRESS_PATTERN.sub("[address redacted]", text)
    text = SECRET_PATTERN.sub("[secret redacted]", text)
    text = PRIVATE_MESSAGE_PATTERN.sub("[private-message reference redacted]", text)
    if flags["payment_present"]:
        text = CURRENCY_PATTERN.sub("[payment amount redacted]", text)
    return text, flags


def canonical_subreddit_url(value: str) -> str | None:
    """Return a canonical public subreddit URL, or None for other Reddit paths."""
    try:
        parsed = urlparse(value)
    except ValueError:
        return None
    if parsed.scheme != "https" or parsed.hostname not in {"reddit.com", "www.reddit.com"}:
        return None
    match = re.fullmatch(r"/r/([A-Za-z0-9_]+)/?", parsed.path or "")
    if not match:
        return None
    return f"https://www.reddit.com/r/{match.group(1)}/"


def discover_subreddits(html: str, known: set[str]) -> list[str]:
    """Extract new subreddit names from public HTML in source order."""
    known_folded = {name.casefold() for name in known}
    discovered: list[str] = []
    seen: set[str] = set()
    candidates: list[str] = []
    for match in HREF_PATTERN.finditer(html or ""):
        href = match.group(1)
        if href.startswith("/r/"):
            candidates.append(f"https://www.reddit.com{href}")
        else:
            candidates.append(href)
    candidates.extend(match.group(0) for match in ABSOLUTE_SUBREDDIT_PATTERN.finditer(html or ""))
    for candidate in candidates:
        canonical = canonical_subreddit_url(candidate)
        if not canonical:
            continue
        name = urlparse(canonical).path.split("/")[2]
        if name.casefold() in known_folded or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        discovered.append(name)
    return discovered


if __name__ == "__main__":
    raise SystemExit("The crawler CLI is added in the next implementation step.")
