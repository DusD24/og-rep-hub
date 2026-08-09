# OG Rep Hub

### Built for one person. Shared with the community.

## Why I built this

I built the first version for my wife. Her research was spread across saved posts, screenshots, and half-remembered seller names, and I wanted to make it easier to compare what people had actually reported. Once it started helping her, I realized the same organizer might help other people in the community too.

So I cleaned it up, made the source trail visible, and shared it.

OG Rep Hub is a free, source-linked organizer for rep-bag research. It brings bag families, exact variants, seller and factory mentions, and the Reddit posts behind each note into one place—without turning community reports into site-level verdicts.

[**Explore the live guide →**](https://dusd24.github.io/og-rep-hub/) · [Contribute research](CONTRIBUTING.md)

[![OG Rep Hub welcome screen](docs/assets/og-rep-hub-preview.png)](https://dusd24.github.io/og-rep-hub/)

## What the guide does

- Organizes research around bag families first, with exact variants underneath.
- Keeps seller and factory names attached to the public posts that reported them.
- Preserves useful observations, limitations, dates, attribution, and media provenance.
- Makes it easy to move from a summary back to the Reddit receipts behind it.
- Shows research gaps instead of filling them with guesses.

The current guide covers a growing set of source-linked collections, including the Neverfull, Classic Flap, Speedy, Margaux, Flamenco, Puzzle, Andiamo, Saint Louis, Birkin 25, Arcadie, Lady Dior, and Book Tote.

## What it does not do

OG Rep Hub does not authenticate goods, guarantee outcomes, claim current stock, broker purchases, or declare a seller or factory “safe,” “trusted,” “best,” or exact. Community signal describes the strength of the research trail—not the certainty of a purchase.

Availability changes quickly. Use the linked dates and sources, then check recent PSPs and reviews before making a decision.

## How the evidence works

Evidence records preserve the source type, author, subreddit, publication date, exact-variant match, seller or factory names as reported, positive observations, negative observations, and media provenance. Repeated posts by one author count as one corroborating source.

Seller reliability uses fulfillment, service and communication, QC transparency, shipping consistency, and payment or risk signals. Bag confidence uses accuracy, construction and materials, exact-variant and availability proof, independent corroboration, and recency. Price is displayed but never scored.

The historical Neverfull campaign remains available as source material while the bag-first guide expands. For the generated research snapshot, see [RESEARCH_SUMMARY.md](RESEARCH_SUMMARY.md).

## Contribute a receipt

Good research gets better when the source trail stays public and specific. You can:

- [Suggest a bag family](https://github.com/DusD24/og-rep-hub/issues/new?template=suggest-a-bag.yml)
- [Submit a public Reddit source](https://github.com/DusD24/og-rep-hub/issues/new?template=submit-reddit-source.yml)
- [Request a correction or media removal](https://github.com/DusD24/og-rep-hub/issues/new?template=correction-or-media-removal.yml)

Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting anything. Public URLs and public post context are welcome; private messages, payment details, addresses, passwords, and unverified contact information are not.

## Run it locally

Python 3.13.7 is pinned in `.python-version`, and the project uses the standard library only.

```sh
python3 scripts/validate.py
python3 scripts/score.py --check
python3 -m unittest discover -s tests -v
python3 scripts/serve.py
```

Then open `http://localhost:8000/`.

The repository is organized into `data/` for normalized public records, `media/evidence/` for attributed research media, `scripts/` for validation and deterministic scoring, `tests/` for the public contracts, and `assets/` for the dependency-free catalog interface.

## Support the project

OG Rep Hub will stay free and public. If this project saved you time or helped you avoid a bad buy, an optional one-time support link will appear here after a payment provider confirms the project is eligible. Support will never unlock research, recommendations, or seller access.

## Public data and attribution

Only public URLs and public post context belong in this repository. Seller and factory names remain attributed to their sources, and public contact rows link back to the community source that listed them. Media records include the post URL, author, subreddit, capture date, hash, alt text, and a removal path.

OG Rep Hub is not affiliated with any brand, seller, factory, subreddit, or Reddit. It is independent public-interest research and does not facilitate purchases.

Released under the [MIT License](LICENSE).
