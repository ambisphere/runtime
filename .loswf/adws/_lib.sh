#!/usr/bin/env bash
# _lib.sh — shared helpers for loswf2 ADW scripts. Source from any adw_*.sh.

set -euo pipefail

LOSWF_STATE_DIR="${LOSWF_STATE_DIR:-.loswf/state}"
LOSWF_EVENT_LOG="$LOSWF_STATE_DIR/events.jsonl"

mkdir -p "$LOSWF_STATE_DIR"

# emit_event <phase> <issue> <agent> <outcome> [duration_ms]
emit_event() {
  local phase="$1" issue="$2" agent="$3" outcome="$4" dur="${5:-0}"
  local ts
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  printf '{"ts":"%s","phase":"%s","issue":%s,"agent":"%s","outcome":"%s","duration_ms":%s}\n' \
    "$ts" "$phase" "$issue" "$agent" "$outcome" "$dur" >> "$LOSWF_EVENT_LOG"
}

# rerun_context <issue> <kind>
# Print a prompt suffix carrying the last rejection feedback so the agent knows
# this is a second pass and what to address. <kind> is "plan" (scan issue
# comments) or "build" (scan the linked PR's comments). Empty output means
# first pass / no prior rejection — caller should pass the normal prompt.
rerun_context() {
  local issue="$1" kind="$2" body=""
  if [ "$kind" = "plan" ]; then
    body=$(gh issue view "$issue" --json comments --jq \
      '[.comments[] | select((.body // "") | test("^(rejected:|revise|changes requested)"; "i"))] | last.body // ""' 2>/dev/null)
  else
    local pr
    pr=$(gh pr list --search "linked:$issue" --state open --json number --jq '.[0].number' 2>/dev/null)
    [ -z "$pr" ] && return 0
    body=$(gh pr view "$pr" --json comments --jq \
      '[.comments[] | select((.body // "") | test("^rejected:"; "i"))] | last.body // ""' 2>/dev/null)
  fi
  [ -z "$body" ] && return 0
  printf '\n\nNOTE: This is a re-run after rejection. Address the reviewer feedback below specifically.\n\nPrevious reviewer feedback:\n---\n%s\n---\n' "$body"
}

# _loswf_speak_enabled — true when LOSWF_SPEAK=1 OR .loswf/config.yaml sets sweep.speak: true.
# Silent on pyyaml import errors (speak is opt-in; must never block the sweep).
_loswf_speak_enabled() {
  [ "${LOSWF_SPEAK:-}" = "1" ] && return 0
  python3 -c 'import yaml,sys; d=yaml.safe_load(open(".loswf/config.yaml")) or {}; sys.exit(0 if (d.get("sweep") or {}).get("speak") else 1)' 2>/dev/null
}

loswf_runtime() {
  printf '%s\n' "${LOSWF_RUNTIME:-claude}"
}

_loswf_run_id() {
  python3 - <<'PY'
import uuid
print(uuid.uuid4())
PY
}

_reconcile_after_run() {
  local issue="$1" hook_agent="$2" run_id="$3"
  local post_agent receipt_dir receipt_path
  post_agent=".loswf/tools/loswf_post_agent.py"
  [ -f "$post_agent" ] || return 0
  receipt_dir="$LOSWF_STATE_DIR/receipts/$run_id"
  receipt_path=""
  if [ -d "$receipt_dir" ]; then
    receipt_path="$(find "$receipt_dir" -maxdepth 1 -type f -name '*.json' ! -name '*.last-message.json' | head -1)"
  fi
  LOSWF_CURRENT_AGENT="$hook_agent" \
  LOSWF_CURRENT_ISSUE="$issue" \
  LOSWF_RECEIPT_PATH="$receipt_path" \
    python3 "$post_agent" < /dev/null >/dev/null 2>&1 || true
}

