import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from scrape_reddit import (  # noqa: E402
    canonical_subreddit_url,
    candidate_from_post,
    discover_subreddits,
    firecrawl_to_listing,
    load_registry,
    old_reddit_url,
    old_search_url,
    parse_old_comments_html,
    parse_old_search_html,
    RedditScraper,
    RunStore,
    sanitize_text,
    search_url,
    _comment_rows,
)


class ScraperContractTests(unittest.TestCase):
    def test_registry_has_four_seed_communities_and_review_queries(self):
        registry = load_registry(ROOT / "data" / "research_sources.json")
        names = {row["subreddit"] for row in registry["sources"]}
        self.assertTrue(
            {"RealRepLadies", "RepTherapy", "RepLadiesWorld", "RepCulture_Bags"} <= names
        )
        self.assertTrue(
            {"review", "QC", "PSP", "receipt", "wear"} <= set(registry["search_terms"])
        )

    def test_sanitize_text_redacts_sensitive_fields_without_losing_review_signal(self):
        text, flags = sanitize_text(
            "Seller WhatsApp +86 123 456 7890; paid $240 by PayPal; "
            "review says leather is soft."
        )
        self.assertNotIn("123 456 7890", text)
        self.assertNotIn("$240", text)
        self.assertIn("leather is soft", text)
        self.assertTrue(flags["contact_present"])
        self.assertTrue(flags["payment_present"])

    def test_sanitize_text_redacts_private_messages_addresses_and_secrets(self):
        text, flags = sanitize_text(
            "DM me at jane@example.com. My address is 123 Main Street. "
            "password: hunter2; sk_live_abc123."
        )
        self.assertNotIn("jane@example.com", text)
        self.assertNotIn("123 Main Street", text)
        self.assertNotIn("hunter2", text)
        self.assertNotIn("sk_live_abc123", text)
        self.assertTrue(flags["private_message_present"])
        self.assertTrue(flags["address_present"])
        self.assertTrue(flags["secret_present"])

    def test_discover_subreddits_only_returns_new_public_subreddit_paths(self):
        html = (
            '<a href="https://www.reddit.com/r/NewRepBags/">new</a>'
            '<a href="https://example.com/r/nope">no</a>'
            '<a href="/r/RepCulture_Bags/">known</a>'
        )
        self.assertEqual(
            discover_subreddits(html, {"RepCulture_Bags"}),
            ["NewRepBags"],
        )

    def test_canonical_subreddit_url_rejects_non_reddit_and_user_paths(self):
        self.assertEqual(
            canonical_subreddit_url("https://www.reddit.com/r/RepCulture_Bags/"),
            "https://www.reddit.com/r/RepCulture_Bags/",
        )
        self.assertIsNone(canonical_subreddit_url("https://www.reddit.com/u/someone/"))
        self.assertIsNone(canonical_subreddit_url("https://example.com/r/RepCulture_Bags/"))

    def test_old_reddit_fallback_urls_and_search_parser_keep_public_post_fields(self):
        self.assertIn("old.reddit.com/r/RepCulture_Bags/search/", old_reddit_url(
            "https://www.reddit.com/r/RepCulture_Bags/search.json?q=review"
        ))
        html = (
            '<div class="search-result search-result-link">'
            '<a class="search-title" href="https://old.reddit.com/r/RepCulture_Bags/comments/abc/title/">'
            "Speedy review</a>"
            '<a class="author">reader</a>'
            '<time datetime="2026-08-08T00:00:00+00:00"></time>'
            '<div class="search-result-body"><div class="md"><p>soft leather</p></div></div>'
            "</div>"
        )
        payload = parse_old_search_html(html, "RepCulture_Bags")
        post = payload["data"]["children"][0]["data"]
        self.assertEqual(post["id"], "abc")
        self.assertEqual(post["author"], "reader")
        self.assertIn("soft leather", post["selftext"])

    def test_old_reddit_comments_parser_keeps_nested_public_replies(self):
        html = (
            '<div class="thing id-t1_c1 comment" data-author="reader" '
            'data-permalink="/r/RepCulture_Bags/comments/post/c1/">'
            '<time datetime="2026-08-08T00:00:00+00:00"></time>'
            '<div class="usertext-body"><div class="md"><p>top reply</p></div></div>'
            '<div class="child"><div class="thing id-t1_c2 comment" data-author="other" '
            'data-permalink="/r/RepCulture_Bags/comments/post/c2/">'
            '<div class="usertext-body"><div class="md"><p>nested reply</p></div></div>'
            "</div></div></div>"
        )
        rows = [child["data"] for listing in parse_old_comments_html(html) for child in listing["data"]["children"]]
        self.assertEqual([row["id"] for row in rows], ["c2", "c1"])
        self.assertEqual(rows[0]["body"], "nested reply")

    def test_firecrawl_to_listing_parses_search_results_via_existing_parser(self):
        html = (
            '<div class="search-result search-result-link">'
            '<a class="search-title" href="https://old.reddit.com/r/RepCulture_Bags/comments/abc/title/">'
            "Speedy review</a>"
            '<a class="author">reader</a>'
            '<time datetime="2026-08-08T00:00:00+00:00"></time>'
            '<div class="search-result-body"><div class="md"><p>soft leather</p></div></div>'
            "</div>"
        )
        payload = firecrawl_to_listing(html, method="json", subreddit="RepCulture_Bags", is_search=True)
        post = payload["data"]["children"][0]["data"]
        self.assertEqual(post["id"], "abc")
        self.assertEqual(post["author"], "reader")

    def test_firecrawl_to_listing_parses_comment_threads_via_existing_parser(self):
        html = (
            '<div class="thing id-t1_c1 comment" data-author="reader" '
            'data-permalink="/r/RepCulture_Bags/comments/post/c1/">'
            '<time datetime="2026-08-08T00:00:00+00:00"></time>'
            '<div class="usertext-body"><div class="md"><p>top reply</p></div></div>'
            "</div>"
        )
        payload = firecrawl_to_listing(html, method="json", subreddit="RepCulture_Bags", is_search=False)
        rows = [child["data"] for listing in payload for child in listing["data"]["children"]]
        self.assertEqual(rows[0]["id"], "c1")

    def test_firecrawl_to_listing_raises_on_empty_html(self):
        with self.assertRaises(RuntimeError):
            firecrawl_to_listing("", method="json", subreddit="RepCulture_Bags", is_search=True)

    def test_firecrawl_result_is_sanitized_like_other_tiers(self):
        html = (
            '<div class="search-result search-result-link">'
            '<a class="search-title" href="https://old.reddit.com/r/RepTherapy/comments/xyz/title/">'
            "Seller contact</a>"
            '<a class="author">reader</a>'
            '<time datetime="2026-08-08T00:00:00+00:00"></time>'
            '<div class="search-result-body"><div class="md">'
            "<p>DM me at jane@example.com for details.</p></div></div>"
            "</div>"
        )
        payload = firecrawl_to_listing(html, method="json", subreddit="RepTherapy", is_search=True)
        post = payload["data"]["children"][0]["data"]
        candidate = candidate_from_post(post, "RepTherapy", "2026-08-08T00:00:00+00:00")
        self.assertNotIn("jane@example.com", candidate["redacted_excerpt"])
        self.assertTrue(candidate["redaction_flags"]["private_message_present"])


