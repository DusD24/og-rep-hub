# Exact Variant Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill every published collection’s exact-variant section in descending evidence-count order, give every accepted variant one policy-compliant hero shot, and commit/push/deploy each completed collection as its own verified checkpoint.

**Architecture:** Keep the existing normalized graph unchanged in shape: variant records live in `data/bags.json`, family membership is declared by `documented_variant_ids` in `data/bag_families.json`, source-to-variant provenance is recorded by adding the exact variant ID to an evidence row’s `bag_ids` in `data/evidence.json`, and each variant hero is linked by `tile_media_id` to `data/media.json`. The existing `familyVariants`, `familyEvidence`, and `renderVariantCards` functions in `assets/app.js` already render these records; this pass is catalog/media normalization, not a UI redesign. Claude stages and visually reviews candidate Reddit media in private manifests; Codex applies only approved media/data rows.

**Tech Stack:** JSON catalog data, Python validation/scoring scripts, local sanitized Reddit captures, Python `unittest`, Node `pnpm test`, Git LFS, and Wrangler dry-run.

## Global Constraints

- Process published families in descending `evidence_coverage.source_count`; start with Chanel 25 (140), Loewe Puzzle (126), Loewe Flamenco (84), Chanel Classic Flap (75), Bottega Veneta Andiamo (62), Dior Lady Dior (52), then continue downward.
- Read full sanitized local captures and the linked public evidence records; do not fetch fresh Reddit pages for this pass.
- Add a variant only when size, model/generation, pattern/material, colorway, or another identity-defining attribute is explicit enough to distinguish it from sibling variants.
- Preserve unresolved fields as `not documented in source`, `unresolved`, or equivalent existing catalog wording; never infer a size, material, color, batch, seller, or factory.
- Link an evidence row to a variant only when that row explicitly supports the exact variant; family-level evidence remains family-level.
- Keep seller/factory names source-reported and use only registered IDs; do not turn a source mention into a normalized attribution.
- Exclude solicitations, generic praise, crossposts, duplicate transactions, private contacts/messages/payment details, and model misattributions.
- Do not open families, change public schema, or alter matcher behavior in this pass.
- Every accepted variant must have exactly one distinct `tile_media_id`, a tracked media file, an allowed direct Reddit-media source URL, matching SHA-256/dimensions, and a private visual-review verdict rejecting official, listing, barcode-tagged, privacy-sensitive, or non-product imagery.
- Reuse an existing policy-compliant media row only when it is the exact variant hero and is not already assigned to another variant; otherwise stage a new candidate with `scripts/backfill_variant_heroes.py`.
- After each collection is verified, commit its public data/media changes, push `main`, wait for the release workflow, and verify the live Pages/Worker SHA before starting the next collection.
- Every batch must be atomic and pass `python3 scripts/validate.py`, `python3 scripts/score.py --check`, `python3 -m unittest discover -s tests -v`, `pnpm test`, `git lfs fsck`, `pnpm exec wrangler deploy --dry-run --config worker/wrangler.jsonc`, and `git diff --check` before any checkpoint.
- Keep Claude’s proposals and raw captures under `local-private/`; never stage that directory.

---

### Task 1: Establish the descending variant-coverage queue

**Files:**
- Read: `data/bag_families.json`, `data/bags.json`, `data/evidence.json`
- Read: `assets/app.js` (`familyVariants`, `familyEvidence`, `renderVariantCards`)
- Create privately: `local-private/research-runs/2026-08-12/variant-coverage-queue.md`

**Interfaces:**
- Consumes: published family source counts and current `documented_variant_ids`.
- Produces: a stable ranked list with family ID, source count, current variant count, and the next audit batch.

- [ ] Run a read-only ranking that sorts by `evidence_coverage.source_count` descending and reports families where `documented_variant_ids` is empty.
- [ ] Record the queue and current baseline in the private report; do not edit public data.
- [ ] Verify that the top empty families are Chanel 25, Loewe Puzzle, Loewe Flamenco, Chanel Classic Flap, Bottega Veneta Andiamo, and Dior Lady Dior.

### Task 2: Audit the first high-coverage families through Claude

**Files:**
- Read: `local-private/research-runs/2026-08-12/captures.jsonl` and the family/evidence/catalog files
- Create privately: `local-private/research-runs/2026-08-12/variant-proposals-chanel25-puzzle.md`
- Create privately: `local-private/research-runs/2026-08-12/variant-proposals-chanel25-puzzle.json`
- Update privately: `local-private/research-runs/2026-08-12/curation-coordination.md`

