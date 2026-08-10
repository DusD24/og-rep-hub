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

RUN_ID="$(date +%Y-%m-%d)"
RUN_DIR="local-private/research-runs/${RUN_ID}"
mkdir -p "$RUN_DIR"

# Keep the key out of the process list and out of the repo.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

if [ "$MODE" = "sweep" ]; then
  CRAWL_ARGS=(--mode sweep --max-pages 10 --max-posts 2000 --max-comments 100 --overnight-hours 8)
else
  CRAWL_ARGS=(--mode daily --max-pages 3 --max-posts 300 --max-comments 40)
fi

echo "==> crawl (${MODE}) into ${RUN_DIR}"
python3 scripts/scrape_reddit.py \
  --run-dir "$RUN_DIR" \
  --resume \
  --delay 1.5 \
  "${CRAWL_ARGS[@]}" \
  > "${RUN_DIR}/last-run.json" || {
    echo "crawl exited non-zero; triaging whatever was captured" >&2
  }

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

Then:
  python3 scripts/draft_evidence.py --apply ${RUN_DIR}/evidence-drafts.json
  python3 scripts/validate.py && python3 scripts/score.py --check

Ledger dispositions were updated; commit data/scrape_ledger.json to keep them.
EOF
