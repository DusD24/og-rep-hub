# Collection Hero Images Design

**Date:** 2026-08-09  
**Status:** Approved design

## Goal

Every collection in OG Rep Hub must render with a complete hero visual in both the Catalog card and Collection Details view. This applies to published and research-queue collections. No future collection may be added without either qualifying community media or a generic bag-type illustration.

## Source policy

Receipt-linked hero photography is restricted to public Reddit and Imgur sources already permitted by the repository's media policy. Official product photography, retailer images, seller catalog images, and other external materials are not allowed.

The preferred hero source is a privacy-safe Reddit or Imgur image linked to a normalized receipt for that exact collection. Community media keeps its existing source URL, post URL, author, subreddit, capture date, removal-check date, dimensions, hash, alt text, and reverse evidence link.

When no qualifying Reddit or Imgur image exists, the collection uses a locally owned generic illustration. Generic illustrations are presentation assets only: they are not evidence, do not enter `data/media.json`, do not receive source attribution, and do not imply an exact product match.

## Hero data contract

Each collection defines exactly one primary hero source:

- `tile_media_id` references a qualifying record in `data/media.json`; or
- `hero_icon` names an approved generic icon type.

The allowed `hero_icon` values are:

- `tote`
- `shoulder-flap`
- `top-handle`
- `hobo`
- `vanity`

The two fields are mutually exclusive. A collection with neither field is invalid. A collection with both fields is invalid.

Published collections continue to require qualifying community media and therefore must use `tile_media_id`. Research-queue collections may use qualifying media when available or `hero_icon` when no qualifying media can be archived. Adding a hero does not change publication status.

Media records used as collection heroes retain `usage_scope: target_tile`. The validator will compare target-tile media records with all collections that use `tile_media_id`, rather than assuming only published collections may have media heroes.

## Generic icon suite

Create five original raster illustrations under `assets/collection-icons/`, one for each allowed icon type. The illustrations use the site's cream, cognac, espresso, and muted-gold palette with simple editorial linework and subtle paper texture.

The icons must remain intentionally generic:

- no brand names, logos, monograms, or signature patterns;
- no recognizable proprietary clasps, hardware, quilting, or exact construction;
- no text embedded in the artwork;
- no attempt to reproduce a specific collection;
- consistent framing, scale, background, and visual weight across the suite.

The icon only communicates the broad bag type. It must not be presented as a source photo or product reference.

## Rendering behavior

Catalog cards and Collection Details continue to use the existing hero frame and crop proportions.

For community media:

- render the receipt-linked image;
- keep the hero clickable to its public source;
- label it `Reddit photo` or `Imgur photo` with source attribution;
- preserve existing accessible source-link text.

For a generic icon:

- render the mapped local illustration in the same hero frame;
- do not make the image a source link;
- label it `Generic collection illustration`;
- use alt text such as `Generic top-handle bag illustration for Balenciaga Rodeo`;
- retain the research-queue badge and all existing evidence counts.

The generic icon for the collection's broad category also sits behind receipt-linked media as a runtime fallback. If a media file fails to load, the frame remains visually complete and exposes non-source fallback labeling without creating a broken-image state.

## Current collection migration

Audit the seven current research-queue collections:

- Balmain Anthem
- Ferragamo Hug Soft
- Saint Laurent LouLou
- Celine New Luggage
- Bottega Veneta Barbara Tote
- Balenciaga Rodeo
- Chanel Slim Vanity

For each collection, first inspect its existing public Reddit/Imgur receipts for a qualifying image that passes the current privacy, attribution, silhouette, and file-integrity requirements. Archive and link qualifying media using the existing evidence workflow. Assign the closest generic `hero_icon` only when no qualifying community image exists.

## Validation

Repository validation must enforce:

- every collection has exactly one of `tile_media_id` or `hero_icon`;
- `hero_icon` is one of the five approved values;
- published collections still use qualifying receipt-linked media;
- every `tile_media_id` resolves to a unique `target_tile` media record;
- target-tile media records and collection media references match exactly;
- generic icon files exist and are safe local raster assets;
- generic icon paths never appear in evidence or media records;
- research status remains unchanged when a hero is added.

## Error handling

Validation blocks image-less collections before publication. At runtime, a missing or failed community media file reveals the derived generic category icon instead of an empty tile. A missing generic asset is a validation failure and must not ship.

No hero fallback changes evidence counts, source labels, confidence, ranking, publication status, or availability claims.

## Testing and verification

Tests will be written before implementation and will cover:

- all current collections satisfy the exactly-one-hero contract;
- a new collection with neither hero field fails validation;
- a collection with both hero fields fails validation;
- unknown icon types and missing icon assets fail validation;
- published collections cannot substitute a generic icon for community media;
- research collections can use either qualifying media or a generic icon;
- generic assets never appear in `data/media.json` or evidence reverse links;
- the UI renders distinct source-photo and generic-illustration markup;
- failed media loads retain a visually complete generic fallback;
- the seven current research collections remain `research_queue`.

Run the full data validator, deterministic score check, Python tests, browser-logic and Worker tests, Worker dry-run, Git LFS check, and diff check. Visually inspect desktop and mobile Catalog cards plus at least one Collection Details page for each generic icon type, confirming consistent framing, readable labels, no overflow, no broken assets, and no misleading source interaction.

## Release

Commit implementation on `codex/collection-hero-images`, push it, and open a pull request. After merge, the existing release workflow must deploy the Worker and Pages and verify both live SHA markers. Production is complete only when the merged SHA is live and the deployed catalog shows a hero visual for every collection.
