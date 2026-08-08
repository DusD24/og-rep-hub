import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SiteContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "assets" / "styles.css").read_text(encoding="utf-8")

    def test_required_views_and_filters_exist(self):
        for item in ("catalog-search", "size-filter", "color-filter", "status-filter", "seller-results", "evidence-results", "outreach-results"):
            self.assertIn(item, self.html)

    def test_ranking_sort_and_evidence_drilldown_exist(self):
        self.assertIn("recommendation_score", self.js)
        self.assertIn("data-open-evidence", self.js)

    def test_contact_links_are_safe_and_media_has_fallback(self):
        self.assertIn('rel="noopener noreferrer"', self.js)
        self.assertIn("Media unavailable", self.css)
        self.assertIn("No selected media archived", self.js)

    def test_responsive_breakpoints_exist(self):
        self.assertIn("@media (max-width: 900px)", self.css)
        self.assertIn("@media (max-width: 600px)", self.css)

    def test_compact_hero_and_reddit_tile_rendering(self):
        self.assertNotIn("<h1>", self.html)
        self.assertIn("bag-tile", self.js)
        self.assertIn("tile_media_id", self.js)
        self.assertIn("Reddit photo", self.js)


if __name__ == "__main__":
    unittest.main()
