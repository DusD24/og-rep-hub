import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from scrape_reddit import (  # noqa: E402
    canonical_subreddit_url,
    discover_subreddits,
    load_registry,
    sanitize_text,
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


if __name__ == "__main__":
    unittest.main()
