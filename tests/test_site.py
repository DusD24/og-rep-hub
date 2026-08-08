import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SiteContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "assets" / "styles.css").read_text(encoding="utf-8")
        cls.families = json.loads((ROOT / "data" / "bag_families.json").read_text(encoding="utf-8"))
        cls.research = json.loads((ROOT / "data" / "research.json").read_text(encoding="utf-8"))

    def test_required_views_and_family_filters_exist(self):
        for item in ("bag-results", "brand-filter", "type-filter", "size-filter", "material-filter", "evidence-type-filter", "seller-results", "factory-results", "evidence-results", "research-results"):
            self.assertIn(item, self.html)
        for label in ("Bags", "Sellers &amp; Factories", "Reviews &amp; Receipts", "Research", "Bag Finder", "Help Fill the Gaps"):
            self.assertIn(label, self.html + self.js)

    def test_all_family_routes_and_detail_rendering_exist(self):
        self.assertEqual(len(self.families), 12)
        self.assertIn("#bag/", self.js)
        self.assertIn("renderBagDetail", self.js)
        self.assertIn("documented_variant_ids", self.js)
        self.assertIn("Reviews &amp; receipts", self.js)

    def test_evidence_types_and_qualitative_badges_exist(self):
        for text in ("In-hand review", "Auth comparison", "Long-term wear", "Needs more receipts", "Community signal", "See reviews &amp; receipts"):
            self.assertIn(text, self.html + self.js)
        self.assertIn("evidence_type", self.js)
        self.assertIn("recommendation_score", self.js)

    def test_contact_links_are_safe_and_media_has_fallback(self):
        self.assertIn('rel="noopener noreferrer"', self.js)
        self.assertIn("Community-listed", self.js)
        self.assertIn("contact-source", self.js)
        self.assertIn("Media unavailable", self.css)
        self.assertIn("No selected media archived", self.js)
        self.assertIn("loading=\"lazy\"", self.js)

    def test_glossary_and_contribution_forms_exist(self):
        glossary_text = json.dumps(self.research)
        for term in ("PSP", "QC", "GL", "RL", "TS", "auth", "ISO", "RH"):
            self.assertIn(term, glossary_text)
        self.assertIn("glossary_source_url", self.js)
        self.assertIn("r/RepLadiesWorld leads", self.js)
        for template in ("suggest-a-bag.yml", "submit-reddit-source.yml", "correction-or-media-removal.yml"):
            self.assertTrue((ROOT / ".github" / "ISSUE_TEMPLATE" / template).is_file())

    def test_responsive_breakpoints_exist(self):
        self.assertIn("@media (max-width: 900px)", self.css)
        self.assertIn("@media (max-width: 600px)", self.css)
        self.assertIn("min-width: 0", self.css)

    def test_old_specific_copy_and_unsupported_site_claims_are_absent(self):
        old_copy = ("Candidate catalog", "Evidence explorer", "Contact queue & drafts", "brown Monogram GM and Eden/floral MM candidates")
        for phrase in old_copy:
            self.assertNotIn(phrase, self.html)
        for phrase in ("trusted", "safe", "1:1", "best factory"):
            self.assertNotIn(phrase, self.html.lower())


if __name__ == "__main__":
    unittest.main()
