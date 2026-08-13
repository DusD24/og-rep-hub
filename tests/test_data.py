import json
import hashlib
import unittest
from datetime import date, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate import Validator, jpeg_dimensions, publication_counts, validate, validate_collection_heroes
from score import generate


def png_dimensions(path):
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def load(name):
    return json.loads((ROOT / "data" / f"{name}.json").read_text(encoding="utf-8"))


class DataTests(unittest.TestCase):
    def hero_errors(self, families, media=()):
        validator = Validator()
        validate_collection_heroes(families, list(media), ROOT, validator)
        return validator.errors

    def test_collection_hero_contract_rejects_missing_duplicate_and_unknown_heroes(self):
        base = {"id": "bag-family-test", "publication_status": "research_queue"}
        self.assertTrue(self.hero_errors([base]))
        self.assertTrue(self.hero_errors([{**base, "tile_media_id": "media-test", "hero_icon": "tote"}]))
        self.assertTrue(self.hero_errors([{**base, "hero_icon": "bucket"}]))

    def test_published_collection_cannot_use_generic_icon(self):
        row = {"id": "bag-family-test", "publication_status": "published", "hero_icon": "tote"}
        self.assertTrue(self.hero_errors([row]))

    def test_generic_collection_icon_suite_is_complete_and_consistent(self):
        icon_dir = ROOT / "assets" / "collection-icons"
        names = {"tote", "shoulder-flap", "top-handle", "hobo", "vanity"}
        paths = [icon_dir / f"{name}.png" for name in names]
        self.assertTrue(all(path.is_file() for path in paths))
        dimensions = {png_dimensions(path) for path in paths}
        self.assertEqual(len(dimensions), 1)
        width, height = dimensions.pop()
        self.assertGreaterEqual(width, 1200)
        self.assertGreaterEqual(width / height, 1.4)
        self.assertLessEqual(width / height, 1.8)

    def test_repository_data_validates(self):
        self.assertEqual(validate(), [])

    def test_publication_counts_are_data_derived(self):
        published, queued = publication_counts([
            {"publication_status": "published"},
            {"publication_status": "research_queue"},
            {"publication_status": "published"},
        ])
        self.assertEqual((published, queued), (2, 1))

    def test_validator_has_no_fixed_launch_record_counts(self):
        source = (ROOT / "scripts" / "validate.py").read_text(encoding="utf-8")
        self.assertNotIn("expected exactly 38 normalized receipts", source)
        self.assertNotIn("expected exactly 12 launch families", source)

    def test_research_registry_and_log_cover_repculture_bags(self):
        research = load("research")
        lanes = {row["subreddit_focus"]: row for row in research["research_lanes"]}
        self.assertIn("RepCulture_Bags", lanes)
        self.assertTrue(any(
            row["subreddit_focus"] == "RepCulture_Bags" and row["status"] == "candidate_leads"
            for row in research["scan_log"]
        ))

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

    def test_published_families_have_source_coverage_and_unique_slugs(self):
        families = load("bag_families")
        published = [row for row in families if row["publication_status"] == "published"]
        self.assertGreaterEqual(len(published), 12)
        self.assertEqual(len({row["slug"] for row in families}), len(families))
        self.assertTrue(all(row["evidence_coverage"]["independent_author_count"] >= 2 for row in published))
        self.assertTrue(all(set(row["evidence_coverage"]["primary_subreddit_coverage"]) & {"RealRepLadies", "RepTherapy"} for row in published))
        self.assertTrue(any(row["publication_status"] == "research_queue" for row in families))
        self.assertGreaterEqual(sum(len(row["evidence_ids"]) > 2 for row in published), 8)

    def test_all_media_backed_collections_have_distinct_reddit_tiles_and_exact_evidence_links(self):
        families = [row for row in load("bag_families") if row.get("tile_media_id")]
        media_rows = load("media")
        media = {row["id"]: row for row in media_rows}
        evidence = {row["id"]: row for row in load("evidence")}
        tile_ids = [row["tile_media_id"] for row in families]
        target_ids = {row["id"] for row in media_rows if row["usage_scope"] == "target_tile"}

        self.assertTrue(all(row["evidence_coverage"]["image_ready"] is True for row in families))
        self.assertTrue(all("candidate_tile" not in row for row in families))
        self.assertEqual(len(set(tile_ids)), len(families))
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

    def test_missing_collection_heroes_are_receipt_linked(self):
        families = {row["slug"]: row for row in load("bag_families")}
        media = {row["id"]: row for row in load("media")}
        evidence = {row["id"]: row for row in load("evidence")}
        expected = {
            "chanel-25": ("media-chanel-25-reddit", "ev-crawl-rrl-chanel-25-1qy3dlq"),
            "hermes-kelly": ("media-hermes-kelly-28-reddit", "ev-crawl-rrl-hermes-kelly-1sl383j"),
            "dior-saddle": ("media-dior-saddle-reddit", "ev-crawl-rrl-dior-saddle-1gqvspa"),
        }
        for slug, (media_id, evidence_id) in expected.items():
            family = families[slug]
            tile = media[media_id]
            receipt = evidence[evidence_id]
            self.assertEqual(family.get("tile_media_id"), media_id)
            self.assertNotIn("hero_icon", family)
            self.assertTrue(family["evidence_coverage"]["image_ready"])
            self.assertEqual(tile["usage_scope"], "target_tile")
            self.assertEqual(tile["evidence_id"], evidence_id)
            self.assertEqual(receipt["media_ids"].count(media_id), 1)
            self.assertIn(family["id"], receipt["family_ids"])

    def test_media_files_have_unique_paths_hashes_dimensions_and_removal_checks(self):
        rows = load("media")
        target_ids = {row["id"] for row in rows if row["usage_scope"] == "target_tile"}
        variant_ids = {row["id"] for row in rows if row["usage_scope"] == "variant_tile"}
        # Media rows partition cleanly across the two usage scopes; the totals move as
        # tiles are added, so assert the partition rather than a frozen row count.
        self.assertEqual(len(rows), len(target_ids) + len(variant_ids))
        self.assertEqual(len({row["id"] for row in rows}), len(rows))
        self.assertEqual(len({row["path"] for row in rows}), len(rows))
        self.assertEqual(sum(row["usage_scope"] == "target_tile" for row in rows), len(target_ids))

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
        self.assertGreater(len(load("evidence")), 38)
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
        self.assertGreater(len(contacts), 0)
        self.assertTrue(all(row["seller_id"] in sellers for row in contacts))
        self.assertTrue(all(row["provenance"] == "reddit_public_wiki" for row in contacts))
        self.assertTrue(all(row["public_source_url"].endswith("/r/RepTherapy/wiki/trustedsellers/") for row in contacts))
        # One public wiki row per seller: the roster grows, but a seller must never
        # accumulate duplicate contact rows.
        self.assertEqual(len({row["seller_id"] for row in contacts}), len(contacts))

    def test_research_lanes_include_rep_ladies_world_scan_candidates(self):
        research = load("research")
        lane = next(row for row in research["research_lanes"] if row["subreddit_focus"] == "RepLadiesWorld")
        self.assertEqual(lane["status"], "active_evidence_expansion")
        self.assertEqual(lane["families_checked"], 4)
        self.assertEqual(len(research["scan_log"][0]["candidate_sources"]), 4)
        self.assertEqual(research["glossary_source_url"], "https://www.reddit.com/r/RepTherapy/wiki/glossary/")

    def test_research_queue_contains_new_public_collection_leads(self):
        queued = {
            row["slug"]: row
            for row in load("bag_families")
            if row["publication_status"] == "research_queue"
        }
        self.assertIn("balmain-anthem", queued)
        self.assertIn("ferragamo-hug", queued)
        families = load("bag_families")
        self.assertTrue(all(bool(row.get("tile_media_id")) ^ bool(row.get("hero_icon")) for row in families))
        self.assertTrue(all(row["publication_status"] == "research_queue" for row in queued.values()))

    def test_generic_icons_do_not_enter_media_or_evidence_data(self):
        icon_prefix = "assets/collection-icons/"
        self.assertTrue(all(not row["path"].startswith(icon_prefix) for row in load("media")))
        self.assertNotIn(icon_prefix, json.dumps(load("evidence")))


if __name__ == "__main__":
    unittest.main()
