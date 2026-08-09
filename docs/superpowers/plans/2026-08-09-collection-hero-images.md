# Collection Hero Images Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every current and future collection a complete Catalog and Collection Details hero using qualifying Reddit/Imgur media first and a clearly labeled generic bag-type illustration only when no qualifying media exists.

**Architecture:** Add a mutually exclusive `tile_media_id`/`hero_icon` contract to collection data. Keep receipt-linked media in the existing evidence/media provenance graph; keep five local generic raster icons outside that graph. Render a generic hero beneath sourced media as a resilient runtime fallback, while preserving source links and attribution only for successful community images.

**Tech Stack:** Dependency-free HTML/CSS/JavaScript, Python 3.13 validation and unittest contracts, JSON normalized data, JPEG evidence media in Git LFS, PNG presentation assets, GitHub Pages, Cloudflare Worker release workflow.

## Global Constraints

- Hero photography may come only from public Reddit or Imgur sources linked to a normalized receipt for the exact collection.
- Official product, retailer, seller-catalog, and other external images are forbidden.
- Every collection must define exactly one of `tile_media_id` or `hero_icon`.
- Allowed `hero_icon` values are `tote`, `shoulder-flap`, `top-handle`, `hobo`, and `vanity`.
- Published collections must continue to use qualifying community media; a generic icon cannot satisfy the publication media gate.
- Generic icons are presentation assets only and must never enter `data/media.json` or an evidence `media_ids` list.
- Adding a hero must not change a collection's `publication_status`, evidence counts, ranking, confidence, or availability claims.
- Keep the static GitHub Pages architecture, existing internal `family_*` schema names, and current card/detail proportions.
- Use tests first for every behavior or validator change and observe the expected failure before implementation.

---

### Task 1: Audit the seven research collections for qualifying community media

**Files:**
- Create: `docs/research/collection-hero-source-audit-2026-08-09.md`
- Read: `data/bag_families.json`
- Read: `data/evidence.json`

**Interfaces:**
- Consumes: the eight existing normalized receipt URLs listed below.
- Produces: one audit row per research collection with `qualifying_media`, direct image URL, receipt ID, privacy result, silhouette result, and fallback icon.

- [ ] **Step 1: Create the audit table with the exact candidate sources**

Write the table with these rows and fallback values:

| Collection | Receipt(s) | Fallback icon |
| --- | --- | --- |
| Balmain Anthem | `ev-crawl-repculture-balmain-anthem-2025` | `shoulder-flap` |
| Ferragamo Hug Soft | `ev-crawl-rt-ferragamo-hug-2026`, `ev-crawl-rll-ferragamo-hug-2026` | `tote` |
| Saint Laurent LouLou | `ev-crawl-rll-ysl-loulou-black-frame-2026` | `shoulder-flap` |
| Celine New Luggage | `ev-crawl-rll-celine-new-luggage-2026` | `top-handle` |
| Bottega Veneta Barbara Tote | `ev-crawl-rll-bv-barbara-medium-2026` | `tote` |
| Balenciaga Rodeo | `ev-crawl-rll-balenciaga-rodeo-medium-2026` | `top-handle` |
| Chanel Slim Vanity | `ev-crawl-rll-chanel-vanity-slim-2026` | `vanity` |

- [ ] **Step 2: Inspect each Reddit post and any author-owned Imgur album**

Use the public post, Reddit embed/media surfaces, and linked Imgur album where present. Do not use search-result thumbnails, brand sites, seller catalogs, reposted third-party images, or private/authenticated material.

Record `qualifying_media: yes` only when all are true:

1. The direct asset host is an approved Reddit-media host or `i.imgur.com`.
2. The public receipt author and post provenance match the normalized evidence row.
3. At least 80% of the intended collection silhouette is visible.
4. No face, address, payment record, private conversation, PSP with identifying order data, or unrelated person is visible.
5. The asset is a stable JPEG candidate and is not an icon, stock image, seller catalog, or official product image.

- [ ] **Step 3: Record a deterministic decision for every row**

For a qualifying source, record the exact direct URL, post URL, receipt ID, author, subreddit, and why the selected frame is safe. For a rejected source, record the failed gate and the exact fallback icon from Step 1. Do not leave a row blank or use an unresolved marker.

- [ ] **Step 4: Review the audit for privacy and provenance**

Run:

```bash
rg -n "official|retailer|seller catalog|private message|address|payment" docs/research/collection-hero-source-audit-2026-08-09.md
```

Expected: no placeholders; any forbidden-source terms appear only in explicit rejection explanations.

