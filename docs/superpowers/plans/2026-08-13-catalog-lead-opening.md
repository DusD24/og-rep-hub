# Catalog Lead Verification and Opening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-verify the existing 2026-08-12 uncatalogued lead pool, stage policy-compliant receipt-linked heroes, and add only the families that pass the project’s evidence, source, author, variant, collision, and hero gates.

**Architecture:** Claude remains the private second reviewer and image-staging auditor. Codex owns the public normalized data transaction: family records, exact variant records, source-linked evidence, media records, and ledger dispositions are changed together only after the private reports identify a lead that clears every gate. Existing families and matcher behavior remain unchanged; a lead that fails any gate stays private and deferred.

**Tech Stack:** JSON normalized data, sanitized local Reddit captures, private Markdown coordination reports, JPEG media with SHA-256 metadata, Python validation/scoring/tests, Git LFS, and Wrangler dry-run verification.

## Global Constraints

- Start from `local-private/research-runs/2026-08-12/new-collection-candidates.json` and its full local sanitized captures; do not launch a new Reddit crawl for this phase.
- Re-count with word-boundary matching, brand proximity, exact-variant separation, distinct-author counting, and same-author duplicate/crosspost exclusion.
- A family may be opened only with at least two independent authors, at least one `RealRepLadies` or `RepTherapy` source, real PSP/QC/in-hand/wear observations, and a policy-compliant hero already identified.
- Use narrow model names: `Chanel WOC`, `Chloe Marcie`, and `Dior D-Joy`; never promote bare `WOC`, `Marcie`, or `Saddle` as a family.
- Preserve exact sizes, materials, colors, patterns, hardware, batches, factories, sellers, dates, and uncertainty exactly as source-reported; never invent seller or factory identities.
- Do not publish solicitations, generic praise, guides, rehomes, listing/catalog images, official product photography, barcode/order tags, private contacts, payment details, addresses, private conversations, or identifying frames.
- Keep raw captures and all Claude reports under `local-private/`; no `local-private/` file may be staged.
- No public family, variant, evidence, media, matcher, or ledger change is allowed until the preceding private report is present and read.

## Candidate Set and Gate Outcomes

The prior counts are hypotheses only and must be replaced by the corrected counts in Claude’s report:

| Lead hypothesis | Narrow public name | Prior author hint |
| --- | --- | ---: |
| Louis Vuitton Keepall | Louis Vuitton Keepall | 57 |
| YSL Niki | YSL Niki | 38 |
| Bottega Veneta Jodie | Bottega Veneta Jodie | 28 |
| Dior D-Joy | Dior D-Joy | 24 |
| Gucci Jackie | Gucci Jackie | 23 |
| Dior Toujours | Dior Toujours | 9 |
| Hermès Evelyne | Hermès Evelyne | 8 |
| Chloe Marcie | Chloe Marcie | 3 |
| Chanel WOC | Chanel WOC | 34 |

The final decision for every lead must be one of `open-ready`, `hero-first`, `thin/hold`, or `collision/defer`. Only `open-ready` rows proceed to the public data transaction; all other rows remain private and eligible for later review.

---

### Task 1: Complete the private consolidated-list re-verification

**Files:**
- Read: `local-private/research-runs/2026-08-12/new-collection-candidates.json`
- Read: full sanitized captures under `local-private/research-runs/2026-08-12/`
- Read: `local-private/research-runs/2026-08-12/catalog-review-134-claude.md` through `catalog-review-153-claude.md`
- Create: `local-private/research-runs/2026-08-12/catalog-lead-reverification-claude.md`
- Modify: `local-private/research-runs/2026-08-12/curation-coordination.md` by appending one completion line only

**Interfaces:**
- Consumes: the deduplicated candidate pool and all full local post captures.
- Produces: one private table for all nine leads with corrected post/author counts, source coverage, exact variant clusters, collision findings, representative private IDs/URLs, and one gate outcome per lead.

