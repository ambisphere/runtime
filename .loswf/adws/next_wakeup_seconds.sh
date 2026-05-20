#!/usr/bin/env bash
# next_wakeup_seconds.sh — emit the number of seconds until the next sweep wake.
#
# Mirrors the pending-count + cadence logic in adws/adw_loop.sh so external
# schedulers (e.g. a future Foreman wrapper) can ask "when should I wake?" in
# a single shot without embedding gh queries themselves.
#
# Behaviour:
#   - Reads sweep.cycle_interval_minutes (default 10) and sweep.min_interval_sec
#     (default 30) from .loswf/config.yaml via the same awk one-liners used by
#     adws/adw_loop.sh:42-53.
#   - Counts open factory issues in the eight active phases (investigating,
#     planning, plan-review, decomposing, building, review, ship, rollup),
#     excluding factory:hold and factory:status:needs-attention — verbatim
#     port of pending_count() from adws/adw_loop.sh:56-72.
#   - Emits max(60, min_interval_sec) seconds when pending > 0, else
#     cycle_interval_minutes * 60.
#   - Always exits 0.

set -euo pipefail

INTERVAL_MIN=""
MIN_INTERVAL_SEC=""

if [ -f .loswf/config.yaml ]; then
  INTERVAL_MIN=$(awk '/^sweep:/{f=1} f && /cycle_interval_minutes:/{print $2; exit}' \
                   .loswf/config.yaml 2>/dev/null || true)
fi
INTERVAL_MIN="${INTERVAL_MIN:-10}"

if [ -f .loswf/config.yaml ]; then
  MIN_INTERVAL_SEC=$(awk '/^sweep:/{f=1} f && /min_interval_sec:/{print $2; exit}' \
                       .loswf/config.yaml 2>/dev/null || true)
fi
MIN_INTERVAL_SEC="${MIN_INTERVAL_SEC:-30}"

# pending_count — open issues queued in an active phase (excluding hold/needs-attention).
pending_count() {
  gh issue list --state open --limit 200 --json labels --jq '
    [ .[]
      | select([.labels[].name] | any(
          . == "factory:phase:investigating" or
          . == "factory:phase:planning" or
          . == "factory:phase:plan-review" or
          . == "factory:phase:decomposing" or
          . == "factory:phase:building" or
          . == "factory:phase:review" or
          . == "factory:phase:ship" or
          . == "factory:phase:rollup"))
      | select(([.labels[].name] | any(
          . == "factory:hold" or
          . == "factory:status:needs-attention")) | not)
    ] | length' 2>/dev/null || echo 0
}

pending=$(pending_count)
if [ "$pending" -gt 0 ]; then
  clamp=$MIN_INTERVAL_SEC
  [ "$clamp" -lt 60 ] && clamp=60
  echo "$clamp"
else
  echo $(( INTERVAL_MIN * 60 ))
fi
exit 0
