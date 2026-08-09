import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SiteContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "assets" / "styles.css").read_text(encoding="utf-8")
        cls.favicon = (ROOT / "favicon.svg").read_text(encoding="utf-8")
        cls.families = json.loads((ROOT / "data" / "bag_families.json").read_text(encoding="utf-8"))
        cls.bags = json.loads((ROOT / "data" / "bags.json").read_text(encoding="utf-8"))
        cls.evidence = json.loads((ROOT / "data" / "evidence.json").read_text(encoding="utf-8"))
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

    def test_bare_root_welcome_and_identity_contracts(self):
        self.assertIn('<body class="welcome-mode">', self.html)
        self.assertIn('id="welcome"', self.html)
        self.assertIn("100svh", self.css)
        self.assertIn(".welcome-mode .app-shell", self.css)
        self.assertIn("Your search ends here", self.html)
        self.assertIn("View the Bags &amp; the Receipts", self.html)
        self.assertIn("welcomeEvidenceIds", self.js)
        self.assertEqual(len(re.findall(r'^\s+"ev-[^"]+"', self.js, re.MULTILINE)), 6)
        self.assertIn("--voice-index", self.js)
        self.assertIn("2s", self.css)
        self.assertNotIn("<blockquote>", self.js)
        self.assertIn('aria-hidden="true"', self.html)
        for identity_part in ("tag-logo", ">OG<", ">REP<", "OG Rep Hub"):
            self.assertIn(identity_part, self.html)
        for identity_part in ("luggage tag", ">OG<", ">REP<"):
            self.assertIn(identity_part, self.favicon)

    def test_single_router_uses_history_and_deep_link_context(self):
        for contract in (
            "function parseRoute()",
            "function navigate(",
            "history[",
            'params.get("family")',
            'params.get("variant")',
            "activeEvidenceContext",
            "resetEvidenceControls()",
            "data-clear-evidence",
            'window.addEventListener("hashchange"',
            "document.startViewTransition",
        ):
            self.assertIn(contract, self.js)
        self.assertIn("#evidence?family=", self.js)
        self.assertIn("#evidence?variant=", self.js)
        self.assertIn('href="./" data-welcome-route', self.html)

    def test_context_receipt_counts_match_public_contract(self):
        neverfull = next(item for item in self.families if item["id"] == "bag-family-louis-vuitton-neverfull")
        variant_ids = set(neverfull["documented_variant_ids"])
        family_receipts = [
            item for item in self.evidence
            if neverfull["id"] in item.get("family_ids", [])
            or variant_ids.intersection(item.get("bag_ids", []))
        ]
        monogram_mm_receipts = [
            item for item in self.evidence
            if "bag-monogram-mm-brown" in item.get("bag_ids", [])
        ]
        self.assertEqual(len(self.evidence), 38)
        self.assertEqual(len(family_receipts), 16)
        self.assertEqual(len(monogram_mm_receipts), 3)

    def test_native_dialog_has_all_dismissal_and_focus_behaviors(self):
        self.assertIn('<dialog id="content-dialog"', self.html)
        self.assertIn("data-dialog-close", self.html + self.js)
        self.assertIn("showModal()", self.js)
        self.assertIn("event.target === dialog", self.js)
        self.assertIn('dialog.addEventListener("close"', self.js)
        self.assertIn("dialogOpener", self.js)
        self.assertIn("target.focus()", self.js)
        self.assertIn('classList.add("dialog-open")', self.js)
        self.assertIn('classList.remove("dialog-open")', self.js)
        self.assertIn(".content-dialog::backdrop", self.css)
        self.assertNotIn('addEventListener("cancel"', self.js)

    def test_family_file_is_receipt_first_and_variant_cards_are_compact(self):
        detail = self.js[self.js.index("function renderBagDetail"):self.js.index("function renderResearch")]
        self.assertLess(detail.index("family-hero"), detail.index("family-receipts"))
        self.assertLess(detail.index("family-receipts"), detail.index("variants-section"))
        self.assertLess(detail.index("variants-section"), detail.index("support-grid"))
        self.assertIn("slice(0, 6)", detail)
        self.assertIn("View all ${evidence.length} receipts", detail)
        self.assertIn("At a glance", detail)
        self.assertIn("Research notes", detail)
        self.assertIn("slice(0, 3)", detail)
        self.assertIn("Read all ${qcNotes.length}", detail)

        variants = self.js[self.js.index("function renderVariantCards"):self.js.index("function reportedPartyNames")]
        for label_text in (">Material<", ">Hardware<"):
            self.assertNotIn(label_text, variants)
        for label_text in (">Size<", ">Pattern<", ">Colorway<", "variantMedia", "receipt-count"):
            self.assertIn(label_text, variants)
        self.assertRegex(variants, r"evidenceCount \? .*href=\"#evidence\?variant=")
        self.assertIn('<span class="receipt-count zero">0 receipts</span>', variants)

    def test_compact_grid_layout_contracts(self):
        self.assertIsNotNone(re.search(r"\.receipt-grid\s*\{[^}]*repeat\(2", self.css, re.DOTALL))
        self.assertIsNotNone(re.search(r"\.directory-grid\s*\{[^}]*repeat\(3", self.css, re.DOTALL))
        self.assertIsNotNone(re.search(r"\.variant-grid\s*\{[^}]*repeat\(2", self.css, re.DOTALL))
        self.assertIn("repeat(auto-fit", self.css)
        self.assertIn("-webkit-line-clamp", self.css)
        self.assertIn(".card-spacer", self.css)
        self.assertIn(".queue-table", self.css)
        self.assertIn(".contribution-grid", self.css)
        mobile = self.css[self.css.index("@media (max-width: 700px)"):]
        self.assertIn(".variant-grid", mobile)
        self.assertIn("grid-template-columns: 1fr", mobile)

    def test_reduced_motion_focus_and_touch_contracts(self):
        self.assertIn("@media (prefers-reduced-motion: reduce)", self.css)
        reduced = self.css[self.css.index("@media (prefers-reduced-motion: reduce)"):]
        for contract in ("scroll-behavior: auto", ".welcome-voice { display: none; }", ".welcome-final { opacity: 1", ".silhouette { animation: none; }"):
            self.assertIn(contract, reduced)
        self.assertIn("min-height: 44px", self.css)
        self.assertIn('class="skip-link app-shell"', self.html)
        self.assertIn('setAttribute("aria-current", "page")', self.js)
        self.assertIn('focus({ preventScroll: true })', self.js)
        self.assertIn('loading="lazy"', self.js)
        self.assertIn("onerror=", self.js)


if __name__ == "__main__":
    unittest.main()
