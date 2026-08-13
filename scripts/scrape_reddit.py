#!/usr/bin/env python3
"""Privacy-safe, resumable discovery helpers for public Reddit research.

Fetching is tiered: the public reddit.com JSON API first, falling back to
parsed old.reddit.com HTML when the JSON API is blocked, and finally
Firecrawl (https://www.firecrawl.dev) as a last resort when both fail. The
Firecrawl tier is optional and stays fully disabled unless a FIRECRAWL_API_KEY
environment variable is set locally.

Two crawl modes share that fetch stack:

  --mode daily  polls /r/<sub>/new.json and stops at the per-subreddit watermark
                in data/scrape_ledger.json. Cost tracks what was posted since the
                last run, so it stays flat as communities are added.
  --mode sweep  runs the full search-term matrix for backfill and for newly added
                communities. Slower and broader; run it deliberately, not nightly.

Both consult the committed ledger so a post already promoted to evidence or
explicitly rejected never resurfaces as a candidate.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from ledger import empty_ledger, is_settled, load_ledger, save_ledger, set_watermark, watermark


HREF_PATTERN = re.compile(r"href\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
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
KNOWN_BAG_TERMS = (
    "Neverfull", "Speedy", "Alma", "Classic Flap", "Chanel 25", "Chanel 19",
    "Chanel 26S", "Shopping Tote", "Andiamo", "Puzzle", "Flamenco", "Margaux",
    "Birkin", "Kelly", "Lady Dior", "Book Tote", "Saint Louis", "Arcadie",
    "Saddle", "Dionysus", "Jackie", "Prada", "Miu Miu", "Loewe", "Chanel",
    "Louis Vuitton", "Dior", "Hermes", "Bottega", "Goyard", "YSL",
    "Saint Laurent", "Balenciaga", "Le City", "Pochette Accessories",
    "Side Trunk", "Barbara", "Mini Loop", "Luggage Tote", "Celine Soft",
    "Ferragamo Hug", "Neo Garden", "Le Click", "Marcie", "Marlo",
    # Added from mining brand-only "Prada"/"YSL"/"Bottega" hits in
    # new-collection-candidates.json: these three brands had no specific-model
    # terms at all, so every post naming a model was invisible past the bare
    # brand match. Ranked by title frequency in local-private/research-runs.
    "Bonnie", "Prada Re-Edition 2005", "Aimee", "Arqué", "Arque", "Cleo",
    "Niki", "Bea", "YSL Puffer", "Le 5 à 7", "Le 37", "Gaby", "Icare",
    "Jodie", "Parachute", "Hop", "Sardine", "Cassette",
)
KNOWN_FACTORY_TERMS = (
    "Birdcage", "Huahui", "Orange Sofa", "Royal", "187", "God", "P9", "Xiao C",
    "OF Factory", "Masoni", "Kendall", "White Factory", "H Factory", "Angel",
)
KNOWN_SELLER_TERMS = (
    "Hyper Peter", "Old Cobbler", "Doris", "Mandy", "Baobao", "Maryya", "Heidi",
    "Mike", "Miss Yu", "Mia", "Alisa", "Alina", "Reykay", "Garmen", "Emily",
    "Andy", "Axin", "Griffin", "Elaine", "Jim", "Ariel", "Mr Canvas", "Yuyu",
    "Tiny Jenny", "Tina", "Annie", "Miss Yu", "Mango",
)
EVIDENCE_LANES = (
    "psp_qc", "long_term_wear", "auth_comparison", "factory_comparison",
    "in_hand_review", "seller_context", "collection", "w2c", "discussion", "other",
)
# Reddit-wide navigation links (front page, sitewide defaults, meta subs) that
# appear in the chrome of nearly every page, not just rep-community links.
# Discovering these burns crawl budget on generic content instead of new
# rep communities, so they are excluded even when literally linked as /r/<name>/.
GENERIC_SUBREDDIT_DENYLIST = frozenset(
    name.casefold()
    for name in (
        "popular", "all", "announcements", "mod", "modsupport", "modnews",
        "reddit", "redditsessions", "help", "ideasfortheadmins", "blog",
        "friends", "reddits", "bestof", "AskReddit", "pics", "funny", "movies",
        "gaming", "worldnews", "videos", "news", "todayilearned", "science",
        "askscience", "IAmA", "gifs", "aww", "music", "art", "books", "food",
        "sports", "askmen", "askwomen",
    )
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
        folded = name.casefold()
        if (
            folded in known_folded
            or folded in seen
            or folded in GENERIC_SUBREDDIT_DENYLIST
            or folded.startswith("u_")
            or "rep" not in folded
        ):
            continue
        seen.add(folded)
        discovered.append(name)
    return discovered


def subreddit_base(subreddit: str) -> str:
    return f"https://www.reddit.com/r/{quote(subreddit, safe='')}/"


def search_url(subreddit: str, query: str, after: str | None = None, limit: int = 100) -> str:
    params = {
        "q": query,
        "restrict_sr": "1",
        "sort": "relevance",
        "t": "all",
        "limit": str(limit),
        "raw_json": "1",
    }
    if after:
        params["after"] = after
    return f"{subreddit_base(subreddit)}search.json?{urlencode(params, quote_via=quote)}"


def new_url(subreddit: str, after: str | None = None, limit: int = 100) -> str:
    """Newest-first listing. Daily mode reads this and stops at the stored watermark."""
    params = {"limit": str(limit), "raw_json": "1"}
    if after:
        params["after"] = after
    return f"{subreddit_base(subreddit)}new.json?{urlencode(params)}"


def old_listing_url(url: str) -> str:
    """Translate a /new.json endpoint to the old-Reddit HTML listing, keeping pagination."""
    parsed = urlparse(url)
    path = parsed.path.replace("/new.json", "/new/")
    params = parse_qs(parsed.query, keep_blank_values=True)
    params.pop("raw_json", None)
    query = urlencode(params, doseq=True)
    return f"https://old.reddit.com{path}{f'?{query}' if query else ''}"


def comments_url(subreddit: str, post_id: str, limit: int = 100) -> str:
    params = {"raw_json": "1", "limit": str(limit), "sort": "top"}
    return f"{subreddit_base(subreddit)}comments/{quote(post_id, safe='')}.json?{urlencode(params)}"


def old_reddit_url(url: str) -> str:
    """Translate a modern public Reddit endpoint to the reachable old-Reddit HTML host."""
    parsed = urlparse(url)
    path = parsed.path or "/"
    if path.endswith(".json"):
        path = path[:-5]
    if "/search" in path and not path.endswith("/"):
        path += "/"
    elif not path.endswith("/"):
        path += "/"
    return f"https://old.reddit.com{path}{f'?{parsed.query}' if parsed.query else ''}"


def old_search_url(url: str) -> str:
    """Translate a search JSON URL while retaining its public search parameters."""
    parsed = urlparse(url)
    path = parsed.path.replace("/search.json", "/search/")
    params = parse_qs(parsed.query, keep_blank_values=True)
    return f"https://old.reddit.com{path}?{urlencode(params, doseq=True)}"


def about_url(subreddit: str) -> str:
    return f"{subreddit_base(subreddit)}about.json?raw_json=1"


def public_post_url(subreddit: str, post: dict[str, Any]) -> str:
    permalink = str(post.get("permalink") or "")
    if permalink.startswith("https://www.reddit.com/"):
        return permalink
    if permalink.startswith("/"):
        return f"https://www.reddit.com{permalink}"
    post_id = str(post.get("id") or "unknown")
    return f"{subreddit_base(subreddit)}comments/{post_id}/"


def iso_date_from_timestamp(value: Any) -> str | None:
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def timestamp_from_datetime(value: str | None) -> float | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _html_text(parts: list[str]) -> str:
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


class OldSearchHTMLParser(HTMLParser):
    """Parse old Reddit's public search result cards into post-like dictionaries."""

    def __init__(self, subreddit: str) -> None:
        super().__init__(convert_charrefs=True)
        self.subreddit = subreddit
        self.depth = 0
        self.result_depth: int | None = None
        self.current: dict[str, Any] | None = None
        self.title_depth: int | None = None
        self.body_depth: int | None = None
        self.author_depth: int | None = None
        self.flair_depth: int | None = None
        self.next_url: str | None = None
        self.posts: list[dict[str, Any]] = []

    @staticmethod
    def _attrs(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key: value or "" for key, value in attrs}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in VOID_TAGS:
            self.depth += 1
        values = self._attrs(attrs)
        classes = set(values.get("class", "").split())
        if tag == "a" and ("next" in classes or values.get("rel") == "nofollow next"):
            self.next_url = values.get("href") or self.next_url
        if self.current is None and tag == "div" and "search-result" in classes:
            self.current = {
                "title_parts": [],
                "body_parts": [],
                "author_parts": [],
                "flair_parts": [],
                "href": "",
                "publication_date": values.get("datetime"),
            }
            self.result_depth = self.depth
        if self.current is None:
            return
        if tag == "a" and "search-title" in classes:
            self.current["href"] = values.get("href", "")
            self.title_depth = self.depth
        elif tag == "div" and "search-result-body" in classes:
            self.body_depth = self.depth
        elif tag == "a" and "author" in classes:
            self.author_depth = self.depth
        elif tag == "span" and ("flairrichtext" in classes or "linkflairlabel" in classes):
            self.flair_depth = self.depth
            if values.get("title"):
                self.current["flair_parts"].append(values["title"])
        elif tag == "time" and values.get("datetime"):
            self.current["publication_date"] = values["datetime"]

    def handle_data(self, data: str) -> None:
        if self.current is None:
            return
        if self.title_depth is not None and self.depth >= self.title_depth:
            self.current["title_parts"].append(data)
        if self.body_depth is not None and self.depth >= self.body_depth:
            self.current["body_parts"].append(data)
        if self.author_depth is not None and self.depth >= self.author_depth:
            self.current["author_parts"].append(data)
        if self.flair_depth is not None and self.depth >= self.flair_depth:
            self.current["flair_parts"].append(data)

    def _finish_current(self) -> None:
        if self.current is None:
            return
        href = self.current.get("href", "")
        path = urlparse(href).path
        match = re.search(r"/comments/([A-Za-z0-9]+)/", path)
        if match:
            self.posts.append({
                "id": match.group(1),
                "permalink": path,
                "title": _html_text(self.current["title_parts"]) or "Untitled public post",
                "selftext": _html_text(self.current["body_parts"]),
                "author": _html_text(self.current["author_parts"]) or "[deleted]",
                "subreddit": self.subreddit,
                "created_utc": timestamp_from_datetime(self.current.get("publication_date")),
                "link_flair_text": _html_text(self.current["flair_parts"]),
            })
        self.current = None
        self.result_depth = None
        self.title_depth = None
        self.body_depth = None
        self.author_depth = None
        self.flair_depth = None

    def handle_endtag(self, tag: str) -> None:
        if self.current is not None:
            if tag == "a" and self.title_depth == self.depth:
                self.title_depth = None
            if tag == "a" and self.author_depth == self.depth:
                self.author_depth = None
            if tag == "span" and self.flair_depth == self.depth:
                self.flair_depth = None
            if tag == "div" and self.body_depth == self.depth:
                self.body_depth = None
            if tag == "div" and self.result_depth == self.depth:
                self._finish_current()
        if tag not in VOID_TAGS:
            self.depth = max(0, self.depth - 1)