- [ ] **Step 1: Confirm the source pool and deduplication baseline**

  Record the current `candidates_in`, `unique_candidates_in`, and `duplicates_collapsed` from `new-collection-candidates.json`. A repeated Reddit `t3_` ID or canonical post URL counts once, while two different posts by the same author remain separate posts but count once toward independent-author coverage.

- [ ] **Step 2: Re-count each lead using the corrected matching rules**

  For each narrow name, record raw matches, qualifying unique posts, distinct authors, qualifying subreddits, same-author duplicate/crosspost exclusions, exact size/material/pattern/colorway clusters, and all material collision terms. Bare `WOC`, bare `Marcie`, and literal-use `Saddle` must be shown separately from the narrow model count.

- [ ] **Step 3: Apply the publication gate**

  Mark `open-ready` only when the corrected count has at least two independent authors, at least one `RealRepLadies` or `RepTherapy` source, at least one substantive public PSP/QC/in-hand/wear observation, and a hero candidate that can pass Task 2. Mark every other lead with the specific failing gate rather than rounding it up.

- [ ] **Step 4: Write and announce the private report**

  Keep URLs and IDs in the private report only. Do not edit public JSON, media, matcher code, or ledger rows. Append a timestamped `Claude: completed ...` line to the coordination file when the report is complete.

---

### Task 2: Stage and visually review heroes for gate-cleared leads

**Files:**
- Read: `local-private/research-runs/2026-08-12/catalog-lead-reverification-claude.md`
- Read: existing public `data/evidence.json`, `data/bags.json`, and `data/media.json`
- Create: `local-private/hero-staging/catalog-leads/` manifests and source images only when the approved private fetch workflow produces them
- Create: `local-private/research-runs/2026-08-12/catalog-hero-readiness-claude.md`
- Modify: `local-private/research-runs/2026-08-12/curation-coordination.md` by appending one completion line only

**Interfaces:**
- Consumes: only leads marked `open-ready` or explicitly `hero-first` in Task 1.
- Produces: a private per-lead hero verdict, exact source/evidence linkage, image hash/path for staged candidates, or a documented conservative rejection.

- [ ] **Step 1: Search existing local media before fetching**

  Reuse an existing image only when its evidence record already identifies the exact lead/variant and the image is not assigned to another family or sibling variant. A media file used by another tile may not be reused as a second family hero.

- [ ] **Step 2: Stage only source-backed candidates**

  When no existing image qualifies, run the repository’s private fetch/staging workflow for the exact source post. Keep downloaded candidates under `local-private/hero-staging/catalog-leads/<lead>/`; do not run `--apply` and do not copy a candidate into tracked `media/evidence/` during this task.

- [ ] **Step 3: Inspect every candidate visually**

  Reject official product photography, retailer or seller catalog imagery, listing photos, barcode/order tags, unrelated products, wrong family/variant, reused sibling photos, and frames containing private or identifying details. Record the rejection reason and source ID privately.

- [ ] **Step 4: Write the readiness report**

  For each lead, report `hero-ready`, `hero-first`, or `no-qualifying-hero`, plus exact family/variant, evidence ID, source URL/ID, staged path/hash when available, and the conservative public recommendation. Append completion to the coordination file without staging or committing private artifacts.

---

### Task 3: Select the public opening set and prepare one atomic normalized data change

**Files:**
- Read: the two private Claude reports from Tasks 1–2
- Modify only if a lead clears every gate: `data/bag_families.json`, `data/bags.json`, `data/evidence.json`, `data/media.json`, `data/offerings.json` when an existing seller/factory/variant relationship is explicitly supported, and `data/scrape_ledger.json`
- Create tracked JPEGs only from the approved private hero manifest: `media/evidence/<stable-source-backed-name>.jpg`

**Interfaces:**
- Consumes: corrected counts, exact source IDs, full post captures, and an approved hero manifest.
- Produces: one public family graph per selected lead, with all reverse links valid and no public record for a lead that failed any gate.

