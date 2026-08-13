#!/usr/bin/env bash
# Reruns `daily_crawl.sh sweep` against the SAME RUN_ID until progress stalls.
#
# Each scrape_reddit.py invocation stops early either because it hit its post
# budget (SWEEP_MAX_POSTS) or its --overnight-hours deadline, not because the
# search-term matrix is exhausted -- that's why one sweep can't make it
# through everything. Reusing RUN_ID makes the next run resume from the
# manifest's completed_endpoints instead of restarting, so successive runs
# advance down the same queue. This loop keeps calling it and watches that
# manifest: once two runs in a row add no new completed endpoints, there is
# nothing left to fetch and it stops on its own.
#
# Usage:
#   SWEEP_MAX_POSTS=26000 RUN_ID=2026-08-12 scripts/sweep_until_saturated.sh
#
# Run it detached so it survives closing the terminal:
#   nohup env SWEEP_MAX_POSTS=26000 RUN_ID=2026-08-12 \
#     scripts/sweep_until_saturated.sh >/dev/null 2>&1 & disown
#
# Tunables (env vars):
#   MAX_ITERATIONS        hard cap on reruns, safety net (default 40)
#   MAX_STALE_ITERATIONS  consecutive no-growth runs before declaring
#                         saturation (default 2)
#   MAX_TOTAL_HOURS       overall wall-clock budget for the whole loop,
#                         independent of any single run's --overnight-hours
#                         (default 10)

set -uo pipefail  # no -e: a single failed iteration must not kill the loop

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

RUN_ID="${RUN_ID:-$(date +%Y-%m-%d)}"
export RUN_ID

MAX_ITERATIONS="${MAX_ITERATIONS:-40}"
MAX_STALE_ITERATIONS="${MAX_STALE_ITERATIONS:-2}"
MAX_TOTAL_HOURS="${MAX_TOTAL_HOURS:-10}"

RUN_DIR="local-private/research-runs/${RUN_ID}"
mkdir -p "$RUN_DIR"
LOOP_LOG="${RUN_DIR}/sweep-loop.log"
MANIFEST="${RUN_DIR}/manifest.json"

source "$REPO_ROOT/scripts/run_lock.sh"
SWEEP_LOCK="${RUN_DIR}/.sweep.lock"
if acquire_run_lock "$SWEEP_LOCK" "sweep_until_saturated"; then
  trap 'release_run_lock "$SWEEP_LOCK"' EXIT
else
  lock_status=$?
  exit "$lock_status"
fi

log() {
  printf '[%s] %s\n' "$(date -Iseconds)" "$*" | tee -a "$LOOP_LOG"
}

completed_endpoint_count() {
  python3 -c "
import json, sys
try:
    d = json.load(open('$MANIFEST'))
except FileNotFoundError:
    print(0)
    sys.exit()
print(len(d.get('completed_endpoints', [])))
"
}

loop_started_at=$(date +%s)
prev_completed=-1
stale_count=0
iteration=0

log "=== starting saturation loop: RUN_ID=${RUN_ID} SWEEP_MAX_POSTS=${SWEEP_MAX_POSTS:-6000} max_iterations=${MAX_ITERATIONS} max_stale=${MAX_STALE_ITERATIONS} max_total_hours=${MAX_TOTAL_HOURS} ==="

while [ "$iteration" -lt "$MAX_ITERATIONS" ]; do
  iteration=$((iteration + 1))

  elapsed_hours=$(( ($(date +%s) - loop_started_at) / 3600 ))
  if [ "$elapsed_hours" -ge "$MAX_TOTAL_HOURS" ]; then
    log "hit MAX_TOTAL_HOURS (${MAX_TOTAL_HOURS}h) at iteration ${iteration}, stopping"
    break
  fi

  log "--- iteration ${iteration}/${MAX_ITERATIONS} (elapsed ${elapsed_hours}h) ---"

  # Snapshot the previous iteration's reviewable outputs before daily_crawl.sh
  # overwrites them -- triage caps the digest per run, so later runs would
  # otherwise clobber earlier shortlists before anyone reads them.
  if [ "$iteration" -gt 1 ]; then
    for f in triage-digest.json triage-context.json evidence-drafts.json new-collection-candidates.json; do
      if [ -f "${RUN_DIR}/${f}" ]; then
        cp "${RUN_DIR}/${f}" "${RUN_DIR}/${f%.json}-iter$((iteration - 1)).json"
      fi
    done
  fi

  # Stream to the terminal AND the log file, rather than only the log file --
  # PIPESTATUS[0] recovers daily_crawl.sh's own exit code since `tee` would
  # otherwise mask it.
  scripts/daily_crawl.sh sweep 2>&1 | tee -a "$LOOP_LOG"
  crawl_exit=${PIPESTATUS[0]}
  if [ "$crawl_exit" -eq 0 ]; then
    log "iteration ${iteration}: daily_crawl.sh exited 0"
  elif [ "$crawl_exit" -eq 75 ]; then
    log "iteration ${iteration}: crawl lock contention; stopping without another triage pass"
    exit 75
  else
    log "iteration ${iteration}: daily_crawl.sh exited ${crawl_exit} (see ${LOOP_LOG}), continuing loop"
  fi

  completed=$(completed_endpoint_count)
  log "iteration ${iteration}: completed_endpoints=${completed} (prev=${prev_completed})"

  if [ "$completed" -le "$prev_completed" ]; then
    stale_count=$((stale_count + 1))
    log "iteration ${iteration}: no new endpoints completed (stale_count=${stale_count}/${MAX_STALE_ITERATIONS})"
  else
    stale_count=0
  fi
  prev_completed=$completed

  if [ "$stale_count" -ge "$MAX_STALE_ITERATIONS" ]; then
    log "saturated: ${MAX_STALE_ITERATIONS} consecutive runs added no new endpoints, stopping after iteration ${iteration}"
    break
  fi
done

log "=== loop finished after ${iteration} iteration(s) ==="
cat <<EOF | tee -a "$LOOP_LOG"

Review when you're back:
  ${RUN_DIR}/triage-digest.json          (final run's shortlist)
  ${RUN_DIR}/triage-digest-iter*.json    (earlier runs' shortlists, snapshotted so nothing was overwritten)
  ${RUN_DIR}/evidence-drafts.json        (+ evidence-drafts-iter*.json)
  ${RUN_DIR}/new-collection-candidates.json (+ -iter*.json)
  ${LOOP_LOG}                            (full loop log)
EOF
