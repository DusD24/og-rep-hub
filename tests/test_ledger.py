import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ledger import (  # noqa: E402
    backfill_from_evidence,
    empty_ledger,
    is_settled,
    load_ledger,
    record,
    save_ledger,
    set_watermark,
    watermark,
)
from model import comparison_url, normalize_evidence_url, reddit_thing_id  # noqa: E402


class UrlCanonicalizationTests(unittest.TestCase):
    def test_matches_worker_normalization_rules(self):
        self.assertEqual(
            normalize_evidence_url("https://old.reddit.com/r/RepTherapy/comments/abc123/title/?utm_source=x&share_id=9"),
            "https://www.reddit.com/r/RepTherapy/comments/abc123/title/",
        )
        self.assertEqual(
            normalize_evidence_url("https://www.imgur.com/a/xyz"),
            "https://imgur.com/a/xyz",
        )
        # Query parameters that survive are sorted so equal URLs stringify identically.
        self.assertEqual(
            normalize_evidence_url("https://www.reddit.com/r/X/comments/a/b/?b=2&a=1"),
            "https://www.reddit.com/r/X/comments/a/b/?a=1&b=2",
        )

    def test_rejects_unusable_urls(self):
        for value in (
            "http://www.reddit.com/r/X/comments/a/b/",  # not https
            "https://evil.example.com/r/X/comments/a/b/",  # host not allowlisted
            "https://user:pw@www.reddit.com/r/X/comments/a/b/",  # credentials
            "",
            None,
            12,
        ):
            self.assertIsNone(normalize_evidence_url(value), value)

    def test_comparison_url_drops_query_and_trailing_slash(self):
        self.assertEqual(
            comparison_url("https://www.reddit.com/r/X/comments/a/b/?c=1"),
            comparison_url("https://old.reddit.com/r/X/comments/a/b"),
        )

    def test_thing_id_distinguishes_posts_from_comments(self):
        self.assertEqual(
            reddit_thing_id("https://www.reddit.com/r/RepTherapy/comments/abc123/some_title/"),
            "t3_abc123",
        )
        self.assertEqual(
            reddit_thing_id("https://www.reddit.com/r/RealRepLadies/comments/1trwyrk/comment/ootqmuf/"),
            "t1_ootqmuf",
        )
        self.assertEqual(
            reddit_thing_id("https://www.reddit.com/r/X/comments/abc123/slug/def456/"),
            "t1_def456",
        )
        self.assertIsNone(reddit_thing_id("https://www.reddit.com/r/X/"))


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tempdir.name) / "scrape_ledger.json"

    def tearDown(self):
        self.tempdir.cleanup()

    def test_missing_file_loads_as_empty_and_round_trips(self):
        ledger = load_ledger(self.path)
        self.assertEqual(ledger["seen"], {})
        record(ledger, "t3_abc", "rejected", reason="off topic")
        save_ledger(ledger, self.path)
        self.assertEqual(load_ledger(self.path)["seen"]["t3_abc"]["disposition"], "rejected")

    def test_settled_entries_suppress_but_pending_and_deferred_do_not(self):
        ledger = empty_ledger()
        record(ledger, "t3_promoted", "promoted", evidence_ids=["ev-a"])
        record(ledger, "t3_rejected", "rejected")
        record(ledger, "t3_deferred", "deferred")
        record(ledger, "t3_pending", "pending")
        self.assertTrue(is_settled(ledger, "t3_promoted"))
        self.assertTrue(is_settled(ledger, "t3_rejected"))
        self.assertFalse(is_settled(ledger, "t3_deferred"))
        self.assertFalse(is_settled(ledger, "t3_pending"))
        self.assertFalse(is_settled(ledger, "t3_unknown"))
        self.assertFalse(is_settled(ledger, None))

    def test_settled_entries_are_not_silently_downgraded(self):
        ledger = empty_ledger()
        record(ledger, "t3_abc", "rejected", decided_on="2026-01-01")
        self.assertFalse(record(ledger, "t3_abc", "pending"))
        self.assertEqual(ledger["seen"]["t3_abc"]["disposition"], "rejected")
        # Promotion is the one allowed upgrade over a prior rejection.
        self.assertTrue(record(ledger, "t3_abc", "promoted", evidence_ids=["ev-a"]))
        self.assertEqual(ledger["seen"]["t3_abc"]["disposition"], "promoted")

    def test_unknown_disposition_is_rejected(self):
        with self.assertRaises(ValueError):
            record(empty_ledger(), "t3_abc", "maybe")

    def test_watermarks_only_advance(self):
        ledger = empty_ledger()
        self.assertEqual(watermark(ledger, "RepTherapy"), 0.0)
        set_watermark(ledger, "RepTherapy", 1000.0)
        set_watermark(ledger, "RepTherapy", 500.0)
        self.assertEqual(watermark(ledger, "RepTherapy"), 1000.0)
        set_watermark(ledger, "RepTherapy", 2000.0, full_sweep=True)
        self.assertEqual(watermark(ledger, "RepTherapy"), 2000.0)
        self.assertIn("last_full_sweep", ledger["watermarks"]["RepTherapy"])

    def test_backfill_is_idempotent_and_groups_multi_record_posts(self):
        evidence = [
            {"id": "ev-one", "url": "https://www.reddit.com/r/RepTherapy/comments/abc/t/", "subreddit": "RepTherapy"},
            {"id": "ev-two", "url": "https://www.reddit.com/r/RepTherapy/comments/abc/t/", "subreddit": "RepTherapy"},
            {"id": "ev-three", "url": "https://www.reddit.com/r/X/comments/def/t/", "subreddit": "X"},
        ]
        ledger = empty_ledger()
        self.assertEqual(backfill_from_evidence(ledger, evidence), 2)
        # A single post backing two records keeps both ids rather than overwriting.
        self.assertEqual(ledger["seen"]["t3_abc"]["evidence_ids"], ["ev-one", "ev-two"])
        self.assertEqual(backfill_from_evidence(ledger, evidence), 0)

    def test_committed_ledger_covers_every_evidence_source(self):
        committed = load_ledger()
        evidence = json.loads((ROOT / "data" / "evidence.json").read_text(encoding="utf-8"))
        for row in evidence:
            thing_id = reddit_thing_id(row["url"])
            self.assertIsNotNone(thing_id, row["id"])
            self.assertTrue(is_settled(committed, thing_id), row["id"])
            self.assertIn(row["id"], committed["seen"][thing_id]["evidence_ids"])

    def test_ledger_stores_no_post_text(self):
        # The ledger is committed, so it must carry identifiers and decisions only.
        committed = load_ledger()
        allowed = {"disposition", "decided_on", "evidence_ids", "subreddit", "reason"}
        for thing_id, entry in committed["seen"].items():
            self.assertTrue(set(entry) <= allowed, f"{thing_id}: {set(entry) - allowed}")


if __name__ == "__main__":
    unittest.main()