- [ ] **Step 1: Freeze the decision table before editing JSON**

  List every lead as `open`, `hold`, or `defer`, with the exact failed gate for non-open rows. The open list must be the intersection of Task 1 `open-ready` and Task 2 `hero-ready`; if that intersection is empty, make no public data change and continue private catalog research.

- [ ] **Step 2: Create stable family IDs and narrow slugs only for the open list**

  Use these deterministic family IDs when the corresponding lead is approved: `bag-family-louis-vuitton-keepall`, `bag-family-ysl-niki`, `bag-family-bottega-veneta-jodie`, `bag-family-dior-d-joy`, `bag-family-gucci-jackie`, `bag-family-dior-toujours`, `bag-family-hermes-evelyne`, `bag-family-chloe-marcie`, and `bag-family-chanel-woc`. Use matching lowercase slugs with the same brand/model boundary. Do not create IDs for held or deferred leads.

- [ ] **Step 3: Add exact variants from the qualifying captures**

  Add one `data/bags.json` row per source-supported size/pattern/colorway/material combination. Use deterministic IDs formed from the approved family token plus normalized exact attributes, preserve `unknown` only when the source leaves the attribute unresolved, and never merge two sizes, materials, patterns, or colorways to reduce row count. Add offerings only when their seller/factory IDs already exist or are independently normalized from public evidence; leave uncertain entities unattributed.

- [ ] **Step 4: Normalize qualifying evidence and reverse links**

  Create evidence records only for substantive public observations selected from full captures. Every record must retain its original Reddit URL, author, subreddit, publication-date precision, source-reported language, exact product match, positive/negative observations, and media IDs. Add each evidence ID to its family and exact variant references, and update `data/scrape_ledger.json` only for the reviewed source posts. No private URL, contact, payment, or raw post text may enter tracked data.

- [ ] **Step 5: Register the approved hero atomically**

  Verify each staged JPEG’s file type, dimensions, SHA-256, and visual content before copying it to tracked `media/evidence/`. Add one unique `target_tile` media row per family, link it exactly once from the source evidence row, set the family `tile_media_id`, remove any `hero_icon` fallback, and set `evidence_coverage.image_ready` to `true`. Keep every public hero tied to the exact receipt and variant it depicts.

- [ ] **Step 6: Commit the public data transaction**

  Stage only the intended `data/` files and approved `media/evidence/` JPEGs. Confirm `git diff --cached --name-only` contains no `local-private/` path, then commit the family opening as one coherent data/media change.

---

### Task 4: Verify the opening and queue independent post-apply QA

**Files:**
- Read: the resulting public data/media/ledger files and the private manifests
- Create: `local-private/research-runs/2026-08-12/catalog-opening-postapply-qa-claude.md` through the coordination lane

**Interfaces:**
- Consumes: the public commit from Task 3.
- Produces: independent confirmation that every opened family, variant, evidence reverse link, hero hash, and ledger disposition is correct.

- [ ] **Step 1: Run focused graph checks**

  Confirm every opened family has a unique slug and tile, exactly one hero path, at least two independent authors, at least one `RealRepLadies` or `RepTherapy` evidence row, no bare collision term, and only source-backed exact variants. Confirm no duplicate evidence URL or repeated `t3_` ID entered the public graph.

- [ ] **Step 2: Run the full repository checks**

  ```bash
  python3 scripts/validate.py
  python3 scripts/score.py --check
  python3 -m unittest discover -s tests -v
  pnpm test
  git lfs fsck
  pnpm exec wrangler deploy --dry-run --config worker/wrangler.jsonc
  git diff --check
  ```

- [ ] **Step 3: Assign Claude read-only post-apply QA**

  Queue a `Codex -> Claude:` task naming the exact commit and opened family IDs. Claude must inspect the final public graph and staged hero files, report any reversal or privacy leak, and must not edit data, settle rows, stage, commit, or publish.

- [ ] **Step 4: Handoff only after QA**

  If QA is clean, report the exact local commit and whether the public release is ready. Do not push or deploy this catalog-opening change until the user explicitly requests publication.
