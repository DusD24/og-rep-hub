import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ledger import empty_ledger, is_settled, record  # noqa: E402
from triage import (  # noqa: E402
    LANE_TO_EVIDENCE_TYPE,
    build_context,
    build_gap_index,
    build_vocabulary,
    load_candidates,
    score_candidate,
    triage,
)


def candidate(
    post_id,
    title="Neverfull review in hand",
    excerpt="The Monogram canvas looks even and the leather has aged well over four months of daily use. Stitching is straight and the hardware still looks right after regular wear, so I am comfortable recommending it.",
    lane="in_hand_review",
    subreddit="RepTherapy",
    author="reader",
    flair="Review",
    flags=None,
):
    return {
        "candidate_id": f"candidate-{subreddit}-{post_id}",
        "source_id": f"post:{subreddit}:{post_id}",
        "url": f"https://www.reddit.com/r/{subreddit}/comments/{post_id}/slug/",
        "subreddit": subreddit,
        "author": author,
        "publication_date": "2026-08-09",
        "title": title,
        "flair": flair,
        "evidence_type": lane,
        "redacted_excerpt": excerpt,
        "redaction_flags": flags or {},
        "status": "needs_normalization",
    }


class VocabularyTests(unittest.TestCase):
    def setUp(self):
        self.vocabulary = build_vocabulary()

    def test_vocabulary_is_derived_from_the_live_catalog(self):
        family_terms = {item["term"] for item in self.vocabulary["families"]}
        catalog_models = {row["model"] for row in json.loads((ROOT / "data" / "bag_families.json").read_text())}
        self.assertTrue(catalog_models <= family_terms | {m for m in catalog_models if len(m) < 3})

    def test_generic_person_names_are_weak_signals(self):
        by_term = {item["term"]: item for item in self.vocabulary["sellers"]}
        # Ordinary English words in the seller roster must not score like a
        # distinctive multi-word match.
        for weak in ("Emily", "Baker", "Booker"):
            if weak in by_term:
                self.assertFalse(by_term[weak]["strong"], weak)
        for strong in ("Hyper Peter (HP)",):
            if strong in by_term:
                self.assertTrue(by_term[strong]["strong"], strong)

    def test_short_terms_are_dropped_entirely(self):
        for group in self.vocabulary.values():
            for item in group:
                self.assertGreaterEqual(len(item["term"]), 3, item["term"])

    def test_catalog_aliases_are_matched(self):
        terms = {item["term"] for item in self.vocabulary["families"]}
        # Aliases are already curated in bag_families.json; ignoring them threw
        # away real recall.
        self.assertIn("Speedy Bandouliere", terms)
        self.assertIn("YSL LouLou", terms)

    def test_size_named_models_match_other_sizes_of_the_same_collection(self):
        # "Birkin 25" is the catalogued model, but a post about a Birkin 30 is
        # still about that collection.
        by_term = {item["term"]: item for item in self.vocabulary["families"]}
        self.assertIn("Birkin", by_term)
        self.assertTrue(by_term["Birkin"]["pattern"].search("just got my Birkin 30"))
        self.assertEqual(by_term["Birkin"]["id"], "bag-family-hermes-birkin-25")

    def test_a_model_named_brand_plus_number_does_not_add_a_strong_brand_term(self):
        # "Chanel 25" strips to "Chanel" -- the brand itself, not a distinctive
        # model head like "Birkin". A strong "Chanel" term would make every post
        # naming the brand register as a strong match for this one specific
        # family, which is exactly what brand-alone matching is meant to avoid.
        for item in self.vocabulary["families"]:
            if item["term"].casefold() == "chanel":
                self.assertFalse(item["strong"], item)

    def test_terms_match_on_word_boundaries_only(self):
        pattern = next(item["pattern"] for item in self.vocabulary["families"] if item["term"] == "Speedy")
        self.assertTrue(pattern.search("bought a Speedy today"))
        self.assertFalse(pattern.search("SpeedyGonzales fan club"))


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.vocabulary = build_vocabulary()
        self.gaps = build_gap_index()
        self.bag_to_family = {
            row["id"]: row.get("family_id")
            for row in json.loads((ROOT / "data" / "bags.json").read_text())
        }

    def score(self, row, known_authors=frozenset()):
        return score_candidate(row, self.vocabulary, self.gaps, set(known_authors), self.bag_to_family)

    def test_scoring_is_deterministic(self):
        row = candidate("a1")
        self.assertEqual(self.score(row), self.score(row))

    def test_post_without_a_catalogued_collection_has_no_anchor(self):
        scored = self.score(candidate("a2", title="What did everyone order this week?", excerpt="Just curious what people bought."))
        self.assertFalse(scored["has_collection_anchor"])

    def test_collection_match_and_lane_drive_the_score(self):
        good = self.score(candidate("a3"))
        self.assertTrue(good["has_collection_anchor"])
        self.assertIn("bag-family-louis-vuitton-neverfull", good["family_ids"])
        self.assertEqual(good["suggested_evidence_type"], "in_hand_review")
        self.assertEqual(good["suggested_source_type"], "reddit_review")
        # A triage-only lane has no landing spot in evidence.json.
        unmappable = self.score(candidate("a4", lane="w2c"))
        self.assertIsNone(unmappable["suggested_evidence_type"])
        self.assertLess(unmappable["score"], good["score"])

    def test_privacy_flags_push_a_candidate_down(self):
        clean = self.score(candidate("a5"))
        flagged = self.score(candidate("a5", flags={"private_message_present": True}))
        self.assertLess(flagged["score"], clean["score"])

    def test_known_author_and_body_length_are_rewarded(self):
        base = self.score(candidate("a6"))
        known = self.score(candidate("a6"), known_authors={"reader"})
        self.assertGreater(known["score"], base["score"])
        thin = self.score(candidate("a7", excerpt="Neverfull. Nice."))
        self.assertLess(thin["score"], base["score"])

    def test_bag_variant_match_implies_its_family(self):
        scored = self.score(candidate("a8", title="Neverfull-style Monogram GM arrived"))
        self.assertIn("bag-family-louis-vuitton-neverfull", scored["family_ids"])

    def test_gap_boost_favours_under_covered_collections(self):
        # Both posts are equally good; only the coverage gap differs.
        busy = self.score(candidate("b1", title="Neverfull review in hand"))
        thin = self.score(candidate("b2", title="Balmain Anthem review in hand"))
        self.assertGreater(thin["gap_boost"], busy["gap_boost"])
        self.assertGreater(thin["priority"], busy["priority"])
        self.assertTrue(thin["gap_reason"])


