# Missing Collection Hero Images Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one hashed, receipt-linked community hero image to each of the three research-queue collections that currently use only a generic icon.

**Architecture:** Reuse the existing `data/media.json` and evidence reverse-link graph. Archive the selected public Reddit/Imgur JPEGs without transformation, verify their bytes and dimensions, then update the three family records and selected evidence rows in one normalized data change. The existing hero validator remains the contract; no schema or UI changes are needed.

**Tech Stack:** JSON normalized data, JPEG evidence assets, Python `unittest`, repository validator/scorer, Git LFS, Wrangler dry run.

## Global Constraints

- Hero photography may come only from public Reddit or Imgur sources linked to a normalized receipt for the exact collection.
- Official product photography, retailer images, seller catalog images, unrelated posts, and generated art are forbidden.
- Every collection must define exactly one of `tile_media_id` or `hero_icon`.
- Preserve exact variants, sizes, materials, colors, hardware, factories, sellers, and publication status; do not infer new entities.
- Use only privacy-safe public frames; do not publish private contacts, payment data, addresses, private conversations, or identifying order information.
- Keep raw crawl artifacts under `local-private/` unchanged and unstaged.
- Do not add a new family, media hero schema, UI field, or publication-status change.
- Do not push, open a PR, deploy, or modify the remote repository.

---

### Task 1: Add the source audit and regression test

**Files:**
- Create: `docs/research/collection-hero-source-audit-2026-08-13.md`
- Modify: `tests/test_data.py`

**Interfaces:**
- Consumes: the three normalized evidence IDs and their exact Reddit post URLs.
- Produces: a public-safe source decision record and a focused test that locks the three family/media/evidence mappings.

- [ ] **Step 1: Write the failing focused test**

Add this method to `DataTests` after the existing media-backed collection test:

```python
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
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
python3 -m unittest tests.test_data.DataTests.test_missing_collection_heroes_are_receipt_linked -v
```

Expected: FAIL because the three families do not yet have the expected `tile_media_id` or media rows.

- [ ] **Step 3: Record the exact public source decisions**

Create the audit table with these rows and no private details:

| Collection | Evidence | Direct image URL | Public album/post provenance | Decision |
| --- | --- | --- | --- | --- |
| Chanel 25 mini metallic silver | `ev-crawl-rrl-chanel-25-1qy3dlq` | `https://i.imgur.com/PqQeG1J.jpeg` | `https://imgur.com/a/EK8zSva` and `https://www.reddit.com/r/RealRepLadies/comments/1qy3dlq/chanel_25_mini_metallic_silver_review/` | Personal front view; full bag visible; no private or identifying content selected. |
| Hermès Kelly 28 Etoupe Togo | `ev-crawl-rrl-hermes-kelly-1sl383j` | `https://i.redd.it/p8zyfbisf4vg1.jpg` | `https://www.reddit.com/r/RealRepLadies/comments/1sl383j/hermes_kelly_28_togo_leather_etoupe_from_mark/` | Public in-hand front view; exact Kelly 28 review; no private or identifying content selected. |
| Dior Saddle | `ev-crawl-rrl-dior-saddle-1gqvspa` | `https://i.imgur.com/EM1sHAt.jpeg` | `https://imgur.com/a/UIkrjdC` and `https://www.reddit.com/r/RealRepLadies/comments/1gqvspa/matte_black_dior_saddle_review/` | Personal front view; full bag visible; no factory, PSP, authentication, or private frame selected. |

State explicitly that the files are author-posted community media, that only the selected frames are archived, and that all three families remain `research_queue`.

- [ ] **Step 4: Commit the audit and failing-test contract**

```bash
git add docs/research/collection-hero-source-audit-2026-08-13.md tests/test_data.py
git commit -m "test: lock missing collection hero sources"
```

### Task 2: Archive and verify the three JPEG assets

**Files:**
- Create: `media/evidence/chanel-25-reddit.jpg`
- Create: `media/evidence/hermes-kelly-28-reddit.jpg`
- Create: `media/evidence/dior-saddle-reddit.jpg`

**Interfaces:**
- Consumes: the direct URLs in the source audit.
- Produces: byte-preserved local JPEGs with these expected integrity values:

| File | SHA-256 | Dimensions |
| --- | --- | --- |
| `chanel-25-reddit.jpg` | `998d12838db86c6bd64755894198194a69079028ab12f034f5179dee8b8e1b74` | `3213 × 5712` |
| `hermes-kelly-28-reddit.jpg` | `6e5db51b9fad8557fb8a49f86fc4855f68bb4a8e60cf0256893e20a9249f4bc5` | `4284 × 5712` |
| `dior-saddle-reddit.jpg` | `57447811f0634a0215f8cea2a9b4e0d3c24eb2b595b2be6a86c95b908f5b6c15` | `3024 × 4032` |