# _runtime_adapter_path <op> — print the absolute path of the runtime adapter
# script for <op>. Operation names match specs/runtime-adapter-contract.md.
# Unknown op: log + return 64 (EX_USAGE).
_runtime_adapter_path() {
  local op="$1" root runtime sub
  root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  runtime="$(loswf_runtime)"
  case "$op" in
    run_headless_phase)      sub="bin/headless-run.sh" ;;
    doctor)                  sub="bin/doctor.sh" ;;
    run_interactive_command) sub="bin/run-interactive.sh" ;;
    enforce_validators)      sub="bin/enforce-validators.sh" ;;
    bootstrap)               sub="bootstrap/install-project-scope.sh" ;;
    *)
      log "runtime: unknown adapter op '$op'"
      return 64
      ;;
  esac
  printf '%s/runtime/%s/%s\n' "$root" "$runtime" "$sub"
}

# run_subagent <agent-name> <prompt> [issue] [hook-agent]
# Invoke a runtime-backed subagent headlessly.
# - <agent-name>  drives the prompt ("Use the X subagent. ...")
# - [issue]       passed to the post-agent Stop hook for state transitions (default 0)
# - [hook-agent]  override the identity reported to the hook; defaults to <agent-name>.
#                 Use this when the prompt invokes a slash command via the `default`
#                 agent but the hook should treat it as e.g. loswf-ship.
# Returns the runtime runner's exit code; output streams to stdout.
run_subagent() {
  local agent="$1" prompt="$2" issue="${3:-0}" hook_agent="${4:-$1}"
  local _preflight_rc=0 run_id
  local runner runtime rc=0
  run_id="$(_loswf_run_id)"
  bash "$(dirname "${BASH_SOURCE[0]}")/_index_preflight.sh" || _preflight_rc=$?
  if [ "$_preflight_rc" -ne 0 ]; then
    emit_event preflight "$issue" index_preflight error
    return 78
  fi
  runtime="$(loswf_runtime)"
  runner="$(_runtime_adapter_path run_headless_phase)"
  if [ ! -x "$runner" ]; then
    log "runtime: missing headless runner for '$runtime' at $runner"
    emit_event runtime "$issue" "$hook_agent" error
    return 69
  fi
  LOSWF_RUN_ID="$run_id" "$runner" "$agent" "$prompt" "$issue" "$hook_agent" || rc=$?
  _reconcile_after_run "$issue" "$hook_agent" "$run_id"
  if _loswf_speak_enabled; then
    local outcome
    if [ "$rc" -eq 0 ]; then outcome="$hook_agent ok"; else outcome="$hook_agent error"; fi
    ( bash "$(dirname "${BASH_SOURCE[0]}")/tts_announce.sh" "$hook_agent" "$outcome" >/dev/null 2>&1 ) &
    disown $!
  fi
  return $rc
}

# run_interactive_command <agent> [initial-prompt]
# Dispatch to the runtime adapter's interactive shell. No preflight gate
# (operator-driven), no receipts (no .loswf/state writes), no TTS.
# Returns 69 if the adapter script is missing/non-executable.
run_interactive_command() {
  local agent="$1" prompt="${2:-}" runner runtime
  runtime="$(loswf_runtime)"
  runner="$(_runtime_adapter_path run_interactive_command)"
  if [ ! -x "$runner" ]; then
    log "runtime: missing interactive runner for '$runtime' at $runner"
    return 69
  fi
  "$runner" "$agent" "$prompt"
}

# enforce_validators [name]
# Dispatch to the runtime adapter's validator runner. With no arg the adapter
# runs every .loswf/config.yaml validate[] entry; with [name] it runs the
# matching entry only. Returns 69 if the adapter script is missing.
enforce_validators() {
  local runner runtime
  runtime="$(loswf_runtime)"
  runner="$(_runtime_adapter_path enforce_validators)"
  if [ ! -x "$runner" ]; then
    log "runtime: missing validator runner for '$runtime' at $runner"
    return 69
  fi
  "$runner" "$@"
}

# get_phase <issue-num> — print the current factory:phase:* label, or empty.
get_phase() {
  gh issue view "$1" --json labels --jq \
    '.labels[].name | select(startswith("factory:phase:"))' 2>/dev/null | head -1
}

