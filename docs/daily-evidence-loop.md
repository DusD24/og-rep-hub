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

## Crawl pacing

`daily_crawl.sh` picks the request delay from whichever rate limit applies, because the
two differ by an order of magnitude:

| Mode | Reddit limit | Delay used |
| --- | --- | --- |
| authenticated (`REDDIT_CLIENT_ID` set) | ~100 req/min | `0.7s` |
| anonymous | ~10 req/min | `1.5s` |

The fast delay is tied to the credential being present rather than set as a flat default,
so a missing or removed key cannot silently leave the crawler running well over the
anonymous limit — which is what earns an IP-level block.

Override the delay, the sweep post cap, or the run directory:

```sh
CRAWL_DELAY=1.0 SWEEP_MAX_POSTS=10000 scripts/daily_crawl.sh sweep
RUN_ID=2026-08-12 scripts/daily_crawl.sh sweep   # continue an earlier run
```

`--max-posts` is a stopping condition rather than a target; `--overnight-hours 8` still
bounds the run. It is divided evenly across seed subreddits to form `source_post_limit`,
so raising it also raises the per-subreddit ceiling. A full historical backfill is
several sweeps, not one: the ledger and the run manifest's `completed_endpoints` let each
run resume where the last stopped.

Two things to know before starting a second sweep back to back:

- **Reuse the run directory.** Resume state lives in that directory's manifest, so a
  sweep in a fresh directory re-crawls from the top of the term list. The default
  directory is date-derived, which means a run started after local midnight silently
  starts over — pass `RUN_ID` to continue the earlier one.
- **Review or apply the drafts first.** Each run rewrites `triage-digest.json` and
  `evidence-drafts.json` in place, so a second sweep discards any judgment fields already
  filled into the previous drafts. Run `draft_evidence.py --apply` (or copy the file
  aside) before crawling again.

Search terms are ordered deliberately: the per-subreddit post budget is spent in query
order, so specific model names come first and generic evidence-lane words (`review`,
`QC`, `PSP`) come last. Position is priority. Because completed endpoints are skipped on
resume, successive sweeps advance further down the list rather than re-running the front
of it.

## Scheduling it

`scripts/daily_crawl.sh` is a plain script; `launchd` runs it nightly. Copy
`docs/launchd/com.ogrephub.daily-crawl.plist` to `~/Library/LaunchAgents/`, edit the
paths, then:

```sh
launchctl load ~/Library/LaunchAgents/com.ogrephub.daily-crawl.plist
```

It only runs while the Mac is awake; `launchd` will run a missed job once on wake.

## Authenticating against the official API

Set `REDDIT_CLIENT_ID` (and `REDDIT_CLIENT_SECRET`, if the app has one) in `.env` — see
`.env.example` — to read Reddit as a registered app instead of anonymously. Manage apps
at <https://www.reddit.com/prefs/apps>.

Two app types work, and the client picks the matching OAuth grant automatically:

| App type | Secret | Grant |
| --- | --- | --- |
| script / web app | yes | `client_credentials` |
| installed app | no | `installed_client` + `device_id` |

Prefer a **script** app for a new setup. Reddit now gates new app registration behind a
separate API-access request, though, so an **installed app** created before that gate may
be the only client an account has — hence both grants. For an installed app, set only
`REDDIT_CLIENT_ID` and leave the secret blank; it is a public client and has no secret.
The startup log and the run summary's `auth_mode` both report which grant was used.

This matters most for sweeps. Anonymous `www.reddit.com` JSON is the most aggressively
throttled path Reddit offers, and a long sweep from one IP eventually collects 403s
across all three tiers — including Firecrawl, whose own fetches of Reddit get blocked
too. The authenticated tier reads `oauth.reddit.com` under a sanctioned per-client rate
limit, so it neither depends on IP reputation nor spends Firecrawl calls to work around
it. The run summary's `auth_mode` field records `oauth` or `anonymous`, and the crawler
prints which one it is on startup.

Credentials are optional and degrade safely: a missing, malformed, or revoked key falls
back to the anonymous endpoint rather than failing the run.

Rotating IPs (VPN, proxies) is not a substitute. Reddit blocks datacenter and shared-VPN
ranges far more aggressively than residential ones, so it usually lowers the success rate
while also breaking Reddit's terms.

## Why the crawl is not in CI

Reddit answers a residential IP far more reliably than a GitHub Actions runner, which
gets 403s often enough that the paid Firecrawl tier would carry the load — a per-run
cost for something that is free locally. Authenticating (above) removes most of this
gap, since an OAuth client is rate-limited per app rather than per IP.

Triage stays local too, for a different reason: it reads `candidates.jsonl` under
`local-private/`, which is gitignored on purpose. Shipping raw captured post text to CI
to save a few seconds of pure-Python scoring would trade the repo's privacy boundary for
nothing. `validate.py` already enforces ledger integrity in CI on every push.

## Cost controls

- `--max-firecrawl-calls` (default 25) caps billable tier-3 scrapes per run; `0` disables
  the tier outright. Run summaries report `firecrawl_fallback_count` and
  `firecrawl_calls_used` separately from the free tier-2 fallback, so a bad night is
  visible rather than merely expensive.
- **`daily_crawl.sh` currently passes `--max-firecrawl-calls 0`.** Firecrawl cannot fetch
  Reddit — its own requests come back `403` — so while Reddit is the only source in the
  registry, tier 3 can only ever bill for pages it fails to retrieve. Raise it in
  `FIRECRAWL_ARGS` if a fetchable non-Reddit source is ever added. The `FIRECRAWL_API_KEY`
  in `.env` can stay; the flag disables the tier regardless of whether a key is present.
- Watermarks only ever advance, and never advance for a source cut short by the failure
  circuit breaker — so a partial run re-checks the same window rather than skipping it.
- `deferred` candidates stay eligible for a later sweep; only `promoted` and `rejected`
  are terminal.
- Triage only ever writes terminal `rejected` for a **below-floor score**. A candidate
  that references no catalogued collection is written back as `deferred` and counted
  under `awaiting_catalog`, because that says the catalog has never heard of the bag
  rather than saying the post is poor — and it stops being true the moment the
  collection is added. Scoring reinforces this: naming a catalogued collection is worth
  30 of 100 points, so an unanchored post is docked for exactly the thing being tested
  and its low score cannot be read as an independent quality judgment. These posts are
  also the input `detect_new_collections.py` reads, so rejecting them terminally would
  let the pipeline discard its own roadmap.
