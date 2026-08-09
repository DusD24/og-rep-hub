#!/usr/bin/env python3
"""Privacy-safe, resumable discovery helpers for public Reddit research."""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen


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
KNOWN_BAG_TERMS = (
    "Neverfull", "Speedy", "Alma", "Classic Flap", "Chanel 25", "Chanel 19",
    "Andiamo", "Puzzle", "Flamenco", "Margaux", "Birkin", "Kelly", "Lady Dior",
    "Book Tote", "Saint Louis", "Arcadie", "Saddle", "Dionysus", "Jackie",
    "Prada", "Miu Miu", "Loewe", "Chanel", "Louis Vuitton", "Dior", "Hermes",
    "Bottega", "Goyard", "YSL", "Saint Laurent",
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


def comments_url(subreddit: str, post_id: str, limit: int = 100) -> str:
    params = {"raw_json": "1", "limit": str(limit), "sort": "top"}
    return f"{subreddit_base(subreddit)}comments/{quote(post_id, safe='')}.json?{urlencode(params)}"


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


def _unique_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    folded = text.casefold()
    return [term for term in terms if term.casefold() in folded]


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
    """Small stdlib-only client for public Reddit endpoints."""

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        retries: int = 3,
        delay: float = 1.5,
        user_agent: str = "OG-Rep-Hub-Research/1.0 (public-source catalog)",
    ) -> None:
        self.timeout = timeout
        self.retries = max(1, retries)
        self.delay = max(0.0, delay)
        self.user_agent = user_agent

    def _get(self, url: str, accept: str) -> bytes:
        last_error: Exception | None = None
        for attempt in range(self.retries):
            if self.delay and attempt:
                time.sleep(self.delay * attempt)
            request = Request(url, headers={"Accept": accept, "User-Agent": self.user_agent})
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    return response.read()
            except HTTPError as error:
                last_error = error
                if error.code not in {429, 500, 502, 503, 504}:
                    raise
            except URLError as error:
                last_error = error
        raise RuntimeError(f"public Reddit request failed after {self.retries} attempts: {url}") from last_error

    def get_text(self, url: str) -> str:
        return self._get(url, "text/html,application/xhtml+xml").decode("utf-8", errors="replace")

    def get_json(self, url: str) -> Any:
        return json.loads(self._get(url, "application/json").decode("utf-8", errors="replace"))