# set_phase <issue-num> <new-phase> — replace the phase label atomically.
set_phase() {
  local issue="$1" new="$2" current
  current=$(get_phase "$issue" || true)
  local args=()
  [ -n "$current" ] && args+=(--remove-label "$current")
  args+=(--add-label "factory:phase:$new")
  gh issue edit "$issue" "${args[@]}" >/dev/null
}

# require_phase <issue-num> <expected-phase> — exit non-zero if mismatch.
require_phase() {
  local issue="$1" expected="$2" actual
  actual=$(get_phase "$issue" | sed 's/factory:phase://')
  if [ "$actual" != "$expected" ]; then
    echo "issue #$issue: expected phase '$expected', got '${actual:-none}'" >&2
    exit 64
  fi
}

# has_status <issue-num> <status> — 0 if label present, 1 otherwise.
has_status() {
  gh issue view "$1" --json labels --jq \
    ".labels[].name | select(. == \"factory:status:$2\" or . == \"factory:hold\")" \
    | grep -q . && return 0 || return 1
}

# has_label <issue-num> <label> — 0 if label present, 1 otherwise.
has_label() {
  gh issue view "$1" --json labels --jq \
    ".labels[].name | select(. == \"$2\")" \
    | grep -q . && return 0 || return 1
}

# list_depends_on <issue-num> — print each sibling number from factory:depends-on:<N>.
list_depends_on() {
  gh issue view "$1" --json labels --jq \
    '.labels[].name | select(startswith("factory:depends-on:")) | sub("factory:depends-on:"; "")' \
    2>/dev/null
}

# depends_satisfied <issue-num> — 0 if every declared dependency is factory:phase:done.
# 0 if no depends-on labels. 1 if any sibling is not yet done.
depends_satisfied() {
  local issue="$1" sibling sibling_phase
  while read -r sibling; do
    [ -z "$sibling" ] && continue
    sibling_phase=$(get_phase "$sibling" | sed 's/factory:phase://')
    if [ "$sibling_phase" != "done" ]; then
      return 1
    fi
  done < <(list_depends_on "$issue")
  return 0
}

# all_children_done <parent-num> — 0 if ≥1 children and all are factory:phase:done.
all_children_done() {
  local parent="$1" count=0 not_done=0
  while read -r child; do
    [ -z "$child" ] && continue
    count=$((count + 1))
    local phase
    phase=$(get_phase "$child" | sed 's/factory:phase://')
    [ "$phase" != "done" ] && not_done=$((not_done + 1))
  done < <(gh issue list --state all --label "factory:parent:$parent" \
             --json number --jq '.[].number' 2>/dev/null)
  [ "$count" -ge 1 ] && [ "$not_done" -eq 0 ]
}

# log <message> — timestamped stderr log.
log() {
  printf '[loswf2 %s] %s\n' "$(date -u +%H:%M:%S)" "$*" >&2
}

# --- sweep sequencing helpers (design: docs/designs/curator-harvester-sequencing-remediation.md) ---

# reset_work_counter — truncate the per-sweep work sentinel. Call at sweep start.
reset_work_counter() {
  : > "$LOSWF_STATE_DIR/sweep.work_count"
}

# bump_work_counter — append one byte to the sentinel. Safe from subshells
# (POSIX O_APPEND is atomic for a single-byte write).
bump_work_counter() {
  printf '.' >> "$LOSWF_STATE_DIR/sweep.work_count"
}

# read_work_counter — print the current byte count (0 if missing).
read_work_counter() {
  if [ -f "$LOSWF_STATE_DIR/sweep.work_count" ]; then
    wc -c < "$LOSWF_STATE_DIR/sweep.work_count" | tr -d ' '
  else
    echo 0
  fi
}