class OldListingHTMLParser(HTMLParser):
    """Parse old Reddit's /new/ listing cards, which use data-* attributes rather than search markup."""

    def __init__(self, subreddit: str) -> None:
        super().__init__(convert_charrefs=True)
        self.subreddit = subreddit
        self.depth = 0
        self.current: dict[str, Any] | None = None
        self.thing_depth: int | None = None
        self.title_depth: int | None = None
        self.body_depth: int | None = None
        self.flair_depth: int | None = None
        self.next_url: str | None = None
        self.posts: list[dict[str, Any]] = []

    @staticmethod
    def _attrs(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key: value or "" for key, value in attrs}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in VOID_TAGS:
            self.depth += 1
        values = self._attrs(attrs)
        classes = set(values.get("class", "").split())
        if tag == "a" and ("next-button" in classes or values.get("rel") == "nofollow next"):
            self.next_url = values.get("href") or self.next_url
        if self.current is None and tag == "div" and "thing" in classes and values.get("data-fullname", "").startswith("t3_"):
            self.current = {
                "fullname": values.get("data-fullname", ""),
                "author": values.get("data-author", ""),
                "permalink": values.get("data-permalink", ""),
                "subreddit": values.get("data-subreddit") or self.subreddit,
                # Old Reddit reports data-timestamp in milliseconds.
                "timestamp": values.get("data-timestamp", ""),
                "title_parts": [],
                "body_parts": [],
                "flair_parts": [],
            }
            self.thing_depth = self.depth
            return
        if self.current is None:
            return
        if tag == "a" and "title" in classes:
            self.title_depth = self.depth
        elif tag == "div" and "md" in classes:
            self.body_depth = self.depth
        elif tag == "span" and ("linkflairlabel" in classes or "flairrichtext" in classes):
            self.flair_depth = self.depth
            if values.get("title"):
                self.current["flair_parts"].append(values["title"])

    def handle_data(self, data: str) -> None:
        if self.current is None:
            return
        if self.title_depth is not None and self.depth >= self.title_depth:
            self.current["title_parts"].append(data)
        if self.body_depth is not None and self.depth >= self.body_depth:
            self.current["body_parts"].append(data)
        if self.flair_depth is not None and self.depth >= self.flair_depth:
            self.current["flair_parts"].append(data)

    def _finish_current(self) -> None:
        if self.current is None:
            return
        post_id = self.current["fullname"].split("_", 1)[-1]
        try:
            created = float(self.current["timestamp"]) / 1000.0 if self.current["timestamp"] else 0.0
        except (TypeError, ValueError):
            created = 0.0
        # Flair arrives twice when the label carries both a title attribute and
        # matching inner text; keep one copy.
        flair_parts = list(dict.fromkeys(part.strip() for part in self.current["flair_parts"] if part.strip()))
        if post_id:
            self.posts.append({
                "id": post_id,
                "permalink": self.current["permalink"],
                "title": _html_text(self.current["title_parts"]) or "Untitled public post",
                "selftext": _html_text(self.current["body_parts"]),
                "author": self.current["author"] or "[deleted]",
                "subreddit": self.current["subreddit"],
                "created_utc": created,
                "link_flair_text": _html_text(flair_parts),
            })
        self.current = None
        self.thing_depth = None
        self.title_depth = None
        self.body_depth = None
        self.flair_depth = None

    def handle_endtag(self, tag: str) -> None:
        if self.current is not None:
            if tag == "a" and self.title_depth == self.depth:
                self.title_depth = None
            if tag == "span" and self.flair_depth == self.depth:
                self.flair_depth = None
            if tag == "div" and self.body_depth == self.depth:
                self.body_depth = None
            if tag == "div" and self.thing_depth == self.depth:
                self._finish_current()
        if tag not in VOID_TAGS:
            self.depth = max(0, self.depth - 1)