- [ ] **Step 1: Download to an isolated temporary directory**

Use a task-specific temporary directory, then verify every response before moving any file into the repository:

```bash
hero_tmp=$(mktemp -d)
curl --fail --location --silent --show-error 'https://i.imgur.com/PqQeG1J.jpeg' -o "$hero_tmp/chanel-25-reddit.jpg"
curl --fail --location --silent --show-error 'https://i.redd.it/p8zyfbisf4vg1.jpg' -o "$hero_tmp/hermes-kelly-28-reddit.jpg"
curl --fail --location --silent --show-error 'https://i.imgur.com/EM1sHAt.jpeg' -o "$hero_tmp/dior-saddle-reddit.jpg"
file "$hero_tmp/chanel-25-reddit.jpg" "$hero_tmp/hermes-kelly-28-reddit.jpg" "$hero_tmp/dior-saddle-reddit.jpg"
```

Expected: all three files report JPEG image data. Do not convert, crop, recompress, or attach any other frame.

- [ ] **Step 2: Check exact hashes and dimensions before archiving**

Run:

```bash
OG_REP_HERO_TMP="$hero_tmp" python3 - <<'PY'
import hashlib
import os
import sys
from pathlib import Path
sys.path.insert(0, "scripts")
from validate import jpeg_dimensions

root = Path(os.environ["OG_REP_HERO_TMP"])
expected = {
    "chanel-25-reddit.jpg": ("998d12838db86c6bd64755894198194a69079028ab12f034f5179dee8b8e1b74", (3213, 5712)),
    "hermes-kelly-28-reddit.jpg": ("6e5db51b9fad8557fb8a49f86fc4855f68bb4a8e60cf0256893e20a9249f4bc5", (4284, 5712)),
    "dior-saddle-reddit.jpg": ("57447811f0634a0215f8cea2a9b4e0d3c24eb2b595b2be6a86c95b908f5b6c15", (3024, 4032)),
}
for name, (digest, dimensions) in expected.items():
    path = root / name
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    assert jpeg_dimensions(path) == dimensions
PY
```

Expected: no assertion failures. Move the three verified files into `media/evidence/` only after all three pass.

- [ ] **Step 3: Visually inspect the final selected frames**

Use the local image viewer on all three repository files. Confirm each frame shows the intended exact collection bag, keeps the bag readable in the existing hero crop, and contains no face, address, payment record, private conversation, or unrelated product.

- [ ] **Step 4: Commit the verified binary assets**

```bash
git add media/evidence/chanel-25-reddit.jpg media/evidence/hermes-kelly-28-reddit.jpg media/evidence/dior-saddle-reddit.jpg
git commit -m "assets: archive missing collection hero photos"
```

### Task 3: Wire media, evidence, and collection records atomically

**Files:**
- Modify: `data/media.json`
- Modify: `data/evidence.json`
- Modify: `data/bag_families.json`

**Interfaces:**
- Consumes: the three verified JPEGs, source audit, and the existing validator contract.
- Produces: three unique `target_tile` media rows, three exact reverse evidence links, and three family `tile_media_id` references with no `hero_icon` fallback.

- [ ] **Step 1: Append the three media records**

Add these objects to `data/media.json`:

```json
{
  "id": "media-chanel-25-reddit",
  "path": "media/evidence/chanel-25-reddit.jpg",
  "attribution": "u/irey_yklm via r/RealRepLadies",
  "source_url": "https://i.imgur.com/PqQeG1J.jpeg",
  "album_url": "https://imgur.com/a/EK8zSva",
  "post_url": "https://www.reddit.com/r/RealRepLadies/comments/1qy3dlq/chanel_25_mini_metallic_silver_review/",
  "author": "irey_yklm",
  "subreddit": "RealRepLadies",
  "capture_date": "2026-08-13",
  "removal_checked_at": "2026-08-13",
  "sha256": "998d12838db86c6bd64755894198194a69079028ab12f034f5179dee8b8e1b74",
  "width": 3213,
  "height": 5712,
  "research_purpose": "Receipt-linked community collection-tile image for the Chanel 25 collection.",
  "alt": "Metallic silver Chanel 25 mini bag shown front-on in the Reddit review author's personal photograph.",
  "source_platform": "Reddit",
  "usage_scope": "target_tile",
  "evidence_id": "ev-crawl-rrl-chanel-25-1qy3dlq"
}
```

Use the same field order and values from the table below for the other two IDs:

