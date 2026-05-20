#!/usr/bin/env python3
# =====================================================================
# LOCAL-OVERRIDE — DO NOT BLINDLY OVERWRITE ON PLUGIN UPGRADE
# ---------------------------------------------------------------------
# This file is the plugin-managed shared reconciler, **but** this host
# repo (ambisphere/runtime) has been customized for `mode: greenfield`
# in .loswf/config.yaml. The greenfield additions are:
#
#   * post_intake routes every type to `researching` when the issue
#     lacks a <!-- loswf:research:complete --> marker comment.
#   * NEW dispatcher `post_researcher` (loswf-researcher): on a
#     <!-- loswf:research:complete --> comment, route → `product`.
#   * NEW dispatcher `post_product` (loswf-product): on a
#     <!-- loswf:product:prd-v1 --> or <!-- loswf:product:signoff -->
#     comment, route → `planning` (feature) or `decomposing`
#     (bug / chore / refactor / docs).
#   * post_investigator in greenfield routes a CONFIRMED bug/spike
#     through `product` first (not straight to `decomposing`) so even
#     technical spikes pass a product gate.
#
# All greenfield branches are gated on `_router_mode() == "greenfield"`
# so a future plugin upgrade that uses git's three-way merge will see
# the unmodified `standard` paths intact.
#
# Re-applying this override after a plugin refresh:
#   - Look for the three GREENFIELD blocks below (search "GREENFIELD").
#   - Re-apply them on top of the upstream file.
#   - Ensure `loswf-researcher` and `loswf-product` remain in DISPATCH.
#
# See .loswf/plugin-managed for the override pin record.
# =====================================================================
"""Stop / SubagentStop hook — deterministic factory:phase transitions.

After each agent run (ADW-driven or interactive Task-tool invocation),
observe repo state (gh issue, gh pr, git diff) and apply the correct
transition. Agents stay strategic; this hook owns state.

Identification — two paths:

  1. ADW path: $LOSWF_CURRENT_AGENT + $LOSWF_CURRENT_ISSUE are set by
     `adws/_lib.sh::run_subagent`. Preferred when present.
  2. Interactive path: stdin payload includes `transcript_path`. The hook
     scans the JSONL backward for the most recent completed Agent tool_use,
     extracts `subagent_type` and parses the issue number from
     `description` (e.g. "Intake #238", "Plan #96"). Dispatches once per
     tool_use_id; a dedupe ledger at `.loswf/state/dispatched.jsonl`
     prevents re-dispatch across Stop and SubagentStop firings.

This hook runs gh/git directly as subprocesses, so it bypasses the
PreToolUse label_transition validator by design — that validator constrains
agents; the orchestrator computes the truth.

Hook wiring (in .claude/settings.json under Stop **and** SubagentStop):
  {"type": "command", "command": ".claude/hooks/loswf_post_agent.py"}
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

STATE_DIR = Path(os.environ.get("LOSWF_STATE_DIR", ".loswf/state"))
EVENT_LOG = STATE_DIR / "events.jsonl"
CONFIG_PATH = Path(".loswf/config.yaml")


def gh_json(args):
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def get_phase(issue):
    data = gh_json(["issue", "view", str(issue), "--json", "labels"])
    if not data:
        return None
    for l in data.get("labels", []):
        if l["name"].startswith("factory:phase:"):
            return l["name"].split(":")[-1]
    return None


def get_parent(issue):
    """Return the int from a `factory:parent:<num>` label, or None."""
    data = gh_json(["issue", "view", str(issue), "--json", "labels"])
    if not data:
        return None
    for l in data.get("labels", []):
        if l["name"].startswith("factory:parent:"):
            try:
                return int(l["name"].split(":")[-1])
            except ValueError:
                return None
    return None


def set_phase(issue, new):
    cur = get_phase(issue)
    args = ["issue", "edit", str(issue)]
    if cur and cur != new:
        args += ["--remove-label", f"factory:phase:{cur}"]
    args += ["--add-label", f"factory:phase:{new}"]
    subprocess.run(["gh", *args], capture_output=True)


def add_label(issue, label):
    subprocess.run(
        ["gh", "issue", "edit", str(issue), "--add-label", label],
        capture_output=True,
    )


def find_open_pr(issue):
    data = gh_json([
        "pr", "list", "--search", f"linked:{issue}", "--state", "open",
        "--json", "number,headRefName,reviewDecision",
    ])
    return data[0] if data else None


def find_merged_pr(issue):
    data = gh_json([
        "pr", "list", "--search", f"linked:{issue}", "--state", "merged",
        "--json", "number",
    ])
    return data[0] if data else None


def factory_branch(issue):
    r = subprocess.run(
        ["git", "branch", "--list", f"factory/{issue}-*"],
        capture_output=True, text=True,
    )
    line = r.stdout.strip().splitlines()[0:1]
    if not line:
        return None
    return line[0].strip().lstrip("* ").strip()


def default_branch():
    """Return configured default branch from .loswf/config.yaml, else main."""
    try:
        for raw in CONFIG_PATH.read_text().splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line or not line.startswith("branch:"):
                continue
            value = line.split(":", 1)[1].strip().strip('"').strip("'")
            return value or "main"
    except Exception:
        pass
    return "main"


def branch_has_diff(branch):
    """True if <branch> differs from origin/<configured branch>."""
    base = default_branch()
    r = subprocess.run(
        ["git", "diff", "--quiet", f"origin/{base}...{branch}"],
        capture_output=True,
    )
    return r.returncode != 0


def emit(phase, issue, agent, outcome, details=None):
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        rec = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "phase": phase, "issue": issue, "agent": agent, "outcome": outcome,
        }
        if details:
            rec.update(details)
        with open(EVENT_LOG, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass


# ---------- per-agent dispatchers ---------------------------------------

INVESTIGATING_TYPES = ("bug", "spike", "investigate")

# --- GREENFIELD: router mode + research/product markers -----------------
# `mode: greenfield` in .loswf/config.yaml inserts a research → product
# gate ahead of planning/decomposing so concept-stage repos can't skip
# discovery. See the LOCAL-OVERRIDE banner at the top of this file.
RESEARCH_COMPLETE_MARKER = "<!-- loswf:research:complete -->"
PRODUCT_PRD_V1_MARKER = "<!-- loswf:product:prd-v1 -->"
PRODUCT_SIGNOFF_MARKER = "<!-- loswf:product:signoff -->"

# Types that need a plan after product sign-off; everything else
# (bug/chore/refactor/docs) skips planning and goes straight to
# decomposing.
PLANNING_TYPES = ("feature",)


def _router_mode() -> str:
    """Return `mode:` from .loswf/config.yaml, default `standard`."""
    try:
        for raw in CONFIG_PATH.read_text().splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line or not line.startswith("mode:"):
                continue
            value = line.split(":", 1)[1].strip().strip('"').strip("'")
            return value or "standard"
    except Exception:
        pass
    return "standard"


def _issue_types(issue) -> list[str]:
    """Return all `factory:type:*` suffixes on the issue."""
    data = gh_json(["issue", "view", str(issue), "--json", "labels"]) or {}
    return [
        l["name"].split(":")[-1]
        for l in data.get("labels", [])
        if l["name"].startswith("factory:type:")
    ]


def _has_marker(issue, marker: str) -> bool:
    """True iff any comment on the issue contains `marker`."""
    data = gh_json(["issue", "view", str(issue), "--json", "comments"]) or {}
    for c in data.get("comments", []):
        if marker in (c.get("body") or ""):
            return True
    return False


def _route_after_product(issue, types: list[str]):
    """Greenfield post-product routing: planning for features,
    decomposing otherwise."""
    if any(t in PLANNING_TYPES for t in types):
        set_phase(issue, "planning")
        return ("planning", "product-signoff")
    set_phase(issue, "decomposing")
    return ("decomposing", "product-signoff")
# --- END GREENFIELD additions -------------------------------------------


def post_intake(issue):
    data = gh_json(["issue", "view", str(issue), "--json", "labels"]) or {}
    names = {l["name"] for l in data.get("labels", [])}
    types = [
        n.split(":")[-1] for n in names if n.startswith("factory:type:")
    ]
    if not types:
        add_label(issue, "factory:status:needs-clarification")
        return ("triage", "missing-type")
    # --- GREENFIELD: insert research gate ahead of every type unless the
    # issue already carries a research-complete marker. Investigation-type
    # issues still bypass to `investigating` because they need
    # reproduction first; their post-investigator transition is the one
    # that picks up the product gate (see post_investigator below).
    if _router_mode() == "greenfield":
        if any(t in INVESTIGATING_TYPES for t in types):
            set_phase(issue, "investigating")
            return ("investigating", "ok")
        if not _has_marker(issue, RESEARCH_COMPLETE_MARKER):
            set_phase(issue, "researching")
            return ("researching", "greenfield-research-gate")
        # Research already complete (e.g. re-triaged issue) — fall through
        # to the post-product router so the product gate still applies.
        set_phase(issue, "product")
        return ("product", "greenfield-product-gate")
    # --- END GREENFIELD ---
    if any(t in INVESTIGATING_TYPES for t in types):
        set_phase(issue, "investigating")
        return ("investigating", "ok")
    set_phase(issue, "planning")
    return ("planning", "ok")


# --- GREENFIELD: research synthesis dispatcher --------------------------
def post_researcher(issue):
    """Greenfield-only: researcher synthesizes findings → route to
    `product`. Requires <!-- loswf:research:complete --> on the issue."""
    if _router_mode() != "greenfield":
        # No-op outside greenfield; researcher is not part of the standard
        # pipeline. Surface to a human if invoked unexpectedly.
        add_label(issue, "factory:status:needs-attention")
        return ("researching", "researcher-outside-greenfield")
    if _has_marker(issue, RESEARCH_COMPLETE_MARKER):
        set_phase(issue, "product")
        return ("product", "research-complete")
    add_label(issue, "factory:status:needs-attention")
    return ("researching", "no-research-complete-marker")


# --- GREENFIELD: product sign-off dispatcher ----------------------------
def post_product(issue):
    """Greenfield-only: product agent posts PRD-v1 or sign-off → route to
    `planning` (feature) or `decomposing` (anything else)."""
    if _router_mode() != "greenfield":
        add_label(issue, "factory:status:needs-attention")
        return ("product", "product-outside-greenfield")
    if (
        _has_marker(issue, PRODUCT_PRD_V1_MARKER)
        or _has_marker(issue, PRODUCT_SIGNOFF_MARKER)
    ):
        return _route_after_product(issue, _issue_types(issue))
    add_label(issue, "factory:status:needs-attention")
    return ("product", "no-prd-or-signoff-marker")
# --- END GREENFIELD dispatchers -----------------------------------------


INVESTIGATION_CONFIRMED = "<!-- loswf:investigation:confirmed -->"
INVESTIGATION_NOT_REPRO = "<!-- loswf:investigation:not-reproducible -->"
INVESTIGATION_TYPE_MISMATCH_PREFIX = "<!-- loswf:investigation:type-mismatch:"


def post_investigator(issue):
    data = gh_json(["issue", "view", str(issue), "--json", "comments"]) or {}
    comments = data.get("comments", [])
    for c in reversed(comments):
        body = c.get("body") or ""
        if INVESTIGATION_CONFIRMED in body:
            # --- GREENFIELD: route confirmed investigations through the
            # product gate first so even technical spikes get a product
            # decision before decomposition. If research was already done
            # by an earlier pass, the issue may carry a research-complete
            # marker — still route to `product`, never skip the gate.
            if _router_mode() == "greenfield":
                set_phase(issue, "product")
                return ("product", "confirmed-greenfield-product-gate")
            # --- END GREENFIELD ---
            set_phase(issue, "decomposing")
            return ("decomposing", "confirmed")
        if INVESTIGATION_NOT_REPRO in body:
            add_label(issue, "factory:status:not-a-bug")
            add_label(issue, "factory:status:needs-attention")
            return ("investigating", "not-reproducible")
        idx = body.find(INVESTIGATION_TYPE_MISMATCH_PREFIX)
        if idx != -1:
            tail = body[idx + len(INVESTIGATION_TYPE_MISMATCH_PREFIX):]
            end = tail.find("-->")
            new_type = tail[:end].strip() if end != -1 else ""
            if new_type:
                subprocess.run(
                    [
                        "gh", "issue", "edit", str(issue),
                        "--remove-label", "factory:type:bug",
                        "--remove-label", "factory:type:spike",
                        "--remove-label", "factory:type:investigate",
                        "--add-label", f"factory:type:{new_type}",
                    ],
                    capture_output=True,
                )
                # --- GREENFIELD: re-typed issue picks up the same gates
                # as a fresh intake; route to `researching` unless
                # research is already complete.
                if _router_mode() == "greenfield":
                    if _has_marker(issue, RESEARCH_COMPLETE_MARKER):
                        set_phase(issue, "product")
                        return ("product", f"retyped-{new_type}")
                    set_phase(issue, "researching")
                    return ("researching", f"retyped-{new_type}")
                # --- END GREENFIELD ---
                set_phase(issue, "planning")
                return ("planning", f"retyped-{new_type}")
    add_label(issue, "factory:status:needs-attention")
    return ("investigating", "no-verdict")


PLAN_MARKER = "<!-- loswf:plan -->"
REVISION_BUDGET = int(os.environ.get("LOSWF_REVISION_BUDGET", "3"))
BUDGET_MARKER = "<!-- loswf:budget-exhausted -->"


def post_final_feedback(issue_or_pr_args, last_feedback, kind):
    body = (
        f"{BUDGET_MARKER}\n"
        f"## Revision budget exhausted ({REVISION_BUDGET} rounds) — {kind}\n\n"
        f"Last reviewer feedback:\n\n{last_feedback}\n\n"
        f"Needs human review."
    )
    subprocess.run(
        ["gh", *issue_or_pr_args, "--body", body], capture_output=True,
    )


def post_planner(issue):
    # Authoritative transport: an issue comment whose body begins with the
    # loswf:plan marker. Local specs/drafts/*.md is a convenience copy that
    # lives inside the planner's worktree and won't survive to the next agent.
    data = gh_json(["issue", "view", str(issue), "--json", "comments"]) or {}
    for c in data.get("comments", []):
        if PLAN_MARKER in (c.get("body") or ""):
            set_phase(issue, "plan-review")
            return ("plan-review", "plan-comment")
    add_label(issue, "factory:status:needs-attention")
    return ("planning", "no-plan-produced")


def post_plan_reviewer(issue):
    data = gh_json(["issue", "view", str(issue), "--json", "comments"]) or {}
    comments = data.get("comments", [])
    if not comments:
        add_label(issue, "factory:status:needs-attention")
        return ("plan-review", "no-verdict-comment")
    last = comments[-1]["body"].lower()[:200]
    if "approved" in last:
        set_phase(issue, "decomposing")
        return ("decomposing", "approved")
    if "rejected" in last or "revise" in last or "changes requested" in last:
        rejections = sum(
            1 for c in comments
            if any(k in (c.get("body") or "").lower()[:200]
                   for k in ("rejected", "revise", "changes requested"))
        )
        if rejections >= REVISION_BUDGET:
            post_final_feedback(
                ["issue", "comment", str(issue)],
                comments[-1]["body"], "plan-review",
            )
            add_label(issue, "factory:status:needs-attention")
            return ("plan-review", f"budget-exhausted-{rejections}")
        set_phase(issue, "planning")
        return ("planning", f"rejected-{rejections}")
    add_label(issue, "factory:status:needs-attention")
    return ("plan-review", "ambiguous-verdict")


def post_decomposer(issue):
    children = gh_json([
        "issue", "list", "--search",
        f'label:"factory:parent:{issue}"',
        "--state", "all", "--json", "number,labels",
    ]) or []
    # TODO: spike short-circuit — a confirmed spike with findings but no
    # code change legitimately produces 0 children; add a path that routes
    # these to done/rollup instead of needs-attention.
    if len(children) < 2:
        add_label(issue, "factory:status:needs-attention")
        return ("decomposing", f"only-{len(children)}-subtasks")
    set_phase(issue, "awaiting-children")
    return ("awaiting-children", f"spawned-{len(children)}")


def check_parent_rollup(parent):
    """Advance parent from awaiting-children → rollup if all children are done."""
    children = gh_json([
        "issue", "list", "--search",
        f'label:"factory:parent:{parent}"',
        "--state", "all", "--json", "number,labels",
    ]) or []
    if not children:
        return False
    for c in children:
        phases = [
            l["name"].split(":")[-1] for l in c.get("labels", [])
            if l["name"].startswith("factory:phase:")
        ]
        if not phases or phases[0] != "done":
            return False
    set_phase(parent, "rollup")
    return True


def post_builder(issue):
    branch = factory_branch(issue)
    if not branch:
        set_phase(issue, "rollup")
        return ("rollup", "no-branch-no-op")
    if not branch_has_diff(branch):
        set_phase(issue, "rollup")
        return ("rollup", "no-diff-no-op")
    pr = find_open_pr(issue)
    if pr:
        set_phase(issue, "review")
        return ("review", f"pr-{pr['number']}")
    add_label(issue, "factory:status:needs-attention")
    return ("building", "diff-but-no-pr")


def post_reviewer(issue):
    pr = find_open_pr(issue)
    if not pr:
        add_label(issue, "factory:status:needs-attention")
        return ("review", "no-pr")
    # Route off the latest sentinel PR comment — `gh pr review --approve`
    # fails with self-approval when builder+reviewer share one identity.
    data = gh_json([
        "pr", "view", str(pr["number"]), "--json", "comments",
    ]) or {}
    verdict = None
    for c in reversed(data.get("comments", [])):
        body = (c.get("body") or "").lstrip().lower()
        for kw in ("approved:", "rejected:", "block:"):
            if body.startswith(kw):
                verdict = kw[:-1]
                break
        if verdict:
            break
    if verdict == "approved":
        set_phase(issue, "ship")
        return ("ship", f"approved-pr-{pr['number']}")
    if verdict == "rejected":
        rejections = sum(
            1 for c in data.get("comments", [])
            if (c.get("body") or "").lstrip().lower().startswith("rejected:")
        )
        if rejections >= REVISION_BUDGET:
            post_final_feedback(
                ["pr", "comment", str(pr["number"])],
                next(
                    (c["body"] for c in reversed(data.get("comments", []))
                     if (c.get("body") or "").lstrip().lower().startswith("rejected:")),
                    "",
                ),
                "review",
            )
            add_label(issue, "factory:status:needs-attention")
            return ("review", f"budget-exhausted-{rejections}")
        set_phase(issue, "building")
        return ("building", f"rejected-{rejections}")
    if verdict == "block":
        add_label(issue, "factory:status:needs-attention")
        return ("review", "blocked")
    return ("review", "pending-no-verdict")


def post_ship(issue):
    pr = find_merged_pr(issue)
    if pr:
        set_phase(issue, "rollup")
        return ("rollup", f"merged-pr-{pr['number']}")
    add_label(issue, "factory:status:needs-attention")
    return ("ship", "merge-failed")


def post_documenter(issue):
    set_phase(issue, "done")
    subprocess.run(["gh", "issue", "close", str(issue)], capture_output=True)
    # If this issue is a decomposition child, check whether the parent can
    # advance awaiting-children → rollup.
    parent = get_parent(issue)
    if parent:
        check_parent_rollup(parent)
    return ("done", "closed")


# Keys stay `loswf-*` (not `loswf:*`) after the plugin rename in #31.
# `LOSWF_CURRENT_AGENT` is set by `adws/_lib.sh::run_subagent`, which passes
# the embed-install agent name (project-scope) regardless of whether the
# operator also installed the user-scope plugin. ADWs run against the embed
# surface; the plugin is user-scope only. Don't add `loswf:*` aliases here.
DISPATCH = {
    "loswf-intake":        post_intake,
    "loswf-investigator":  post_investigator,
    "loswf-planner":       post_planner,
    "loswf-plan-reviewer": post_plan_reviewer,
    "loswf-decomposer":    post_decomposer,
    "loswf-builder":       post_builder,
    "loswf-reviewer":      post_reviewer,
    "loswf-ship":          post_ship,
    "loswf-documenter":    post_documenter,
    # GREENFIELD-only dispatchers — guarded internally by _router_mode().
    "loswf-researcher":    post_researcher,
    "loswf-product":       post_product,
    # loswf-architect, loswf-harvester, loswf-curator, loswf-designer,
    # loswf-escalation, loswf-red-team, loswf-scout, loswf-setup — no transition.
    # (Setup configures the host repo itself; it is not a pipeline phase.)
}


DISPATCHED_LEDGER = STATE_DIR / "dispatched.jsonl"


def _normalize_agent(name: str) -> str:
    """Normalize plugin/embed/bare agent names to DISPATCH keys.

    Accepts `loswf:intake`, `loswf-intake`, or bare `intake`; returns
    `loswf-intake`. Returns "" if the role is unknown.
    """
    if not name:
        return ""
    role = name.split(":", 1)[-1] if ":" in name else name
    if role.startswith("loswf-"):
        role = role[len("loswf-"):]
    key = f"loswf-{role}"
    return key if key in DISPATCH else ""


_ISSUE_RE = None
def _parse_issue(description: str) -> int | None:
    global _ISSUE_RE
    import re
    if _ISSUE_RE is None:
        _ISSUE_RE = re.compile(r"#(\d+)")
    if not description:
        return None
    m = _ISSUE_RE.search(description)
    return int(m.group(1)) if m else None


def _already_dispatched(tool_use_id: str) -> bool:
    if not tool_use_id or not DISPATCHED_LEDGER.exists():
        return False
    try:
        for line in DISPATCHED_LEDGER.read_text().splitlines():
            try:
                if json.loads(line).get("id") == tool_use_id:
                    return True
            except json.JSONDecodeError:
                continue
    except OSError:
        return False
    return False


def _mark_dispatched(tool_use_id: str, agent: str, issue: int) -> None:
    if not tool_use_id:
        return
    try:
        DISPATCHED_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with DISPATCHED_LEDGER.open("a") as f:
            f.write(json.dumps({
                "id": tool_use_id, "agent": agent, "issue": issue,
                "ts": int(time.time()),
            }) + "\n")
    except OSError:
        pass


def _scan_transcript(path: str) -> list[tuple[str, str, int]]:
    """Return completed, undispatched (tool_use_id, agent_key, issue) from
    the transcript. Only Agent tool_uses with a matching tool_result count
    as completed.
    """
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []

    tool_uses: dict[str, tuple[str, str]] = {}  # id → (subagent_type, description)
    completed: set[str] = set()
    try:
        for line in p.read_text().splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = ev.get("message") or {}
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            for c in content:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "tool_use" and c.get("name") == "Agent":
                    inp = c.get("input") or {}
                    tool_uses[c.get("id", "")] = (
                        inp.get("subagent_type", ""),
                        inp.get("description", ""),
                    )
                elif c.get("type") == "tool_result":
                    tid = c.get("tool_use_id", "")
                    if tid:
                        completed.add(tid)
    except OSError:
        return []

    out: list[tuple[str, str, int]] = []
    for tid, (subtype, desc) in tool_uses.items():
        if tid not in completed:
            continue
        if _already_dispatched(tid):
            continue
        agent_key = _normalize_agent(subtype)
        issue = _parse_issue(desc)
        if not agent_key or not issue:
            continue
        out.append((tid, agent_key, issue))
    return out


def _dispatch(agent: str, issue: int, source: str,
              tool_use_id: str = "") -> None:
    # Mark dispatched BEFORE running the subagent so concurrent Stop/SubagentStop
    # invocations that race on the same transcript cannot double-dispatch.
    # (Previously this was written after _dispatch, causing duplicate ledger entries
    # when SubagentStop fired multiple times before any write completed.)
    _mark_dispatched(tool_use_id, agent, issue)
    before = get_phase(issue)
    try:
        after, outcome = DISPATCH[agent](issue)
    except Exception as e:
        emit("post-agent", issue, agent, "error",
             {"error": str(e)[:300], "source": source})
        return
    emit("post-agent", issue, agent, "transition",
         {"before": before, "after": after, "result": outcome,
          "source": source})


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}

    # Path 1: ADW — env-var identification.
    agent = os.environ.get("LOSWF_CURRENT_AGENT", "")
    issue_str = os.environ.get("LOSWF_CURRENT_ISSUE", "")
    if agent and agent in DISPATCH and issue_str.isdigit():
        _dispatch(agent, int(issue_str), source="env")
        return 0

    # Path 2: interactive — transcript-based discovery. Fires on both Stop
    # (end-of-turn, possibly multiple completed subagents) and SubagentStop
    # (per-subagent). Dedupe via dispatched.jsonl ledger.
    transcript = ""
    if isinstance(payload, dict):
        transcript = payload.get("transcript_path") or ""
    for tool_use_id, agent_key, issue in _scan_transcript(transcript):
        _dispatch(agent_key, issue, source="transcript",
                  tool_use_id=tool_use_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