def parse_old_listing_html(html: str, subreddit: str) -> dict[str, Any]:
    parser = OldListingHTMLParser(subreddit)
    parser.feed(html or "")
    parser.close()
    after = None
    if parser.next_url:
        after = parse_qs(urlparse(parser.next_url).query).get("after", [None])[0]
    return {"data": {"children": [{"kind": "t3", "data": post} for post in parser.posts], "after": after}}


def parse_old_search_html(html: str, subreddit: str) -> dict[str, Any]:
    parser = OldSearchHTMLParser(subreddit)
    parser.feed(html or "")
    parser.close()
    after = None
    if parser.next_url:
        after = parse_qs(urlparse(parser.next_url).query).get("after", [None])[0]
    return {"data": {"children": [{"kind": "t3", "data": post} for post in parser.posts], "after": after}}


class OldCommentsHTMLParser(HTMLParser):
    """Parse public old-Reddit comment blocks, including nested replies."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.stack: list[dict[str, Any]] = []
        self.comments: list[dict[str, Any]] = []

    @staticmethod
    def _attrs(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key: value or "" for key, value in attrs}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in VOID_TAGS:
            self.depth += 1
        values = self._attrs(attrs)
        classes = set(values.get("class", "").split())
        if tag == "div" and "comment" in classes and values.get("data-permalink"):
            comment_id = ""
            id_match = re.search(r"id-t1_([A-Za-z0-9]+)", values.get("id", ""))
            if id_match:
                comment_id = id_match.group(1)
            if not comment_id:
                comment_id = values["data-permalink"].rstrip("/").rsplit("/", 1)[-1]
            self.stack.append({
                "depth": self.depth,
                "body_depth": None,
                "record": {
                    "id": comment_id,
                    "permalink": values["data-permalink"],
                    "author": values.get("data-author") or "[deleted]",
                    "created_utc": None,
                    "body_parts": [],
                },
            })
        if self.stack and tag == "div" and "usertext-body" in classes:
            self.stack[-1]["body_depth"] = self.depth
        if self.stack and tag == "time" and values.get("datetime"):
            self.stack[-1]["record"]["created_utc"] = timestamp_from_datetime(values["datetime"])

    def handle_data(self, data: str) -> None:
        if self.stack and self.stack[-1]["body_depth"] is not None and self.depth >= self.stack[-1]["body_depth"]:
            self.stack[-1]["record"]["body_parts"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self.stack:
            current = self.stack[-1]
            if current["body_depth"] == self.depth:
                current["body_depth"] = None
            if current["depth"] == self.depth:
                record = current["record"]
                record["body"] = _html_text(record.pop("body_parts"))
                self.comments.append(record)
                self.stack.pop()
        if tag not in VOID_TAGS:
            self.depth = max(0, self.depth - 1)


def parse_old_comments_html(html: str) -> list[dict[str, Any]]:
    parser = OldCommentsHTMLParser()
    parser.feed(html or "")
    parser.close()
    return [{"data": {"children": [{"kind": "t1", "data": row} for row in parser.comments]}}]


def firecrawl_to_listing(
    html: str,
    *,
    method: str,
    subreddit: str,
    is_search: bool,
    is_listing: bool = False,
) -> Any:
    """Reshape a Firecrawl scrape's HTML into the same shape old-Reddit HTML parsing produces."""
    if not html:
        raise RuntimeError("firecrawl response had no html payload")
    if method == "text":
        return html
    if is_search:
        return parse_old_search_html(html, subreddit)
    if is_listing:
        return parse_old_listing_html(html, subreddit)
    return parse_old_comments_html(html)


def _unique_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    folded = text.casefold()
    return [term for term in terms if term.casefold() in folded]


def matches_scope(
    text: str,
    include_terms: list[str] | None,
    exclude_terms: list[str] | None,
) -> bool:
    """Screen a scoped-request candidate by simple casefolded substring match."""
    folded = text.casefold()
    if include_terms and not any(term.casefold() in folded for term in include_terms):
        return False
    if exclude_terms and any(term.casefold() in folded for term in exclude_terms):
        return False
    return True


def evidence_type_for(title: str, text: str, flair: str | None = None) -> str:
    """Classify a public post conservatively for normalization review."""
    haystack = " ".join(part for part in (flair or "", title, text) if part).casefold()
    precedence = (
        (("qc", "quality check", "psp", "pre-shipment", "green light", "red light"), "psp_qc"),
        (("long term", "long-term", "months later", "wear test", "worn"), "long_term_wear"),
        (("auth comparison", "auth vs", "authentic vs", "compared to auth"), "auth_comparison"),
        (("factory", "batch", "187", "god factory", "xiao c", "birdcage"), "factory_comparison"),
        (("seller", "ordered from", "purchase experience", "service"), "seller_context"),
        (("review", "in hand", "haul", "arrived", "received", "unboxing"), "in_hand_review"),
        (("collection", "my bags", "my collection"), "collection"),
        (("w2c", "where to cop", "where to buy", "seller recommendation"), "w2c"),
        (("discussion", "thoughts", "question", "help"), "discussion"),
    )
    for needles, lane in precedence:
        if any(needle in haystack for needle in needles):
            return lane
    return "other"


def _merge_flags(*flags: dict[str, bool]) -> dict[str, bool]:
    keys = {key for item in flags for key in item}
    return {key: any(item.get(key, False) for item in flags) for key in sorted(keys)}


def candidate_from_post(post: dict[str, Any], subreddit: str, captured_at: str) -> dict[str, Any]:
    """Make a reviewable, sanitized candidate without asserting normalized facts."""
    title, title_flags = sanitize_text(str(post.get("title") or ""))
    body, body_flags = sanitize_text(str(post.get("selftext") or ""))
    flags = _merge_flags(title_flags, body_flags)
    excerpt = " ".join(part.strip() for part in (body, title) if part.strip())[:600]
    post_id = str(post.get("id") or "unknown")
    return {
        "candidate_id": f"candidate-{subreddit}-{post_id}",
        "source_id": f"post:{subreddit}:{post_id}",
        "url": public_post_url(subreddit, post),
        "subreddit": subreddit,
        "author": str(post.get("author") or "[deleted]"),
        "publication_date": iso_date_from_timestamp(post.get("created_utc")),
        "title": title or "Untitled public post",
        "flair": str(post.get("link_flair_text") or post.get("flair") or ""),
        "evidence_type": evidence_type_for(title, body, str(post.get("link_flair_text") or "")),
        "bag_terms": _unique_terms(f"{title} {body}", KNOWN_BAG_TERMS),
        "seller_terms": _unique_terms(f"{title} {body}", KNOWN_SELLER_TERMS),
        "factory_terms": _unique_terms(f"{title} {body}", KNOWN_FACTORY_TERMS),
        "redacted_excerpt": excerpt,
        "redaction_flags": flags,
        "status": "needs_normalization",
        "captured_at": captured_at,
    }


