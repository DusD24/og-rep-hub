import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import draft_evidence  # noqa: E402
from draft_evidence import (
    decline_candidates,  # noqa: E402
    JUDGMENT_FIELDS,
    PLACEHOLDER,
    _incomplete,
    _subreddit_slug,
    apply_drafts,
    build_drafts,
    evidence_id_for,
    recompute_coverage,
)
from ledger import empty_ledger, is_settled  # noqa: E402


def digest_entry(post_id="abc123", subreddit="RepTherapy", families=("bag-family-ysl-loulou",)):
    return {
        "candidate_id": f"candidate-{subreddit}-{post_id}",
        "thing_id": f"t3_{post_id}",
        "url": f"https://www.reddit.com/r/{subreddit}/comments/{post_id}/slug/",
        "subreddit": subreddit,
        "author": "reader",
        "publication_date": "2026-08-09",
        "flair": "Review",
        "title": "Loulou review in hand",
        "excerpt": "The bag arrived with even grain.",
        "priority": 90,
        "score": 65,
        "gap_boost": 25,
        "gap_reason": "family is still in the research queue",
        "signals": ["names a catalogued collection"],
        "matched": {"family_ids": list(families), "bag_ids": [], "seller_ids": [], "factory_ids": []},
        "suggested_evidence_type": "in_hand_review",
        "suggested_source_type": "reddit_review",
    }


def completed(draft):
    draft = dict(draft)
    draft["source_type"] = "reddit_review"
    draft["evidence_type"] = "in_hand_review"
    draft["exact_product_match"] = False
    draft["paraphrase"] = "An owner reports the bag arrived with even grain and straight stitching."
    draft["positive_observations"] = ["Owner describes even grain and straight stitching in hand."]
    draft["negative_observations"] = ["No factory or price detail; a single author with no corroboration."]
    return draft


class IdGenerationTests(unittest.TestCase):
    def test_subreddit_slug_uses_capitalised_word_initials(self):
        self.assertEqual(_subreddit_slug("RepTherapy"), "rt")
        self.assertEqual(_subreddit_slug("RealRepLadies"), "rrl")
        self.assertEqual(_subreddit_slug("RepLadiesWorld"), "rlw")

    def test_ids_are_deterministic_and_avoid_collisions(self):
        entry = digest_entry()
        first = evidence_id_for(entry, set())
        self.assertEqual(first, evidence_id_for(entry, set()))
        self.assertIn("abc123", first)
        second = evidence_id_for(entry, {first})
        self.assertNotEqual(second, first)
        self.assertEqual(evidence_id_for(entry, {first, second}), f"{first}-3")

    def test_generated_ids_do_not_collide_with_the_committed_catalog(self):
        existing = {row["id"] for row in json.loads((ROOT / "data" / "evidence.json").read_text())}
        drafts = build_drafts({"entries": [digest_entry()]}, existing)
        self.assertNotIn(drafts[0]["id"], existing)


class DraftShapeTests(unittest.TestCase):
    def setUp(self):
        self.draft = build_drafts({"entries": [digest_entry()]}, set())[0]

    def test_mechanical_fields_are_prefilled(self):
        self.assertEqual(self.draft["subreddit"], "RepTherapy")
        self.assertEqual(self.draft["author"], "reader")
        self.assertEqual(self.draft["publication_date"], "2026-08-09")
        self.assertEqual(self.draft["media_ids"], [])
        self.assertEqual(self.draft["publication_date_precision"], "exact")
        self.assertTrue(self.draft["url"].startswith("https://www.reddit.com/"))

    def test_judgment_fields_are_left_for_a_reviewer(self):
        self.assertEqual(self.draft["exact_product_match"], PLACEHOLDER)
        self.assertEqual(self.draft["paraphrase"], PLACEHOLDER)
        self.assertEqual(self.draft["positive_observations"], [])
        self.assertEqual(self.draft["negative_observations"], [])

    def test_incomplete_drafts_are_reported_field_by_field(self):
        problems = " ".join(_incomplete(self.draft))
        for field in ("exact_product_match", "paraphrase", "positive_observations"):
            self.assertIn(field, problems)
        self.assertEqual(_incomplete(completed(self.draft)), [])

    def test_invalid_enum_values_are_caught(self):
        draft = completed(self.draft)
        draft["evidence_type"] = "w2c"
        self.assertTrue(any("evidence_type" in problem for problem in _incomplete(draft)))
        draft = completed(self.draft)
        draft["source_type"] = "tweet"
        self.assertTrue(any("source_type" in problem for problem in _incomplete(draft)))


class CoverageRecomputeTests(unittest.TestCase):
    def test_counts_match_linked_evidence(self):
        evidence = [
            {"id": "ev-a", "author": "Ann", "subreddit": "RepTherapy", "evidence_type": "in_hand_review"},
            {"id": "ev-b", "author": "ann", "subreddit": "RepTherapy", "evidence_type": "psp_qc"},
            {"id": "ev-c", "author": "Bo", "subreddit": "RealRepLadies", "evidence_type": "in_hand_review"},
        ]
        families = [{"id": "fam", "evidence_ids": ["ev-a", "ev-b", "ev-c"], "evidence_coverage": {}}]
        recompute_coverage(families, evidence)
        coverage = families[0]["evidence_coverage"]
        self.assertEqual(coverage["source_count"], 3)
        # Authors are deduplicated case-insensitively, matching validate.py.
        self.assertEqual(coverage["independent_author_count"], 2)
        self.assertEqual(coverage["primary_subreddit_coverage"], ["RealRepLadies", "RepTherapy"])
        self.assertEqual(coverage["evidence_types"], ["in_hand_review", "psp_qc"])


