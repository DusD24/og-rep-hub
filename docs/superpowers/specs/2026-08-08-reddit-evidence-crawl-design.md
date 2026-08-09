# Reddit Evidence Crawl Design

**Date:** 2026-08-08  
**Status:** Approved working design for the active catalog-expansion goal

## Goal

Expand OG Rep Hub’s public research corpus beyond the current two-source baseline for most launch families, incorporate `r/RepCulture_Bags`, discover additional public rep communities from subreddit navigation, and add source-supported bag collections without exposing private contact, payment, address, or buyer-conversation material.

## Current context

The catalog is a dependency-free static site backed by normalized JSON records for families, exact variants, sellers, factories, offerings, evidence, media, contacts, outreach, rankings, and research notes. The existing evidence model already separates seller evidence from factory/batch evidence and exact bag variants, but the current scraper surface is manual and the launch validator assumes 12 published families and 38 evidence records.

The initial crawl seeds four public communities:

- `r/RealRepLadies`
- `r/RepTherapy`
- `r/RepLadiesWorld`
- `r/RepCulture_Bags`

The crawler may discover additional subreddit names only from public sidebar/wiki navigation links. Discovery is bounded by an explicit allowlist/queue and a configurable maximum so a malformed page cannot cause an unbounded crawl.

## Source-informed fields

The crawl preserves enough public context to support later normalization:

- subreddit, post/comment ID, public URL, author, publication date, title, flair, and capture timestamp;
- evidence lane: review, long-term wear, PSP/QC, auth comparison, factory comparison, seller context, collection, W2C, discussion, or other;
- bag terms and exact-variant clues: brand, model, size, pattern, colorway, material, hardware, dimensions, and factory/batch names when publicly stated;
- seller-service fields: fulfillment/timeline, communication, QC transparency, shipping, and incentive/promotion disclosure;
- product observations: positive observations, negative observations, wear, construction/materials, fit/capacity, and unresolved questions;
- media URLs and post provenance without downloading or publishing media until a separate attribution/removal check passes.

These fields mirror the public RepCulture_Bags review/QC guides and the RepTherapy review template. RepTherapy’s public wiki also exposes a glossary for terms such as PSP, QC, GL, RL, W2C, and PoP. Community guidance is treated as field-discovery guidance, not as a catalog endorsement.

## Architecture

### 1. Public source registry

Create `data/research_sources.json` as a safe, committed configuration file. Each source records its subreddit name, public landing URL, wiki/sidebar paths to inspect, search terms, and whether public comments are included. It contains no seller contact values or captured post text.

The initial registry includes the four seed subreddits and a search vocabulary covering `review`, `QC`, `PSP`, `haul`, `receipt`, `wear`, `seller`, `factory`, and the current family aliases. Subreddit links discovered from public wiki/sidebar HTML enter a bounded discovery queue and are recorded as source metadata only after the URL passes the subreddit allowlist check.

### 2. Local, resumable captures

Create `scripts/scrape_reddit.py`. It uses Python’s standard library HTTP client, a descriptive user agent, retries with bounded backoff, a configurable delay, and public Reddit JSON/HTML endpoints. It fetches:

1. subreddit landing/about/sidebar pages;
2. public wiki index and linked wiki pages;
3. search result pages with pagination;
4. individual post metadata and public comment trees for high-signal posts.

The run writes to `local-private/research-runs/<run-id>/`, which is already ignored by Git:

- `manifest.json` tracks source, endpoint, cursor, status, retry count, and last successful capture;
- `captures.jsonl` stores deduplicated, sanitized records keyed by post/comment ID;
- `candidates.json` stores safe extraction candidates and unresolved fields;
- `run-summary.json` records counts, errors, discovered subreddits, and query coverage.

The scraper supports bounded single runs and a long-running overnight mode. A second invocation resumes from the manifest and skips already captured IDs. Network failures are recorded per endpoint and do not discard successful captures from other communities.

### 3. Sanitization and public research inbox

The capture layer redacts phone numbers, email addresses, payment/account references, addresses, WhatsApp/Telegram contact URLs, private-message language, credentials, and secret-like tokens before writing any local capture. It retains the fact that a source contained a contact or payment field through a boolean flag, not the value.

The candidate layer keeps only public-source metadata, short redacted excerpts, extracted bag/seller/factory terms, heuristic evidence type, and a review status. It never promotes an automated inference directly into `data/evidence.json` or `data/contacts.json`.

### 4. Manual normalization boundary

High-signal candidates are normalized into the existing public records only after a review pass confirms:

- a public Reddit URL, author, subreddit, and date;
- the evidence type is accurate;
- exact variant details are not conflated across size, pattern, colorway, or batch;
- seller and factory names remain separate and are attributed as reported;
- promotional/incentive disclosure and material uncertainty are preserved;
- no private conversation, payment data, address, actual reply, or unverified allegation is copied;
- media has a public post URL, attribution, capture date, hash, dimensions, alt text, and removal path before it becomes a site tile.

Listings remain advertising evidence only. Historical purchases do not establish current availability, and a repeated author counts once for independent-source coverage.

### 5. Collection expansion

New bag collections are first represented as candidates with public source links and exact-variant clues. A candidate can become a published family when it has a source trail strong enough to explain the family, at least two independent authors for a launch-quality record, and a distinct source-backed representative tile. Candidate-only discoveries remain in the research queue and do not receive seller or quality rankings.

The validator and site are changed from fixed launch counts to data-derived counts while retaining the publication gates for every published family. This permits the 12 existing families plus newly supported collections without weakening existing evidence and media invariants.

## Site behavior

The Research view gains a dated crawl summary showing communities checked, wiki/sidebar status, search terms, captured posts/comments, candidate leads, and errors. Candidate collections and unnormalized leads remain visibly labeled as research queue material. Published family files continue to show source-linked receipts first, exact variants separately, and research gaps without turning evidence volume into a seller verdict.

## Error handling and safety

- Respect public endpoints with a configurable delay and bounded retries.
- Keep going when one wiki, search query, or post is unavailable.
- Treat disabled wikis and empty sidebars as recorded source states, not failures that require guessing.
- Reject non-Reddit links for normalized Reddit evidence.
- Redact sensitive patterns before persistence and run the existing public-data validator against every normalized change.
- Preserve conflicting public observations rather than collapsing them into a single conclusion.
- Never send outreach messages, contact sellers, or publish private-source-only information.

## Testing and verification

Tests will cover the crawler as pure behavior plus a fixture-backed transport:

- endpoint construction and subreddit-link discovery;
- pagination and manifest resume behavior;
- retry/error isolation;
- sanitization of contact, payment, address, private-message, and secret-like content;
- evidence-lane classification and safe candidate extraction;
- no direct candidate-to-public-record promotion;
- dynamic family/evidence/media count validation;
- existing 34 tests plus the full normalized-data and site contract suite.

The overnight run is verified with its manifest and run summary, then the selected public data is verified with `scripts/validate.py`, `scripts/score.py --check`, `python3 -m unittest discover -s tests -v`, and a local HTTP smoke test of the catalog routes.

## Out of scope

- authenticated Reddit access, private communities, private messages, or moderator-only pages;
- automated quality/authentication verdicts;
- public publication of phone numbers, payment methods/details, addresses, buyer conversations, or actual comment replies;
- automatic seller outreach or purchase facilitation;
- downloading or publishing every discovered image.

