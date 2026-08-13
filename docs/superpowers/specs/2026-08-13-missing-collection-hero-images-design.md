# Missing Collection Hero Images Design

**Date:** 2026-08-13  
**Status:** Approved design

## Goal

Backfill the three research-queue collections that currently have only generic
category icons: Chanel 25, Hermès Kelly 28, and Dior Saddle. Each collection
should receive one privacy-safe, locally archived hero photograph when a
qualifying public image can be tied to its existing normalized Reddit evidence.

The work must not alter publication status, evidence counts, variant claims,
factory attribution, ranking, or the raw crawl artifacts.

## Approaches considered

1. **Receipt-linked community photo (selected).** Use a personal or in-hand
   image from an existing normalized Reddit review, archive it under
   `media/evidence/`, compute its SHA-256 and dimensions, add the existing
   media provenance fields, link the media ID exactly once from the evidence
   row, and set the family's `tile_media_id`.
2. **Keep the generic icon.** This is safe and requires no new asset handling,
   but does not satisfy the requested image backfill and leaves the collection
   without a sourced hero.
3. **Generate replacement artwork.** This would avoid provenance work, but a
   generated illustration is not evidence and would misrepresent the request
   for a hashed community hero, so it is out of scope.

## Source decisions

- Chanel 25: prefer the review author's personal-photo frame from
  `ev-crawl-rrl-chanel-25-1qy3dlq`, not the linked factory or authentication
  comparison frames.
- Dior Saddle: prefer the review author's personal-photo frame from
  `ev-crawl-rrl-dior-saddle-1gqvspa`, not its factory, PSP, or authentication
  frames.
- Hermès Kelly 28: use the exact Kelly 28 review
  `ev-crawl-rrl-hermes-kelly-1sl383j`, whose public post supplies a clean,
  front-facing in-hand frame. The separate HSS Kelly capture was inspected but
  its available frame is packaging rather than a qualifying bag hero.

Only a direct Reddit-media or author-owned Imgur image that passes the existing
  validator's host, provenance, JPEG, privacy, and exact-family checks may be
  archived. No official product photography, seller catalog image, PSP with
  identifying order data, private conversation, payment information, address,
  or unrelated post image may enter the public data graph.

## Data and asset changes

For each qualifying source:

1. Download the public image into `media/evidence/` as a readable JPEG.
2. Record the exact byte hash, dimensions, source URL, post URL, author,
   subreddit, capture date, removal check date, alt text, and evidence ID in
   `data/media.json` with `usage_scope: target_tile`.
3. Add the media ID once to the selected evidence record's `media_ids` list.
4. Replace the collection's `hero_icon` with `tile_media_id` and mark
   `evidence_coverage.image_ready` true.
5. Remove only the stale no-tile-image gap; leave all other research gaps and
   claims unchanged.

The three changes will be applied as one atomic data update. If Kelly has no
qualifying public image, only Chanel 25 and Dior Saddle will be promoted to
`tile_media_id`; Kelly will remain a valid `hero_icon` collection and will be
reported as unresolved rather than receiving a guessed asset.

## Verification

The final state must satisfy:

- every target-tile media path exists, is a JPEG, and matches its SHA-256 and
  declared dimensions;
- every hero media row has exactly one reverse evidence link and exact family
  provenance;
- no duplicate media URL or duplicate evidence media ID is introduced;
- collection hero XOR remains valid and the three families remain
  `research_queue`;
- `python3 scripts/validate.py`, `python3 scripts/score.py --check`, the full
  Python and frontend test suites, `git lfs fsck`, Wrangler dry-run deployment,
  and `git diff --check` pass;
- no `local-private/` artifact is staged.