class ApplyTests(unittest.TestCase):
    """apply_drafts writes to data/, so every test here runs against a temp copy."""

    def setUp(self):
        self.tmp = Path(self.enterContext(__import__("tempfile").TemporaryDirectory()))
        self.evidence_path = self.tmp / "evidence.json"
        self.families_path = self.tmp / "bag_families.json"
        self.evidence = [{
            "id": "ev-existing", "url": "https://www.reddit.com/r/RepTherapy/comments/old1/t/",
            "subreddit": "RepTherapy", "author": "someone", "evidence_type": "in_hand_review",
        }]
        self.families = [{
            "id": "bag-family-ysl-loulou", "evidence_ids": ["ev-existing"],
            "evidence_coverage": {}, "tile_media_id": None, "last_updated": "2026-01-01",
        }]
        self.evidence_path.write_text(json.dumps(self.evidence), encoding="utf-8")
        self.families_path.write_text(json.dumps(self.families), encoding="utf-8")
        loaded = {"evidence": self.evidence, "bag_families": self.families}
        self.enterContext(mock.patch.object(draft_evidence, "EVIDENCE_PATH", self.evidence_path))
        self.enterContext(mock.patch.object(draft_evidence, "FAMILIES_PATH", self.families_path))
        self.enterContext(
            mock.patch.object(draft_evidence, "load", lambda name: json.loads(json.dumps(loaded[name])))
        )

    def _draft(self, **overrides):
        draft = completed(build_drafts({"entries": [digest_entry(**overrides)]}, set())[0])
        return draft

    def test_apply_writes_records_and_updates_coverage(self):
        ledger = empty_ledger()
        result = apply_drafts([self._draft()], ledger=ledger)
        self.assertEqual(result["applied"], 1)
        written = json.loads(self.evidence_path.read_text())
        self.assertEqual(len(written), 2)
        family = json.loads(self.families_path.read_text())[0]
        self.assertEqual(family["evidence_coverage"]["source_count"], 2)
        self.assertEqual(family["evidence_coverage"]["independent_author_count"], 2)
        self.assertNotEqual(family["last_updated"], "2026-01-01")
        # The promotion is recorded so the post never resurfaces as a candidate.
        self.assertEqual(ledger["seen"]["t3_abc123"]["disposition"], "promoted")

    def test_review_block_is_stripped_from_written_records(self):
        apply_drafts([self._draft()], ledger=empty_ledger())
        written = json.loads(self.evidence_path.read_text())
        self.assertTrue(all(not key.startswith("_") for row in written for key in row))

    def test_nothing_is_written_when_any_draft_is_incomplete(self):
        incomplete = build_drafts({"entries": [digest_entry(post_id="bad1")]}, set())[0]
        result = apply_drafts([self._draft(), incomplete], ledger=empty_ledger())
        self.assertEqual(result["applied"], 0)
        self.assertTrue(result["problems"])
        # The good draft in the same batch is not partially applied.
        self.assertEqual(len(json.loads(self.evidence_path.read_text())), 1)

    def test_duplicate_source_url_is_refused(self):
        draft = self._draft()
        draft["url"] = "https://old.reddit.com/r/RepTherapy/comments/old1/t/?utm_source=x"
        result = apply_drafts([draft], ledger=empty_ledger())
        self.assertEqual(result["applied"], 0)
        self.assertTrue(any("already cited" in problem for problem in result["problems"]))

    def test_unknown_family_is_refused(self):
        result = apply_drafts([self._draft(families=("bag-family-nope",))], ledger=empty_ledger())
        self.assertEqual(result["applied"], 0)
        self.assertTrue(any("unknown family_id" in problem for problem in result["problems"]))

    def test_judgment_fields_are_the_only_ones_a_reviewer_must_write(self):
        draft = build_drafts({"entries": [digest_entry()]}, set())[0]
        missing = {problem.split()[0] for problem in _incomplete(draft)}
        self.assertTrue(missing <= set(JUDGMENT_FIELDS))


if __name__ == "__main__":
    unittest.main()


class DeclineTests(unittest.TestCase):
    def test_declining_settles_a_post_so_it_leaves_the_queue(self):
        ledger = empty_ledger()
        result = decline_candidates(
            [{
                "url": "https://www.reddit.com/r/RepTherapy/comments/abc123/slug/",
                "subreddit": "RepTherapy",
                "reason": "asks for a seller recommendation; reports nothing about a bag",
            }],
            ledger=ledger,
        )
        self.assertEqual(result["declined"], 1)
        self.assertEqual(result["problems"], [])
        self.assertEqual(ledger["seen"]["t3_abc123"]["disposition"], "rejected")
        self.assertIn("reviewed and not promoted", ledger["seen"]["t3_abc123"]["reason"])
        # Settled means it never returns to a later shortlist.
        self.assertTrue(is_settled(ledger, "t3_abc123"))

    def test_a_decline_without_a_reason_is_refused_and_writes_nothing(self):
        ledger = empty_ledger()
        result = decline_candidates(
            [{"url": "https://www.reddit.com/r/RepTherapy/comments/abc123/slug/"}], ledger=ledger
        )
        self.assertEqual(result["declined"], 0)
        self.assertTrue(result["problems"])
        self.assertEqual(ledger["seen"], {})

    def test_one_bad_row_blocks_the_whole_batch(self):
        ledger = empty_ledger()
        result = decline_candidates(
            [
                {"url": "https://www.reddit.com/r/RepTherapy/comments/good01/s/", "reason": "not a bag"},
                {"reason": "no identifier at all"},
            ],
            ledger=ledger,
        )
        self.assertEqual(result["declined"], 0)
        self.assertEqual(ledger["seen"], {}, "a partial batch must not be written")
