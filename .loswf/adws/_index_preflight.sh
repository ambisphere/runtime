#!/usr/bin/env bash
# _index_preflight.sh — fail-closed runtime gate for the semantic code index.
#
# Probes (in order, fast-fail):
#   1. .loswf/config.yaml and `code_search:` block present
#   2. Qdrant reachable at configured qdrant_url (/readyz)
#   3. Ollama reachable at configured ollama_url (/api/tags)
#   4. `bin/loswf-index status --json` returns metadata (symbols > 0, lastSha set)
#   5. metadata lastSha == current HEAD
#
# Exit codes:
#   0   all probes passed (or host-repo fail-open on missing config only)
#   78  EX_CONFIG — index unhealthy; one-line remediation on stderr
#
# Semantics:
#   Self-hosted (LOSWF_SELF_HOSTED=1): all probes fail-closed (exit 78).
#   Host repo:  missing `code_search:` block fails OPEN with stderr warn (exit 0);
#               reachability/staleness still fail CLOSED.
#
# Budget: <300ms happy path (warm). Callable from adws/_lib.sh run_subagent.
set -euo pipefail

CONFIG="${LOSWF_CONFIG:-.loswf/config.yaml}"
SELF_HOSTED="${LOSWF_SELF_HOSTED:-}"

warn() { printf 'preflight: %s\n' "$1" >&2; }
fail() { printf 'preflight: %s\n' "$1" >&2; exit 78; }

# Probe 1 — config + code_search block
if [ ! -f "$CONFIG" ]; then
  if [ "$SELF_HOSTED" = "1" ]; then
    fail "config file $CONFIG missing (self-hosted, fail-closed)"
  fi
  warn "config file $CONFIG missing — falling through (host repo, fail-open). See specs/SRS.md §4.7."
  exit 0
fi

parse=$(python3 - "$CONFIG" <<'PYEOF' 2>&1
import sys
try:
    import yaml
except ImportError:
    print("PYYAML_MISSING", file=sys.stderr)
    sys.exit(2)
try:
    with open(sys.argv[1]) as f:
        d = yaml.safe_load(f) or {}
except Exception as e:
    print(f"PARSE_FAIL:{e}", file=sys.stderr)
    sys.exit(3)
cs = d.get("code_search")
if not cs:
    print("NO_CODE_SEARCH")
    sys.exit(0)
print("OK")
print(cs.get("qdrant_url") or "http://localhost:6333")
print(cs.get("ollama_url") or "http://localhost:11434")
PYEOF
) || parse_rc=$?
parse_rc="${parse_rc:-0}"

if [ "$parse_rc" = "2" ]; then
  fail "pyyaml missing — pip install pyyaml"
fi
if [ "$parse_rc" = "3" ]; then
  fail "failed to parse $CONFIG: $parse"
fi

first_line=$(printf '%s\n' "$parse" | head -1)
if [ "$first_line" = "NO_CODE_SEARCH" ]; then
  if [ "$SELF_HOSTED" = "1" ]; then
    fail "code_search block missing in $CONFIG (self-hosted, fail-closed). See specs/SRS.md §4.7."
  fi
  warn "code_search block missing — falling through (host repo, fail-open). See specs/SRS.md §4.7."
  exit 0
fi

qdrant_url=$(printf '%s\n' "$parse" | sed -n '2p')
ollama_url=$(printf '%s\n' "$parse" | sed -n '3p')

# Probe 2 — Qdrant reachable
if ! curl --max-time 2 -fsS "$qdrant_url/readyz" >/dev/null 2>&1; then
  fail "Qdrant unreachable at $qdrant_url — docker compose -f .loswf/templates/docker-compose.yml.example up -d"
fi

# Probe 3 — Ollama reachable
if ! curl --max-time 2 -fsS "$ollama_url/api/tags" >/dev/null 2>&1; then
  fail "Ollama unreachable at $ollama_url — start ollama and run ollama pull <embed_model>"
fi

# Probe 4 — index metadata present
status_json=$(bin/loswf-index status 2>&1) || {
  fail "loswf-index status failed: $(printf '%s' "$status_json" | head -1)"
}

read -r symbols last_sha <<<"$(printf '%s' "$status_json" | python3 -c '
import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("0 ")
    sys.exit(0)
print(d.get("symbols", 0), d.get("lastSha") or "")
')"

if [ -z "${symbols:-}" ] || [ "$symbols" = "0" ] || [ -z "${last_sha:-}" ]; then
  fail "index metadata absent — run loswf-index init"
fi

# Probe 5 — metadata matches current HEAD. On divergence, attempt a
# synchronous auto-repair via `bin/loswf-index update`, then re-probe.
head_sha=$(git rev-parse HEAD 2>/dev/null || echo "")
if [ -n "$head_sha" ] && [ "$last_sha" != "$head_sha" ]; then
  warn "index stale (sha $last_sha vs HEAD $head_sha) — attempting auto-repair via loswf-index update"
  if ! bin/loswf-index update >/dev/null 2>&1; then
    fail "auto-repair failed — run loswf-index update manually"
  fi
  # Re-probe lastSha after the update.
  status_json=$(bin/loswf-index status 2>&1) || {
    fail "loswf-index status failed after update: $(printf '%s' "$status_json" | head -1)"
  }
  read -r _symbols2 last_sha2 <<<"$(printf '%s' "$status_json" | python3 -c '
import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("0 ")
    sys.exit(0)
print(d.get("symbols", 0), d.get("lastSha") or "")
')"
  if [ "$last_sha2" != "$head_sha" ]; then
    fail "index still stale after auto-repair (sha $last_sha2 vs HEAD $head_sha) — run loswf-index update manually"
  fi
fi

exit 0
