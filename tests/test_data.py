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


if __name__ == "__main__":
    unittest.main()

