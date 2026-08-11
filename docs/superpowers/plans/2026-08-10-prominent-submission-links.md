# Prominent Submission Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the three Cloudflare-backed contribution forms prominent on Research and add contextual form launchers to the Catalog and individual bag pages.

**Architecture:** Keep the existing dialog and Worker submission pipeline intact. Centralize contribution-card labels and markup in `assets/app.js`, reuse that renderer for Research and bag-detail content, and add one static Suggest a Bag callout after the Catalog grid. Extend the existing contribution styles with explicit single- and two-action layouts.

**Tech Stack:** Dependency-free HTML, CSS, and browser JavaScript; Python `unittest` contract tests; Node Worker/UI tests; Cloudflare Wrangler dry-run validation.

## Global Constraints

- Reuse the existing `suggest-bag`, `submit-source`, and `correction-media-removal` dialogs and Worker endpoints.
- Do not change form fields, validation, privacy protections, Turnstile behavior, Worker behavior, GitHub issue creation, or submission payloads.
- Keep Suggest a Bag on Research and the Catalog, but not on individual bag pages.
- Keep Submit a Reddit Source and Correction or Media Removal on Research and individual bag pages.
- Use real `button` elements with the existing contribution-dialog data attributes.
- Keep the layouts responsive at the existing breakpoints.
- Do not add a floating button or permanent primary-navigation item.

---

### Task 1: Shared contribution launchers and Research prominence

**Files:**
- Modify: `tests/test_site.py:267-278`
- Modify: `assets/app.js:500-526`

**Interfaces:**
- Consumes: the existing dialog contract `data-dialog-kind="contribute"` plus contribution IDs `suggest-bag`, `submit-source`, and `correction-media-removal`.
- Produces: `CONTRIBUTION_LINKS`, a frozen map of contribution metadata, and `renderContributionCards(kinds, layout = "three")`, which returns contribution-card HTML for the named kinds.

- [ ] **Step 1: Write the failing Research placement test**

Add this test to `SiteContractTests` in `tests/test_site.py`:

```python
def test_research_starts_with_cloudflare_backed_contribution_paths(self):
    research = self.js[self.js.index("function renderResearch"):self.js.index("function sellerDialog")]
    self.assertIn("CONTRIBUTION_LINKS", self.js)
    self.assertIn("function renderContributionCards", self.js)
    self.assertLess(research.index("contribution-section"), research.index("How this corpus grew"))
    self.assertIn("Contribute to the research", research)
    for kind in ("suggest-bag", "submit-source", "correction-media-removal"):
        self.assertIn(kind, research)
```

- [ ] **Step 2: Run the focused test and verify that it fails**

Run:

```bash
python -m unittest tests.test_site.SiteContractTests.test_research_starts_with_cloudflare_backed_contribution_paths -v
```

Expected: FAIL because `CONTRIBUTION_LINKS` and `renderContributionCards` do not exist and the contribution section follows all other Research sections.

- [ ] **Step 3: Add the shared card renderer**

In `assets/app.js`, immediately before `renderResearch`, add:

```js
const CONTRIBUTION_LINKS = Object.freeze({
  "suggest-bag": {
    title: "Suggest a Bag",
    description: "Add a collection candidate with public source URLs and no private contact details.",
  },
  "submit-source": {
    title: "Submit a Reddit Source",
    description: "Add a review, PSP/QC post, auth comparison, or in-hand receipt with provenance.",
  },
  "correction-media-removal": {
    title: "Correction or Media Removal",
    description: "Flag a source, attribution, image, or research note for review.",
  },
});

function renderContributionCards(kinds, layout = "three") {
  const cards = kinds.map(kind => ({ kind, ...CONTRIBUTION_LINKS[kind] })).filter(item => item.title);
  return `<div class="contribution-grid contribution-grid-${escapeHtml(layout)}">${cards.map(item => `<button class="contribution-card dialog-trigger" type="button" data-dialog-kind="contribute" data-dialog-id="${escapeHtml(item.kind)}"><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.description)}</span></button>`).join("")}</div>`;
}
```