- [ ] **Step 5: Commit the audit**

```bash
git add docs/research/collection-hero-source-audit-2026-08-09.md
git commit -m "docs: audit collection hero sources"
```

---

### Task 2: Create and verify the generic icon suite

**Files:**
- Create: `assets/collection-icons/tote.png`
- Create: `assets/collection-icons/shoulder-flap.png`
- Create: `assets/collection-icons/top-handle.png`
- Create: `assets/collection-icons/hobo.png`
- Create: `assets/collection-icons/vanity.png`
- Modify: `tests/test_data.py`

**Interfaces:**
- Consumes: approved icon names from the design spec.
- Produces: five 16:10 local raster presentation assets and a standard-library `png_dimensions(path)` test helper.

- [ ] **Step 1: Write the failing icon-asset test**

Add a PNG dimension helper using the IHDR header and this test:

```python
def png_dimensions(path):
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")

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
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
python -m unittest tests.test_data.DataTests.test_generic_collection_icon_suite_is_complete_and_consistent -v
```

Expected: FAIL because the five PNG files do not exist.

- [ ] **Step 3: Generate five original icons**

Use the image-generation tool once per icon. Start with this exact tote prompt:

```text
Create one original 16:10 editorial illustration of a generic tote bag for OG Rep Hub. Warm cream paper background, cognac and espresso linework, restrained muted-gold accent, subtle paper grain, centered silhouette, generous negative space, same visual language as a refined vintage luggage tag. No text, no letters, no logos, no monograms, no signature patterns, no recognizable proprietary clasp or hardware, no quilting, no exact branded product, no person, no room scene, no extra objects. This is a generic category icon, not product photography. Output a complete landscape raster composition suitable for a website hero crop.
```

Save that output as `tote.png`. Repeat the exact prompt four times, replacing only `generic tote bag` with `generic shoulder or flap bag`, `generic top-handle bag`, `generic hobo bag`, and `generic vanity case bag`, and save them to their corresponding exact paths.

- [ ] **Step 4: Inspect all five assets visually**

Reject and regenerate once if an asset contains text, a logo, monogram, signature hardware, recognizable exact product construction, inconsistent background/crop, or a non-bag object. Confirm the silhouettes are distinct and share consistent scale and visual weight.

- [ ] **Step 5: Correct inconsistent outputs through image generation**

If any approved output differs in dimensions or falls outside the `1.4`–`1.8` landscape ratio, use the image-generation tool to regenerate that icon with the same prompt and the explicit instruction `match the dimensions, framing, and canvas ratio of the approved tote icon`. Do not resize, crop, or redraw the asset with Python or another image-editing tool.

- [ ] **Step 6: Run the focused test and verify GREEN**

Run:

```bash
python -m unittest tests.test_data.DataTests.test_generic_collection_icon_suite_is_complete_and_consistent -v
```

Expected: PASS with five readable, same-size landscape PNG files at least 1200 pixels wide.

- [ ] **Step 7: Commit the icon suite**

```bash
git add assets/collection-icons tests/test_data.py
git commit -m "feat: add generic collection icon suite"
```

---

### Task 3: Enforce the hero contract and migrate collection data

**Files:**
- Modify: `scripts/validate.py:30-50,150-190,394-429`
- Modify: `tests/test_data.py:85-108,166-175`
- Modify: `data/bag_families.json`
- Modify when the audit finds qualifying media: `data/media.json`
- Modify when the audit finds qualifying media: `data/evidence.json`
- Create when its audit row qualifies: `media/evidence/balmain-anthem-reddit.jpg`
- Create when its audit row qualifies: `media/evidence/ferragamo-hug-soft-reddit.jpg`
- Create when its audit row qualifies: `media/evidence/ysl-loulou-reddit.jpg`
- Create when its audit row qualifies: `media/evidence/celine-new-luggage-reddit.jpg`
- Create when its audit row qualifies: `media/evidence/bv-barbara-tote-reddit.jpg`
- Create when its audit row qualifies: `media/evidence/balenciaga-rodeo-reddit.jpg`
- Create when its audit row qualifies: `media/evidence/chanel-slim-vanity-reddit.jpg`

**Interfaces:**
- Produces: `HERO_ICON_PATHS: dict[str, str]` and `validate_collection_heroes(families, media_rows, root, validator) -> None`.
- Consumes: Task 1 audit decisions and Task 2 icon assets.

- [ ] **Step 1: Write failing validator unit tests**

Add tests for a focused helper:

