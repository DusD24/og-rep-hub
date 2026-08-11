# Contributing to OG Rep Hub

Thanks for helping make the research trail more useful. The best contributions are public, specific, attributed, and honest about what the source does not establish.

## Choose the right contribution path

The "Bring a receipt" section on the [Research page](https://dusd24.github.io/og-rep-hub/#research) has an in-page form for each path below. Forms submit anonymously through a Cloudflare Worker and file a public GitHub issue without leaving the site:

- **Suggest a Bag** when a collection is missing from the guide.
- **Submit a Reddit Source** for a public review, PSP/QC post, auth comparison, factory comparison, or long-term wear report.
- **Correction or Media Removal** for incorrect attribution, broken provenance, factual corrections, or image-removal requests.

Each evidence card also has a **Request a receipt update** button for changes tied to a specific receipt.

If you'd rather file directly on GitHub (or JavaScript is unavailable), the same three request types have issue templates: [Suggest a bag](https://github.com/DusD24/og-rep-hub/issues/new?template=suggest-a-bag.yml), [Submit a Reddit source](https://github.com/DusD24/og-rep-hub/issues/new?template=submit-reddit-source.yml), [Request a correction or media removal](https://github.com/DusD24/og-rep-hub/issues/new?template=correction-or-media-removal.yml). Blank issues are disabled so each request arrives with the context needed for review.

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

## Maintainer: the daily evidence loop

Catalog updates come from a nightly local crawl, not from CI. `scripts/daily_crawl.sh`
crawls what is new, ranks it deterministically, and writes a capped review shortlist plus
evidence drafts into `local-private/research-runs/<date>/`. Only six judgment fields per
record need writing by hand; `draft_evidence.py --apply` handles the rest, including the
collection coverage counts `validate.py` cross-checks.

`data/scrape_ledger.json` is committed alongside `data/evidence.json` — it records what
has already been reviewed, so decisions are not re-litigated on the next run. See
[docs/daily-evidence-loop.md](docs/daily-evidence-loop.md).

Running `scripts/scrape_reddit.py` locally is optional and manual (it is not part of CI). It works with no setup; copy `.env.example` to `.env` and set `FIRECRAWL_API_KEY` only if you want it to fall back to Firecrawl when the public Reddit endpoints and the old.reddit.com HTML fallback both fail.

## Research boundaries

OG Rep Hub organizes public reports. It does not authenticate goods, guarantee outcomes, broker purchases, claim current stock, or issue site-level “safe,” “trusted,” “best,” or exactness verdicts about sellers and factories.
