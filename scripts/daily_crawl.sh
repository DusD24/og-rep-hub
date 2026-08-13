#!/usr/bin/env bash
# Nightly evidence loop: crawl what is new, then rank it deterministically.
#
# Runs locally on purpose. Reddit answers a residential IP far more reliably than a
# datacenter one, which keeps the billable Firecrawl tier a rare last resort instead
# of a per-run cost. Triage needs no network, so it runs here too rather than in CI --
# raw candidates live under local-private/, which is gitignored by design and never
# leaves the machine.
#
# Nothing in here spends model tokens. The only output meant for a reader is a capped
# digest plus the drafts built from it.
#
# Usage:
#   scripts/daily_crawl.sh              # daily incremental poll
#   scripts/daily_crawl.sh sweep        # full search-term backfill (run weekly)
#
# Schedule it with launchd; see docs/daily-evidence-loop.md.

set -euo pipefail

MODE="${1:-daily}"
LIMIT="${TRIAGE_LIMIT:-25}"
FLOOR="${TRIAGE_FLOOR:-30}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# The run directory holds the resume state: a run reuses its manifest's
# completed_endpoints to skip work already done. Successive sweeps therefore want the
# SAME directory, so they advance down the search-term list instead of restarting at the
# top. Because the default is date-derived, a sweep started after local midnight lands in
# a fresh directory and re-crawls from scratch -- set RUN_ID to continue an earlier run.
RUN_ID="${RUN_ID:-$(date +%Y-%m-%d)}"
RUN_DIR="local-private/research-runs/${RUN_ID}"
mkdir -p "$RUN_DIR"

# A sweep and a daily run must never share a run directory concurrently. Without
# this guard, stale processes can overwrite candidates and the committed ledger
# with older in-memory snapshots after a newer process has made decisions.
source "$REPO_ROOT/scripts/run_lock.sh"
CRAWL_LOCK="${RUN_DIR}/.crawl.lock"
if acquire_run_lock "$CRAWL_LOCK" "daily_crawl:${MODE}"; then
  trap 'release_run_lock "$CRAWL_LOCK"' EXIT
else
  lock_status=$?
  exit "$lock_status"
fi

# Keep the key out of the process list and out of the repo.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

# Firecrawl (tier 3) is off while Reddit is the only crawl target. Firecrawl's own
# fetches of Reddit return 403, so every call it made was billable and recovered
# nothing -- see the 2026-08-12 run, where all 12 calls failed that way. The
# authenticated OAuth tier removed the pressure that pushed us to tier 3 at all.
# Re-enable by raising this if a non-Reddit source is ever added to the registry.
FIRECRAWL_ARGS=(--max-firecrawl-calls 0)

# Pace to whichever rate limit actually applies. An authenticated client gets ~100
# requests/minute (one per 0.6s), so 0.7s uses most of that with headroom to spare.
# Anonymous access is limited to ~10/minute, where anything near 0.7s earns a block --
# so the fast delay is deliberately tied to REDDIT_CLIENT_ID being present rather than
# being a flat default that silently overruns when credentials go missing.
if [ -n "${REDDIT_CLIENT_ID:-}" ]; then
  DELAY="${CRAWL_DELAY:-0.7}"
else
  DELAY="${CRAWL_DELAY:-1.5}"
fi

# The sweep cap is a stopping condition, not a target: --overnight-hours still bounds
# the run. It is divided evenly across seed subreddits (source_post_limit), so raising
# it raises the per-subreddit ceiling too.
SWEEP_MAX_POSTS="${SWEEP_MAX_POSTS:-6000}"

if [ "$MODE" = "sweep" ]; then
  CRAWL_ARGS=(--mode sweep --max-pages 10 --max-posts "$SWEEP_MAX_POSTS" --max-comments 100 --overnight-hours 8 "${FIRECRAWL_ARGS[@]}")
else
  CRAWL_ARGS=(--mode daily --max-pages 3 --max-posts 300 --max-comments 40 "${FIRECRAWL_ARGS[@]}")
fi

echo "==> crawl (${MODE}) into ${RUN_DIR} (delay ${DELAY}s)"
crawl_exit=0
python3 scripts/scrape_reddit.py \
  --run-dir "$RUN_DIR" \
  --resume \
  --delay "$DELAY" \
  "${CRAWL_ARGS[@]}" \
  > "${RUN_DIR}/last-run.json" || crawl_exit=$?
if [ "$crawl_exit" -eq 75 ]; then
  echo "crawl lock contention; refusing to triage a concurrently changing run" >&2
  exit 75
elif [ "$crawl_exit" -ne 0 ]; then
    echo "crawl exited non-zero; triaging whatever was captured" >&2
fi

# Runs BEFORE triage, and deliberately so. triage.py rejects anything that references no
# catalogued collection, and writes that rejection to the ledger as terminal -- but a post
# about a model the catalog has never seen is exactly the signal for what to catalogue
# next. Reading it first means the only record of an uncatalogued bag is captured before
# the step that suppresses it. Read-only: it touches neither data/ nor the ledger.
echo "==> new-collection signal"
python3 scripts/detect_new_collections.py --run-dir "$RUN_DIR"

echo "==> triage (cap ${LIMIT}, floor ${FLOOR})"
python3 scripts/triage.py \
  --run-dir "$RUN_DIR" \
  --limit "$LIMIT" \
  --floor "$FLOOR"

echo "==> drafts"
python3 scripts/draft_evidence.py \
  --from-digest "${RUN_DIR}/triage-digest.json" \
  --out "${RUN_DIR}/evidence-drafts.json"

# The ledger is committed data, so it is held to the same bar as the catalog.
echo "==> validate"
python3 scripts/validate.py

cat <<EOF

Done. Review shortlist:
  ${RUN_DIR}/triage-digest.json     (what to read)
  ${RUN_DIR}/triage-context.json    (ids and enums, so you need not open data/)
  ${RUN_DIR}/evidence-drafts.json   (fill the TODO fields, then apply)

  ${RUN_DIR}/new-collection-candidates.json
      bags with evidence but no collection yet -- what to catalogue next

Then:
  python3 scripts/draft_evidence.py --apply ${RUN_DIR}/evidence-drafts.json
  python3 scripts/validate.py && python3 scripts/score.py --check

Ledger dispositions were updated; commit data/scrape_ledger.json to keep them.
EOF