```python
from validate import Validator, validate_collection_heroes

def hero_errors(families, media=()):
    validator = Validator()
    validate_collection_heroes(families, list(media), ROOT, validator)
    return validator.errors

def test_collection_hero_contract_rejects_missing_duplicate_and_unknown_heroes(self):
    base = {"id": "bag-family-test", "publication_status": "research_queue"}
    self.assertTrue(hero_errors([base]))
    self.assertTrue(hero_errors([{**base, "tile_media_id": "media-test", "hero_icon": "tote"}]))
    self.assertTrue(hero_errors([{**base, "hero_icon": "bucket"}]))

def test_published_collection_cannot_use_generic_icon(self):
    row = {"id": "bag-family-test", "publication_status": "published", "hero_icon": "tote"}
    self.assertTrue(hero_errors([row]))
```

Update the existing collection test to require every current row to satisfy XOR:

```python
self.assertTrue(all(bool(row.get("tile_media_id")) ^ bool(row.get("hero_icon")) for row in families))
self.assertTrue(all(row["publication_status"] == "research_queue" for row in queued.values()))
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
python -m unittest tests.test_data.DataTests.test_collection_hero_contract_rejects_missing_duplicate_and_unknown_heroes tests.test_data.DataTests.test_published_collection_cannot_use_generic_icon tests.test_data.DataTests.test_research_queue_contains_new_public_collection_leads -v
```

Expected: FAIL because `validate_collection_heroes` is absent and research rows have no hero field.

- [ ] **Step 3: Implement the minimal hero validator**

Add:

```python
HERO_ICON_PATHS = {
    "tote": "assets/collection-icons/tote.png",
    "shoulder-flap": "assets/collection-icons/shoulder-flap.png",
    "top-handle": "assets/collection-icons/top-handle.png",
    "hobo": "assets/collection-icons/hobo.png",
    "vanity": "assets/collection-icons/vanity.png",
}

def validate_collection_heroes(families, media_rows, root, validator):
    target_ids = {row["id"] for row in media_rows if row.get("usage_scope") == "target_tile"}
    referenced_tiles = []
    for index, family in enumerate(families):
        where = f"bag_families[{index}]"
        tile_id = family.get("tile_media_id")
        icon = family.get("hero_icon")
        if bool(tile_id) == bool(icon):
            validator.error(f"{where}: exactly one of tile_media_id or hero_icon is required")
        if icon and icon not in HERO_ICON_PATHS:
            validator.error(f"{where}: invalid hero_icon {icon}")
        if icon and not (root / HERO_ICON_PATHS[icon]).is_file():
            validator.error(f"{where}: missing hero icon asset {HERO_ICON_PATHS[icon]}")
        if family.get("publication_status") == "published" and icon:
            validator.error(f"{where}: published collection requires receipt-linked media")
        if tile_id:
            referenced_tiles.append(tile_id)
    if len(referenced_tiles) != len(set(referenced_tiles)):
        validator.error("bag_families.json: collection tile_media_id values must be unique")
    if set(referenced_tiles) != target_ids:
        validator.error("bag_families.json: collection media heroes must exactly match target_tile media records")
```

Call the helper after loading family/media rows. Replace the published-only tile-set comparison with this helper. Keep the detailed source/evidence validation, but run it for every collection with `tile_media_id`, regardless of publication status.

- [ ] **Step 4: Apply Task 1 audit decisions to the seven collections**

For each audit row with `qualifying_media: no`, add its exact fallback `hero_icon` from Task 1 and leave `tile_media_id: null` removed or absent.

For each audit row with `qualifying_media: yes`:

1. Download the audited direct asset into the exact collection path listed in the Task 3 file list.
2. Confirm it is a readable JPEG and record actual width, height, SHA-256, and `removal_checked_at: 2026-08-09`.
3. Add the corresponding exact media ID: `media-balmain-anthem-reddit`, `media-ferragamo-hug-soft-reddit`, `media-ysl-loulou-reddit`, `media-celine-new-luggage-reddit`, `media-bv-barbara-tote-reddit`, `media-balenciaga-rodeo-reddit`, or `media-chanel-slim-vanity-reddit`.
4. Set `usage_scope: target_tile` and link the exact audited evidence ID.
5. Add that media ID exactly once to the evidence row's `media_ids`.
6. Set the collection's `tile_media_id` and keep `hero_icon` absent.
7. Set `evidence_coverage.image_ready: true` only for a qualifying archived media hero; generic icons do not change evidence readiness.

Do not change any of the seven `publication_status: research_queue` values.

- [ ] **Step 5: Prevent generic assets from entering evidence data**