class FakeClient:
    def __init__(self, fail_urls=None, posts=None):
        self.fail_urls = set(fail_urls or ())
        self.posts = list(posts or ())
        self.calls = []

    def get_text(self, url):
        self.calls.append(("text", url))
        if url in self.fail_urls:
            raise OSError(f"fixture failure for {url}")
        return '<a href="/r/DiscoveredRep/">discovered</a>'

    def get_json(self, url):
        self.calls.append(("json", url))
        if url in self.fail_urls:
            raise OSError(f"fixture failure for {url}")
        if "/comments/" in url:
            return [{"kind": "Listing", "data": {"children": []}}]
        if "search.json" in url:
            return {"data": {"children": [{"kind": "t3", "data": post} for post in self.posts], "after": None}}
        return {"data": {}}


class FailFirstSourceClient(FakeClient):
    """Make every request for the first seed fail while later seeds work."""

    @staticmethod
    def _fails(url):
        return "RepCulture_Bags" in url

    def get_text(self, url):
        if self._fails(url):
            self.calls.append(("text", url))
            raise OSError("first source fixture failure")
        return super().get_text(url)

    def get_json(self, url):
        if self._fails(url):
            self.calls.append(("json", url))
            raise OSError("first source fixture failure")
        return super().get_json(url)