**Interfaces:**
- Consumes: the exact family IDs `bag-family-chanel-25` and `bag-family-loewe-puzzle`.
- Produces: proposal rows containing stable variant ID, name, size, pattern, colorway, material, hardware, family ID, supporting evidence IDs, and source-grounded notes.

- [ ] Claude reads every full local capture selected for these two families and distinguishes exact variants from family-only mentions.
- [ ] Claude groups synonymous descriptions only when the source itself makes the equivalence clear; retain distinct sizes, generations, materials, colors, and batches.
- [ ] Claude checks every proposed supporting evidence ID against the current public record and records `defer` for ambiguous rows instead of guessing.
- [ ] Claude writes the private proposal and appends a `Claude -> Codex:` completion line without editing public data, settling ledger rows, staging, committing, pushing, or deploying.
- [ ] After variant proposals are accepted, Claude stages and visually reviews one candidate hero per accepted variant in a private manifest, recording direct media URL, SHA-256, dimensions, and a policy-safe verdict without applying it.

### Task 3: Validate and apply one proposal batch atomically

**Files:**
- Modify: `data/bags.json`
- Modify: `data/bag_families.json`
- Modify: `data/evidence.json`
- Test: `tests/test_data.py` and existing repository test suite

**Interfaces:**
- Consumes: a completed private proposal JSON from Task 2.
- Produces: normalized variant records with reverse-linked family and evidence provenance.

- [ ] Check that every proposed variant ID is new, every family ID exists, every evidence ID exists, and every evidence row currently belongs to the family.
- [ ] Check that each variant’s `(size, pattern, colorway)` tuple is unique across all `data/bags.json` rows, using the repository’s existing data-test contract.
- [ ] Add only accepted variant rows to `data/bags.json`, append their IDs to the correct family’s `documented_variant_ids`, and add their IDs to the explicitly supporting evidence rows’ `bag_ids`.
- [ ] Apply only hero manifest rows that match accepted variant IDs; add each media record, set the variant’s `tile_media_id`, and add the media ID to the supporting evidence row’s `media_ids`.
- [ ] Recompute affected family coverage only if the repository’s existing normalization path requires it; do not lower source counts or move family-level receipts.
- [ ] Run the full global verification commands and inspect the diff for privacy, duplicate IDs, incorrect family links, and invented attributions.
- [ ] Commit only the completed collection’s public data/media files, push `main`, wait for the Pages/Worker workflow, and verify its live SHA before moving on.

### Task 4: Drain the queue in descending batches

**Files:**
- Create privately: `local-private/research-runs/2026-08-12/variant-proposals-<batch>.md`
- Create privately: `local-private/research-runs/2026-08-12/variant-proposals-<batch>.json`
- Modify: `data/bags.json`, `data/bag_families.json`, `data/evidence.json` per accepted batch
- Update privately: `local-private/research-runs/2026-08-12/curation-coordination.md`

**Interfaces:**
- Consumes: the ranked queue and the prior batch’s updated catalog.
- Produces: one independently verified batch at a time, preserving stable ordering and exact provenance.

- [ ] Assign Claude the next descending block only after the prior block’s public diff and tests are clean.
- [ ] Use these next blocks unless the current audit proves a family already has complete exact coverage: Flamenco + Classic Flap; Andiamo + Lady Dior; Margaux + Rodeo; then LouLou, Kelly, Birkin, Slim Vanity, Saddle, Le City, Book Tote, and the remaining families.
- [ ] After each batch, compare variant count and exact evidence links before/after; record accepted, deferred, and excluded proposals privately.
- [ ] For each collection checkpoint, assert every accepted variant has one unique hero file/hash/media ID and that every hero is receipt-linked to the exact variant.
- [ ] Stop adding to a family when remaining rows are family-level only, ambiguous, duplicate, or would require an inferred identity.

### Task 5: Final all-collection integrity checkpoint

**Files:**
- Modify: the accepted public data files only
- Read: all private batch reports and `curation-coordination.md`

**Interfaces:**
- Consumes: all accepted variant batches and their verification outputs.
- Produces: a clean local branch ready for the user’s publication decision.

- [ ] Run the complete verification command set against the final catalog.
- [ ] Confirm every published family with a non-empty variant section has reverse-linked variant evidence and no duplicate variant identity tuple.
- [ ] Confirm no `local-private/` path is staged and the working diff contains only intended public data changes.
- [ ] Confirm every published family has a reviewed variant section; if a family has no reliable exact identity, record the evidence-backed reason privately rather than inventing a placeholder variant.
- [ ] Confirm every variant has exactly one live hero, no duplicate tuple/ID/hash/path exists, every hero is receipt-linked, and no private artifact is staged.
- [ ] Verify the live site’s final catalog/media graph and matching Pages/Worker release SHA.
