#!/usr/bin/env bash
# bootstrap-labels.sh — create the loswf2 factory:* label vocabulary on a GitHub repo.
# Idempotent: re-running updates color/description without erroring on duplicates.
#
# Usage: ./bin/bootstrap-labels.sh [<owner>/<repo>]
#   If no repo arg given, uses the current directory's default remote.
#
# Note: `factory:parent:<num>` and `factory:depends-on:<num>` are dynamic label
# families created on demand by `.claude/agents/loswf-decomposer.md` via
# `gh label create --force`. They are not listed here.

set -euo pipefail

REPO="${1:-}"
GH_ARGS=()
[ -n "$REPO" ] && GH_ARGS+=(--repo "$REPO")

# label_name|color (hex, no #)|description
LABELS=$(cat <<'EOF'
factory:type:feature|0e8a16|Net-new capability
factory:type:bug|d93f0b|Defect against shipped behavior
factory:type:spike|d876e3|Time-boxed technical exploration with findings deliverable
factory:type:investigate|d876e3|Technical question requiring code investigation
factory:type:research|6f42c1|Open-ended research study — surveys topic, runs experiments, produces Atomic Research artifacts
factory:type:chore|c2e0c6|Maintenance, dep bumps, small cleanups
factory:type:refactor|fbca04|Internal restructuring, no behavior change
factory:type:docs|0075ca|Documentation only
factory:size:xs|c5def5|Single file, <30 LoC
factory:size:s|c5def5|Single module, <200 LoC
factory:size:m|bfd4f2|Multiple files, <500 LoC
factory:size:l|9ec5f5|Cross-module, design needed
factory:size:xl|7aa9f0|Multi-day, must re-slice before building
factory:phase:triage|ededed|Intake processing
factory:phase:investigating|fef2c0|Investigator reproducing/scouting before sizing
factory:phase:researching|6f42c1|Researcher running experiments + synthesizing atomic findings
factory:phase:product|fbca04|Product agent authoring PRD v1 from Brief + Research Findings + User Scenarios
factory:phase:planning|fef2c0|Planner producing plan
factory:phase:red-team|ff7f7f|Red-team adversarial gate before plan approval
factory:phase:plan-review|fef2c0|Plan-reviewer validating
factory:phase:decomposing|fef2c0|Decomposer splitting plan into sub-issues
factory:phase:awaiting-children|ededed|Parent blocked on sub-issue completion
factory:phase:building|d4c5f9|Builder implementing
factory:phase:review|c5def5|Reviewer evaluating PR
factory:phase:ship|0e8a16|Approved, awaiting merge
factory:phase:rollup|0e8a16|Merged, documenter pending
factory:phase:done|cccccc|Complete
factory:status:needs-clarification|fbca04|Awaiting human answer
factory:status:not-a-bug|c2e0c6|Investigator could not reproduce; not a defect
factory:status:needs-attention|b60205|Pipeline halted, human triage required
factory:status:human-only|e99695|Genuinely human-gated blocker — credentials, external API, product call
factory:status:healing|f9d0c4|Escalation attempting repair
factory:status:blocked|d93f0b|Waiting on external dependency
factory:hold|000000|Pause all factory automation on this issue
factory:roadmap|0052cc|Roadmap tracker issue
factory:curator-proposals|5319e7|Curator proposals tracker
EOF
)

count=0
existing_labels() {
  gh label list ${GH_ARGS[@]+"${GH_ARGS[@]}"} --limit 200 2>/dev/null | awk 'NF {print $1}'
}

while IFS='|' read -r name color desc; do
  [ -z "$name" ] && continue
  if existing_labels | grep -Fxq "$name"; then
    gh label edit "$name" ${GH_ARGS[@]+"${GH_ARGS[@]}"} --color "$color" --description "$desc" >/dev/null
    echo "  updated: $name"
  else
    gh label create "$name" ${GH_ARGS[@]+"${GH_ARGS[@]}"} --color "$color" --description "$desc" >/dev/null
    echo "  created: $name"
  fi
  count=$((count + 1))
done <<< "$LABELS"

echo "done — $count labels reconciled"