class RedditClient:
    """Small stdlib-only client for public Reddit endpoints.

    Anonymous www.reddit.com JSON is the most aggressively throttled way to read
    Reddit, which is what pushes a long sweep down into the HTML and billable
    Firecrawl tiers. When REDDIT_CLIENT_ID is present the client authenticates as
    a registered app and reads oauth.reddit.com instead, which is both sanctioned
    and far higher throughput. Credentials are optional: with none set the client
    behaves exactly as it did before.

    Reddit issues app-only tokens under two different grants, and which one applies
    is decided by the app type rather than by preference:

      script / web app  (confidential, has a secret) -> client_credentials
      installed app     (public, no secret)          -> installed_client + device_id

    Supporting both matters because Reddit now gates new app registration, so an
    older installed app may be the only client available to a given account.
    """

    TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
    OAUTH_HOST = "oauth.reddit.com"
    PUBLIC_HOSTS = frozenset({"www.reddit.com", "reddit.com"})
    INSTALLED_CLIENT_GRANT = "https://oauth.reddit.com/grants/installed_client"

    def __init__(
        self,
        *,
        timeout: float = 15.0,
        retries: int = 3,
        delay: float = 1.5,
        user_agent: str = "OG-Rep-Hub-Research/1.0 (public-source catalog)",
        client_id: str | None = None,
        client_secret: str | None = None,
        device_id: str | None = None,
    ) -> None:
        self.timeout = timeout
        self.retries = max(1, retries)
        self.delay = max(0.0, delay)
        self.user_agent = user_agent
        self.client_id = (client_id if client_id is not None else os.environ.get("REDDIT_CLIENT_ID", "")).strip()
        self.client_secret = (
            client_secret if client_secret is not None else os.environ.get("REDDIT_CLIENT_SECRET", "")
        ).strip()
        # Reddit requires a 20-30 char device id for the installed-app grant and
        # documents this literal as the opt-out value, which is what a research
        # crawler wants: no per-device profile is needed or desired.
        self.device_id = (
            device_id if device_id is not None else os.environ.get("REDDIT_DEVICE_ID", "")
        ).strip() or "DO_NOT_TRACK_THIS_DEVICE"
        self._last_request_at = 0.0
        self._token: str | None = None
        self._token_expires_at = 0.0

    @property
    def authenticated(self) -> bool:
        # An installed app authenticates with an id alone, so a secret is not required.
        return bool(self.client_id)

    @property
    def grant_type(self) -> str | None:
        if not self.authenticated:
            return None
        return "client_credentials" if self.client_secret else "installed_client"

    def _access_token(self) -> str | None:
        """Return a cached app-only bearer token, fetching one when needed.

        A failure here is not fatal: the caller falls back to the anonymous
        endpoint, so a bad key degrades throughput rather than stopping a crawl.
        """
        if not self.authenticated:
            return None
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token
        if self.client_secret:
            grant: dict[str, str] = {"grant_type": "client_credentials"}
        else:
            grant = {"grant_type": self.INSTALLED_CLIENT_GRANT, "device_id": self.device_id}
        # An installed app authenticates as "<client_id>:" -- id with an empty password.
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        request = Request(
            self.TOKEN_URL,
            data=urlencode(grant).encode(),
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": self.user_agent,
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
        except (HTTPError, URLError, ValueError):
            self._token = None
            # Do not retry the token endpoint on every request while it is failing.
            self._token_expires_at = time.monotonic() + 60.0
            return None
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not token:
            self._token = None
            self._token_expires_at = time.monotonic() + 60.0
            return None
        try:
            expires_in = float(payload.get("expires_in") or 3600)
        except (TypeError, ValueError):
            expires_in = 3600.0
        self._token = str(token)
        # Refresh a minute early so a token never expires mid-page-loop.
        self._token_expires_at = time.monotonic() + max(60.0, expires_in - 60.0)
        return self._token

    def _authorized_url(self, url: str) -> str:
        """Point a public reddit.com URL at the OAuth host.

        Only www.reddit.com/reddit.com are swapped. old.reddit.com is left alone
        because the HTML fallback tier depends on it and oauth.reddit.com serves
        JSON only. The URL builders keep emitting canonical public URLs so that
        candidate ids, ledger keys, and evidence URLs are unaffected by auth.
        """
        parsed = urlparse(url)
        if parsed.netloc.casefold() not in self.PUBLIC_HOSTS:
            return url
        return urlunparse(parsed._replace(netloc=self.OAUTH_HOST))

    def _get(self, url: str, accept: str) -> bytes:
        last_error: Exception | None = None
        for attempt in range(self.retries):
            if self.delay:
                remaining = self.delay - (time.monotonic() - self._last_request_at)
                if remaining > 0:
                    time.sleep(remaining)
            self._last_request_at = time.monotonic()
            headers = {"Accept": accept, "User-Agent": self.user_agent}
            target = url
            token = self._access_token()
            if token:
                target = self._authorized_url(url)
                if target != url:
                    headers["Authorization"] = f"Bearer {token}"
            request = Request(target, headers=headers)
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    return response.read()
            except HTTPError as error:
                last_error = error
                if error.code in {401, 403} and "Authorization" in headers:
                    # Token rejected or revoked mid-run: drop it and let the next
                    # attempt re-mint one, falling back to anonymous if that fails.
                    self._token = None
                    self._token_expires_at = 0.0
                    continue
                if error.code not in {429, 500, 502, 503, 504}:
                    raise
            except URLError as error:
                last_error = error
        raise RuntimeError(f"public Reddit request failed after {self.retries} attempts: {url}") from last_error

    def get_text(self, url: str) -> str:
        return self._get(url, "text/html,application/xhtml+xml").decode("utf-8", errors="replace")

    def get_json(self, url: str) -> Any:
        return json.loads(self._get(url, "application/json").decode("utf-8", errors="replace"))


class FirecrawlClient:
    """Small stdlib-only client for the Firecrawl scrape API, used as a last-resort fallback."""

    API_URL = "https://api.firecrawl.dev/v1/scrape"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout: float = 20.0,
        retries: int = 2,
        delay: float = 1.0,
        max_calls: int = 25,
    ) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.retries = max(1, retries)
        self.delay = max(0.0, delay)
        # This is the only metered tier. A night of 403s upstream must not turn into an
        # unbounded bill, so the budget is enforced here rather than by the caller.
        self.max_calls = max(0, max_calls)
        self.call_count = 0
        self._last_request_at = 0.0

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    @property
    def budget_remaining(self) -> int:
        return max(0, self.max_calls - self.call_count)

    def scrape(self, url: str) -> dict[str, Any]:
        if not self.budget_remaining:
            raise RuntimeError(f"firecrawl call budget exhausted after {self.call_count} calls")
        self.call_count += 1
        payload = json.dumps({"url": url, "formats": ["html"], "onlyMainContent": False}).encode("utf-8")
        last_error: Exception | None = None
        for attempt in range(self.retries):
            if self.delay:
                remaining = self.delay - (time.monotonic() - self._last_request_at)
                if remaining > 0:
                    time.sleep(remaining)
            self._last_request_at = time.monotonic()
            request = Request(
                self.API_URL,
                data=payload,
                method="POST",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    body = json.loads(response.read().decode("utf-8", errors="replace"))
                    return body.get("data", {})
            except HTTPError as error:
                last_error = error
                if error.code not in {429, 500, 502, 503, 504}:
                    raise
            except URLError as error:
                last_error = error
        raise RuntimeError(f"firecrawl request failed after {self.retries} attempts: {url}") from last_error


class RunStore:
    """Persist captures, candidates, and progress so an interrupted run resumes."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifest.json"
        self.captures_path = self.root / "captures.jsonl"
        self.candidates_path = self.root / "candidates.jsonl"
        self.legacy_candidates_path = self.root / "candidates.json"
        self.summary_path = self.root / "run-summary.json"
        self.history_path = self.root / "run-history.jsonl"
        self.manifest = self._read_json(self.manifest_path, {
            "schema_version": "1.0.0",
            "started_at": None,
            "updated_at": None,
            "completed_endpoints": [],
            "errors": [],
        })
        self.capture_keys = self._load_capture_keys()
        # Membership is checked on every fetch, so the set is built once here rather
        # than rebuilt from the (unbounded) manifest list per call.
        self.completed_endpoints = set(self.manifest.get("completed_endpoints", []))
        self.candidates = self._load_candidates()
        self.candidate_ids = {row.get("candidate_id") for row in self.candidates if row.get("candidate_id")}

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default

    def _load_candidates(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if self.candidates_path.exists():
            for line in self.candidates_path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
            return rows
        # Resume a run directory written before candidates moved to JSONL.
        legacy = self._read_json(self.legacy_candidates_path, [])
        return [row for row in legacy if isinstance(row, dict)] if isinstance(legacy, list) else []

    def _load_capture_keys(self) -> set[str]:
        keys: set[str] = set()
        if not self.captures_path.exists():
            return keys
        for line in self.captures_path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("id") and row.get("kind"):
                keys.add(f"{row['kind']}:{row['id']}")
        return keys

    def endpoint_complete(self, url: str) -> bool:
        return url in self.completed_endpoints

    def mark_endpoint_complete(self, url: str, timestamp: str) -> None:
        completed = self.manifest.setdefault("completed_endpoints", [])
        if url not in self.completed_endpoints:
            completed.append(url)
            self.completed_endpoints.add(url)
        self.manifest["updated_at"] = timestamp
        self.save_manifest()

    def add_error(self, error: dict[str, str], timestamp: str) -> None:
        self.manifest.setdefault("errors", []).append(error)
        self.manifest["updated_at"] = timestamp
        self.save_manifest()

    def append_capture(self, record: dict[str, Any]) -> bool:
        if not record.get("id") or not record.get("kind"):
            return False
        key = f"{record['kind']}:{record['id']}"
        if key in self.capture_keys:
            return False
        with self.captures_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        self.capture_keys.add(key)
        return True

    def append_candidate(self, record: dict[str, Any]) -> bool:
        candidate_id = record.get("candidate_id")
        if not candidate_id or candidate_id in self.candidate_ids:
            return False
        self.candidates.append(record)
        self.candidate_ids.add(candidate_id)
        # Append rather than rewriting the whole array per candidate; the old
        # write_text form was quadratic and a long sweep spends real time in it.
        with self.candidates_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return True

    def save_manifest(self) -> None:
        self.manifest_path.write_text(
            json.dumps(self.manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _read_summary_history(self) -> list[dict[str, Any]]:
        history: list[dict[str, Any]] = []
        if not self.history_path.exists():
            return history
        for line in self.history_path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                history.append(row)
        return history

    @staticmethod
    def _ordered_union(history: list[dict[str, Any]], field: str) -> list[Any]:
        values: list[Any] = []
        seen: set[str] = set()
        for row in history:
            for value in row.get(field, []) if isinstance(row.get(field, []), list) else []:
                marker = json.dumps(value, ensure_ascii=False, sort_keys=True)
                if marker in seen:
                    continue
                seen.add(marker)
                values.append(value)
        return values

    @staticmethod
    def _summed_mapping(history: list[dict[str, Any]], field: str) -> dict[str, int]:
        totals: dict[str, int] = {}
        for row in history:
            values = row.get(field, {})
            if not isinstance(values, dict):
                continue
            for key, value in values.items():
                try:
                    totals[str(key)] = totals.get(str(key), 0) + int(value)
                except (TypeError, ValueError):
                    continue
        return totals

    def _aggregate_summaries(self, history: list[dict[str, Any]]) -> dict[str, Any]:
        first = history[0]
        last = history[-1]
        aggregate: dict[str, Any] = {
            "schema_version": "1.1.0",
            "started_at": first.get("started_at"),
            "finished_at": last.get("finished_at"),
            "run_count": len(history),
            "run_history_path": self.history_path.name,
            "last_run": last,
        }
        for field in (
            "sources_requested",
            "successful_endpoint_count",
            "fallback_endpoint_count",
            "html_fallback_count",
            "firecrawl_fallback_count",
            "firecrawl_calls_used",
            "failed_endpoint_count",
            "skipped_endpoint_count",
            "settled_skip_count",
            "new_capture_count",
            "new_candidate_count",
            "post_count",
            "comment_count",
        ):
            aggregate[field] = sum(int(row.get(field, 0) or 0) for row in history)
        aggregate["consecutive_failure_count"] = int(last.get("consecutive_failure_count", 0) or 0)
        aggregate["subreddits_checked"] = self._ordered_union(history, "subreddits_checked")
        aggregate["known_subreddits"] = sorted({
            str(value)
            for row in history
            for value in row.get("known_subreddits", [])
            if isinstance(row.get("known_subreddits", []), list)
        })
        aggregate["discovered_subreddits"] = self._ordered_union(history, "discovered_subreddits")
        aggregate["query_counts"] = self._summed_mapping(history, "query_counts")
        aggregate["source_post_counts"] = self._summed_mapping(history, "source_post_counts")
        aggregate["errors"] = [
            error
            for row in history
            for error in row.get("errors", [])
            if isinstance(error, dict)
        ]
        aggregate["capture_count"] = len(self.capture_keys)
        aggregate["candidate_count"] = len(self.candidates)
        aggregate["duration_seconds"] = round(sum(float(row.get("duration_seconds", 0) or 0) for row in history), 3)
        return aggregate

    def save_summary(self, summary: dict[str, Any]) -> None:
        history = self._read_summary_history()
        if not history and self.summary_path.exists():
            legacy = self._read_json(self.summary_path, None)
            if isinstance(legacy, dict) and legacy.get("started_at"):
                with self.history_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(legacy, ensure_ascii=False, sort_keys=True) + "\n")
                history.append(legacy)
        with self.history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(summary, ensure_ascii=False, sort_keys=True) + "\n")
        history.append(summary)
        self.summary_path.write_text(
            json.dumps(self._aggregate_summaries(history), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def _comment_rows(payload: Any):
    if not isinstance(payload, list):
        return
    for listing in payload:
        if not isinstance(listing, dict):
            continue
        data = listing.get("data", {})
        for child in data.get("children", []) if isinstance(data, dict) else []:
            if not isinstance(child, dict) or child.get("kind") != "t1":
                continue
            row = child.get("data", {})
            if not isinstance(row, dict) or not row.get("id"):
                continue
            yield row
            replies = row.get("replies")
            if replies:
                yield from _comment_rows([replies] if isinstance(replies, dict) else replies)


class RedditScraper:
    def __init__(
        self,
        registry: dict[str, Any],
        store: RunStore,
        *,
        client: Any | None = None,
        firecrawl: FirecrawlClient | None = None,
        max_pages: int = 3,
        max_posts: int = 250,
        max_comments: int = 100,
        resume: bool = True,
        overnight_hours: float | None = None,
        mode: str = "sweep",
        ledger: dict[str, Any] | None = None,
        ad_hoc_queries: list[str] | None = None,
        include_terms: list[str] | None = None,
        exclude_terms: list[str] | None = None,
    ) -> None:
        self.registry = registry
        self.store = store
        self.client = client or RedditClient()
        self.firecrawl = firecrawl
        if mode not in {"daily", "sweep"}:
            raise ValueError(f"unknown mode {mode!r}")
        self.mode = mode
        # An empty ledger means "nothing settled yet", so the crawler behaves exactly
        # as it did before the ledger existed.
        self.ledger = ledger if ledger is not None else empty_ledger()
        self.max_pages = max(1, max_pages)
        self.max_posts = max(1, max_posts)
        self.max_comments = max(0, max_comments)
        self.resume = resume
        self.deadline = time.monotonic() + overnight_hours * 3600 if overnight_hours else None
        self.ad_hoc_queries = ad_hoc_queries or None
        self.include_terms = include_terms or None
        self.exclude_terms = exclude_terms or None
        seed_count = max(1, len(registry.get("sources", [])))
        self.source_post_limit = max(1, self.max_posts // seed_count)

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _within_budget(self) -> bool:
        return self.deadline is None or time.monotonic() < self.deadline

    @staticmethod
    def _progress(message: str) -> None:
        """Live status to stderr. stdout carries only the final JSON summary,
        so this is safe to print freely without breaking that contract.

        Local time, unlike the UTC used for captured data: this line exists to be
        read against a wall clock by whoever is watching the run.
        """
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", file=sys.stderr, flush=True)

    def _html_fallback(self, url: str, method: str) -> tuple[bool, Any, str | None]:
        """Use old Reddit HTML when modern JSON is blocked by the public endpoint."""
        if not hasattr(self.client, "get_text"):
            return False, None, None
        parsed = urlparse(url)
        if method == "text":
            fallback_url = old_reddit_url(url)
        elif "/search.json" in parsed.path:
            fallback_url = old_search_url(url)
        elif parsed.path.endswith("/new.json"):
            fallback_url = old_listing_url(url)
        elif "/comments/" in parsed.path and parsed.path.endswith(".json"):
            fallback_url = old_reddit_url(url)
        elif parsed.path.endswith("/about.json"):
            subreddit = parsed.path.split("/r/", 1)[1].split("/", 1)[0]
            fallback_url = f"https://old.reddit.com/r/{subreddit}/"
        else:
            return False, None, None
        try:
            html = self.client.get_text(fallback_url)
        except Exception as error:
            return False, None, f"{type(error).__name__}: {error}"
        if method == "text":
            return True, html, None
        subreddit = parsed.path.split("/r/", 1)[1].split("/", 1)[0] if "/r/" in parsed.path else ""
        if "/search.json" in parsed.path:
            return True, parse_old_search_html(html, subreddit), None
        if parsed.path.endswith("/new.json"):
            return True, parse_old_listing_html(html, subreddit), None
        if "/comments/" in parsed.path:
            return True, parse_old_comments_html(html), None
        return True, {}, None

    def _firecrawl_fallback(self, url: str, method: str) -> tuple[bool, Any, str | None]:
        """Last resort: ask Firecrawl for the old-Reddit page when both prior tiers failed."""
        if self.firecrawl is None or not self.firecrawl.enabled:
            return False, None, None
        if not self.firecrawl.budget_remaining:
            return False, None, "firecrawl call budget exhausted"
        parsed = urlparse(url)
        is_search = "/search.json" in parsed.path
        is_listing = parsed.path.endswith("/new.json")
        if method == "text":
            target_url = old_reddit_url(url)
        elif is_search:
            target_url = old_search_url(url)
        elif is_listing:
            target_url = old_listing_url(url)
        elif "/comments/" in parsed.path and parsed.path.endswith(".json"):
            target_url = old_reddit_url(url)
        elif parsed.path.endswith("/about.json"):
            subreddit = parsed.path.split("/r/", 1)[1].split("/", 1)[0]
            target_url = f"https://old.reddit.com/r/{subreddit}/"
        else:
            return False, None, None
        try:
            data = self.firecrawl.scrape(target_url)
            html = str(data.get("html") or "")
            subreddit = parsed.path.split("/r/", 1)[1].split("/", 1)[0] if "/r/" in parsed.path else ""
            result = firecrawl_to_listing(
                html, method=method, subreddit=subreddit, is_search=is_search, is_listing=is_listing
            )
        except Exception as error:
            return False, None, f"{type(error).__name__}: {error}"
        return True, result, None

    def _fetch(self, url: str, method: str, summary: dict[str, Any]) -> Any | None:
        if self.resume and self.store.endpoint_complete(url):
            summary["skipped_endpoint_count"] += 1
            return None
        try:
            result = self.client.get_json(url) if method == "json" else self.client.get_text(url)
        except Exception as error:  # keep unrelated sources running
            fallback_error = None
            if method in {"json", "text"}:
                tier = "html"
                handled, result, fallback_error = self._html_fallback(url, method)
                if not handled:
                    tier = "firecrawl"
                    handled, result, firecrawl_error = self._firecrawl_fallback(url, method)
                    if firecrawl_error:
                        fallback_error = f"{fallback_error or ''} | firecrawl: {firecrawl_error}".strip(" |")
                if handled:
                    summary["successful_endpoint_count"] += 1
                    summary["fallback_endpoint_count"] += 1
                    # Tier 3 is the only tier that costs money; keep it separately
                    # countable so a run summary shows exactly what was paid for.
                    summary[f"{tier}_fallback_count"] += 1
                    summary["consecutive_failure_count"] = 0
                    self.store.mark_endpoint_complete(url, self._timestamp())
                    return result
            summary["failed_endpoint_count"] += 1
            summary["consecutive_failure_count"] += 1
            entry = {"url": url, "error": f"{type(error).__name__}: {error}"}
            if fallback_error:
                entry["fallback_error"] = fallback_error
            summary["errors"].append(entry)
            self.store.add_error(entry, self._timestamp())
            return None
        summary["successful_endpoint_count"] += 1
        summary["consecutive_failure_count"] = 0
        self.store.mark_endpoint_complete(url, self._timestamp())
        return result

    def _capture_post(
        self,
        subreddit: str,
        post: dict[str, Any],
        summary: dict[str, Any],
        *,
        include_comments: bool,
    ) -> bool:
        post_id = str(post.get("id") or "")
        if not post_id:
            return False
        # Cross-run memory: a post already promoted to evidence or explicitly rejected
        # never becomes a candidate again, no matter which run directory is in use.
        if is_settled(self.ledger, f"t3_{post_id.casefold()}"):
            summary["settled_skip_count"] += 1
            return False
        title, title_flags = sanitize_text(str(post.get("title") or ""))
        body, body_flags = sanitize_text(str(post.get("selftext") or ""))
        if not matches_scope(f"{title} {body}", self.include_terms, self.exclude_terms):
            summary["scope_filtered_count"] = summary.get("scope_filtered_count", 0) + 1
            return False
        record = {
            "id": post_id,
            "kind": "post",
            "url": public_post_url(subreddit, post),
            "subreddit": subreddit,
            "author": str(post.get("author") or "[deleted]"),
            "publication_date": iso_date_from_timestamp(post.get("created_utc")),
            "title": title or "Untitled public post",
            "flair": str(post.get("link_flair_text") or post.get("flair") or ""),
            "text": body,
            "redaction_flags": _merge_flags(title_flags, body_flags),
            "captured_at": self._timestamp(),
        }
        if self.store.append_capture(record):
            summary["new_capture_count"] += 1
        candidate = candidate_from_post(post, subreddit, record["captured_at"])
        if self.store.append_candidate(candidate):
            summary["new_candidate_count"] += 1
        summary["post_count"] += 1

        if self.max_comments <= 0 or not include_comments:
            return True
        comment_payload = self._fetch(comments_url(subreddit, post_id, self.max_comments), "json", summary)
        if comment_payload is None:
            return True
        for index, comment in enumerate(_comment_rows(comment_payload)):
            if index >= self.max_comments or not self._within_budget():
                break
            self._capture_comment(subreddit, post, comment, summary)
        return True

    def _capture_comment(self, subreddit: str, post: dict[str, Any], comment: dict[str, Any], summary: dict[str, Any]) -> None:
        comment_id = str(comment.get("id") or "")
        if not comment_id:
            return
        body, flags = sanitize_text(str(comment.get("body") or ""))
        record = {
            "id": comment_id,
            "kind": "comment",
            "url": str(comment.get("permalink") or public_post_url(subreddit, post)),
            "parent_post_url": public_post_url(subreddit, post),
            "subreddit": subreddit,
            "author": str(comment.get("author") or "[deleted]"),
            "publication_date": iso_date_from_timestamp(comment.get("created_utc")),
            "title": str(post.get("title") or "Untitled public post"),
            "text": body,
            "redaction_flags": flags,
            "captured_at": self._timestamp(),
        }
        if self.store.append_capture(record):
            summary["new_capture_count"] += 1
        summary["comment_count"] += 1

    def _daily_source(
        self,
        source: dict[str, Any],
        summary: dict[str, Any],
        post_limit: int,
        *,
        include_comments: bool,
    ) -> int:
        """Poll newest-first and stop at the stored watermark.

        Cost is proportional to what was posted since the last run, not to the size
        of the search-term matrix, which is what keeps a daily crawl flat as more
        communities are added.
        """
        subreddit = source["subreddit"]
        since = watermark(self.ledger, subreddit)
        newest_seen = since
        source_post_count = 0
        after = None
        reached_watermark = False
        for _page in range(self.max_pages):
            if (
                reached_watermark
                or not self._within_budget()
                or summary["post_count"] >= self.max_posts
                or source_post_count >= post_limit
                or summary["consecutive_failure_count"] >= 3
            ):
                break
            payload = self._fetch(new_url(subreddit, after), "json", summary)
            if not isinstance(payload, dict):
                break
            listing = payload.get("data", {})
            children = listing.get("children", []) if isinstance(listing, dict) else []
            for child in children:
                if (
                    summary["post_count"] >= self.max_posts
                    or source_post_count >= post_limit
                    or not self._within_budget()
                    or summary["consecutive_failure_count"] >= 3
                ):
                    break
                post = child.get("data") if isinstance(child, dict) else None
                if not isinstance(post, dict):
                    continue
                try:
                    created = float(post.get("created_utc") or 0)
                except (TypeError, ValueError):
                    created = 0.0
                newest_seen = max(newest_seen, created)
                if since and created and created <= since:
                    # Listing is newest-first, so the first already-seen post means
                    # everything below it was covered by an earlier run.
                    reached_watermark = True
                    break
                if self._capture_post(subreddit, post, summary, include_comments=include_comments):
                    source_post_count += 1
            after = listing.get("after") if isinstance(listing, dict) else None
            if not after or not children:
                break
        # Only advance once the source finished cleanly; a run cut short by the
        # circuit breaker must re-check the same window tomorrow.
        if summary["consecutive_failure_count"] < 3:
            set_watermark(self.ledger, subreddit, newest_seen)
        return source_post_count

    def _source(self, source: dict[str, Any], summary: dict[str, Any], post_limit: int) -> list[str]:
        subreddit = source["subreddit"]
        base = subreddit_base(subreddit)
        discovered: list[str] = []
        source_post_count = 0
        # Failure streaks are scoped to one source. A blocked seed must not
        # prevent later communities in the same crawl from being attempted.
        summary["consecutive_failure_count"] = 0
        # Wiki/landing discovery is a sweep concern. A daily poll re-reading static
        # wiki pages every night is pure waste, so it is skipped in daily mode.
        if self.mode == "sweep":
            html_urls = [source["landing_url"]] + [f"{base.rstrip('/')}{path}" for path in source.get("wiki_paths", [])]
            for url in html_urls:
                if not self._within_budget() or summary["consecutive_failure_count"] >= 3:
                    break
                html = self._fetch(url, "text", summary)
                if isinstance(html, str):
                    discovered.extend(discover_subreddits(html, summary["known_subreddits"]))

        include_comments = bool(
            source.get("include_comments", self.registry.get("include_comments_by_default", True))
        )
        if self.mode == "daily":
            source_post_count = self._daily_source(
                source, summary, post_limit, include_comments=include_comments
            )
            summary["source_post_counts"][f"r/{subreddit}"] = source_post_count
            return discovered

        queries = list(dict.fromkeys(self.ad_hoc_queries or self.registry.get("search_terms", [])))
        # Breadth before depth: page 1 of every term, then page 2 of every term, and so
        # on -- rather than draining one term to its last page before starting the next.
        #
        # The per-subreddit post budget is finite and spent in the order requests are
        # made, so a depth-first pass lets a handful of high-volume terms consume it
        # entirely and the remaining terms never issue a single request. Reordering the
        # term list only moves which ones get starved. Since Reddit sorts search results
        # by relevance, page 1 of a term is also its best page, so this spends the budget
        # on the strongest results for every term before any term's weaker pages.
        cursors: dict[str, str | None] = {query: None for query in queries}
        exhausted: set[str] = set()
        for page_index in range(self.max_pages):
            if (
                not self._within_budget()
                or summary["post_count"] >= self.max_posts
                or source_post_count >= post_limit
                or summary["consecutive_failure_count"] >= 3
                or len(exhausted) >= len(queries)
            ):
                break
            for query_index, query in enumerate(queries, start=1):
                if query in exhausted:
                    continue
                if (
                    not self._within_budget()
                    or summary["post_count"] >= self.max_posts
                    or source_post_count >= post_limit
                    or summary["consecutive_failure_count"] >= 3
                ):
                    break
                self._progress(
                    f"r/{subreddit}: page {page_index + 1}/{self.max_pages} "
                    f"query {query_index}/{len(queries)} \"{query}\""
                )
                endpoint = search_url(subreddit, query, cursors[query])
                payload = self._fetch(endpoint, "json", summary)
                if not isinstance(payload, dict):
                    exhausted.add(query)
                    continue
                listing = payload.get("data", {})
                children = listing.get("children", []) if isinstance(listing, dict) else []
                summary["query_counts"].setdefault(f"r/{subreddit}:{query}", 0)
                for child in children:
                    if (
                        summary["post_count"] >= self.max_posts
                        or source_post_count >= post_limit
                        or not self._within_budget()
                        or summary["consecutive_failure_count"] >= 3
                    ):
                        break
                    post = child.get("data") if isinstance(child, dict) else None
                    if isinstance(post, dict):
                        captured = self._capture_post(
                            subreddit,
                            post,
                            summary,
                            include_comments=include_comments,
                        )
                        if captured:
                            source_post_count += 1
                        summary["query_counts"][f"r/{subreddit}:{query}"] += 1
                after = listing.get("after") if isinstance(listing, dict) else None
                if not after or not children:
                    exhausted.add(query)
                else:
                    cursors[query] = after
        summary["source_post_counts"][f"r/{subreddit}"] = source_post_count
        return discovered

    def run(self) -> dict[str, Any]:
        run_started_monotonic = time.monotonic()
        started_at = self._timestamp()
        self._progress(
            f"auth: OAuth app-only via {getattr(self.client, 'grant_type', 'unknown')} (oauth.reddit.com)"
            if getattr(self.client, "authenticated", False)
            else "auth: anonymous public JSON -- set REDDIT_CLIENT_ID for higher limits"
        )
        self.store.manifest.setdefault("started_at", started_at)
        self.store.manifest["updated_at"] = started_at
        self.store.save_manifest()
        summary: dict[str, Any] = {
            "started_at": started_at,
            "finished_at": None,
            "sources_requested": 0,
            "subreddits_checked": [],
            "known_subreddits": {row["subreddit"] for row in self.registry.get("sources", [])},
            "discovered_subreddits": [],
            "successful_endpoint_count": 0,
            "fallback_endpoint_count": 0,
            "html_fallback_count": 0,
            "firecrawl_fallback_count": 0,
            "failed_endpoint_count": 0,
            "consecutive_failure_count": 0,
            "skipped_endpoint_count": 0,
            "settled_skip_count": 0,
            "new_capture_count": 0,
            "new_candidate_count": 0,
            "post_count": 0,
            "comment_count": 0,
            "scope_filtered_count": 0,
            "query_counts": {},
            "source_post_counts": {},
            "errors": [],
        }
        queue = list(self.registry.get("sources", []))
        max_discovered = int(self.registry.get("max_discovered_subreddits", 0) or 0)
        while queue and self._within_budget() and summary["post_count"] < self.max_posts:
            source = queue.pop(0)
            subreddit = source["subreddit"]
            if subreddit in summary["subreddits_checked"]:
                continue
            summary["sources_requested"] += 1
            summary["subreddits_checked"].append(subreddit)
            self._progress(f"r/{subreddit}: starting ({self.mode} mode)")
            discovered = self._source(source, summary, self.source_post_limit)
            self._progress(
                f"r/{subreddit}: done, "
                f"{summary['source_post_counts'].get(f'r/{subreddit}', 0)} posts captured this source "
                f"({summary['post_count']} total, {summary['new_candidate_count']} new candidates)"
            )
            for name in discovered:
                if (
                    name.casefold() in {item.casefold() for item in summary["known_subreddits"]}
                    or len(summary["discovered_subreddits"]) >= max_discovered
                ):
                    continue
                summary["known_subreddits"].add(name)
                summary["discovered_subreddits"].append(name)
                queue.append({
                    "subreddit": name,
                    "landing_url": subreddit_base(name),
                    "wiki_paths": ["/wiki/", "/about/sidebar/"],
                    "include_comments": self.registry.get("include_comments_by_default", True),
                })
        if self.mode == "sweep":
            for name in summary["subreddits_checked"]:
                set_watermark(self.ledger, name, watermark(self.ledger, name), full_sweep=True)
        summary["mode"] = self.mode
        summary["auth_mode"] = getattr(self.client, "grant_type", None) or "anonymous"
        summary["finished_at"] = self._timestamp()
        summary["capture_count"] = len(self.store.capture_keys)
        summary["candidate_count"] = len(self.store.candidates)
        summary["duration_seconds"] = round(time.monotonic() - run_started_monotonic, 3)
        summary["firecrawl_calls_used"] = self.firecrawl.call_count if self.firecrawl else 0
        summary["known_subreddits"] = sorted(summary["known_subreddits"])
        self.store.save_summary(summary)
        return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=Path("data/research_sources.json"))
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=("daily", "sweep"),
        default="sweep",
        help="daily polls /new.json down to the stored watermark; sweep runs the full search-term matrix",
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=None,
        help="path to the committed crawl ledger (defaults to data/scrape_ledger.json)",
    )
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--max-posts", type=int, default=250)
    parser.add_argument("--max-comments", type=int, default=100)
    parser.add_argument("--delay", type=float, default=1.5)
    parser.add_argument("--overnight-hours", type=float)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--max-firecrawl-calls",
        type=int,
        default=25,
        help="hard cap on billable tier-3 Firecrawl scrapes per run (0 disables the tier)",
    )
    parser.add_argument(
        "--query",
        action="append",
        dest="queries",
        help="Ad-hoc search query for a scoped request (repeatable). Replaces the registry's search_terms for this run.",
    )
    parser.add_argument(
        "--include-terms",
        action="append",
        dest="include_terms",
        help="Only keep posts whose title/body contains at least one of these terms (repeatable).",
    )
    parser.add_argument(
        "--exclude-terms",
        action="append",
        dest="exclude_terms",
        help="Discard posts whose title/body contains any of these terms (repeatable).",
    )
    args = parser.parse_args()
    registry = load_registry(args.registry)
    firecrawl_key = os.environ.get("FIRECRAWL_API_KEY", "").strip() or None
    ledger = load_ledger(args.ledger)
    scraper = RedditScraper(
        registry,
        RunStore(args.run_dir),
        client=RedditClient(delay=args.delay),
        firecrawl=(
            FirecrawlClient(api_key=firecrawl_key, max_calls=args.max_firecrawl_calls)
            if firecrawl_key and args.max_firecrawl_calls > 0
            else None
        ),
        max_pages=args.max_pages,
        max_posts=args.max_posts,
        max_comments=args.max_comments,
        resume=args.resume,
        overnight_hours=args.overnight_hours,
        mode=args.mode,
        ledger=ledger,
        ad_hoc_queries=args.queries,
        include_terms=args.include_terms,
        exclude_terms=args.exclude_terms,
    )
    summary = scraper.run()
    # Watermarks advance during the run; persist them so tomorrow starts where
    # tonight stopped. Triage writes the dispositions later.
    save_ledger(scraper.ledger, args.ledger)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["successful_endpoint_count"] or not summary["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
