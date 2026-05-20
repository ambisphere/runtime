#!/usr/bin/env bash
# doctor.sh — preflight check for loswf prerequisites.
# Run before installing into a new repo or before kicking off the first ADW.
#
# Usage: ./bin/doctor.sh

set -uo pipefail

PASS="✓"
FAIL="✗"
WARN="!"
exit_code=0

check() {
  local name="$1" cmd="$2" required="${3:-required}"
  if eval "$cmd" >/dev/null 2>&1; then
    printf '  %s %s\n' "$PASS" "$name"
  else
    if [ "$required" = "optional" ]; then
      printf '  %s %s (optional)\n' "$WARN" "$name"
    else
      printf '  %s %s\n' "$FAIL" "$name"
      exit_code=1
    fi
  fi
}

echo "loswf doctor — checking prerequisites"
echo

echo "Required tools:"
check "claude (Claude Code CLI)" "command -v claude"
check "gh (GitHub CLI)"           "command -v gh"
check "git ≥ 2.40 (worktrees)"    "git --version | awk '{print \$3}' | awk -F. '{exit !(\$1 > 2 || (\$1 == 2 && \$2 >= 40))}'"
check "bash"                      "command -v bash"
check "python3"                   "command -v python3"

echo
echo "Authentication:"
check "gh authenticated"          "gh auth status"
check "claude authenticated"      "claude --version"

echo
echo "Repo state:"
check "in a git repo"             "git rev-parse --show-toplevel"
check ".claude/ present"          "[ -d .claude ]"
check ".claude/agents/ has files" "ls .claude/agents/*.md"
check ".claude/settings.json"     "[ -f .claude/settings.json ]"
check "post-agent hook wired (Stop/SubagentStop)" \
  "python3 -c \"import json,sys; s=json.load(open('.claude/settings.json')); hooks=s.get('hooks',{}); ok=any('loswf_post_agent.py' in (h.get('command','') or '') for k in ('Stop','SubagentStop') for entry in hooks.get(k,[]) or [] for h in entry.get('hooks',[]) or []); sys.exit(0 if ok else 1)\""
check ".loswf/config.yaml"        "[ -f .loswf/config.yaml ]"
check "adws/ present"             "[ -d adws ]"

echo
echo "Semantic index:"
check "qdrant reachable"  "curl -sf http://localhost:6333/healthz"
check "ollama reachable"  "curl -sf http://localhost:11434/api/tags"

# index-present: branch on exit code first, parse JSON only on success.
idx_json=$(bin/loswf-index status 2>/dev/null)
idx_rc=$?
if [ "$idx_rc" -ne 0 ]; then
  printf '  %s %s\n' "$FAIL" "index-present: not configured (run setup or add code_search: block)"
  echo "    → run: bin/loswf-index init    (or 'update' if already initialized)"
  echo "    → see: specs/SRS.md §4.7"
  exit_code=1
elif printf '%s' "$idx_json" | python3 -c 'import json,sys; s=json.load(sys.stdin); sys.exit(0 if s.get("symbols",0) > 0 and s.get("upToDate") else 1)' 2>/dev/null; then
  printf '  %s %s\n' "$PASS" "index-present"
else
  printf '  %s %s\n' "$FAIL" "index-present: empty or stale"
  echo "    → run: bin/loswf-index update"
  echo "    → see: specs/SRS.md §4.7"
  exit_code=1
fi

echo
echo "Optional integrations:"
check "ngrok / cloudflared (AFK)" "command -v ngrok || command -v cloudflared" optional

echo
echo "GitHub repo readiness:"
if gh repo view --json name >/dev/null 2>&1; then
  repo=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
  echo "  $PASS gh sees current repo: $repo"
  label_count=$(gh label list --limit 200 --json name --jq '[.[] | select(.name | startswith("factory:"))] | length' 2>/dev/null || echo 0)
  if [ "$label_count" -ge 27 ]; then
    echo "  $PASS factory:* labels present ($label_count)"
  else
    echo "  $WARN factory:* labels missing ($label_count/27) — run: ./bin/bootstrap-labels.sh"
  fi
else
  echo "  $WARN no GitHub remote detected — gh repo view failed"
fi

echo
if [ "$exit_code" -eq 0 ]; then
  echo "doctor: ready"
else
  echo "doctor: prerequisites missing — fix the $FAIL items above"
fi
exit "$exit_code"