Add this assertion:

```python
icon_prefix = "assets/collection-icons/"
self.assertTrue(all(not row["path"].startswith(icon_prefix) for row in load("media")))
self.assertNotIn(icon_prefix, json.dumps(load("evidence")))
```

- [ ] **Step 6: Run focused tests and validator and verify GREEN**

Run:

```bash
python -m unittest tests.test_data -v
python scripts/validate.py
```

Expected: all data tests pass; validator reports no missing, duplicate, unknown, or unlinked heroes.

- [ ] **Step 7: Commit the data contract and migration**

```bash
git add scripts/validate.py tests/test_data.py data/bag_families.json data/media.json data/evidence.json media/evidence
git commit -m "feat: require a hero for every collection"
```

---

### Task 4: Render sourced and generic heroes without misleading provenance

**Files:**
- Modify: `assets/app.js:261-270`
- Modify: `assets/styles.css:357-373,412-415`
- Modify: `tests/test_site.py:74-80`

**Interfaces:**
- Produces: `heroIconType(family) -> string`, `heroIconPath(family) -> string`, and `genericHeroMarkup(family, detail, hiddenFallback) -> string`.
- Consumes: collection `tile_media_id`, optional `hero_icon`, category, and Task 2 icon assets.

- [ ] **Step 1: Write the failing UI contract test**

Replace the empty-media expectation with explicit generic/source behavior:

```python
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
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
python -m unittest tests.test_site.SiteContractTests.test_collection_heroes_distinguish_sources_from_generic_fallbacks -v
```

Expected: FAIL because generic hero rendering and the stacked fallback do not exist.

- [ ] **Step 3: Add icon maps and generic markup**

Add:

```javascript
const heroIconPaths = {
  "tote": "assets/collection-icons/tote.png",
  "shoulder-flap": "assets/collection-icons/shoulder-flap.png",
  "top-handle": "assets/collection-icons/top-handle.png",
  "hobo": "assets/collection-icons/hobo.png",
  "vanity": "assets/collection-icons/vanity.png",
};

const categoryHeroIcons = {
  "tote": "tote",
  "shoulder-bag": "shoulder-flap",
  "top-handle": "top-handle",
  "hobo": "hobo",
  "vanity": "vanity",
};

function heroIconType(family) {
  return family.hero_icon || categoryHeroIcons[family.category] || "tote";
}

function heroIconPath(family) {
  return heroIconPaths[heroIconType(family)] || heroIconPaths.tote;
}
```

`genericHeroMarkup` must render a non-linking `<div class="bag-tile generic-hero">`, the local icon, `Generic collection illustration`, and an alt string derived from the icon label plus brand/model. When `hiddenFallback` is true, add `aria-hidden="true"` until a media error reveals it.

- [ ] **Step 4: Stack sourced media over the generic fallback**

Change `renderFamilyTile` so:

- no media returns only `genericHeroMarkup(...)`;
- media returns `<div class="hero-stack">` containing a hidden generic fallback followed by the existing source `<a>`;
- the image `onerror` adds `media-unavailable` to the source link and removes `aria-hidden` from the sibling generic fallback;
- successful media keeps its source link, attribution, and `Reddit photo`/`Imgur photo` label.

- [ ] **Step 5: Add complete-frame CSS**

Implement these behaviors:

```css
.hero-stack { position: relative; aspect-ratio: 16 / 10; overflow: hidden; background: #efe4d6; }
.hero-stack > .bag-tile { position: absolute; inset: 0; }
.generic-hero { display: block; color: var(--brown); background: #efe4d6; }
.generic-hero img { width: 100%; height: 100%; object-fit: cover; }
.generic-hero .bag-tile-source { color: var(--brown-deep); text-shadow: none; }
.bag-tile.media-unavailable { display: none; }
```

Keep `16 / 10` on Catalog and Collection Details. Disable hover zoom for `.generic-hero`.

- [ ] **Step 6: Run focused and complete site tests**

Run:

```bash
python -m unittest tests.test_site -v
pnpm test
```

Expected: all site, frontend-behavior, and Worker tests pass.

- [ ] **Step 7: Commit the rendering change**

```bash
git add assets/app.js assets/styles.css tests/test_site.py
git commit -m "feat: render complete collection heroes"
```

---

### Task 5: Make the hero requirement visible to contributors

**Files:**
- Modify: `.github/ISSUE_TEMPLATE/suggest-a-bag.yml`
- Modify: `CONTRIBUTING.md`
- Modify: `tests/test_site.py`

**Interfaces:**
- Produces: required source/fallback information for every proposed new collection.