class TriageRunTests(unittest.TestCase):
    def test_cap_holds_and_ordering_is_stable(self):
        rows = [candidate(f"p{index:03d}") for index in range(200)]
        ledger = empty_ledger()
        first = triage(rows, ledger, limit=25, floor=30, excerpt_chars=400, per_family_cap=0)
        self.assertEqual(len(first["entries"]), 25)
        self.assertEqual(first["counts"]["candidates_in"], 200)
        second = triage(rows, empty_ledger(), limit=25, floor=30, excerpt_chars=400, per_family_cap=0)
        self.assertEqual(
            json.dumps(first["entries"], sort_keys=True),
            json.dumps(second["entries"], sort_keys=True),
        )

    def test_entries_are_ordered_by_priority(self):
        rows = [
            candidate("busy1", title="Neverfull review in hand"),
            candidate("thin1", title="Balmain Anthem review in hand"),
        ]
        digest = triage(rows, empty_ledger(), limit=25, floor=30, excerpt_chars=400)
        priorities = [entry["priority"] for entry in digest["entries"]]
        self.assertEqual(priorities, sorted(priorities, reverse=True))
        self.assertEqual(digest["entries"][0]["candidate_id"], "candidate-RepTherapy-thin1")

    def test_below_floor_candidates_are_rejected_in_the_ledger(self):
        # Anchored (names Neverfull) but thin: rejection here is a judgment about the
        # post, which is the only case that is allowed to be terminal.
        noise = candidate("noise1", title="Neverfull", excerpt="Got one.", lane="discussion", flair="")
        ledger = empty_ledger()
        digest = triage([noise], ledger, limit=25, floor=30, excerpt_chars=400)
        self.assertEqual(digest["counts"]["auto_rejected"], 1)
        self.assertEqual(digest["entries"], [])
        self.assertTrue(is_settled(ledger, "t3_noise1"))
        self.assertEqual(ledger["seen"]["t3_noise1"]["disposition"], "rejected")
        self.assertIn("below floor", ledger["seen"]["t3_noise1"]["reason"])

    def test_uncatalogued_collection_is_deferred_not_rejected(self):
        # A bag the catalog has never seen. Rejecting this terminally would discard the
        # only signal for what to catalogue next.
        unknown = candidate(
            "newbag1",
            title="Prada Galleria review in hand",
            excerpt="Saffiano leather is crisp and the hardware has held up over three months of daily use. "
            "Stitching is even throughout and the lining shows no wear worth reporting.",
        )
        ledger = empty_ledger()
        digest = triage([unknown], ledger, limit=25, floor=30, excerpt_chars=400)
        self.assertEqual(digest["counts"]["auto_rejected"], 0)
        self.assertEqual(digest["counts"]["awaiting_catalog"], 1)
        self.assertEqual(ledger["seen"]["t3_newbag1"]["disposition"], "deferred")
        self.assertIn("catalog", ledger["seen"]["t3_newbag1"]["reason"])
        # Eligible again once the collection exists.
        self.assertFalse(is_settled(ledger, "t3_newbag1"))

    def test_unanchored_defers_even_when_it_also_scores_below_the_floor(self):
        # Naming a catalogued collection is worth 30 of 100 points, so an unanchored
        # post is penalised for the very thing under test. Its low score must not be
        # read as an independent quality judgment and made terminal.
        thin_unknown = candidate("newbag2", title="Prada Galleria", excerpt="Got one.", lane="discussion", flair="")
        ledger = empty_ledger()
        digest = triage([thin_unknown], ledger, limit=25, floor=30, excerpt_chars=400)
        self.assertEqual(digest["counts"]["auto_rejected"], 0)
        self.assertEqual(digest["counts"]["awaiting_catalog"], 1)
        self.assertFalse(is_settled(ledger, "t3_newbag2"))

    def test_overflow_is_deferred_not_rejected(self):
        rows = [candidate(f"q{index:03d}") for index in range(30)]
        ledger = empty_ledger()
        digest = triage(rows, ledger, limit=5, floor=30, excerpt_chars=400, per_family_cap=0)
        self.assertEqual(digest["counts"]["shortlisted"], 5)
        self.assertEqual(digest["counts"]["deferred"], 25)
        deferred = [key for key, row in ledger["seen"].items() if row["disposition"] == "deferred"]
        self.assertEqual(len(deferred), 25)
        # Deferred work stays eligible for a later sweep.
        self.assertFalse(any(is_settled(ledger, key) for key in deferred))

    def test_one_collection_cannot_monopolise_the_shortlist(self):
        # The gap boost is a per-family constant, so without a cap the neediest
        # collection takes every slot -- and closing its gap needs two authors,
        # not a whole day of review.
        rows = [candidate(f"an{index:03d}", title="Balmain Anthem review in hand") for index in range(20)]
        rows += [candidate(f"ll{index:03d}", title="YSL Loulou review in hand") for index in range(20)]
        digest = triage(rows, empty_ledger(), limit=10, floor=30, excerpt_chars=400, per_family_cap=3)
        counts = {}
        for entry in digest["entries"]:
            for family_id in entry["matched"]["family_ids"]:
                counts[family_id] = counts.get(family_id, 0) + 1
        self.assertTrue(counts)
        self.assertLessEqual(max(counts.values()), 3)
        self.assertGreaterEqual(len(counts), 2)

    def test_per_family_cap_can_be_disabled(self):
        rows = [candidate(f"an{index:03d}", title="Balmain Anthem review in hand") for index in range(10)]
        digest = triage(rows, empty_ledger(), limit=10, floor=30, excerpt_chars=400, per_family_cap=0)
        self.assertEqual(len(digest["entries"]), 10)

    def test_settled_candidates_never_reach_the_digest(self):
        rows = [candidate("s1"), candidate("s2")]
        ledger = empty_ledger()
        record(ledger, "t3_s1", "promoted", evidence_ids=["ev-existing"])
        digest = triage(rows, ledger, limit=25, floor=30, excerpt_chars=400)
        self.assertEqual(digest["counts"]["already_settled"], 1)
        self.assertEqual([entry["candidate_id"] for entry in digest["entries"]], ["candidate-RepTherapy-s2"])

    def test_digest_entries_stay_compact(self):
        digest = triage([candidate("c1")], empty_ledger(), limit=25, floor=30, excerpt_chars=400)
        entry = digest["entries"][0]
        self.assertLessEqual(len(entry["excerpt"]), 400)
        # A shortlist entry has to stay small enough that a full day's digest is
        # a few thousand tokens, not a few hundred thousand.
        self.assertLess(len(json.dumps(entry)), 2200)

    def test_lane_mapping_covers_every_scraper_lane(self):
        from scrape_reddit import EVIDENCE_LANES

        self.assertEqual(set(EVIDENCE_LANES), set(LANE_TO_EVIDENCE_TYPE))
        valid = set(build_context()["evidence_types"])
        for lane, mapped in LANE_TO_EVIDENCE_TYPE.items():
            if mapped is not None:
                self.assertIn(mapped, valid, lane)


class CandidateLoadingTests(unittest.TestCase):
    def test_reads_jsonl_and_falls_back_to_legacy_json(self):
        with tempfile.TemporaryDirectory() as name:
            run_dir = Path(name)
            (run_dir / "candidates.jsonl").write_text(
                json.dumps(candidate("j1")) + "\n" + "not json\n", encoding="utf-8"
            )
            self.assertEqual(len(load_candidates(run_dir)), 1)
        with tempfile.TemporaryDirectory() as name:
            run_dir = Path(name)
            (run_dir / "candidates.json").write_text(json.dumps([candidate("j2")]), encoding="utf-8")
            self.assertEqual(len(load_candidates(run_dir)), 1)


class ContextTests(unittest.TestCase):
    def test_context_lists_ids_and_enums_without_bulk_prose(self):
        context = build_context()
        self.assertEqual(
            set(context["source_types"]),
            {"reddit_review", "reddit_qc", "reddit_discussion", "catalog", "official_reference"},
        )
        self.assertTrue(all({"id", "name"} <= set(row) for row in context["sellers"]))
        # The whole point is that this replaces reading data/, so it must stay small.
        self.assertLess(len(json.dumps(context)), 20000)


if __name__ == "__main__":
    unittest.main()
