---
name: engagement-plan
description: Produce a multi-deliverable engagement plan that synthesizes prior agency artifacts (audits, RFP responses, discovery notes) into a sequenced action plan for the next 4-12 weeks of client work. Use this skill after an initial repo-audit (or multiple audits) when the agency needs to propose what comes next. Output is a markdown plan at proposals/<client>/engagement-plan.md covering scope, sequencing, milestones, risks, and review cadence. Do not use this for one-off deliverables (use the relevant single-deliverable skill) or for iteration-level breakdowns (use iteration-plan once the engagement plan defines a phase).
max_iterations: 80
side: client
contract:
  kind: deliverable
  inputs:
    - kind: layer-4
      path: proposals/{repo}/audit/*.md
      required: true
    - kind: layer-4
      path: proposals/{repo}/product-brief.md
      required: false
    - kind: layer-4
      path: proposals/{repo}/00-cover-letter.md
      required: false
  outputs:
    - path: proposals/{repo}/engagement-plan.md
      required: true
  verify:
    - truthful-status
    - skill-frontmatter
---

# Engagement Plan

This skill is the **strategic bridge** between an initial audit (or any
opening-phase artifacts) and the per-deliverable work that follows. It
sequences the next 4-12 weeks of agency activity into a single document
the client can review and approve.

## Purpose and boundaries

The plan commits to:

- A sequenced list of phases, each with named deliverables
- Named skill bundles per deliverable (so each phase maps directly to
  agency operations the kernel knows how to execute)
- Risk register with mitigations
- Review cadence (when and how the client signs off)

It does **not** commit to:

- Fixed-fee pricing (agency commercial terms are a separate
  document; this skill is operational, not commercial)
- Specific calendar dates (use relative weeks: "Week 1-2", "Week
  3-4") — calendar-binding is a separate scheduling step
- Iteration-level work breakdown (that's `iteration-plan`'s job, invoked
  per phase)
- Cross-engagement commitments (this plan is one client, one
  engagement)

## Inputs

Required:

- **Prior agency artifacts** — at minimum one `repo-audit` output.
  More inputs sharpen the plan: multiple audits, the RFP response if
  one exists, any discovery notes.
- **Client name** — used in the output path and throughout the plan.

Optional:

- **Engagement length hint** — operator-supplied target window
  ("4 weeks", "12 weeks"). Plan adapts the phase count to fit.

## Output

A single markdown file at `proposals/<client>/engagement-plan.md`
with this structure:

```
# Engagement Plan — <client>

| Field | Value |
|---|---|
| Client | <client> |
| Plan date | YYYY-MM-DD |
| Author | LOSWF Agency |
| Engagement window | <relative weeks> |
| Inputs synthesized | <list of prior artifacts by path> |

## Summary

Three sentences: (1) the engagement's overall objective in client
terms, (2) the sequencing thesis (why this order), (3) the single most
important risk and how the plan addresses it.

## Phases

### Phase 1 — <name> (Week X-Y)

**Objective**: one sentence stating what gets resolved in this phase.

**Deliverables**:
| Deliverable | Skill | Owner |
|---|---|---|
| <artifact name + path> | <skill-name> | LOSWF Agency |

**Inputs required from client**: bulleted list of what we need from
the client before the phase begins (access, sign-off, source
documents).

**Exit criteria**: bulleted list of what makes this phase done.

### Phase 2 — ... (Week ...)

...

## Risk register

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R-1 | <one-line> | low/med/high | low/med/high | <one-line> |

## Review cadence

- **Per-phase review**: at the close of each phase, the client receives
  the phase's deliverables and a one-page phase summary.
- **Mid-engagement check-in**: at the midpoint, the plan itself is
  re-evaluated and re-sequenced if needed.
- **Engagement close**: a closeout document summarizing all
  deliverables and recommended follow-on work.
```

## Workflow

### Step 1: Read all input artifacts

Use `read_file` (and `gh api` for client-repo content if needed) to
load every prior artifact. Build an index of findings, recommendations,
and known constraints.

### Step 2: Identify natural phase boundaries

Most engagements decompose into 3-5 phases. Common boundaries:

- **Stabilize then build** — Phase 1 addresses audit blockers, Phase
  2+ produces new value
- **Discover then ship** — Phase 1 is research/PRD work, Phase 2+ is
  delivery
- **Per-repo** — when audits span multiple repos, each repo becomes
  a phase

Pick the boundary that matches the inputs. If two boundaries compete,
prefer "stabilize then build" — finishing what's broken before
opening new fronts is the operational default.

### Step 3: Map each phase to skills

For every deliverable in every phase, name the skill that produces
it. If no current skill fits, name the deliverable with a placeholder
`(new skill needed)` — surfacing the gap is a finding, not a
fabrication.

### Step 4: Write the risk register

Three to seven risks. Each tied to a phase. Each with a mitigation
that is also in the plan (not a new commitment outside the plan's
scope). If a risk has no mitigation, name it as a `blocker` risk —
the plan cannot start until the client resolves it.

### Step 5: Write the review cadence

Default: per-phase review at phase close. Mid-engagement check-in if
the window is >8 weeks. Engagement close at the end. Adjust if
client context requires.

### Step 6: Self-check

- Every deliverable in every phase names a skill (existing or
  `(new skill needed)`)
- The risk register has at least one entry per phase
- The plan does not include calendar dates (only relative weeks)
- The plan does not include pricing
- The literal phrase "Inputs synthesized" appears in the metadata
  table with the list of source artifacts

## Illustrating this artifact

An engagement plan typically benefits from a single inline diagram
of the **phase timeline + dependencies** — Week ranges across the
top, phases as rows or columns, blocked-on relationships as arrows.
Default to a `mermaid` fence (Gantt or flowchart); escalate to
`.loswf/tools/generate_image.py` only for client-facing kickoff
covers. See [`illustrate-doc`](../illustrate-doc/SKILL.md) for the
decision tree. The `illustrated-planning` cardinal practice
surfaces engagement plans that ship ≥600 words without a visual.

## Failure modes to avoid

- **Over-promising.** This plan is a proposal, not a contract.
  Avoid "we will deliver X by date Y" — use "Phase N produces X."
- **Phases without exit criteria.** A phase that can't be marked
  done is a tar pit. Every phase must declare what "done" means.
- **Skills you don't have.** If you name a skill, it should exist in
  the LOSWF Agency catalog (`skills/`). Naming a skill that doesn't
  exist is a gap to be filled, not a fabrication — mark it explicitly
  as `(new skill needed)`.
- **Calendar-pinning.** Calendar dates change. Use relative weeks
  and let the scheduling layer (separate skill, future) bind to
  actual dates.

## Verification

The plan is complete when:

- The output file exists at `proposals/<client>/engagement-plan.md`
- All three top-level sections are present: Phases, Risk register,
  Review cadence
- The Inputs synthesized field lists at least one source artifact
  by path
- Every phase has a Deliverables table with at least one row
- Every Deliverables row names a skill (existing or new-skill marker)