| ID | Path | Source URL | Attribution | Evidence ID | Dimensions | SHA-256 |
| --- | --- | --- | --- | --- | --- | --- |
| `media-hermes-kelly-28-reddit` | `media/evidence/hermes-kelly-28-reddit.jpg` | `https://i.redd.it/p8zyfbisf4vg1.jpg` | `u/pawelbag via r/RealRepLadies` | `ev-crawl-rrl-hermes-kelly-1sl383j` | `4284 × 5712` | `6e5db51b9fad8557fb8a49f86fc4855f68bb4a8e60cf0256893e20a9249f4bc5` |
| `media-dior-saddle-reddit` | `media/evidence/dior-saddle-reddit.jpg` | `https://i.imgur.com/EM1sHAt.jpeg` | `u/StretchEnough2845 via r/RealRepLadies` | `ev-crawl-rrl-dior-saddle-1gqvspa` | `3024 × 4032` | `57447811f0634a0215f8cea2a9b4e0d3c24eb2b595b2be6a86c95b908f5b6c15` |

Their `research_purpose` must say `Receipt-linked community collection-tile image for the Hermès Kelly 28 collection.` and `... Dior Saddle collection.` respectively. Their `alt` text must describe the visible bag and source context in at least 24 characters, without candidate language.

- [ ] **Step 2: Add exactly one media ID to each evidence row**

Update only these existing `media_ids` arrays:

```json
"ev-crawl-rrl-chanel-25-1qy3dlq": ["media-chanel-25-reddit"]
"ev-crawl-rrl-hermes-kelly-1sl383j": ["media-hermes-kelly-28-reddit"]
"ev-crawl-rrl-dior-saddle-1gqvspa": ["media-dior-saddle-reddit"]
```

Leave every other evidence field and every raw capture unchanged.

- [ ] **Step 3: Replace the three generic heroes with tile media**

For each matching family, set the `tile_media_id` shown below, remove its `hero_icon` key, set `evidence_coverage.image_ready` to `true`, and remove only the stale no-tile-image research-gap sentence:

```text
bag-family-chanel-25  -> media-chanel-25-reddit
bag-family-hermes-kelly -> media-hermes-kelly-28-reddit
bag-family-dior-saddle -> media-dior-saddle-reddit
```

Keep all three `publication_status` values as `research_queue`, preserve all source counts and author counts, and leave unrelated research gaps untouched.

- [ ] **Step 4: Run the focused test and data gates**

Run:

```bash
python3 -m unittest tests.test_data.DataTests.test_missing_collection_heroes_are_receipt_linked -v
python3 scripts/validate.py
python3 scripts/score.py --check
```

Expected: all commands pass; validation must report no missing file, hash mismatch, duplicate reverse link, hero XOR, or stale media-gap error.

- [ ] **Step 5: Commit the normalized data update**

```bash
git add data/media.json data/evidence.json data/bag_families.json
git commit -m "data: add missing collection hero media"
```

### Task 4: Run the full repository verification and handoff

**Files:**
- Read-only verification of all tracked files and repository state.

**Interfaces:**
- Consumes: the three committed asset/data changes.
- Produces: a clean verification report with no private artifacts staged and no remote publication.

- [ ] **Step 1: Run the complete required checks**

Run each command from the repository root:

```bash
python3 scripts/validate.py
python3 scripts/score.py --check
python3 -m unittest discover -s tests -v
pnpm test
git lfs fsck
pnpm exec wrangler deploy --dry-run --config worker/wrangler.jsonc
git diff --check
```

Expected: every command exits 0. A dry-run is the only Wrangler action permitted here.

- [ ] **Step 2: Audit the final diff for privacy and duplicates**

Run:

```bash
git status --short
git diff --cached --name-only
test -z "$(git diff --cached --name-only | rg '^local-private/' || true)"
test -z "$(git ls-files --stage | rg 'local-private/' || true)"
python3 - <<'PY'
import json
from pathlib import Path

root = Path(".")
families = json.loads((root / "data/bag_families.json").read_text())
media = json.loads((root / "data/media.json").read_text())
evidence = json.loads((root / "data/evidence.json").read_text())
assert len([row for row in media if row.get("usage_scope") == "target_tile"]) == len({row["tile_media_id"] for row in families if row.get("tile_media_id")})
assert len({row["source_url"] for row in media}) == len(media)
assert all(len(row["media_ids"]) == len(set(row["media_ids"])) for row in evidence)
PY
```

The `local-private/` checks are repository-state checks: private files may exist locally, but no such path may appear in the index or staged file list. Do not stage or commit any private crawl artifact.

- [ ] **Step 3: Report completion without pushing**

Report the three media IDs, exact source evidence IDs, verification results, and the fact that no push, PR, or deploy occurred. Include the three local asset links and the source audit link.
