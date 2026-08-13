#!/usr/bin/env bash
# Sourceable, process-level lock for a private crawl run directory.
#
# The lock uses mkdir because directory creation is atomic on macOS and does not
# require an external flock binary. Only the lock's own metadata files are removed;
# raw crawl artifacts are never touched.

acquire_run_lock() {
  local lock_dir="$1"
  local label="${2:-run}"
  local owner_pid=""

  while true; do
    if mkdir "$lock_dir" 2>/dev/null; then
      printf '%s\n' "$$" > "$lock_dir/pid"
      printf '%s\n' "$label" > "$lock_dir/label"
      return 0
    fi

    if [ ! -f "$lock_dir/pid" ]; then
      printf 'run lock exists without a verifiable owner: %s\n' "$lock_dir" >&2
      return 75
    fi

    IFS= read -r owner_pid < "$lock_dir/pid" || owner_pid=""
    case "$owner_pid" in
      ''|*[!0-9]*)
        printf 'run lock has an invalid owner: %s\n' "$lock_dir" >&2
        return 75
        ;;
    esac

    if kill -0 "$owner_pid" 2>/dev/null; then
      printf 'run lock active: %s (pid %s)\n' "$lock_dir" "$owner_pid" >&2
      return 75
    fi

    # The recorded process is gone. Remove only known lock metadata, then retry
    # mkdir; if another process won the race, report the lock as busy.
    rm -f "$lock_dir/pid" "$lock_dir/label"
    if ! rmdir "$lock_dir" 2>/dev/null; then
      printf 'run lock changed while reclaiming: %s\n' "$lock_dir" >&2
      return 75
    fi
  done
}


release_run_lock() {
  local lock_dir="$1"
  local owner_pid=""
  [ -d "$lock_dir" ] || return 0
  [ -f "$lock_dir/pid" ] || return 1
  IFS= read -r owner_pid < "$lock_dir/pid" || return 1
  [ "$owner_pid" = "$$" ] || return 1
  rm -f "$lock_dir/pid" "$lock_dir/label"
  rmdir "$lock_dir"
}