- [ ] **Step 4: Move the Research contribution section to the top**

Remove the local `forms` array from `renderResearch`. Make the first section assigned to `#research-results`:

```js
<section class="research-section contribution-section" aria-labelledby="research-contribution-title"><p class="eyebrow">Public contribution paths</p><h2 id="research-contribution-title">Contribute to the research</h2>${renderContributionCards(["suggest-bag", "submit-source", "correction-media-removal"])}</section>
```

Keep the campaign, lane, scan-lead, glossary, and queue sections in their existing relative order after this section. Delete the old trailing contribution section.

- [ ] **Step 5: Run the focused test and existing submission contract test**

Run:

```bash
python -m unittest \
  tests.test_site.SiteContractTests.test_research_starts_with_cloudflare_backed_contribution_paths \
  tests.test_site.SiteContractTests.test_all_contribution_paths_submit_through_the_worker -v
```

Expected: both tests PASS.

- [ ] **Step 6: Commit the Research placement**

```bash
git add assets/app.js tests/test_site.py
git commit -m "feat: promote research submission forms"
```

---

### Task 2: Contextual Catalog and bag-detail launchers

**Files:**
- Modify: `tests/test_site.py:279-323`
- Modify: `index.html:50-75`
- Modify: `assets/app.js:470-529`
- Modify: `assets/styles.css:481-498, 610-637`

**Interfaces:**
- Consumes: `renderContributionCards(kinds, layout)` from Task 1 and the existing delegated `.dialog-trigger` click handler.
- Produces: `#catalog-contribution-title`, a static Catalog Suggest a Bag callout, and `#bag-contribution-title`, a dynamic two-action bag-detail section.

- [ ] **Step 1: Write failing contextual-placement tests**

Add these tests to `SiteContractTests` in `tests/test_site.py`:

```python
def test_catalog_ends_with_suggest_a_bag_callout(self):
    catalog = self.html[self.html.index('<section id="bags"'):self.html.index('<section id="sellers"')]
    self.assertLess(catalog.index('id="bag-results"'), catalog.index('id="catalog-contribution-title"'))
    self.assertIn('data-dialog-kind="contribute"', catalog)
    self.assertIn('data-dialog-id="suggest-bag"', catalog)
    self.assertIn("Don’t see your bag?", catalog)

def test_bag_detail_ends_with_source_and_correction_actions(self):
    detail = self.js[self.js.index("function renderBagDetail"):self.js.index("const CONTRIBUTION_LINKS")]
    self.assertLess(detail.index("support-grid"), detail.index("bag-contribution-title"))
    self.assertIn('renderContributionCards(["submit-source", "correction-media-removal"], "two")', detail)
    contribution = detail[detail.index("bag-contribution-title"):]
    self.assertNotIn("suggest-bag", contribution)
    self.assertIn("Help improve this bag’s research", contribution)
```

Extend `test_compact_grid_layout_contracts` with:

```python
self.assertIn(".catalog-contribution", self.css)
self.assertIn(".contribution-grid-two", self.css)
self.assertIn(".contribution-grid-single", self.css)
```

- [ ] **Step 2: Run the focused tests and verify that they fail**

Run:

```bash
python -m unittest \
  tests.test_site.SiteContractTests.test_catalog_ends_with_suggest_a_bag_callout \
  tests.test_site.SiteContractTests.test_bag_detail_ends_with_source_and_correction_actions \
  tests.test_site.SiteContractTests.test_compact_grid_layout_contracts -v
```

Expected: the two new tests FAIL because the contextual sections do not exist; the layout test FAILS because the new selectors do not exist.

- [ ] **Step 3: Add the Catalog callout**

In `index.html`, immediately after `<div id="bag-results" ...></div>`, add:

