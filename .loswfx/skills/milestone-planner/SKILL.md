---
name: milestone-planner
description: Plan the next batch of LOSWFX milestones — review the history (recent closeouts + carry-forward), the roadmap (themes, the active arc), the vision (FOUNDATIONS/ARCHITECTURE), and the snapshot (next-in-flight), take any operator intention as input, then interact with the operator via AskUserQuestion to settle the strategic decisions and draft one or more MILESTONE-<N>-PLANNING-DRAFT.md files (and an optional arc note) that conform to docs/MILESTONE-TEMPLATE.md and are ready for milestone-grinder to promote. It is the upstream complement to milestone-grinder, which refuses to start a milestone with no PLANNING-DRAFT. Use when the operator says "plan the next milestones", "scope the next arc", "draft the next batch", or wants to turn an intention/roadmap direction into grindable plans. Do NOT use it to execute or promote a plan (use milestone-grinder), to write the closeout for a delivered milestone (grinder owns that), or to invent scope with no roadmap/vision/operator signal.
side: shadow
output_dir: docs
contract:
  kind: deliverable
  inputs:
    - kind: layer-4
      path: docs/ROADMAP.md
      required: true
    - kind: layer-4
      path: docs/PROJECT-DEVELOPMENT-SNAPSHOT.md
      required: false
  outputs:
    - path: docs/milestones/MILESTONE-*-PLANNING-DRAFT.md
      required: true
  verify:
    - skill-frontmatter
---

# milestone-planner

The upstream half of the milestone loop. `milestone-grinder` delivers
and closes a milestone, then auto-drafts the *single* next planning
draft from the closeout. This skill is for the deliberate, operator-led
case: turning a **vision/roadmap intention into a batch of grindable
milestone drafts**, with the strategic decisions settled through
`AskUserQuestion` before anything is written.

Hand-off contract: this skill stops at `MILESTONE-<N>-PLANNING-DRAFT.md`
files conforming to [`docs/MILESTONE-TEMPLATE.md`](../../docs/MILESTONE-TEMPLATE.md).
`milestone-grinder` Phase 2 promotes a draft to `PLAN` (resolving open
questions, removing `[?]`, scaffolding TRACKING/EVIDENCE). The planner
never promotes, executes, or closes.

## Purpose and boundaries

The skill commits to:

- **Reviewing real state** before proposing: recent closeouts +
  carry-forward (history), `ROADMAP.md` themes + active arc (direction),
  `FOUNDATIONS.md` / `ARCHITECTURE.md` (vision/constraints),
  `PROJECT-DEVELOPMENT-SNAPSHOT.md` (next-in-flight).
- **Taking operator intention as the primary input** when supplied, and
  grounding it against that state.
- **Surfacing every strategic decision through `AskUserQuestion`** — the
  batch theme, how many milestones, sequencing, scope class, which
  carry-forward signals to pick up, hard non-goals.
- **Drafting one PLANNING-DRAFT per milestone** in the batch, in template
  shape, sequenced so each is independently shippable.
- Optionally writing an **arc note** (`docs/<ARC-NAME>.md`) when the batch
  is a named arc, mirroring the existing `*-ARC.md` convention.
- Leaving the output **ready for grinder** — drafts that promote cleanly.

It does **not** commit to:

- Promoting, executing, or closing milestones (that is `milestone-grinder`).
- Inventing scope with no history/roadmap/vision/operator signal.
- Resolving genuinely delivery-time-dependent questions — those stay as
  `[?]` Open Questions for the grinder's promotion gate.
- Editing already-delivered milestone artifacts.

## Inputs the skill reviews (in order)

