#!/usr/bin/env bash
# Claude headless runtime runner for ADW orchestration.

set -euo pipefail

agent="$1"
prompt="$2"
issue="${3:-0}"
hook_agent="${4:-$1}"

LOSWF_CURRENT_AGENT="$hook_agent" LOSWF_CURRENT_ISSUE="$issue" \
  exec claude -p "Use the $agent subagent. $prompt" \
    --output-format stream-json \
    --verbose \
    --permission-mode default
