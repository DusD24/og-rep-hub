# OG Rep Hub

### Built for one person. Shared with the community.

## Why I built this

I built the first version for my wife. Her research was spread across saved posts, screenshots, and half-remembered seller names, and I wanted to make it easier to compare what people had actually reported. Once it started helping her, I realized the same organizer might help other people in the community too.

So I cleaned it up, made the source trail visible, and shared it.

OG Rep Hub is a free, source-linked organizer for rep-bag research. It brings bag collections, exact variants, seller and factory mentions, and the Reddit posts behind each note into one place—without turning community reports into site-level verdicts.

[**Explore the live guide →**](https://dusd24.github.io/og-rep-hub/) · [Contribute research](CONTRIBUTING.md)

[![OG Rep Hub welcome screen](docs/assets/og-rep-hub-preview.png)](https://dusd24.github.io/og-rep-hub/)

## What the guide does

- Organizes research around bag collections first, with exact variants underneath.
- Keeps seller and factory names attached to the public posts that reported them.
- Preserves useful observations, limitations, dates, attribution, and media provenance.
- Makes it easy to move from a summary back to the Reddit receipts behind it.
- Shows research gaps instead of filling them with guesses.

The current guide covers a growing set of source-linked collections, including the Neverfull, Classic Flap, Speedy, Margaux, Flamenco, Puzzle, Andiamo, Saint Louis, Birkin 25, Arcadie, Lady Dior, and Book Tote. The internal `data/bag_families.json` filename and `family_id` references remain unchanged for backward compatibility.

## What it does not do

OG Rep Hub does not authenticate goods, guarantee outcomes, claim current stock, broker purchases, or declare a seller or factory “safe,” “trusted,” “best,” or exact. Community signal describes the strength of the research trail—not the certainty of a purchase.

Availability changes quickly. Use the linked dates and sources, then check recent PSPs and reviews before making a decision.

## How the evidence works

Evidence records preserve the source type, author, subreddit, publication date, exact-variant match, seller or factory names as reported, positive observations, negative observations, and media provenance. Repeated posts by one author count as one corroborating source.

Seller reliability uses fulfillment, service and communication, QC transparency, shipping consistency, and payment or risk signals. Bag confidence uses accuracy, construction and materials, exact-variant and availability proof, independent corroboration, and recency. Price is displayed but never scored.

The historical Neverfull campaign remains available as source material while the bag-first guide expands. For the generated research snapshot, see [RESEARCH_SUMMARY.md](RESEARCH_SUMMARY.md).

## Contribute a receipt

Good research gets better when the source trail stays public and specific. The "Bring a receipt" section on the live site's Research page has an in-page, anonymous form for each of these:

- Suggest a bag collection
- Submit a public Reddit source
- Request a correction or media removal

Each evidence card also has its own "Request a receipt update" button. All four submit through a Cloudflare Worker straight to a public GitHub issue — no GitHub account needed. See [CONTRIBUTING.md](CONTRIBUTING.md) before submitting anything. Public URLs and public post context are welcome; private messages, payment details, addresses, passwords, and unverified contact information are not.

## Run it locally

Python 3.13.7 is pinned in `.python-version`. Node.js 24 or newer and pnpm 11.20.0 run the receipt-form logic and Worker tests.

```sh
pnpm install --frozen-lockfile
python3 scripts/validate.py
python3 scripts/score.py --check
python3 -m unittest discover -s tests -v
pnpm test
pnpm exec wrangler deploy --dry-run --config worker/wrangler.jsonc
python3 scripts/serve.py
```

Then open `http://localhost:8000/`.

The repository is organized into `data/` for normalized public records, `media/evidence/` for attributed research media, `scripts/` for validation and deterministic scoring, `tests/` for public contracts, `assets/` for the dependency-free catalog interface, and `worker/` for protected anonymous receipt-update intake.

## Support the project

OG Rep Hub will stay free and public. If this project saved you time or helped you avoid a bad buy, an optional one-time support link will appear here after a payment provider confirms the project is eligible. Support will never unlock research, recommendations, or seller access.

## Public data and attribution

Only public URLs and public post context belong in this repository. Seller and factory names remain attributed to their sources, and public contact rows link back to the community source that listed them. Media records include the post URL, author, subreddit, capture date, hash, alt text, and a removal path.

OG Rep Hub is not affiliated with any brand, seller, factory, subreddit, or Reddit. It is independent public-interest research and does not facilitate purchases.

## Submission service and release setup

All four contribution paths — receipt updates, bag suggestions, Reddit source submissions, and correction/media-removal requests — open a branded, anonymous in-page form. Accepted submissions become public GitHub issues; none of the forms collect contact details. The Worker resolves receipt/collection metadata from the bundled canonical dataset instead of trusting browser-supplied metadata, and validates every submitted URL against an HTTPS Reddit/Imgur allowlist. See [worker/README.md](worker/README.md) for the one-time Cloudflare and GitHub configuration.

Pull requests run the Python, browser-logic, Worker, LFS, deterministic-score, validation, and Worker-bundle checks. A `main` release deploys the Worker first and Pages second, then polls the public `build-meta.json` and Worker `/health` markers until both report the merged commit SHA.

## Analytics

The site can optionally load Google Analytics (GA4) to track traffic, since GitHub Pages doesn't provide its own. It ships with none configured. To turn it on, set the `GA_MEASUREMENT_ID` GitHub Actions repository variable (see [worker/README.md](worker/README.md)) to a GA4 measurement id from [analytics.google.com](https://analytics.google.com). Analytics only loads client-side after a visitor accepts the cookie-consent banner; declining or ignoring it keeps the site tracker-free for that visitor.

Released under the [MIT License](LICENSE).
