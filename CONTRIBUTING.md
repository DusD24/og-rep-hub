# Contributing to OG Rep Hub

Thanks for helping make the research trail more useful. The best contributions are public, specific, attributed, and honest about what the source does not establish.

## Choose the right contribution path

- [Suggest a bag](https://github.com/DusD24/og-rep-hub/issues/new?template=suggest-a-bag.yml) when a collection is missing from the guide.
- [Submit a Reddit source](https://github.com/DusD24/og-rep-hub/issues/new?template=submit-reddit-source.yml) for a public review, PSP/QC post, auth comparison, factory comparison, or long-term wear report.
- [Request a correction or media removal](https://github.com/DusD24/og-rep-hub/issues/new?template=correction-or-media-removal.yml) for incorrect attribution, broken provenance, factual corrections, or image-removal requests.

Blank issues are disabled so each request arrives with the context needed for review.

## Public-source requirements

Every research submission must include a public URL. Include as much of the following as the source supports:

- bag brand, collection, exact size, material, pattern, colorway, and hardware;
- source author, subreddit, publication date, and evidence type;
- seller or factory name exactly as the source reports it;
- useful positive and negative observations;
- whether the source is an exact-variant match or related collection context; and
- any uncertainty, contradiction, or missing detail that remains unresolved.

A listing or catalog image can document that something was shown publicly. It cannot, by itself, prove current stock, quality, fulfillment, or a buyer's outcome.

## Privacy and safety

Do not submit:

- private messages or screenshots from private conversations;
- payment details, transaction records, addresses, passwords, or account credentials;
- private or unverified contact information;
- claims about a person's identity that are not part of the public source; or
- copied media without a public post URL and clear provenance.

If a public source contains private details, do not reproduce them. Link the public post and describe only the research-relevant context.

## Attribution and media

Names, adjectives, seller or factory mentions, and conclusions stay attached to the source that made them. A source's wording does not become an OG Rep Hub endorsement.

Media selected for the public guide must have a documented research purpose, public post URL, attribution, capture date, local path, alt text, dimensions, and SHA-256 hash. Removal requests take priority over preserving a tile or screenshot.

## Corrections and removals

Use the correction and media-removal form to identify the affected public URL or collection route, explain the requested change, and provide a public source when one is available. For a media-removal request, identifying the public post and the affected image is enough; do not upload private proof.

## Local checks

Before proposing repository changes, run:

```sh
pnpm install --frozen-lockfile
python3 scripts/validate.py
python3 scripts/score.py --check
python3 -m unittest discover -s tests -v
pnpm test
pnpm exec wrangler deploy --dry-run --config worker/wrangler.jsonc
```

These checks protect the normalized data relationships, deterministic scoring, public-data boundaries, media provenance, and site behavior.

## Research boundaries

OG Rep Hub organizes public reports. It does not authenticate goods, guarantee outcomes, broker purchases, claim current stock, or issue site-level “safe,” “trusted,” “best,” or exactness verdicts about sellers and factories.
