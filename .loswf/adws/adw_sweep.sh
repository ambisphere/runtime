#!/usr/bin/env bash
# adw_sweep.sh — one full factory sweep. Advances every eligible issue by one phase.
# Designed to be re-run on a cadence (cron, launchd, GitHub Actions schedule).
#
# Phase ordering is declarative: the walk is driven by `sweep.sequence` in
# .loswf/config.yaml and dispatched by `run_sequence` in _lib.sh. See
# docs/designs/curator-harvester-sequencing-remediation.md §4-§5.
#
# Usage: ./adws/adw_sweep.sh [--max-builds N]

set -euo pipefail

# shellcheck source=./_lib.sh
. "$(dirname "$0")/_lib.sh"

MAX_BUILDS=3
while [ $# -gt 0 ]; do
  case "$1" in
    --max-builds) MAX_BUILDS="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 64 ;;
  esac
done
export MAX_BUILDS

acquire_lock sweep

start_ts=$(date +%s)
log "sweep starting (max concurrent builds: $MAX_BUILDS)"

if [ -s "$LOSWF_STATE_DIR/index-queue" ]; then
  log "draining index-queue"
  bin/loswf-index update >/dev/null 2>&1 || emit_event sweep 0 index-drain error
fi

reset_work_counter
snapshot_phases
run_sequence
log "work counter: $(read_work_counter)"

dur=$(( ($(date +%s) - start_ts) * 1000 ))
emit_event sweep 0 adw_sweep done "$dur"
log "sweep complete in ${dur}ms"
