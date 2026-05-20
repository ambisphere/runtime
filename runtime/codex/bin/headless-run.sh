#!/usr/bin/env bash
# Codex headless runtime runner for ADW orchestration.
#
# Current scope:
# - invoke `codex exec` with a bounded LOSWF phase prompt
# - request a final JSON object shaped like the shared phase receipt schema
# - persist the final receipt under .loswf/state/receipts/
# - synthesize a failure receipt when Codex is unavailable or returns invalid data

set -euo pipefail

agent="$1"
prompt="$2"
issue="${3:-0}"
hook_agent="${4:-$1}"

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
STATE_DIR="${LOSWF_STATE_DIR:-.loswf/state}"
SCHEMA=""
RUN_ID="${LOSWF_RUN_ID:-$(python3 - <<'PY'
import uuid
print(uuid.uuid4())
PY
)}"

mkdir -p "$STATE_DIR"

phase_for_agent() {
  case "$1" in
    loswf-builder|builder) printf 'build\n' ;;
    loswf-reviewer|reviewer) printf 'review\n' ;;
    loswf-setup|setup) printf 'setup\n' ;;
    loswf-planner|planner) printf 'planning\n' ;;
    loswf-plan-reviewer|plan-reviewer) printf 'plan-review\n' ;;
    loswf-curator|curator) printf 'curator\n' ;;
    loswf-harvester|harvester) printf 'harvest\n' ;;
    loswf-ship|ship) printf 'ship\n' ;;
    *) printf '%s\n' "${1#loswf-}" ;;
  esac
}

read_repo() {
  if [ -f .loswf/config.yaml ]; then
    awk '/^[[:space:]]*repo:[[:space:]]*/ {print $2; exit}' .loswf/config.yaml 2>/dev/null || true
  fi
}

find_schema() {
  local candidate
  for candidate in \
    "$ROOT/factory/schemas/phase-receipt.schema.json" \
    "$ROOT/.loswf/schemas/phase-receipt.schema.json"
  do
    if [ -f "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

receipt_dir="$STATE_DIR/receipts/$RUN_ID"
phase="$(phase_for_agent "$hook_agent")"
receipt_file="$receipt_dir/${phase}-${issue}.json"
event_file="$receipt_dir/${phase}-${issue}.jsonl"
stderr_file="$receipt_dir/${phase}-${issue}.stderr"
last_message_file="$receipt_dir/${phase}-${issue}.last-message.json"
ledger_file="$STATE_DIR/receipts.jsonl"
repo="$(read_repo)"
repo="${repo:-unknown/unknown}"
issue_title="Issue #$issue"
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

mkdir -p "$receipt_dir"

append_receipt_to_ledger() {
  python3 - "$receipt_file" "$ledger_file" <<'PY'
import pathlib
import sys

receipt_path = pathlib.Path(sys.argv[1])
ledger_path = pathlib.Path(sys.argv[2])
ledger_path.parent.mkdir(parents=True, exist_ok=True)
with receipt_path.open("r", encoding="utf-8") as src, ledger_path.open("a", encoding="utf-8") as dst:
    dst.write(src.read().strip())
    dst.write("\n")
PY
}

write_synthetic_receipt() {
  local status="$1"
  local transition_hint="$2"
  local needs_human="$3"
  local summary="$4"
  local warning="${5:-}"
  local completed_at
  completed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  python3 - "$receipt_file" "$RUN_ID" "$repo" "$issue" "$issue_title" "$phase" "$hook_agent" "$status" "$summary" "$transition_hint" "$needs_human" "$started_at" "$completed_at" "$warning" <<'PY'
import json
import sys
import uuid

path = sys.argv[1]
run_id = sys.argv[2]
repo = sys.argv[3]
issue = int(sys.argv[4])
issue_title = sys.argv[5]
phase = sys.argv[6]
role = sys.argv[7]
status = sys.argv[8]
summary = sys.argv[9]
transition_hint = sys.argv[10]
needs_human = sys.argv[11].lower() == "true"
started_at = sys.argv[12]
completed_at = sys.argv[13]
warning = sys.argv[14]

payload = {
    "schema_version": "1",
    "receipt_id": str(uuid.uuid4()),
    "run_id": run_id,
    "runtime": "codex",
    "mode": "headless",
    "repo": repo,
    "issue": {
        "number": issue,
        "title": issue_title,
    },
    "phase": phase,
    "role": role,
    "status": status,
    "summary": summary,
    "transition_hint": transition_hint,
    "needs_human": needs_human,
    "artifacts": [],
    "validator_results": [],
    "warnings": [warning] if warning else [],
    "started_at": started_at,
    "completed_at": completed_at,
}

with open(path, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2)
    fh.write("\n")
PY
  append_receipt_to_ledger
}

build_instruction() {
  cat <<EOF
You are running one bounded LOSWF phase in headless Codex mode.

Carry out the requested work inside the current repository and return ONLY one
JSON object that satisfies the provided schema.

Use these exact facts in the final receipt unless the work itself proves they
are wrong:
- schema_version: "1"
- run_id: "$RUN_ID"
- runtime: "codex"
- mode: "headless"
- repo: "$repo"
- issue.number: $issue
- issue.title: "$issue_title"
- phase: "$phase"
- role: "$hook_agent"

Receipt guidance:
- keep summary concise and factual
- use transition_hint to suggest what the reconciler should inspect next
- record only artifacts and validator results that actually happened
- use needs_human=true only if operator intervention is required

Bounded task:
Use the $agent role. $prompt
EOF
}

SCHEMA="$(find_schema || true)"

if [ -z "$SCHEMA" ] || [ ! -f "$SCHEMA" ]; then
  printf 'loswf: missing phase receipt schema at %s\n' "$SCHEMA" >&2
  write_synthetic_receipt failed blocked true \
    "Unable to launch Codex headless phase because the receipt schema is missing." \
    "missing phase receipt schema"
  exit 70
fi

if ! command -v codex >/dev/null 2>&1; then
  printf 'loswf: codex CLI not found on PATH\n' >&2
  write_synthetic_receipt failed blocked true \
    "Unable to launch Codex headless phase because the codex CLI is unavailable." \
    "codex CLI not found on PATH"
  exit 69
fi

instruction="$(build_instruction)"
rc=0
LOSWF_CURRENT_AGENT="$hook_agent" LOSWF_CURRENT_ISSUE="$issue" \
  codex exec \
    --full-auto \
    -C "$PWD" \
    --json \
    --output-schema "$SCHEMA" \
    --output-last-message "$last_message_file" \
    "$instruction" >"$event_file" 2>"$stderr_file" || rc=$?

if [ "$rc" -ne 0 ]; then
  printf 'loswf: codex exec failed with exit %s\n' "$rc" >&2
  write_synthetic_receipt failed retry true \
    "Codex headless phase execution failed before producing a valid receipt." \
    "codex exec exited non-zero"
  exit "$rc"
fi

if ! python3 -m json.tool "$last_message_file" >/dev/null 2>&1; then
  printf 'loswf: codex exec did not produce valid JSON receipt output\n' >&2
  write_synthetic_receipt failed retry true \
    "Codex headless phase execution completed without a valid JSON receipt." \
    "invalid codex final JSON output"
  exit 65
fi

cp "$last_message_file" "$receipt_file"
append_receipt_to_ledger
