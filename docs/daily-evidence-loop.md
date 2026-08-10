# The daily evidence loop

How the catalog stays current without the review step growing with it.

## The problem this solves

Crawl output scales with communities × search terms × catalog size. Reading time does
not. Before this loop existed, every candidate was raw post text that a person or a
model had to read, and a fresh run directory re-presented posts that had already been
normalized months earlier.

Three things fix that, and all three are free:

1. **A committed ledger** (`data/scrape_ledger.json`) remembers every disposition, so a
   post reviewed once never comes back.
2. **Daily mode** polls `/new.json` down to a per-subreddit watermark instead of
   re-running the search matrix — about 144× fewer listing requests today, and it stays
   O(communities) rather than O(communities × terms × pages).
3. **Deterministic triage** scores every candidate in Python and hands over a capped
   shortlist. The digest is sized by `--limit`, not by how much was crawled.

Net effect on a 600-candidate run: 436 auto-rejected, 139 deferred, 25 shortlisted —
a 296KB raw crawl becomes a ~37KB read (~9k tokens), and that number does not move when
you add communities.

## Nightly

```sh
scripts/daily_crawl.sh
```

Crawls what is new, triages it, and writes three files into
`local-private/research-runs/<date>/`:

| File | What it is |
| --- | --- |
| `triage-digest.json` | the shortlist — the only thing you read |
| `triage-context.json` | ids and enums, so you never open `data/` to write a record |
| `evidence-drafts.json` | skeletons with the mechanical fields already filled |

## Weekly

```sh
scripts/daily_crawl.sh sweep
```

Runs the full search-term matrix. Use it for backfill and whenever you add a community —
daily mode only sees what is posted from now on, so a new subreddit needs one sweep to
pick up its history.

## Reviewing

Open `evidence-drafts.json` and fill the `TODO` fields. Only six carry judgment:

`source_type`, `evidence_type`, `exact_product_match`, `paraphrase`,
`positive_observations`, `negative_observations`

Everything else — id, canonical url, subreddit, author, dates, media — is already there.
Each draft carries a `_review` block with the post excerpt, the matched entities, and
why triage ranked it where it did; `--apply` strips that block before writing.

```sh
python3 scripts/draft_evidence.py --apply local-private/research-runs/<date>/evidence-drafts.json
python3 scripts/validate.py && python3 scripts/score.py --check
```

`--apply` refuses a batch outright rather than applying it partially, and it recomputes
each affected collection's `evidence_coverage` — `source_count`,
`independent_author_count`, `primary_subreddit_coverage`, `evidence_types` — because
`validate.py` cross-checks those against the linked records.

Commit `data/evidence.json`, `data/bag_families.json`, and `data/scrape_ledger.json`
together. The ledger is what stops tonight's decisions being re-litigated tomorrow.

## Where the budget goes

Triage points the daily shortlist at what actually blocks publication, using
`validate.py`'s own gates: a collection still in `research_queue`, or with fewer than two
independent authors, or with no RealRepLadies/RepTherapy source, is boosted. The
best-covered collection is penalised.

A per-collection cap (default 3) stops one needy collection taking the whole day —
closing a coverage gap needs two independent authors, not twenty posts.

Tune per run:

```sh
TRIAGE_LIMIT=40 TRIAGE_FLOOR=25 scripts/daily_crawl.sh
```

## Scheduling it

`scripts/daily_crawl.sh` is a plain script; `launchd` runs it nightly. Copy
`docs/launchd/com.ogrephub.daily-crawl.plist` to `~/Library/LaunchAgents/`, edit the
paths, then:

```sh
launchctl load ~/Library/LaunchAgents/com.ogrephub.daily-crawl.plist
```

It only runs while the Mac is awake; `launchd` will run a missed job once on wake.

## Why the crawl is not in CI

Reddit answers a residential IP far more reliably than a GitHub Actions runner, which
gets 403s often enough that the paid Firecrawl tier would carry the load — a per-run
cost for something that is free locally.

Triage stays local too, for a different reason: it reads `candidates.jsonl` under
`local-private/`, which is gitignored on purpose. Shipping raw captured post text to CI
to save a few seconds of pure-Python scoring would trade the repo's privacy boundary for
nothing. `validate.py` already enforces ledger integrity in CI on every push.

## Cost controls

- `--max-firecrawl-calls` (default 25) caps billable tier-3 scrapes per run. Run
  summaries report `firecrawl_fallback_count` and `firecrawl_calls_used` separately from
  the free tier-2 fallback, so a bad night is visible rather than merely expensive.
- Watermarks only ever advance, and never advance for a source cut short by the failure
  circuit breaker — so a partial run re-checks the same window rather than skipping it.
- `deferred` candidates stay eligible for a later sweep; only `promoted` and `rejected`
  are terminal.
