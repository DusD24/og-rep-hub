import json
import hashlib
import unittest
from datetime import date, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate import jpeg_dimensions, validate
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

    def test_all_launch_families_have_distinct_reddit_tiles_and_exact_evidence_links(self):
        families = load("bag_families")
        media_rows = load("media")
        media = {row["id"]: row for row in media_rows}
        evidence = {row["id"]: row for row in load("evidence")}
        tile_ids = [row["tile_media_id"] for row in families]
        target_ids = {row["id"] for row in media_rows if row["usage_scope"] == "target_tile"}

        self.assertEqual(len(families), 12)
        self.assertTrue(all(row["publication_status"] == "published" for row in families))
        self.assertTrue(all(row["evidence_coverage"]["image_ready"] is True for row in families))
        self.assertTrue(all("candidate_tile" not in row for row in families))
        self.assertEqual(len(set(tile_ids)), 12)
        self.assertEqual(set(tile_ids), target_ids)

        for family in families:
            tile = media[family["tile_media_id"]]
            receipt = evidence[tile["evidence_id"]]
            self.assertEqual(tile["usage_scope"], "target_tile")
            self.assertTrue(tile["post_url"].startswith("https://www.reddit.com/"))
            self.assertIn(tile["evidence_id"], family["evidence_ids"])
            self.assertEqual(receipt["media_ids"].count(tile["id"]), 1)
            self.assertEqual(tile["post_url"], receipt["url"])
            self.assertEqual(tile["author"], receipt["author"])
            self.assertEqual(tile["subreddit"], receipt["subreddit"])
            self.assertIn(family["id"], receipt["family_ids"])

    def test_media_files_have_unique_paths_hashes_dimensions_and_removal_checks(self):
        rows = load("media")
        self.assertEqual(len(rows), 13)
        self.assertEqual(len({row["id"] for row in rows}), len(rows))
        self.assertEqual(len({row["path"] for row in rows}), len(rows))
        self.assertEqual(sum(row["usage_scope"] == "target_tile" for row in rows), 12)

        required = {
            "evidence_id", "source_url", "post_url", "author", "subreddit",
            "capture_date", "removal_checked_at", "sha256", "width", "height", "alt",
        }
        for row in rows:
            self.assertTrue(required <= row.keys())
            path = ROOT / row["path"]
            self.assertTrue(path.is_file())
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"])
            self.assertEqual(jpeg_dimensions(path), (row["width"], row["height"]))
            self.assertGreaterEqual(len(row["alt"].strip()), 24)
            date.fromisoformat(row["removal_checked_at"])

    def test_evidence_count_and_published_state_have_no_stale_media_candidates(self):
        self.assertEqual(len(load("evidence")), 38)
        families = load("bag_families")
        stale_family_text = json.dumps(families).casefold()
        self.assertNotIn("candidate_not_archived", stale_family_text)
        self.assertNotIn("archive and hash the selected reddit image", stale_family_text)
        self.assertNotIn("launch candidate", stale_family_text)
        lane_notes = " ".join(row["status_note"] for row in load("research")["research_lanes"]).casefold()
        self.assertNotIn("local media archive and hash remain", lane_notes)
        self.assertNotIn("publication gate for the 11", lane_notes)

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
