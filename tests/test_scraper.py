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
    load_registry,
    old_reddit_url,
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
