import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from detect_new_collections import detect  # noqa: E402


def candidate(post_id, title, bag_terms, author="reader", subreddit="RealRepLadies"):
    return {
        "candidate_id": f"candidate-{subreddit}-{post_id}",
        "url": f"https://www.reddit.com/r/{subreddit}/comments/{post_id}/slug/",
        "subreddit": subreddit,
        "author": author,
        "title": title,
        "flair": "",
        "evidence_type": "other",
        "redacted_excerpt": "",
        "redaction_flags": {},
        "bag_terms": bag_terms,
    }


class DetectNewCollectionsTests(unittest.TestCase):
    def test_catalogued_terms_are_excluded(self):
        candidates = [candidate("1", "Neverfull review", ["Neverfull"])]
        report = detect(candidates, min_authors=2)
        terms = {e["term"] for e in report["entries"]}
        self.assertNotIn("Neverfull", terms)

    def test_uncatalogued_term_needs_two_distinct_authors_to_meet_floor(self):
        candidates = [
            candidate("1", "Prada haul", ["Prada"], author="alice"),
            candidate("2", "Prada review", ["Prada"], author="bob"),
        ]
        report = detect(candidates, min_authors=2)
        entry = next(e for e in report["entries"] if e["term"] == "Prada")
        self.assertTrue(entry["meets_floor"])
        self.assertEqual(entry["independent_author_count"], 2)

    def test_repeat_posts_by_the_same_author_do_not_meet_the_floor(self):
        candidates = [
            candidate("1", "Prada haul", ["Prada"], author="alice"),
            candidate("2", "Prada again", ["Prada"], author="alice"),
        ]
        report = detect(candidates, min_authors=2)
        entry = next(e for e in report["entries"] if e["term"] == "Prada")
        self.assertFalse(entry["meets_floor"])
        self.assertEqual(entry["independent_author_count"], 1)

    def test_candidates_with_a_catalogued_anchor_are_skipped_entirely(self):
        candidates = [candidate("1", "Neverfull review with Prada bag too", ["Neverfull", "Prada"])]
        report = detect(candidates, min_authors=1)
        self.assertEqual(report["entries"], [])

    def test_brand_only_match_does_not_hide_a_specific_uncatalogued_model(self):
        # "Chanel" alone weakly anchors to every Chanel family without confirming
        # the model, so a post naming a distinct, uncatalogued Chanel model must
        # still surface -- it is real new-collection signal, not noise. Uses a
        # synthetic model name rather than a real one so this test does not break
        # every time the live catalog grows to cover another Chanel model.
        candidates = [
            candidate("1", "Chanel Faketown Special review", ["Faketown Special", "Chanel"], author="alice"),
            candidate("2", "Another Chanel Faketown Special review", ["Faketown Special", "Chanel"], author="bob"),
        ]
        report = detect(candidates, min_authors=2)
        entry = next(e for e in report["entries"] if e["term"] == "Faketown Special")
        self.assertTrue(entry["meets_floor"])
        self.assertEqual(entry["independent_author_count"], 2)


if __name__ == "__main__":
    unittest.main()
