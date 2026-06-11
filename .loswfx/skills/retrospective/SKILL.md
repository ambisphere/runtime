---
name: retrospective
description: Read the workspace's ledger and produce a retrospective report covering recent capability runs, pipeline outcomes, halt patterns, escalations, and proposal-worthy drift signals. Use this skill at the close of an iteration, at the close of an engagement, or on demand when an operator wants to see "what's been happening." Output is a markdown report at proposals/<client>/retros/<timestamp>.md grounded entirely in ledger evidence — no speculation, no synthesis from outside the ledger. Use a different skill (proposal-promotion) to turn a retro's findings into tracked work items.
max_iterations: 60
side: shadow
output_dir: engagements/{repo}/retros
contract:
  kind: deliverable
  inputs:
    - kind: layer-3
      path: .loswf/state/ledger.jsonl
      required: true
  outputs:
    - path: engagements/{repo}/retros/*.md
      required: true
  verify:
    - shadow-persistence
    - skill-frontmatter
---

# Retrospective

This skill is the **Operations & Continuity** gear's primary
synthesis surface. It reads what already happened (the ledger) and
produces an honest report of where things went well, where they
halted, and where the operator should look next.

## Purpose and boundaries

The retro commits to:

- Reading recent ledger events grouped by capability / phase / outcome
- Surfacing **drift signals** with citations (event IDs, work-item
  IDs, paths)
- Naming concrete proposal candidates that the `proposal-promotion`
  skill can later act on
- Calibrated tone: operational, not celebratory or defeatist

It does **not** commit to:

- Storytelling beyond what the ledger shows
- Praising or blaming individuals or models — observations are
  about the system, not the people running it
- Proposing fixes inside the retro (those are proposal drafts;
  promotion is a separate skill)
- Speculating about why something happened without ledger evidence

## Inputs

Required:

- The workspace's `.loswfx/state/events.jsonl` ledger (read via
  `read_file`; default LOSWFX workspaces have this on disk).
- The list of work items via `loswfx work list --json` (run through
  `run_command` if available).

Optional:

- **Time window** — retros default to "since the last retro" (which
  the operator can establish by passing the prior retro's timestamp).
  Otherwise: last 100 events or last 7 days, whichever is shorter.
- **Client / engagement scope** — when the workspace serves multiple
  clients, optionally filter by client name in work-item titles.

## Output

A markdown file at `proposals/<client>/retros/<YYYY-MM-DD>.md` (or
`retros/<YYYY-MM-DD>.md` if no client scope):

```
# Retrospective — <window>

| Field | Value |
|---|---|
| Window | YYYY-MM-DD to YYYY-MM-DD |
| Workspace | <path> |
| Events analyzed | <count> |
| Work items in window | <count> |
| Author | LOSWF Agency |

## Summary

Three sentences: (1) what shipped, (2) what halted, (3) the single
most actionable drift signal.

## What shipped

| Work item | Outcome | Capability runs | Notes |
|---|---|---|---|
| <id>: <title> | done/approved | plan, build, verify, review | one-line |

## What halted

| Work item | Halt phase | Reason | First halt event ID |
|---|---|---|---|
| <id>: <title> | verify | verify failed after 3 attempt(s) | <event-id> |

## Drift signals

Patterns observed across multiple events. Each signal includes:

| ID | Signal | Frequency | Evidence | Proposal candidate |
|---|---|---|---|---|
| D-1 | <one-line> | N occurrences in window | <event-ids> | <one-line of what to do> |

## Escalations + needs-attention

| Work item | Type | Action required |
|---|---|---|

## Skill usage

| Skill | Invocations | Resolved | Missed |
|---|---|---|---|

## Proposal candidates

Numbered list of proposal candidates the operator should consider
promoting via the `proposal-promotion` skill. Each entry references
a drift signal ID from above.

1. **<title>** — addresses D-<n>. Acceptance: <one-line>.
```

## Workflow

### Step 1: Load the ledger

`read_file('.loswfx/state/events.jsonl')`. The file is line-delimited
JSON; each line is one event with `type`, `data`, `workItemId`,
`parentEventID`, `timestamp`. Parse line by line.

### Step 2: Determine the window

If the operator supplied a since-timestamp, use it. Otherwise, take
the most recent 100 events or the last 7 days, whichever is shorter.
Always note the actual window in the output's Window field — never
generalize beyond it.

### Step 3: Group by outcome

- **Shipped**: work items whose latest phase event is `transition.recorded`
  to phase `done` AND the pipeline's final status was approved or
  approved_with_followup.
- **Halted**: work items where a phase event recorded a halt without
  recovery.
- **In flight**: work items neither shipped nor halted within the
  window.

### Step 4: Identify drift signals

Patterns worth surfacing (at least 2 occurrences):

- **Verify-fail patterns**: `agent.verify.failed` events with similar
  command shapes — same `wc -l | grep` smell, same anchored-regex
  smell, etc.
- **Review-changes-requested loops**: work items that needed
  multiple build retries.
- **Iteration cap hits**: agent loops returning `incomplete` with
  reason `max_iterations`.
- **Skill load misses**: `skill.load.attempted` events with
  `resolved: false`.
- **Tool-call decode failures**: `provider_truncated_tool_calls`,
  `provider_malformed_response`.
- **Policy denials**: verify commands blocked because the policy
  didn't allow them.

For each signal: cite the event IDs, count the frequency, propose a
one-line candidate.

### Step 5: Tally skill usage

Count `skill.load.attempted` events grouped by `data.skill`. For
each skill: total invocations, resolved=true count, resolved=false
count. Skills with multiple misses get a proposal candidate
(typically: the skill exists but the search path is misconfigured;
or the skill name is being typo'd).

### Step 6: Write the report

Follow the output template exactly. Every claim cites an event ID or
a work-item ID. No speculation.

### Step 7: Self-check

- Every "shipped" row's outcome appears in the ledger
- Every "halted" row has a first halt event ID
- Every drift signal references at least 2 evidence event IDs
- Proposal candidates reference drift signal IDs from the same retro

## Illustrating this artifact

A retrospective benefits from a **cycle diagram** (what we did →
what we learned → what we'll change) or a **signal-to-proposal
map** when retro findings will be promoted to work items. Default
to a `mermaid` fence; retros are internal, brand polish unnecessary.
See [`illustrate-doc`](../illustrate-doc/SKILL.md).

## Failure modes to avoid

- **Storytelling beyond evidence.** If the ledger doesn't show why
  something halted, the retro doesn't either. Write "halt reason
  not recorded" — that itself is a proposal candidate.
- **Single-event drift signals.** A pattern requires multiple events.
  A single weird event is a note, not a drift signal.
- **Celebratory framing.** "Great work this iteration!" is not
  operational. Observations of what shipped are.
- **Praising or blaming individual model runs.** "qwen3-next did X
  well" or "the planner messed up" — the retro is about the system,
  not actors. Frame as: "the dispatch path for X took Y attempts."

## Verification

The retro is complete when:

- The output file exists at the named path
- The Summary section is three sentences and references the drift
  signal cited in the Proposal candidates section
- Every drift signal table row cites at least 2 evidence event IDs
- The Proposal candidates list references the drift signal IDs from
  the body