class AlwaysFailClient(FakeClient):
    """Every request fails, so both the JSON API and the old-Reddit HTML fallback are exhausted."""

    def get_text(self, url):
        self.calls.append(("text", url))
        raise OSError(f"fixture failure for {url}")

    def get_json(self, url):
        self.calls.append(("json", url))
        raise OSError(f"fixture failure for {url}")


class FakeFirecrawlClient:
    def __init__(self, html_by_url=None, fail_urls=None, enabled=True):
        self.html_by_url = dict(html_by_url or {})
        self.fail_urls = set(fail_urls or ())
        self._enabled = enabled
        self.calls = []

    @property
    def enabled(self):
        return self._enabled

    def scrape(self, url):
        self.calls.append(url)
        if url in self.fail_urls:
            raise OSError(f"firecrawl fixture failure for {url}")
        return {"html": self.html_by_url.get(url, "")}


class CrawlerRunTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tempdir.name)
        self.registry = {
            "max_discovered_subreddits": 1,
            "include_comments_by_default": False,
            "search_terms": ["review"],
            "sources": [
                {
                    "subreddit": "RepCulture_Bags",
                    "landing_url": "https://www.reddit.com/r/RepCulture_Bags/",
                    "wiki_paths": ["/wiki/", "/about/sidebar/"],
                    "include_comments": False,
                },
                {
                    "subreddit": "RepTherapy",
                    "landing_url": "https://www.reddit.com/r/RepTherapy/",
                    "wiki_paths": ["/wiki/"],
                    "include_comments": False,
                },
            ],
        }

    def tearDown(self):
        self.tempdir.cleanup()

    def test_search_endpoint_encodes_query_and_cursor(self):
        endpoint = search_url("RepCulture_Bags", "receipt review", "t3_after")
        self.assertIn("restrict_sr=1", endpoint)
        self.assertIn("after=t3_after", endpoint)
        self.assertIn("receipt%20review", endpoint)

    def test_resume_skips_post_ids_already_in_manifest(self):
        store = RunStore(self.run_dir)
        store.append_capture({"id": "post-1", "kind": "post"})
        client = FakeClient(posts=[
            {
                "id": "post-1",
                "title": "A review",
                "selftext": "The leather is soft.",
                "author": "reader",
                "subreddit": "RepCulture_Bags",
                "created_utc": 1783907242.0,
                "permalink": "/r/RepCulture_Bags/comments/post-1/a_review/",
                "link_flair_text": "Review",
                "num_comments": 0,
            }
        ])
        summary = RedditScraper(
            self.registry,
            store,
            client=client,
            max_pages=1,
            max_posts=10,
        ).run()
        self.assertEqual(summary["new_capture_count"], 0)

    def test_one_failed_endpoint_is_recorded_and_other_sources_continue(self):
        failed = "https://www.reddit.com/r/RepTherapy/wiki/"
        client = FakeClient(fail_urls={failed, old_reddit_url(failed)})
        summary = RedditScraper(
            self.registry,
            RunStore(self.run_dir),
            client=client,
            max_pages=1,
            max_posts=10,
        ).run()
        self.assertGreater(summary["successful_endpoint_count"], 0)
        self.assertTrue(any(failed in error["url"] for error in summary["errors"]))

    def test_three_failures_in_one_source_do_not_poison_later_seed_sources(self):
        client = FailFirstSourceClient(posts=[
            {
                "id": "post-after-failure",
                "title": "A later-source review",
                "selftext": "The leather is soft.",
                "author": "reader",
                "subreddit": "RepTherapy",
                "created_utc": 1783907242.0,
                "permalink": "/r/RepTherapy/comments/post-after-failure/review/",
                "link_flair_text": "Review",
                "num_comments": 0,
            }
        ])
        summary = RedditScraper(
            self.registry,
            RunStore(self.run_dir),
            client=client,
            max_pages=1,
            max_posts=10,
        ).run()
        self.assertEqual(summary["source_post_counts"]["r/RepCulture_Bags"], 0)
        self.assertEqual(summary["source_post_counts"]["r/RepTherapy"], 1)

    def test_firecrawl_used_only_after_html_fallback_fails(self):
        search_endpoint = search_url("RepTherapy", "review")
        firecrawl_target = old_search_url(search_endpoint)
        search_html = (
            '<div class="search-result search-result-link">'
            '<a class="search-title" href="https://old.reddit.com/r/RepTherapy/comments/xyz/title/">'
            "Speedy review</a>"
            '<a class="author">reader</a>'
            '<time datetime="2026-08-08T00:00:00+00:00"></time>'
            '<div class="search-result-body"><div class="md"><p>soft leather</p></div></div>'
            "</div>"
        )
        client = AlwaysFailClient()
        firecrawl = FakeFirecrawlClient(html_by_url={firecrawl_target: search_html})
        summary = RedditScraper(
            self.registry,
            RunStore(self.run_dir),
            client=client,
            firecrawl=firecrawl,
            max_pages=1,
            max_posts=10,
        ).run()
        self.assertGreater(summary["fallback_endpoint_count"], 0)
        self.assertGreaterEqual(summary["new_candidate_count"], 1)
        self.assertIn(firecrawl_target, firecrawl.calls)

    def test_firecrawl_disabled_by_default_is_a_noop(self):
        client = AlwaysFailClient()
        summary = RedditScraper(
            self.registry,
            RunStore(self.run_dir),
            client=client,
            firecrawl=None,
            max_pages=1,
            max_posts=10,
        ).run()
        self.assertEqual(summary["new_candidate_count"], 0)
        self.assertTrue(summary["errors"])

    def test_firecrawl_fallback_respects_consecutive_failure_circuit_breaker(self):
        client = AlwaysFailClient()
        firecrawl = FakeFirecrawlClient()  # no html configured, so every scrape() yields empty content
        summary = RedditScraper(
            self.registry,
            RunStore(self.run_dir),
            client=client,
            firecrawl=firecrawl,
            max_pages=1,
            max_posts=10,
        ).run()
        self.assertEqual(summary["source_post_counts"]["r/RepCulture_Bags"], 0)
        self.assertEqual(summary["source_post_counts"]["r/RepTherapy"], 0)

    def test_run_writes_manifest_candidates_and_summary(self):
        client = FakeClient(posts=[
            {
                "id": "post-2",
                "title": "Speedy review after delivery",
                "selftext": "Factory: P9. The leather feels soft.",
                "author": "reader",
                "subreddit": "RepCulture_Bags",
                "created_utc": 1783907242.0,
                "permalink": "/r/RepCulture_Bags/comments/post-2/speedy_review/",
                "link_flair_text": "Review",
                "num_comments": 0,
            }
        ])
        RedditScraper(
            self.registry,
            RunStore(self.run_dir),
            client=client,
            max_pages=1,
            max_posts=10,
        ).run()
        for filename in ("manifest.json", "candidates.json", "run-summary.json", "captures.jsonl"):
            self.assertTrue((self.run_dir / filename).exists(), filename)

        summary = json.loads((self.run_dir / "run-summary.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(summary["duration_seconds"], 0)

    def test_resumed_summary_keeps_segment_history_and_cumulative_counts(self):
        store = RunStore(self.run_dir)

        def segment(started_at, finished_at, new_candidates, posts, source_posts):
            return {
                "started_at": started_at,
                "finished_at": finished_at,
                "sources_requested": 1,
                "subreddits_checked": ["RepCulture_Bags"],
                "known_subreddits": ["RepCulture_Bags"],
                "discovered_subreddits": [],
                "successful_endpoint_count": 1,
                "fallback_endpoint_count": 0,
                "failed_endpoint_count": 0,
                "consecutive_failure_count": 0,
                "skipped_endpoint_count": 2,
                "new_capture_count": new_candidates,
                "new_candidate_count": new_candidates,
                "post_count": posts,
                "comment_count": 0,
                "query_counts": {"r/RepCulture_Bags:review": posts},
                "source_post_counts": {"r/RepCulture_Bags": source_posts},
                "errors": [],
                "capture_count": new_candidates,
                "candidate_count": new_candidates,
                "duration_seconds": 1.0,
            }

        store.save_summary(segment("2026-08-08T01:00:00+00:00", "2026-08-08T01:00:01+00:00", 2, 2, 2))
        store.save_summary(segment("2026-08-08T02:00:00+00:00", "2026-08-08T02:00:01+00:00", 1, 1, 1))

        summary = json.loads((self.run_dir / "run-summary.json").read_text(encoding="utf-8"))
        history = (self.run_dir / "run-history.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(history), 2)
        self.assertEqual(summary["run_count"], 2)
        self.assertEqual(summary["new_candidate_count"], 3)
        self.assertEqual(summary["post_count"], 3)
        self.assertEqual(summary["source_post_counts"]["r/RepCulture_Bags"], 3)
        self.assertEqual(summary["last_run"]["new_candidate_count"], 1)

    def test_source_specific_comment_setting_overrides_registry_default(self):
        registry = json.loads(json.dumps(self.registry))
        registry["include_comments_by_default"] = True
        registry["sources"][0]["include_comments"] = False
        registry["sources"][1]["include_comments"] = True
        client = FakeClient(posts=[
            {
                "id": "post-4",
                "title": "A review",
                "selftext": "The leather is soft.",
                "author": "reader",
                "subreddit": "RepCulture_Bags",
                "created_utc": 1783907242.0,
                "permalink": "/r/RepCulture_Bags/comments/post-4/a_review/",
                "link_flair_text": "Review",
                "num_comments": 1,
            }
        ])
        RedditScraper(
            registry,
            RunStore(self.run_dir),
            client=client,
            max_pages=1,
            max_posts=10,
            max_comments=5,
        ).run()
        comment_calls = [url for kind, url in client.calls if kind == "json" and "/comments/" in url]
        self.assertTrue(any("/r/RepTherapy/comments/" in url for url in comment_calls))
        self.assertFalse(any("/r/RepCulture_Bags/comments/" in url for url in comment_calls))

    def test_candidate_is_safe_and_classified_without_asserting_normalized_facts(self):
        candidate = candidate_from_post(
            {
                "id": "post-3",
                "title": "Speedy review after long-term wear",
                "selftext": "Factory: P9. Seller WhatsApp +86 123 456 7890. Leather is soft.",
                "author": "reader",
                "subreddit": "RepCulture_Bags",
                "created_utc": 1783907242.0,
                "permalink": "/r/RepCulture_Bags/comments/post-3/speedy_review/",
                "link_flair_text": "Review",
            },
            "RepCulture_Bags",
            "2026-08-08T00:00:00+00:00",
        )
        self.assertEqual(candidate["evidence_type"], "long_term_wear")
        self.assertIn("Speedy", candidate["bag_terms"])
        self.assertIn("P9", candidate["factory_terms"])
        self.assertNotIn("123 456 7890", candidate["redacted_excerpt"])
        self.assertEqual(candidate["status"], "needs_normalization")
        self.assertNotIn("family_ids", candidate)

    def test_comment_rows_extract_nested_public_comment_data(self):
        payload = [
            {
                "data": {
                    "children": [
                        {
                            "kind": "t1",
                            "data": {
                                "id": "comment-1",
                                "body": "top",
                                "replies": {
                                    "data": {
                                        "children": [
                                            {"kind": "t1", "data": {"id": "comment-2", "body": "reply"}}
                                        ]
                                    }
                                },
                            },
                        }
                    ]
                }
            }
        ]
        self.assertEqual([row["id"] for row in _comment_rows(payload)], ["comment-1", "comment-2"])


if __name__ == "__main__":
    unittest.main()
