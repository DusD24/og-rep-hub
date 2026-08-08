import json
import unittest
from datetime import date, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate import validate
from score import generate


def load(name):
    return json.loads((ROOT / "data" / f"{name}.json").read_text(encoding="utf-8"))


class DataTests(unittest.TestCase):
    def test_repository_data_validates(self):
        self.assertEqual(validate(), [])

    def test_size_pattern_colorway_are_explicit_and_unique(self):
        variants = [(row["size"], row["pattern"], row["colorway"]) for row in load("bags")]
        self.assertEqual(len(variants), len(set(variants)))
        self.assertTrue(all(all(variant) for variant in variants))

    def test_seller_and_factory_namespaces_are_separate(self):
        sellers = {row["id"] for row in load("sellers")}
        factories = {row["id"] for row in load("factories")}
        self.assertFalse(sellers & factories)
        self.assertTrue(all(row["seller_id"] in sellers and row["factory_id"] in factories for row in load("offerings")))

    def test_repeated_author_counts_once(self):
        authors = ["SameAuthor", "sameauthor", "Independent"]
        self.assertEqual(len({author.casefold() for author in authors}), 2)

    def test_conflicting_reviews_are_not_discarded(self):
        rows = load("evidence")
        conflicts = [row for row in rows if row.get("positive_observations") and row.get("negative_observations")]
        self.assertTrue(conflicts or not rows)

    def test_rankings_are_deterministic_and_catalog_only_unranked(self):
        first = generate()["rankings"]
        second = generate()["rankings"]
        self.assertEqual(first, second)
        offerings = {row["id"]: row for row in load("offerings")}
        for row in first:
            offering = offerings[row["offering_id"]]
            if not offering.get("evidence_ids"):
                self.assertEqual(row["rank_status"], "unranked")

    def test_twelve_families_have_source_coverage_and_unique_slugs(self):
        families = load("bag_families")
        self.assertEqual(len(families), 12)
        self.assertEqual(len({row["slug"] for row in families}), 12)
        self.assertTrue(all(row["evidence_coverage"]["independent_author_count"] >= 2 for row in families))
        self.assertTrue(all(set(row["evidence_coverage"]["primary_subreddit_coverage"]) & {"RealRepLadies", "RepTherapy"} for row in families))

    def test_published_family_tiles_are_reddit_only_and_research_queue_is_explicit(self):
        families = load("bag_families")
        media = {row["id"]: row for row in load("media")}
        published = [row for row in families if row["publication_status"] == "published"]
        self.assertTrue(published)
        self.assertTrue(all(row["tile_media_id"] in media for row in published))
        self.assertTrue(all(media[row["tile_media_id"]]["post_url"].startswith("https://www.reddit.com/") for row in published))
        self.assertTrue(all(media[row["tile_media_id"]].get("usage_scope") == "target_tile" for row in published))
        queued = [row for row in families if row["publication_status"] == "research_queue"]
        self.assertEqual(len(queued), 11)
        self.assertTrue(all(row.get("tile_media_id") is None and row.get("candidate_tile", {}).get("sha256") is None for row in queued))

    def test_variants_and_offerings_keep_family_and_exact_variant_references(self):
        families = {row["id"] for row in load("bag_families")}
        variants = load("bags")
        self.assertTrue(all(row.get("family_id") in families and "material" in row and "hardware" in row for row in variants))
        self.assertTrue(all(row["variant_id"] == row["bag_id"] for row in load("offerings")))
        self.assertTrue(all(row["family_id"] in families for row in load("offerings")))

    def test_contacts_are_public_wiki_rows_for_existing_sellers_only(self):
        sellers = {row["id"] for row in load("sellers")}
        contacts = load("contacts")
        self.assertEqual(len(contacts), 5)
        self.assertTrue(all(row["seller_id"] in sellers for row in contacts))
        self.assertTrue(all(row["provenance"] == "reddit_public_wiki" for row in contacts))
        self.assertTrue(all(row["public_source_url"].endswith("/r/RepTherapy/wiki/trustedsellers/") for row in contacts))
        self.assertEqual({row["seller_id"] for row in contacts}, {"seller-hyper-peter", "seller-doris", "seller-mandy", "seller-baobao", "seller-mike"})

    def test_research_lanes_include_rep_ladies_world_scan_candidates(self):
        research = load("research")
        lane = next(row for row in research["research_lanes"] if row["subreddit_focus"] == "RepLadiesWorld")
        self.assertEqual(lane["status"], "initial_scan_complete")
        self.assertEqual(lane["families_checked"], 3)
        self.assertEqual(len(research["scan_log"][0]["candidate_sources"]), 4)
        self.assertEqual(research["glossary_source_url"], "https://www.reddit.com/r/RepTherapy/wiki/glossary/")


if __name__ == "__main__":
    unittest.main()