1. **Operator intention** — whatever the operator passed ("land real
   execution", "harden the loop", a pasted paragraph). The primary
   signal when present.
2. **History** — the most recent `docs/milestones/MILESTONE-<N>-CLOSEOUT.md`
   "Carry forward" sections and any reopened milestones. What's owed.
3. **Roadmap** — `docs/ROADMAP.md` "Current Position", "Strategic
   priority" arc, and "Roadmap Themes". The declared direction.
4. **Vision** — `docs/FOUNDATIONS.md` + `docs/ARCHITECTURE.md`. The
   constraints any milestone must respect (bounded loops, OpenAI-shape
   providers only, IO at the edges).
5. **Snapshot** — `docs/PROJECT-DEVELOPMENT-SNAPSHOT.md` "next in flight"
   and "last shipped". Where the loop currently points.

The next milestone number is `max(<N> across docs/milestones/MILESTONE-<N>-*.md) + 1`.
A draft earns its place only if it traces to an intention, a carry-forward
item, or a roadmap line. No signal → not a milestone.

## The operator interaction (AskUserQuestion)

Every strategic decision is the operator's — surface them through
`AskUserQuestion`, never assume. Typical questions (batch as needed,
2–4 at a time, with a recommended option first):

- **Batch intention / theme** — confirm the arc this batch lands, in one
  line. (Pre-fill from the operator's input or the roadmap arc.)
- **Batch size** — how many milestones (e.g. 1, a 3-milestone arc, a
  6-milestone arc like M170–M175). Affects granularity.
- **Sequencing** — which milestone is first; what unblocks what. Offer the
  dependency-derived order as the recommended option.
- **Scope class per milestone** — Small / Medium / Large (drives the
  commit estimate). Offer the size implied by the proposed scope.
- **Carry-forward selection** — which closeout carry-forward items this
  batch picks up vs. defers.
- **Hard non-goals** — what to explicitly exclude so the grinder doesn't
  drift into it.

Do not proceed to drafting until the intention, size, and sequencing are
settled. Tactical details the operator doesn't care about → choose the
obvious default and note it in the draft, don't ask.

## Output

For a batch of size K, write **K** files
`docs/milestones/MILESTONE-<N>-PLANNING-DRAFT.md` … `<N+K-1>`, each in the
`PLANNING-DRAFT` shape from `docs/MILESTONE-TEMPLATE.md`:

- `# Milestone <N> Planning Draft` + `Date:` + `Working name:` (txt block)
- `## Status` — "Draft. Not yet promoted to MILESTONE-<N>-PLAN.md."
  (+ where it sits in the batch sequence)
- `## Goal` — 2–4 sentences; success as the operator would see it
- `## Context` — the prior-closeout / roadmap signal this picks up
- `## Usage Scenarios` — operator-facing flows with observable outcomes
- `## Primary Scope` — Track A/B/… with rough file paths
- `## Definition Of Done` — one-line claims, ending with the standing
  rows (`go test ./...` green; `./scripts/check.sh`; `git diff --check`;
  tracking + closeout land)
- `## Non-Goals` · `## Open Questions` (genuine `[?]` only) · `## Risk`
- `## Scope Class` + commit estimate

When the batch is a named arc, also write `docs/<ARC-NAME>.md`: the
one-paragraph thesis, the milestone list with one-line each, and the
arc-level Definition of Done — mirroring the existing `*-ARC.md` docs the
roadmap links.

## Workflow

### Step 1 — Read the state

Gather the five inputs above. Note the next milestone number, the open
carry-forward items, the active roadmap arc, and any vision constraint a
candidate would touch.

### Step 2 — Synthesize candidate milestones

From operator intention × state, draft a candidate list: for each,
one line of (goal · the signal it traces to · rough scope class). Drop
any candidate with no signal or that duplicates an in-flight plan.

### Step 3 — Settle decisions with the operator

Run the `AskUserQuestion` round(s): theme, size, sequencing, scope class,
carry-forward selection, non-goals. Fold the answers back into the
candidate list and re-order by dependency.

### Step 4 — Write the drafts

Write one PLANNING-DRAFT per chosen milestone in template shape,
sequenced. Make every Definition-of-Done bullet a measurable claim.
Reference real files/symbols (read them if unsure they exist). Keep only
genuine delivery-time unknowns as `[?]` Open Questions. Write the arc
note if the batch is named.

### Step 5 — Self-check (ready for grinder)

- Each draft matches the template section order exactly
- `## Status` says Draft / not yet promoted
- Definition Of Done is measurable and includes the standing test/check/
  diff/tracking rows
- Scope references existing files/symbols or explicitly creates them
- No `[?]` marker hides a strategic decision the operator should have made
  (those were settled in Step 3); only delivery-time unknowns remain
- The sequence is dependency-ordered; each milestone is independently
  shippable
- A one-line summary of each draft + the settled decisions is reported to
  the operator

## Failure modes to avoid

- **Skipping the operator.** Strategic scope is the operator's call —
  surface it through `AskUserQuestion`, don't assume the theme or size.
- **Signal-less invention.** A milestone nobody's intention, no
  carry-forward, and no roadmap line asked for is speculation.
- **Promoting / executing.** This skill stops at drafts. Promotion and
  delivery are `milestone-grinder`.
- **Off-template drafts.** A draft the grinder can't parse/promote is not
  ready. Match `docs/MILESTONE-TEMPLATE.md` exactly.
- **Burying decisions as `[?]`.** Open Questions are for delivery-time
  unknowns, not for choices the operator should have made now.
- **Unshippable batches.** If milestone N+1 can't ship without N's
  unfinished internals, they're one milestone — or the sequence is wrong.
- **Vision drift.** A draft that needs a non-OpenAI provider or threads IO
  through the core violates the foundations — reject it at planning time.

## See also

- [`skills/milestone-grinder/SKILL.md`](../milestone-grinder/SKILL.md) —
  the downstream half; promotes these drafts to PLAN and delivers them.
- [`skills/iteration-plan/SKILL.md`](../iteration-plan/SKILL.md) ·
  [`skills/effort-pointing/SKILL.md`](../effort-pointing/SKILL.md) —
  for breaking a single milestone's scope into pointed iteration items.
- [`docs/MILESTONE-TEMPLATE.md`](../../docs/MILESTONE-TEMPLATE.md) — the
  canonical artifact schema every draft must match.
- [`docs/ROADMAP.md`](../../docs/ROADMAP.md) ·
  [`docs/PROJECT-DEVELOPMENT-SNAPSHOT.md`](../../docs/PROJECT-DEVELOPMENT-SNAPSHOT.md)
  · [`docs/FOUNDATIONS.md`](../../docs/FOUNDATIONS.md) — the state and
  vision every batch traces back to.