# snapshot_phases — record `<issue> <phase>` for every open factory issue
# into $LOSWF_STATE_DIR/sweep.phase_snapshot. Used by compare_phase to detect
# post-dispatch phase transitions and bump the work counter accordingly.
snapshot_phases() {
  local snap="$LOSWF_STATE_DIR/sweep.phase_snapshot"
  gh issue list --state open --search "label:factory:type:bug label:factory:type:feature label:factory:type:chore label:factory:type:spike label:factory:type:investigate" \
    --json number,labels \
    --jq '.[] | "\(.number) \(.labels[].name | select(startswith("factory:phase:")))"' \
    2>/dev/null > "$snap" || : > "$snap"
}

# compare_phase <issue> — if the issue's phase now differs from the snapshot
# (or the issue was absent from the snapshot), bump the work counter.
compare_phase() {
  local issue="$1" snap="$LOSWF_STATE_DIR/sweep.phase_snapshot"
  local before="" after
  if [ -f "$snap" ]; then
    before=$(awk -v n="$issue" '$1 == n {print $2; exit}' "$snap")
  fi
  after=$(get_phase "$issue" || true)
  if [ -z "$before" ]; then
    # Not in snapshot — treat as new work (e.g. issue created mid-sweep).
    bump_work_counter
    return 0
  fi
  if [ "$before" != "$after" ]; then
    bump_work_counter
  fi
}

# read_sweep_sequence — emit one `|`-delimited record per sweep.sequence entry:
#   name|kind|agent|mode|enabled|parallel_max|idle_gated|cadence_hours|counts_as_work|handler|command
# Missing fields are empty. Defaults:
#   enabled=true, idle_gated=false, counts_as_work=true, parallel_max=0.
read_sweep_sequence() {
  python3 - <<'PYEOF'
import sys
try:
    import yaml
except ImportError:
    sys.stderr.write("read_sweep_sequence: pyyaml not installed — install pyyaml: pip install pyyaml\n")
    sys.exit(2)
try:
    with open(".loswf/config.yaml") as f:
        cfg = yaml.safe_load(f) or {}
except FileNotFoundError:
    sys.stderr.write("read_sweep_sequence: .loswf/config.yaml not found\n")
    sys.exit(2)
seq = ((cfg.get("sweep") or {}).get("sequence") or [])
for e in seq:
    if not isinstance(e, dict):
        continue
    name = e.get("name", "")
    kind = e.get("kind", "")
    agent = e.get("agent", "")
    mode = e.get("mode", "")
    enabled = e.get("enabled", True)
    parallel_max = ((e.get("parallel") or {}).get("max")) if isinstance(e.get("parallel"), dict) else 0
    idle_gated = e.get("idle_gated", False)
    cadence_hours = e.get("cadence_hours", "")
    counts_as_work = e.get("counts_as_work", True)
    handler = e.get("handler", "")
    command = e.get("command", "")
    def s(v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if v is None:
            return ""
        return str(v)
    fields = [name, kind, agent, mode, s(enabled), s(parallel_max or 0),
              s(idle_gated), s(cadence_hours), s(counts_as_work),
              handler, command]
    print("|".join(fields))
PYEOF
}

# promote_rollup_if_ready — bash handler for the awaiting-children phase.
# Mirrors the inline block formerly at adw_sweep.sh:124-130, but additionally
# bumps the work counter on each successful promotion (design §5.1).
promote_rollup_if_ready() {
  local issue
  gh issue list --state open --label "factory:phase:awaiting-children" \
    --search "sort:created-asc" \
    --json number,labels \
    --jq '.[] | select(([.labels[].name] | any(. == "factory:hold" or . == "factory:status:needs-attention")) | not) | .number' \
    2>/dev/null | while read -r issue; do
      [ -z "$issue" ] && continue
      if all_children_done "$issue"; then
        set_phase "$issue" rollup
        emit_event awaiting-children "$issue" sweep promoted
        bump_work_counter
      fi
    done
}

# _cadence_ok <name> <hours> — 0 if the cadence-gated step is due (no marker
# yet, or marker older than <hours>). 1 if a recent marker exists.
_cadence_ok() {
  local name="$1" hours="$2"
  local mark="$LOSWF_STATE_DIR/${name}.last_run"
  [ -z "$hours" ] && return 0
  [ ! -f "$mark" ] && return 0
  find "$mark" -mmin +$((hours * 60)) -print 2>/dev/null | grep -q . && return 0
  return 1
}

# run_sequence — declarative sweep dispatcher. Reads `read_sweep_sequence` and
# runs each step in order, honoring enabled / idle_gated / cadence_hours /
# parallel.max. The caller is
# expected to have called `reset_work_counter` and `snapshot_phases` at the
# start of the sweep. MAX_BUILDS env caps building-phase concurrency (default
# = parallel.max from config).
run_sequence() {
  local line name kind agent mode enabled parallel_max idle_gated cadence counts handler command
  local records
  records=$(read_sweep_sequence) || return $?
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    IFS='|' read -r name kind agent mode enabled parallel_max idle_gated cadence counts handler command <<<"$line"

    if [ "$enabled" = "false" ]; then
      log "seq: $name — disabled, skipping"
      continue
    fi

    if [ "$idle_gated" = "true" ]; then
      local wc
      wc=$(read_work_counter)
      if [ "${wc:-0}" -gt 0 ]; then
        log "seq: $name — idle-gated (work=$wc), skipping"
        emit_event idle-gate 0 sweep skipped
        continue
      fi
      emit_event idle-gate 0 sweep ran
    fi

    if [ -n "$cadence" ] && ! _cadence_ok "$name" "$cadence"; then
      log "seq: $name — cadence ${cadence}h not yet elapsed, skipping"
      continue
    fi

    log "phase: $name"
    case "$kind" in
      subagent)
        _run_sequence_subagent "$name" "$agent" "$mode" "$parallel_max" "$counts"
        ;;
      bash)
        if [ -z "$handler" ]; then
          log "seq: $name — bash kind but no handler; skipping"
        elif ! declare -F "$handler" >/dev/null 2>&1; then
          log "seq: $name — handler '$handler' not defined; skipping"
        else
          "$handler" || emit_event "$name" 0 "$handler" error
        fi
        ;;
      command)
        _run_sequence_command "$name" "$command" "$counts"
        ;;
      *)
        log "seq: $name — unknown kind '$kind', skipping"
        ;;
    esac

    # Touch cadence marker after a successful dispatch pass.
    if [ -n "$cadence" ]; then
      touch "$LOSWF_STATE_DIR/${name}.last_run"
    fi
  done <<<"$records"
}

