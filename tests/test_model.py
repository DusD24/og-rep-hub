import unittest

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from model import bag_confidence, recommendation, seller_reliability, tier_for


class ScoreTests(unittest.TestCase):
    def test_seller_weights(self):
        metrics = {
            "fulfillment": 100,
            "service_communication": 80,
            "qc_transparency": 60,
            "shipping_consistency": 40,
            "payment_risk_signals": 20,
        }
        self.assertEqual(seller_reliability(metrics), 70.0)

    def test_bag_weights(self):
        metrics = {
            "accuracy": 100,
            "construction_materials": 80,
            "exact_variant_availability": 60,
            "independent_corroboration": 40,
            "recency": 20,
        }
        self.assertEqual(bag_confidence(metrics), 73.0)

    def test_recommendation_weights(self):
        self.assertEqual(recommendation(80, 60), 73.0)

    def test_tier_a_gates(self):
        self.assertEqual(tier_for(80, exact_variant=True, independent_authors=2, unresolved_major_negative=False, quality_evidence=True), "A")
        self.assertNotEqual(tier_for(90, exact_variant=True, independent_authors=1, unresolved_major_negative=False, quality_evidence=True), "A")
        self.assertNotEqual(tier_for(90, exact_variant=False, independent_authors=3, unresolved_major_negative=False, quality_evidence=True), "A")
        self.assertNotEqual(tier_for(90, exact_variant=True, independent_authors=3, unresolved_major_negative=True, quality_evidence=True), "A")

    def test_catalog_only_and_no_evidence_are_unranked(self):
        self.assertIsNone(tier_for(100, exact_variant=True, independent_authors=4, unresolved_major_negative=False, quality_evidence=False))


if __name__ == "__main__":
    unittest.main()