- [ ] **Step 1: Write the failing contribution-contract test**

Add:

```python
def test_new_collection_template_requires_a_hero_path(self):
    template = (ROOT / ".github" / "ISSUE_TEMPLATE" / "suggest-a-bag.yml").read_text(encoding="utf-8")
    self.assertIn("Reddit or Imgur hero source", template)
    self.assertIn("Generic fallback bag type", template)
    self.assertIn("tote, shoulder/flap, top-handle, hobo, or vanity", template)
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
python -m unittest tests.test_site.SiteContractTests.test_new_collection_template_requires_a_hero_path -v
```

Expected: FAIL because the contribution template lacks hero inputs.

- [ ] **Step 3: Add the source and fallback fields**

Add an optional `Reddit or Imgur hero source` URL field limited by description to public Reddit/Imgur. Add a required `Generic fallback bag type` dropdown with `tote`, `shoulder/flap`, `top-handle`, `hobo`, and `vanity`. Explain that the fallback is used only when no qualifying community image exists.

- [ ] **Step 4: Document the invariant**

In `CONTRIBUTING.md`, state that a new collection cannot be added without a hero path: qualifying receipt-linked Reddit/Imgur media first, otherwise an approved generic bag-type illustration. Reiterate that generic artwork is not evidence.

- [ ] **Step 5: Run the focused test and verify GREEN**

Run:

```bash
python -m unittest tests.test_site.SiteContractTests.test_new_collection_template_requires_a_hero_path -v
```

Expected: PASS.

- [ ] **Step 6: Commit contributor guidance**

```bash
git add .github/ISSUE_TEMPLATE/suggest-a-bag.yml CONTRIBUTING.md tests/test_site.py
git commit -m "docs: require hero guidance for new collections"
```

---

### Task 6: Verify, publish, and confirm production

**Files:**
- Verify: all changed files
- Create: `qa-artifacts/collection-heroes-desktop.png`
- Create: `qa-artifacts/collection-hero-mobile.png`

**Interfaces:**
- Consumes: complete implementation from Tasks 1-5.
- Produces: green local checks, browser evidence, pull request, and matching live release SHA markers.

- [ ] **Step 1: Run the complete local release checks**

Run:

```bash
python scripts/validate.py
python scripts/score.py --check
python -m unittest discover -s tests -v
pnpm test
pnpm exec wrangler deploy --dry-run --config worker/wrangler.jsonc
git lfs fsck
git diff --check
```

Expected: every command exits 0; no validation, test, bundle, LFS, or whitespace failures.

- [ ] **Step 2: Run desktop browser QA**

Serve the repository through its existing local server. Verify all 19 Catalog cards have a visible hero, stable card height, no broken image, and correct source/generic labeling. Confirm generic heroes are not clickable and sourced heroes open their public receipt. Capture `qa-artifacts/collection-heroes-desktop.png`.

- [ ] **Step 3: Run mobile browser QA**

At a mobile viewport, verify no horizontal overflow, complete 16:10 hero frames, readable generic labels, and a Collection Details hero for at least one generic icon. Capture `qa-artifacts/collection-hero-mobile.png`.

- [ ] **Step 4: Verify runtime media failure fallback**

Temporarily intercept or alter one media request in the browser without editing committed data. Confirm the sourced link disappears, the generic illustration appears, its accessible fallback is revealed, and layout position does not jump. Restore normal network behavior before continuing.

- [ ] **Step 5: Review final scope and commit any QA-only fixes**

Run:

```bash
git status -sb
git diff --stat origin/main...HEAD
git diff --check origin/main...HEAD
```

Expected: only hero assets, hero data/validation/rendering, source audit, contributor guidance, tests, and approved QA artifacts are in scope.

- [ ] **Step 6: Push and open a pull request**

```bash
git push -u origin codex/collection-hero-images
```

Open a ready pull request to `main` summarizing the hero invariant, source audit results, generic icon policy, source/generic UI distinction, and full verification results.

- [ ] **Step 7: Merge only after pull-request validation passes**

Confirm the PR validation job passes before merging the exact tested head SHA. Do not bypass or dismiss failed checks.

- [ ] **Step 8: Verify the live release**

Wait for the main release workflow to deploy Worker first and Pages second. Confirm both:

```text
https://dusd24.github.io/og-rep-hub/build-meta.json
https://og-rep-hub-issue-intake.og-rep-hub.workers.dev/health
```

report the merged SHA. Then load the production Catalog and verify every collection has a hero visual with correct source/generic behavior.
