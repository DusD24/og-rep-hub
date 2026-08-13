# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

OG Rep Hub is a free, source-linked static catalog for rep-bag research: it organizes bag collections/variants, seller and factory mentions, and the Reddit posts behind each claim. It does not authenticate goods or declare sellers "safe" — it surfaces the public source trail. Live at https://dusd24.github.io/og-rep-hub/.

## Commands

Toolchain: Python 3.13.7 (pinned in `.python-version`), Node.js 24+, pnpm 11.20.0 (pinned in `package.json`'s `packageManager`).

```sh
pnpm install --frozen-lockfile          # install JS deps (site has no runtime deps; only wrangler + test tooling)
python3 scripts/validate.py             # validate data/*.json: schema, refs, safety constraints, media hashes
python3 scripts/score.py --check        # verify committed rankings.json matches deterministic scoring
python3 scripts/score.py                # regenerate data/rankings.json
python3 -m unittest discover -s tests -v   # Python tests (data, model, scraper, deployment, site)
pnpm test                               # Node tests: frontend behavior (tests/frontend_behavior.test.cjs) + worker (worker/test/worker.test.mjs)
pnpm exec wrangler deploy --dry-run --config worker/wrangler.jsonc   # verify Worker bundles/deploys without publishing
python3 scripts/serve.py                # local dev server, http://localhost:8000/
```

Daily evidence loop (see `docs/daily-evidence-loop.md`):

```sh
scripts/daily_crawl.sh                  # nightly: incremental crawl + triage + drafts
scripts/daily_crawl.sh sweep            # weekly: full search-term backfill
python3 scripts/draft_evidence.py --apply <run-dir>/evidence-drafts.json   # merge reviewed drafts
```

Run a single Python test module: `python3 -m unittest tests.test_data -v` (or `tests.test_model`, `tests.test_scraper`, `tests.test_ledger`, `tests.test_triage`, `tests.test_draft_evidence`, `tests.test_deployment`, `tests.test_site`).

Run a single Node test file directly: `node --test tests/frontend_behavior.test.cjs` or `node --test worker/test/worker.test.mjs`.

Before proposing any change to this repo, run the full local-check sequence from `CONTRIBUTING.md`: `validate.py`, `score.py --check`, the unittest suite, `pnpm test`, and the wrangler dry run.

## Architecture

**Data-first, dependency-free frontend.** All content lives as normalized JSON in `data/` (`bag_families.json`, `bags.json`, `sellers.json`, `factories.json`, `offerings.json`, `evidence.json`, `contacts.json`, `media.json`, `research.json`, `research_sources.json`, `rankings.json`, `outreach.json`, `site_config.json`). `assets/app.js` and `assets/ui-logic.js` (vanilla JS, no framework) render `index.html` directly from these files at request time — there is no build step for the site itself.

**`scripts/model.py` is the shared core**: it loads `data/*.json` and defines the deterministic scoring formulas (`seller_reliability`, `bag_confidence`) used by both `score.py` (generates/checks `data/rankings.json`) and `validate.py`. Scores are weighted sums of fixed metric weights — never hand-edit `rankings.json`; regenerate it with `score.py`.

**`scripts/validate.py`** is the data integrity gate: enforces required fields, cross-file ID references, allowed enums (status, source type, evidence type, contact type), forbidden/sensitive-data keys and patterns (payment info, private messages, credentials), and SHA-256 verification of media files tracked via Git LFS (`media/evidence/*` — see `.gitattributes`).

**Evidence model**: every claim about a seller/factory traces back to an `evidence` record (source type, author, subreddit, date, exact-variant match, positive/negative observations). Repeated posts by the same author count as one corroborating source, not independent evidence. `offerings.json` links a `bag` + `seller` to its supporting `evidence_ids`; scores in `rankings.json` are only generated when non-catalog, exact-variant evidence exists.

**Evidence ingestion pipeline** (`docs/daily-evidence-loop.md`) — four stages, none of which touch the validated `data/` records until the last one:

- **`scripts/scrape_reddit.py`** pulls candidate source material from Reddit. Fetching is tiered: reddit.com JSON, then parsed old.reddit.com HTML, then Firecrawl (optional, billable, capped by `--max-firecrawl-calls`; per-tier counters in the run summary show which tier served each request). When `REDDIT_CLIENT_ID` (plus `REDDIT_CLIENT_SECRET`, if the app has one) is set, tier 1 authenticates as a registered app and reads `oauth.reddit.com` at the official rate limit instead of the heavily-throttled anonymous endpoints. Both app-only grants are supported and selected automatically — `client_credentials` for script/web apps, `installed_client` for secret-less installed apps — because Reddit gates new app registration, so an older installed app may be an account's only usable client. The summary's `auth_mode` reports which grant applied. The host swap happens only at request time; URL builders keep emitting canonical `www.reddit.com` forms so candidate ids, ledger keys, and evidence URLs are unaffected by auth. `--mode daily` polls `/new.json` down to a per-subreddit watermark; `--mode sweep` runs the full search-term matrix for backfill (Reddit search caps at ~1000 results per query, so breadth comes from more search terms rather than deeper pagination).
- **`data/scrape_ledger.json`** (via `scripts/ledger.py`) is committed cross-run memory keyed by Reddit thing id: `promoted`/`rejected` are terminal and permanently suppress a post, `deferred`/`pending` stay eligible. It stores identifiers and dispositions only, never post text. `validate.py` enforces its shape and that every committed receipt is settled.
- **`scripts/triage.py`** scores candidates deterministically against terms derived from the live catalog, boosts collections by coverage gap (using `validate.py`'s own publication gates), and emits a shortlist capped by `--limit` with a per-collection cap. This is the cost gate: the digest is sized by the cap, not by crawl volume. Only a below-floor score is written back as terminal `rejected` — that judges the post. A candidate referencing no catalogued collection is written back as `deferred` instead, because that judges the *catalog* and stops being true once the collection is added; naming a catalogued collection is itself worth 30 of the 100 points, so an unanchored post's low score is not independent evidence of low quality.
- **`scripts/detect_new_collections.py`** reads the run's `candidates.jsonl` and groups posts naming bags with no catalogued family, so the crawl's own output says what to catalogue next. `daily_crawl.sh` runs it **before** `triage.py`, so the signal is captured ahead of the step that defers it. Read-only: it never writes `data/` or the ledger.
- **`scripts/draft_evidence.py`** emits evidence skeletons with mechanical fields pre-filled, leaving six judgment fields to a reviewer; `--apply` merges them and recomputes each affected family's `evidence_coverage`.

URL canonicalization is shared: `model.normalize_evidence_url` is a Python port of `normalizeEvidenceUrl` in `worker/src/index.js` — **keep the two in sync**, since ledger keys, worker submissions, and committed evidence URLs all depend on identical canonical forms.

**`worker/`** is a separate Cloudflare Worker (`worker/src/index.js`) that is the only way public users can propose data changes: it accepts anonymous "receipt-update" submissions from the production Pages origin only, verifies Turnstile, applies a per-IP Cloudflare rate limit, validates/normalizes evidence URLs, resolves canonical receipt metadata **server-side** (never trusts browser-supplied metadata), and files the result as a public GitHub issue in `DusD24/og-rep-hub`. It has its own `package.json`/`wrangler.jsonc` — see `worker/README.md` for the one-time Cloudflare/GitHub secret and variable setup (`GITHUB_ISSUE_TOKEN`, `TURNSTILE_SECRET_KEY`, `CLOUDFLARE_API_TOKEN`, etc.). Secrets never live in the repo.

**Release/deploy** (`.github/workflows/pages.yml`): a merge to `main` deploys the Worker first, tagging it with the commit SHA as `BUILD_SHA`, then deploys Pages, then polls the public `build-meta.json` and the Worker's `GET /health` until both report the same SHA — so a Worker deploy failure blocks the Pages deploy, and there's no window where the two are out of sync.

## Contribution paths (not code)

Public data changes flow through GitHub issue templates, not direct edits: "Suggest a bag collection," "Submit a public Reddit source," "Request a correction or media removal" (see `CONTRIBUTING.md`). Only public URLs and public post context belong in `data/`/`media/evidence/` — never private messages, payment details, addresses, or unverified contact info; `validate.py`'s forbidden-key/sensitive-pattern checks enforce this.