# _command_hook_agent <command> — map a slash command like `/loswf:ship` to the
# hook-facing synthetic agent name `loswf-ship`.
_command_hook_agent() {
  local command="$1" stem
  stem="${command#/}"
  stem="${stem#loswf:}"
  stem="${stem#loswf-}"
  printf 'loswf-%s\n' "${stem//:/-}"
}

# _run_sequence_command <phase-name> <command> <counts_as_work>
# Internal helper for command-backed sweep phases. Today this is only used by
# the `ship` phase, which requires resolving the linked open PR for each issue.
_run_sequence_command() {
  local name="$1" command="$2" counts="$3"
  local issue pr prompt hook_agent
  hook_agent=$(_command_hook_agent "$command")

  gh issue list --state open --label "factory:phase:$name" \
    --search "sort:created-asc" \
    --json number,labels \
    --jq '.[] | select(([.labels[].name] | any(. == "factory:hold" or . == "factory:status:needs-attention")) | not) | .number' \
    2>/dev/null | while read -r issue; do
      [ -z "$issue" ] && continue
      pr=$(gh pr list --search "linked:$issue" --state open --json number --jq '.[0].number' 2>/dev/null)
      if [ -z "$pr" ]; then
        log "  $command #$issue — no linked open PR, skipping"
        emit_event "$name" "$issue" "$hook_agent" error
        continue
      fi

      prompt="Run the $command slash command on PR #$pr."
      log "  $command #$issue → PR #$pr"
      run_subagent default "$prompt" "$issue" "$hook_agent" \
        || emit_event "$name" "$issue" "$hook_agent" error
      [ "$counts" = "true" ] && compare_phase "$issue"
    done
}