```html
<section class="catalog-contribution contribution-section" aria-labelledby="catalog-contribution-title">
  <div>
    <p class="eyebrow">Grow the Catalog</p>
    <h2 id="catalog-contribution-title">Don’t see your bag?</h2>
    <p>Suggest a collection and include the public sources that put it on the research trail.</p>
  </div>
  <div class="contribution-grid contribution-grid-single">
    <button class="contribution-card dialog-trigger" type="button" data-dialog-kind="contribute" data-dialog-id="suggest-bag">
      <strong>Suggest a Bag</strong>
      <span>Add a collection candidate with public source URLs and no private contact details.</span>
    </button>
  </div>
</section>
```

- [ ] **Step 4: Add the bag-detail contribution section**

In the final `container.innerHTML` template inside `renderBagDetail`, place this section after `support-grid` and before the closing backtick:

```js
<section class="family-section contribution-section bag-contribution" aria-labelledby="bag-contribution-title">
  <p class="eyebrow">Community contributions</p>
  <h2 id="bag-contribution-title">Help improve this bag’s research</h2>
  <p>Bring a public receipt, flag a correction, or request review of attributed media.</p>
  ${renderContributionCards(["submit-source", "correction-media-removal"], "two")}
</section>
```

- [ ] **Step 5: Add explicit one- and two-action layouts**

In the Research/contribution section of `assets/styles.css`, add:

```css
.catalog-contribution { display: grid; grid-template-columns: minmax(0, 1fr) minmax(260px, .55fr); gap: 24px; align-items: center; }
.catalog-contribution h2, .bag-contribution h2 { margin: 5px 0 9px; font-size: clamp(27px, 4vw, 38px); }
.catalog-contribution p, .bag-contribution > p { max-width: 650px; color: var(--muted); line-height: 1.5; }
.contribution-grid-single { grid-template-columns: minmax(0, 360px); justify-content: end; }
.contribution-grid-two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
```

Inside `@media (max-width: 900px)`, extend the contribution rule to:

```css
.catalog-contribution { grid-template-columns: 1fr; gap: 12px; }
.contribution-grid, .contribution-grid-single, .contribution-grid-two { grid-template-columns: 1fr; }
```

- [ ] **Step 6: Run the focused tests and make sure they pass**

Run:

```bash
python -m unittest \
  tests.test_site.SiteContractTests.test_catalog_ends_with_suggest_a_bag_callout \
  tests.test_site.SiteContractTests.test_bag_detail_ends_with_source_and_correction_actions \
  tests.test_site.SiteContractTests.test_compact_grid_layout_contracts -v
```

Expected: all three tests PASS.

- [ ] **Step 7: Run all site and browser-logic tests**

Run:

```bash
python -m unittest tests.test_site -v
pnpm test
```

Expected: all tests PASS.

- [ ] **Step 8: Commit the contextual launchers**

```bash
git add index.html assets/app.js assets/styles.css tests/test_site.py
git commit -m "feat: add contextual submission links"
```

---

### Task 3: Release-candidate verification

**Files:**
- Verify only: no planned file changes.

**Interfaces:**
- Consumes: the completed frontend changes from Tasks 1 and 2.
- Produces: a verified feature branch ready for review, push, and pull request publication.

- [ ] **Step 1: Check repository and data integrity**

Run:

```bash
git lfs fsck
python scripts/validate.py
python scripts/score.py --check
```

Expected: LFS objects are valid, catalog validation passes, and derived rankings are current.

- [ ] **Step 2: Run the complete automated suite**

Run:

```bash
python -m unittest discover -s tests -v
pnpm test
```

Expected: all Python, UI behavior, and Worker tests PASS.

- [ ] **Step 3: Validate the Worker bundle**

Run:

```bash
pnpm exec wrangler deploy --dry-run --config worker/wrangler.jsonc
```

Expected: Wrangler completes the dry-run bundle successfully without deploying.

- [ ] **Step 4: Review the final diff and branch state**

Run:

```bash
git diff origin/main...HEAD --check
git diff --stat origin/main...HEAD
git status --short
```

Expected: no whitespace errors, only the design/plan and intended frontend/test files are committed, and the unrelated `docs/research/moderator-outreach-drafts.md` remains untracked and untouched.

