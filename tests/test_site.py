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
        cls.ui_logic = (ROOT / "assets" / "ui-logic.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "assets" / "styles.css").read_text(encoding="utf-8")
        cls.favicon = (ROOT / "favicon.svg").read_text(encoding="utf-8")
        cls.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        cls.research_summary = (ROOT / "RESEARCH_SUMMARY.md").read_text(encoding="utf-8")
        cls.families = json.loads((ROOT / "data" / "bag_families.json").read_text(encoding="utf-8"))
        cls.bags = json.loads((ROOT / "data" / "bags.json").read_text(encoding="utf-8"))
        cls.evidence = json.loads((ROOT / "data" / "evidence.json").read_text(encoding="utf-8"))
        cls.research = json.loads((ROOT / "data" / "research.json").read_text(encoding="utf-8"))

    def test_required_views_and_collection_filters_exist(self):
        for item in (
            "bag-results", "brand-filter", "type-filter", "size-filter", "material-filter",
            "seller-results", "factory-results", "evidence-results", "research-results",
            "evidence-collection-filter", "evidence-seller-filter", "evidence-factory-filter",
            "evidence-subreddit-filter", "evidence-source-filter", "evidence-type-filter",
            "evidence-match-filter", "evidence-clear-filters",
        ):
            self.assertIn(item, self.html)
        for label in ("Catalog", "Sellers", "Factories", "Reviews &amp; Receipts", "Research", "The Catalog", "Help Fill the Gaps"):
            self.assertIn(label, self.html + self.js)

    def test_public_catalog_and_collection_language_is_current(self):
        public_copy = "\n".join((self.html, self.js, self.readme, self.research_summary))
        self.assertNotIn("Bag-first catalog", public_copy)
        self.assertNotIn("Bag Finder", public_copy)
        for stale_phrase in (
            "Open family file", "family files", "bag families", "bag family",
            "Useful family facts", "Family gap", "family candidate", "families checked",
            "Family-level", "family-level",
        ):
            self.assertNotIn(stale_phrase, public_copy)
        for current_phrase in ("The Catalog", "Collection Details", "bag collections", "source-linked collections"):
            self.assertIn(current_phrase, public_copy)

    def test_sellers_and_factories_are_distinct_routes(self):
        self.assertIn('id="sellers"', self.html)
        self.assertIn('id="factories"', self.html)
        self.assertIn('data-view-nav="sellers"', self.html)
        self.assertIn('data-view-nav="factories"', self.html)
        self.assertIn('"sellers", "factories"', self.js)

    def test_all_family_routes_and_detail_rendering_exist(self):
        self.assertGreaterEqual(len(self.families), 12)
        self.assertIn("#bag/", self.js)
        self.assertIn("renderBagDetail", self.js)
        self.assertIn("documented_variant_ids", self.js)
        self.assertIn("Reviews &amp; receipts", self.js)

    def test_site_copy_allows_collection_growth_beyond_launch_baseline(self):
        self.assertNotIn("12 launch families", self.html + self.js + self.readme)
        self.assertIn("state.bag_families.length", self.js)
        self.assertIn("state.evidence.length", self.js)

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

    def test_collection_heroes_distinguish_sources_from_generic_fallbacks(self):
        for contract in (
            "function heroIconType(family)",
            "function genericHeroMarkup(",
            "Generic collection illustration",
            "hero-stack",
            "generic-hero",
            "media-unavailable",
            "removeAttribute(\"aria-hidden\")",
        ):
            self.assertIn(contract, self.js + self.css)
        self.assertNotIn("Reddit photo pending", self.js)

    def test_glossary_and_contribution_forms_exist(self):
        glossary_text = json.dumps(self.research)
        for term in ("PSP", "QC", "GL", "RL", "TS", "auth", "ISO", "RH"):
            self.assertIn(term, glossary_text)
        self.assertIn("glossary_source_url", self.js)
        self.assertIn("Recent public scan leads", self.js)
        self.assertNotIn("r/RepLadiesWorld leads", self.js)
        for template in ("suggest-a-bag.yml", "submit-reddit-source.yml", "correction-or-media-removal.yml"):
            self.assertTrue((ROOT / ".github" / "ISSUE_TEMPLATE" / template).is_file())

    def test_repository_front_door_links_to_real_local_resources(self):
        expected_targets = {
            "CONTRIBUTING.md",
            "docs/assets/og-rep-hub-preview.png",
        }
        markdown_targets = {
            target.split("#", 1)[0]
            for target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", self.readme)
            if not re.match(r"^(?:https?://|mailto:|#)", target)
        }
        self.assertTrue(expected_targets.issubset(markdown_targets))
        for target in markdown_targets:
            self.assertTrue((ROOT / target).is_file(), f"README target does not exist: {target}")

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
        self.assertIn("voice-bubble-in", self.css)
        self.assertIn("2.35s", self.css)
        self.assertNotIn("<blockquote>", self.js)
        self.assertIn('aria-hidden="true"', self.html)
        for identity_part in ("tag-logo", ">OG<", ">REP<", "OG Rep Hub"):
            self.assertIn(identity_part, self.html)
        for identity_part in ("luggage tag", ">OG<", ">REP<"):
            self.assertIn(identity_part, self.favicon)

    def test_welcome_chatter_persists_and_lines_up_before_catalog(self):
        for contract in (
            "function enterCatalogFromWelcome()",
            'classList.add("welcome-transitioning")',
            'classList.add("welcome-exiting")',
            "welcomeExitDuration",
            "--voice-line-y",
            "--voice-exit-delay",
        ):
            self.assertIn(contract, self.js)
        for contract in (
            ".welcome-ready:not(.welcome-exiting) .welcome-voice",
            ".welcome-exiting .welcome-voice",
            "welcome-curtain-out",
            "opacity: .62",
            "top: var(--voice-line-y)",
        ):
            self.assertIn(contract, self.css)
        voice_animation = self.css[self.css.index("@keyframes voice-bubble-in"):self.css.index(".welcome-final")]
        self.assertIn("100% { opacity: .62", voice_animation)
        self.assertNotIn("100% { opacity: 0", voice_animation)

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
            "evidence-clear-filters",
            'window.addEventListener("hashchange"',
            "document.startViewTransition",
        ):
            self.assertIn(contract, self.js)
        self.assertIn("#evidence?family=", self.js)
        self.assertIn("#evidence?variant=", self.js)
        self.assertIn('href="./" data-welcome-route', self.html)

    def test_context_receipt_counts_match_public_contract(self):
        # The UI derives every receipt count at request time (state.evidence.length,
        # coverage.sourceCount), so this asserts the derivation paths agree rather than
        # freezing record counts that grow with each ingestion run.
        self.assertGreater(len(self.evidence), 38)
        evidence_by_id = {item["id"]: item for item in self.evidence}
        for family in self.families:
            variant_ids = set(family.get("documented_variant_ids", []))
            # #evidence?family= context: family_ids match or any documented variant match.
            family_receipts = [
                item for item in self.evidence
                if family["id"] in item.get("family_ids", [])
                or variant_ids.intersection(item.get("bag_ids", []))
            ]
            coverage = family.get("evidence_coverage", {})
            linked = [evidence_by_id[eid] for eid in family.get("evidence_ids", []) if eid in evidence_by_id]
            self.assertEqual(len(linked), len(family.get("evidence_ids", [])), family["id"])
            self.assertEqual(coverage.get("source_count"), len(linked), family["id"])
            self.assertEqual(
                coverage.get("independent_author_count"),
                len({item["author"].casefold() for item in linked if item.get("author")}),
                family["id"],
            )
            # Every explicitly linked receipt must also be reachable from the family context
            # the UI routes to, otherwise the detail page and the filtered view disagree.
            self.assertTrue(set(family.get("evidence_ids", [])) <= {item["id"] for item in family_receipts}, family["id"])
            # #evidence?variant= context is always a subset of its family context.
            for variant_id in variant_ids:
                variant_receipts = [item for item in self.evidence if variant_id in item.get("bag_ids", [])]
                self.assertTrue(set(r["id"] for r in variant_receipts) <= {r["id"] for r in family_receipts}, variant_id)
            if family.get("publication_status") == "published":
                self.assertGreater(len(family_receipts), 0, family["id"])

    def test_native_dialog_has_all_dismissal_and_focus_behaviors(self):
        self.assertIn('<dialog id="content-dialog"', self.html)
        self.assertIn("data-dialog-close", self.html + self.js)
        self.assertIn("showModal()", self.js)
        self.assertIn("event.target === dialog", self.js)
        self.assertIn('dialog.addEventListener("close"', self.js)
        self.assertIn("dialogOpener", self.js)
        self.assertIn("target.focus({ preventScroll: true })", self.js)
        self.assertIn('classList.add("dialog-open")', self.js)
        self.assertIn('classList.remove("dialog-open")', self.js + self.ui_logic)
        self.assertIn("restoreLockedScroll", self.js)
        self.assertIn("scroll-restoring", self.css)
        self.assertIn(".content-dialog::backdrop", self.css)
        self.assertNotIn('addEventListener("cancel"', self.js)

    def test_consent_banner_hidden_attribute_actually_hides_it(self):
        self.assertIn('id="consent-banner"', self.html)
        self.assertIn("data-consent-accept", self.html)
        self.assertIn("data-consent-decline", self.html)
        self.assertIn("data-consent-preferences", self.html)
        unscoped_banner_rule = re.search(r"\.consent-banner\s*\{[^}]*\}", self.css)
        self.assertIsNotNone(unscoped_banner_rule)
        self.assertNotIn("display", unscoped_banner_rule.group(0), (
            "`.consent-banner { display: ... }` outranks the browser's default "
            "`[hidden] { display: none }` rule (same specificity, author style wins), "
            "so toggling the hidden attribute would stop actually hiding the banner. "
            "Scope any `display` declaration to `.consent-banner:not([hidden])` instead."
        ))
        self.assertIn(".consent-banner:not([hidden])", self.css)

    def test_consent_banner_only_shows_once_the_welcome_curtain_is_gone(self):
        self.assertIn("function syncAnalyticsBanner()", self.js)
        self.assertIn("analyticsBannerPending", self.js)
        self.assertIn('classList.contains("welcome-mode")', self.js)
        self.assertRegex(self.js, r"function setDisplayMode\([^)]*\)\s*\{[^}]*syncAnalyticsBanner\(\)")

    def test_receipt_dialog_can_swap_to_branded_update_form(self):
        for contract in (
            "Request a receipt update", "renderReceiptUpdateForm", "receipt-update-form",
            "Back to receipt", "turnstileToken", "evidenceUrls",
        ):
            self.assertIn(contract, self.html + self.js)

    def test_all_contribution_paths_submit_through_the_worker(self):
        for contract in (
            "CONTRIBUTION_FORMS", "submitContributionForm", "contributionDialogContent",
            "/issues/suggest-bag", "/issues/submit-source", "/issues/correction-media-removal",
            "data-contribution-kind", "suggest-bag-form", "submit-source-form", "correction-media-removal-form",
        ):
            self.assertIn(contract, self.js)
        self.assertNotIn("issues/new?template=", self.js)

        shared_launcher = self.js[self.js.index("function renderContributionCards"):self.js.index("function renderResearch")]
        for contract in (
            'class="contribution-card dialog-trigger"',
            'data-dialog-kind="contribute"',
            'data-dialog-id="${escapeHtml(item.kind)}"',
        ):
            self.assertIn(contract, shared_launcher)

        dialog_router = self.js[self.js.index("function dialogContent"):self.js.index("function setDialogContent")]
        self.assertIn('if (kind === "contribute") return contributionDialogContent(id);', dialog_router)

        click_dispatch = self.js[self.js.index("function bindControls"):self.js.index("function loadAnalytics")]
        self.assertIn('const dialogTrigger = event.target.closest(".dialog-trigger");', click_dispatch)
        self.assertIn("if (dialogTrigger) return openDialog(dialogTrigger);", click_dispatch)

    def test_research_starts_with_cloudflare_backed_contribution_paths(self):
        research = self.js[self.js.index("function renderResearch"):self.js.index("function sellerDialog")]
        self.assertIn("CONTRIBUTION_LINKS", self.js)
        self.assertIn("function renderContributionCards", self.js)
        self.assertLess(research.index("contribution-section"), research.index("How this corpus grew"))
        self.assertIn("Contribute to the research", research)
        for kind in ("suggest-bag", "submit-source", "correction-media-removal"):
            self.assertIn(kind, research)

    def test_catalog_ends_with_suggest_a_bag_callout(self):
        catalog = self.html[self.html.index('<section id="bags"'):self.html.index('<section id="sellers"')]
        self.assertIn('id="catalog-contribution-title"', catalog)
        self.assertLess(catalog.index('id="bag-results"'), catalog.index('id="catalog-contribution-title"'))
        self.assertIn('class="contribution-card dialog-trigger"', catalog)
        self.assertIn('data-dialog-kind="contribute"', catalog)
        self.assertIn('data-dialog-id="suggest-bag"', catalog)
        self.assertIn("Don’t see your bag?", catalog)

    def test_bag_detail_ends_with_source_and_correction_actions(self):
        detail = self.js[self.js.index("function renderBagDetail"):self.js.index("const CONTRIBUTION_LINKS")]
        self.assertIn("bag-contribution-title", detail)
        self.assertLess(detail.index("support-grid"), detail.index("bag-contribution-title"))
        self.assertIn('renderContributionCards(["submit-source", "correction-media-removal"], "two")', detail)
        contribution = detail[detail.index("bag-contribution-title"):]
        self.assertNotIn("suggest-bag", contribution)
        self.assertIn("Help improve this bag’s research", contribution)

    def test_family_file_is_receipt_first_and_variant_cards_are_compact(self):
        detail = self.js[self.js.index("function renderBagDetail"):self.js.index("function renderResearch")]
        self.assertLess(detail.index("family-hero"), detail.index("family-receipts"))
        self.assertLess(detail.index("family-receipts"), detail.index("variants-section"))
        self.assertLess(detail.index("variants-section"), detail.index("support-grid"))
        self.assertIn("slice(0, 6)", detail)
        self.assertIn("View all ${evidence.length} receipts", detail)
        self.assertIn("At a glance", detail)
        self.assertIn("Useful collection facts", detail)
        self.assertIn("Research notes", detail)
        self.assertIn("collectionResearchNotes", detail)
        self.assertIn("researchNotes.summary", detail)
        self.assertIn("researchNotes.watchouts", detail)
        self.assertIn("Read all ${researchNotes.watchouts.length}", detail)

        variants = self.js[self.js.index("function renderVariantCards"):self.js.index("function reportedPartyNames")]
        for label_text in (">Material<", ">Hardware<"):
            self.assertNotIn(label_text, variants)
        for label_text in (">Size<", ">Pattern<", ">Colorway<", "variantMedia", "receipt-count"):
            self.assertIn(label_text, variants)
        self.assertRegex(variants, r"evidenceCount \? .*href=\"#evidence\?variant=")
        self.assertIn('<span class="receipt-count zero">0 receipts</span>', variants)

    def test_variant_cards_are_ordered_by_receipt_count(self):
        variants = self.js[self.js.index("function familyVariants"):self.js.index("function reportedPartyNames")]
        self.assertIn("function variantEvidenceCount(variant)", variants)
        self.assertIn("variantEvidenceCount(b) - variantEvidenceCount(a)", variants)
        self.assertIn("ids.indexOf(a.id) - ids.indexOf(b.id)", variants)

    def test_published_variant_ids_are_hero_backed(self):
        bags_by_id = {row["id"]: row for row in self.bags}
        for family in self.families:
            for variant_id in family.get("documented_variant_ids", []):
                self.assertTrue(
                    bags_by_id[variant_id].get("tile_media_id"),
                    f"{family['id']} exposes a variant without a hero: {variant_id}",
                )
        variants = self.js[self.js.index("function familyVariants"):self.js.index("function variantEvidenceCount")]
        self.assertIn("const ids = unique(family.documented_variant_ids || []);", variants)
        self.assertNotIn("state.bags || []", variants)

    def test_variant_section_labels_hero_backed_rows_and_retained_leads(self):
        detail = self.js[self.js.index("function renderBagDetail"):self.js.index("const CONTRIBUTION_LINKS")]
        self.assertIn("Hero-backed source-documented identities", detail)
        self.assertIn("unillustrated lead", detail)
        self.assertIn("state.bags || []", detail)

    def test_collection_research_notes_are_one_summary_and_watchouts(self):
        notes = self.research.get("collection_notes", [])
        by_family = {row.get("family_id"): row for row in notes}
        self.assertEqual(set(by_family), {family["id"] for family in self.families})
        for row in notes:
            self.assertTrue(row.get("summary"), row.get("family_id"))
            self.assertGreaterEqual(len(row.get("watchouts", [])), 1, row.get("family_id"))
            self.assertNotRegex(json.dumps(row), r"(?i)(whatsapp|\bpayment\b|\baddress\b|\bcredentials?\b)")

    def test_compact_grid_layout_contracts(self):
        self.assertIsNotNone(re.search(r"\.receipt-grid\s*\{[^}]*repeat\(2", self.css, re.DOTALL))
        self.assertIsNotNone(re.search(r"\.directory-grid\s*\{[^}]*repeat\(3", self.css, re.DOTALL))
        self.assertIsNotNone(re.search(r"\.variant-grid\s*\{[^}]*repeat\(2", self.css, re.DOTALL))
        self.assertIn("repeat(auto-fit", self.css)
        self.assertIn("-webkit-line-clamp", self.css)
        self.assertIn(".card-spacer", self.css)
        self.assertIn(".queue-table", self.css)
        self.assertIn(".contribution-grid", self.css)
        self.assertIn(".catalog-contribution", self.css)
        self.assertIn(".contribution-grid-two", self.css)
        self.assertIn(".contribution-grid-single", self.css)
        tablet = self.css[self.css.index("@media (max-width: 900px)"):self.css.index("@media (max-width: 700px)")]
        self.assertIn(".catalog-contribution { grid-template-columns: 1fr; gap: 12px; }", tablet)
        self.assertIn(".contribution-grid, .contribution-grid-single, .contribution-grid-two { grid-template-columns: 1fr; }", tablet)
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

    def test_mobile_navigation_does_not_duplicate_accessible_link_names(self):
        self.assertNotIn('content: "Catalog"', self.css)
        self.assertNotIn('content: "Factories"', self.css)
        self.assertNotIn('content: "Receipts"', self.css)

    def test_expected_view_transition_cancellation_is_consumed(self):
        transition = self.js[self.js.index("function transitionView"):self.js.index("function focusAndScroll")]
        self.assertIn("transition.ready.catch", transition)
        self.assertIn("transition.finished.catch", transition)


if __name__ == "__main__":
    unittest.main()