# _run_sequence_subagent <name> <agent> <mode> <parallel_max> <counts_as_work>
# Internal helper for run_sequence. For the building phase (parallel_max > 0),
# launches concurrent subshells each capped by MAX_BUILDS and performs
# compare_phase INSIDE the subshell (design §5.1 invariant). Otherwise loops
# sequentially and compare_phase'es each issue after dispatch.
_run_sequence_subagent() {
  local name="$1" agent="$2" mode="$3" parallel_max="$4" counts="$5"
  local issue ctx pr max_builds cap
  cap="${MAX_BUILDS:-${parallel_max:-0}}"
  [ -z "$cap" ] && cap=0

  # Step 1 (intake) has no phase yet — iterate label-less open issues.
  if [ "$name" = "intake" ]; then
    gh issue list --state open --search "sort:created-asc" --json number,labels --jq \
      '.[] | select([.labels[].name] | any(startswith("factory:phase:")) | not)
           | select(([.labels[].name] | any(. == "factory:hold")) | not)
           | .number' 2>/dev/null | while read -r issue; do
        [ -z "$issue" ] && continue
        log "  $agent #$issue"
        run_subagent "loswf-$agent" "Run intake on issue #$issue." "$issue" \
          || emit_event "$name" "$issue" "$agent" error
        [ "$counts" = "true" ] && compare_phase "$issue"
      done
    return 0
  fi

  # Harvest runs once per sweep with no issue context.
  if [ "$name" = "harvest" ]; then
    run_subagent "loswf-$agent" "Scan for new work and create issues. Cap at 5." \
      || emit_event "$name" 0 "$agent" error
    return 0
  fi

  # Curator-steward: single invocation, no issue loop.
  if [ "$name" = "curator-steward" ]; then
    local prompt="Run a curator pass. Reconcile label families, close stale needs-clarification issues older than 14 days, drop healing labels that have been green for 24 hours, cleanup merged worktrees, and open PRs for any proposed config/prompt changes. Honor .loswf/config.yaml curator ignore lists."
    run_subagent "loswf-$agent" "$prompt" \
      || emit_event "$name" 0 "$agent" error
    return 0
  fi

  # Escalation: route every factory:status:needs-attention issue through
  # curator in mode=escalation. Curator resolves the blocker internally
  # (drops needs-attention + re-applies factory:phase:*) or escalates to
  # the operator by adding factory:status:human-only. Only human-only
  # (and factory:hold) exclude an issue from the next escalation sweep.
  if [ "$name" = "escalation" ]; then
    gh issue list --state open --search 'label:"factory:status:needs-attention" sort:created-asc' \
      --json number,labels \
      --jq '.[] | select(([.labels[].name] | any(. == "factory:hold" or . == "factory:status:human-only")) | not) | .number' \
      2>/dev/null | while read -r issue; do
        [ -z "$issue" ] && continue
        log "  curator (escalation) #$issue"
        run_subagent "loswf-$agent" "mode=escalation: Resolve the needs-attention blocker on issue #$issue. Read the issue body, all comments, and any linked PR feedback. Classify the blocker, post a rationale comment, and either (a) remove factory:status:needs-attention and re-apply the correct factory:phase:* to let the pipeline proceed, or (b) apply factory:status:human-only with a one-line reason if genuinely unresolvable without operator input." "$issue" \
          || emit_event "$name" "$issue" "$agent" error
        [ "$counts" = "true" ] && compare_phase "$issue"
      done
    return 0
  fi

  # Building: parallel with in-subshell compare_phase.
  if [ "${parallel_max:-0}" -gt 0 ] 2>/dev/null; then
    log "  parallel cap: $cap"
    gh issue list --state open --label "factory:phase:$name" \
      --search "sort:created-asc" \
      --json number,labels \
      --jq '.[] | select(([.labels[].name] | any(. == "factory:hold" or . == "factory:status:needs-attention")) | not) | .number' \
      2>/dev/null | while read -r issue; do
        [ -z "$issue" ] && continue
        if ! depends_satisfied "$issue"; then
          log "  #$issue: waiting on depends-on siblings"; continue
        fi
        while [ "$(jobs -rp | wc -l | tr -d ' ')" -ge "$cap" ]; do sleep 5; done
        log "  $agent #$issue (background)"
        ctx=$(rerun_context "$issue" build)
        (
          run_subagent "loswf-$agent" "Implement the approved plan for issue #$issue.$ctx" "$issue" \
            || emit_event "$name" "$issue" "$agent" error
          # Invariant (design §5.1): compare_phase MUST run inside the subshell
          # so bump_work_counter sees this build's transition before `wait`.
          [ "$counts" = "true" ] && compare_phase "$issue"
        ) &
      done
    wait
    return 0
  fi

  # Review phase needs a linked PR to exist.
  if [ "$name" = "review" ]; then
    gh issue list --state open --label "factory:phase:$name" \
      --search "sort:created-asc" \
      --json number,labels \
      --jq '.[] | select(([.labels[].name] | any(. == "factory:hold" or . == "factory:status:needs-attention")) | not) | .number' \
      2>/dev/null | while read -r issue; do
        [ -z "$issue" ] && continue
        pr=$(gh pr list --search "linked:$issue" --state open --json number --jq '.[0].number')
        if [ -z "$pr" ]; then
          log "  #$issue: no linked PR, skipping"; continue
        fi
        log "  $agent PR #$pr (issue #$issue)"
        run_subagent "loswf-$agent" "Review PR #$pr (linked to #$issue)." "$issue" \
          || emit_event "$name" "$issue" "$agent" error
        [ "$counts" = "true" ] && compare_phase "$issue"
      done
    return 0
  fi

  # Default: sequential per-issue dispatch keyed off factory:phase:<name>.
  gh issue list --state open --label "factory:phase:$name" \
    --search "sort:created-asc" \
    --json number,labels \
    --jq '.[] | select(([.labels[].name] | any(. == "factory:hold" or . == "factory:status:needs-attention")) | not) | .number' \
    2>/dev/null | while read -r issue; do
      [ -z "$issue" ] && continue

      # Generic dispatch with optional mode prefix.
      local prompt_prefix=""
      [ -n "$mode" ] && prompt_prefix="mode=$mode: "
      log "  $agent #$issue${mode:+ (mode=$mode)}"
      run_subagent "loswf-$agent" "${prompt_prefix}Run $agent on issue #$issue." "$issue" \
        || emit_event "$name" "$issue" "$agent" error
      [ "$counts" = "true" ] && compare_phase "$issue"
    done
}

# acquire_lock <name> — portable single-instance guard via atomic mkdir.
# Exits the calling script with code 75 (EX_TEMPFAIL) if another holder
# is alive; takes over a stale lock whose pid no longer exists. Auto-
# released on EXIT/INT/TERM via trap.
acquire_lock() {
  local name="$1"
  local lock="$LOSWF_STATE_DIR/$name.lock"
  if mkdir "$lock" 2>/dev/null; then
    :
  else
    local other=""
    [ -r "$lock/pid" ] && other=$(cat "$lock/pid" 2>/dev/null || true)
    if [ -n "$other" ] && kill -0 "$other" 2>/dev/null; then
      log "$name: another instance is running (pid=$other) — exiting"
      exit 75
    fi
    log "$name: stale lock from pid=${other:-unknown} — taking over"
    rm -rf "$lock"
    mkdir "$lock" || { log "$name: failed to acquire lock"; exit 75; }
  fi
  echo $$ > "$lock/pid"
  # shellcheck disable=SC2064
  trap "rm -rf '$lock'" EXIT INT TERM
}
