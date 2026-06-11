---
name: iteration-plan
description: Break a phase of an engagement plan (or an audit's remediation list) into one iteration of shippable work items, each estimable in T-shirt size and independently testable. Use this skill after engagement-plan or after a repo-audit, when the operator is ready to commit a phase to delivery. Output is a markdown iteration plan at proposals/<client>/iterations/<n>-<theme>.md. LOSWF Agency uses "iteration" rather than "sprint" deliberately — sprints imply a race; iterations imply thoughtful, repeatable cycles. Slow and steady. We do X sweeps per iteration; we ship every iteration. Do not use this for engagement-level sequencing (use engagement-plan).
max_iterations: 60
side: client
contract:
  kind: deliverable
  inputs:
    - kind: layer-4
      path: proposals/{repo}/engagement-plan.md
      required: false
    - kind: layer-4
      path: proposals/{repo}/audit/*.md
      required: false
  outputs:
    - path: proposals/{repo}/iterations/*.md
      required: true
  verify:
    - truthful-status
    - skill-frontmatter
---

# Iteration Plan

This skill is the **execution-readiness layer**. It takes a phase's
worth of intent and produces a discrete, ordered list of work items
each small enough to ship in a single pipeline sweep.

## Why "iteration" and not "sprint"

Sprints imply a race against time; iterations imply a repeatable
cycle. LOSWF Agency moves **thoughtfully over speedily** — slow and
steady wins the race. Within one iteration we run multiple **sweeps**
(passes over the work-item queue), each sweep advancing one item
through plan → build → verify → review. An iteration is done when
its work items reach their definitions of done, not when a calendar
deadline arrives.

This terminology is operational, not cosmetic. When a skill names
"the next iteration", the operator hears: a complete, reviewable
cycle. When a doc names "the next sprint", the operator hears:
hurry up. We choose the framing that matches how we actually work.

## Purpose and boundaries

The plan commits to:

- An iteration theme (one-line, names what the cycle accomplishes)
- 5-15 shippable work items, each with title + scope + skill mapping
  + effort estimate (S / M / L)
- A definition of done for the iteration as a whole
- A demo/review handoff plan

It does **not** commit to:

- Actual story points or hour estimates (T-shirt sizes only —
  S/M/L; operational sizing, not commercial estimation)
- Calendar dates (operator schedules; iteration close happens when
  the items are done, not when the calendar says so)
- Cross-iteration dependencies (those live in `engagement-plan`)
- Per-work-item code-level design (skills produce code; this plan
  produces the queue)

## Inputs

Required:

- **Phase context** — either a phase from a prior `engagement-plan`
  or a remediation list from a prior `repo-audit`. Read it with
  `read_file`.

Optional:

- **Iteration number / theme** — operator-supplied. Defaults to next
  available number under `proposals/<client>/iterations/`.

## Output

A markdown file at `proposals/<client>/iterations/<n>-<theme>.md`:

```
# Iteration <n>: <theme>

| Field | Value |
|---|---|
| Client | <client> |
| Iteration | <n> |
| Theme | <one-line> |
| Source | <phase or audit doc path> |
| Plan date | YYYY-MM-DD |
| Author | LOSWF Agency |

## Iteration goal

One sentence: what the team has accomplished when the iteration is
done. Outcome-shaped, not output-shaped.

## Work items

| ID | Title | Skill | Effort | Done when |
|---|---|---|---|---|
| W-1 | <imperative title> | <skill-name or `(manual)`> | S/M/L | <one-line exit criterion> |

## Sweep ordering

Numbered list of sweeps. Each sweep names which work items advance
through which phases. A sweep is one pass over the queue.

Example:
1. Sweep 1: W-1 (plan), W-2 (plan), W-3 (plan)
2. Sweep 2: W-1 (build → verify → review), W-2 (build)
3. Sweep 3: W-2 (verify → review), W-3 (build → verify → review)

Parallel-safe groups noted explicitly: "W-2 and W-3 can ship in
parallel after W-1".

## Definition of done (iteration)

Bulleted criteria that make the iteration as a whole done. At least
one item must be a verification anchor (test pass, audit re-run
result, demo).

## Demo / handoff

What the operator shows the client at iteration review. Concrete:
- a running demo of code shipped
- a re-run of an audit showing closed findings
- a walkthrough of new documents

## Risks (iteration-scoped)

Three to five risks specific to this iteration with mitigations.
```

## Workflow

### Step 1: Read the source

Phase or audit. Build a list of EVERYTHING that's in the source's
scope: deliverables, remediations, recommendations.

### Step 2: Decompose to shippable items

Each work item must:
- Have an imperative title ("Add LICENSE file", not "License")
- Map to a skill OR be marked `(manual)` for operator work
- Fit a single pipeline run (rule of thumb: if the title needs an
  "AND" or "THEN", split)

5-15 items is the sweet spot. Fewer means the iteration isn't
iteration-sized; consider rolling forward to the next iteration. More
means items are too small; bundle.

### Step 3: Size with T-shirts

- **S** — single file change, single capability run. Example: add a
  LICENSE file.
- **M** — multiple files or multiple capability runs in one work
  item. Example: bootstrap CI workflow + test job.
- **L** — would benefit from being split further but staying as one
  item makes more sense for cohesion. Example: full design-system
  starter pack.

If you find yourself wanting `XL`, split.

### Step 4: Plan the sweeps

An iteration consists of N sweeps. Each sweep is one pass over the
work-item queue; in each sweep, work items advance one or more
phases (plan → build → verify → review). Number the sweeps and note
which items advance through which phases in each.

Most iterations run 3-5 sweeps. Fewer sweeps means items are too
serial (bottlenecks); more sweeps means items are too granular
(thrash).

### Step 5: Write definition of done + demo

The iteration is done when an external observer (the client) can see
the difference. Definition-of-done must include at least one
externally-verifiable anchor.

### Step 6: Self-check

- 5-15 work items
- Every item has T-shirt size
- Every item names a skill or `(manual)`
- Sweep ordering references items by ID
- Demo/handoff is concrete (not "review the work")

## Illustrating this artifact

An iteration plan typically benefits from one inline diagram —
either the **sweep ordering** (a small flowchart from intake through
the work items in this iteration to demo/handoff) or the
**risks-to-phase map** when ≥3 risks are tied to specific phases.
Default to a `mermaid` fence; the iteration plan is internal, so
brand-voiced image generation is usually overkill. See
[`illustrate-doc`](../illustrate-doc/SKILL.md) for the decision
tree.

## Failure modes to avoid

- **Sprint vibes.** If you find yourself writing "by next Friday"
  or "in two weeks" — stop. We move when the work is done, not
  when the calendar demands. Use sweeps + definition-of-done.
- **Bundle creep.** Work items that grow to encompass a full
  iteration defeat the granularity. Split.
- **Skills you don't have.** Same rule as `engagement-plan` — if
  you name a skill, it must exist in the catalog or be marked
  `(new skill needed)`.
- **No verification anchor in Definition of done.** "Code reviewed"
  is not an iteration exit; "audit re-run shows blocker count = 0"
  is.
- **Hour estimates.** Resist them. T-shirts are operational sizing.

## Verification

The plan is complete when:

- The output file exists at `proposals/<client>/iterations/<n>-<theme>.md`
- The work-items table has 5-15 rows
- Every row has Title, Skill, Effort, Done-when populated
- Sweep ordering references items by ID
- Demo/handoff is non-empty