class RunStore:
    """Persist captures, candidates, and progress so an interrupted run resumes."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifest.json"
        self.captures_path = self.root / "captures.jsonl"
        self.candidates_path = self.root / "candidates.json"
        self.summary_path = self.root / "run-summary.json"
        self.manifest = self._read_json(self.manifest_path, {
            "schema_version": "1.0.0",
            "started_at": None,
            "updated_at": None,
            "completed_endpoints": [],
            "errors": [],
        })
        self.capture_keys = self._load_capture_keys()
        self.candidates = self._read_json(self.candidates_path, [])
        self.candidate_ids = {row.get("candidate_id") for row in self.candidates if row.get("candidate_id")}

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default

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
        return url in set(self.manifest.get("completed_endpoints", []))

    def mark_endpoint_complete(self, url: str, timestamp: str) -> None:
        completed = self.manifest.setdefault("completed_endpoints", [])
        if url not in completed:
            completed.append(url)
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
        self.candidates_path.write_text(
            json.dumps(self.candidates, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return True

    def save_manifest(self) -> None:
        self.manifest_path.write_text(
            json.dumps(self.manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def save_summary(self, summary: dict[str, Any]) -> None:
        self.summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
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
        max_pages: int = 3,
        max_posts: int = 250,
        max_comments: int = 100,
        resume: bool = True,
        overnight_hours: float | None = None,
    ) -> None:
        self.registry = registry
        self.store = store
        self.client = client or RedditClient()
        self.max_pages = max(1, max_pages)
        self.max_posts = max(1, max_posts)
        self.max_comments = max(0, max_comments)
        self.resume = resume
        self.deadline = time.monotonic() + overnight_hours * 3600 if overnight_hours else None

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _within_budget(self) -> bool:
        return self.deadline is None or time.monotonic() < self.deadline

    def _fetch(self, url: str, method: str, summary: dict[str, Any]) -> Any | None:
        if self.resume and self.store.endpoint_complete(url):
            summary["skipped_endpoint_count"] += 1
            return None
        try:
            result = self.client.get_json(url) if method == "json" else self.client.get_text(url)
        except Exception as error:  # keep unrelated sources running
            summary["failed_endpoint_count"] += 1
            entry = {"url": url, "error": f"{type(error).__name__}: {error}"}
            summary["errors"].append(entry)
            self.store.add_error(entry, self._timestamp())
            return None
        summary["successful_endpoint_count"] += 1
        self.store.mark_endpoint_complete(url, self._timestamp())
        return result

    def _capture_post(
        self,
        subreddit: str,
        post: dict[str, Any],
        summary: dict[str, Any],
        *,
        include_comments: bool,
    ) -> None:
        post_id = str(post.get("id") or "")
        if not post_id:
            return
        title, title_flags = sanitize_text(str(post.get("title") or ""))
        body, body_flags = sanitize_text(str(post.get("selftext") or ""))
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
            return
        comment_payload = self._fetch(comments_url(subreddit, post_id, self.max_comments), "json", summary)
        if comment_payload is None:
            return
        for index, comment in enumerate(_comment_rows(comment_payload)):
            if index >= self.max_comments or not self._within_budget():
                break
            self._capture_comment(subreddit, post, comment, summary)

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

    def _source(self, source: dict[str, Any], summary: dict[str, Any]) -> list[str]:
        subreddit = source["subreddit"]
        base = subreddit_base(subreddit)
        discovered: list[str] = []
        html_urls = [source["landing_url"]] + [f"{base.rstrip('/')}{path}" for path in source.get("wiki_paths", [])]
        for url in html_urls:
            if not self._within_budget():
                break
            html = self._fetch(url, "text", summary)
            if isinstance(html, str):
                discovered.extend(discover_subreddits(html, summary["known_subreddits"]))
        self._fetch(about_url(subreddit), "json", summary)

        queries = list(dict.fromkeys(self.registry.get("search_terms", [])))
        for query in queries:
            after = None
            for _page in range(self.max_pages):
                if not self._within_budget() or summary["post_count"] >= self.max_posts:
                    break
                endpoint = search_url(subreddit, query, after)
                payload = self._fetch(endpoint, "json", summary)
                if not isinstance(payload, dict):
                    break
                listing = payload.get("data", {})
                children = listing.get("children", []) if isinstance(listing, dict) else []
                summary["query_counts"].setdefault(f"r/{subreddit}:{query}", 0)
                for child in children:
                    if summary["post_count"] >= self.max_posts or not self._within_budget():
                        break
                    post = child.get("data") if isinstance(child, dict) else None
                    if isinstance(post, dict):
                        self._capture_post(
                            subreddit,
                            post,
                            summary,
                            include_comments=bool(
                                source.get(
                                    "include_comments",
                                    self.registry.get("include_comments_by_default", True),
                                )
                            ),
                        )
                        summary["query_counts"][f"r/{subreddit}:{query}"] += 1
                after = listing.get("after") if isinstance(listing, dict) else None
                if not after or not children:
                    break
        return discovered

    def run(self) -> dict[str, Any]:
        run_started_monotonic = time.monotonic()
        started_at = self._timestamp()
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
            "failed_endpoint_count": 0,
            "skipped_endpoint_count": 0,
            "new_capture_count": 0,
            "new_candidate_count": 0,
            "post_count": 0,
            "comment_count": 0,
            "query_counts": {},
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
            discovered = self._source(source, summary)
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
        summary["finished_at"] = self._timestamp()
        summary["capture_count"] = len(self.store.capture_keys)
        summary["candidate_count"] = len(self.store.candidates)
        summary["duration_seconds"] = round(time.monotonic() - run_started_monotonic, 3)
        summary["known_subreddits"] = sorted(summary["known_subreddits"])
        self.store.save_summary(summary)
        return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=Path("data/research_sources.json"))
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--max-posts", type=int, default=250)
    parser.add_argument("--max-comments", type=int, default=100)
    parser.add_argument("--delay", type=float, default=1.5)
    parser.add_argument("--overnight-hours", type=float)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    registry = load_registry(args.registry)
    summary = RedditScraper(
        registry,
        RunStore(args.run_dir),
        client=RedditClient(delay=args.delay),
        max_pages=args.max_pages,
        max_posts=args.max_posts,
        max_comments=args.max_comments,
        resume=args.resume,
        overnight_hours=args.overnight_hours,
    ).run()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["successful_endpoint_count"] or not summary["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
