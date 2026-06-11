---
name: research-design-implications
description: Read a draft research brief and contribute the Design gear's perspective — UX implications, design choices the brief surfaces or omits, design risks the engagement should plan for. Use this skill in the Designer role as the third phase of a research-tandem workflow, AFTER Product has set acceptance criteria and Researcher has drafted the brief. Skip this skill when the dimension has no UX surface (e.g., dependency-audit research often doesn't). Output is a markdown file at engagements/<client-repo>/research/<dimension>/design-implications.md inside the shadow repo. PRIVATE — agency-internal. Use a different skill (research-brief) for the actual investigation, or (research-brief-verdict) for Product's validation pass.
max_iterations: 30
side: shadow
output_dir: engagements/{repo}/research
contract:
  kind: deliverable
  inputs:
    - kind: layer-4
      path: engagements/{repo}/research/*.md
      required: true
  outputs:
    - path: engagements/{repo}/research/*/design-implications.md
      required: true
  verify:
    - shadow-persistence
    - skill-frontmatter
---

# Research Design Implications (Design gear)

This skill is the **Design gear's** contribution to the research-tandem
workflow. Design reads the Researcher's draft brief and answers one
question: **what does this mean for how the client's product looks
and feels?**

## Why Design contributes here

In the 7-gear org chart, Design owns UX choices so Development never
has to make them under pressure. That responsibility starts in the
research phase: when Research surfaces, say, "the client wants a
spatial workspace with persistent layout state," Design has to weigh
in on whether that's HCI-novel-but-feasible vs. HCI-novel-and-risky.
Without this pass, Development inherits design decisions implicitly,
which is exactly the failure mode the org chart was drawn to prevent.

## When to skip this skill

Not every research dimension has a UX surface:

- `dependency-audit` — purely technical, no UX.
- `license-and-governance` — legal/process, no UX.
- `ci-and-build` — infrastructure, no UX.

When the dimension is one of these (or the operator otherwise marks
the work item `skip-design`), the foreman should not dispatch this
skill. If you DO get dispatched on a clearly UX-free dimension, emit
a one-sentence note and exit cleanly — don't fabricate implications.

## Output destination

Per the kernel's resolution, the output lands at:

```
<shadow-root>/engagements/<client-repo>/research/<dimension>/design-implications.md
```

Use the `shadow:` write-path prefix: `write_file` with
`path: "shadow:engagements/<client-repo>/research/<dimension>/design-implications.md"`.

## Required shape of the output

Every design-implications document MUST include, in this order:

1. **Frontmatter** — `phase: design:plan`, `dimension`, `date`,
   `author` (LOSWF Agency Design gear + operator handle if relevant),
   `engagement` (client/repo), `references` (paths of the
   acceptance-criteria.md and brief.md you read).
2. **Stance** — one sentence. The Design gear's overall read on
   what the brief implies for UX. E.g., "Brief surfaces three
   choices Design must lead on before Development engages."
3. **Design choices surfaced** — numbered list (1-7). Each item:
   the choice + which finding in the brief it derives from + a
   recommendation (or "needs client conversation"). A "choice" here
   means a yes/no or among-N decision that affects pixels,
   interaction, or affordance.
4. **Design risks** — numbered list (1-5). Each: the risk + the
   triggering finding from the brief + a mitigation hook
   (prototype, spike, design-system constraint).
5. **What's MISSING from the brief** — bullets. Things the Designer
   needed to weigh in but the Researcher didn't surface. These
   become candidates Product can either send back to Research OR
   accept as out-of-scope.
6. **What downstream Development needs to know** — short paragraph.
   The bridge from this design read to the eventual implementation
   work. Should reference at least one specific design constraint
   that, if violated, would invalidate Design's recommendation.

## Tools

You should read:

- The acceptance-criteria.md from this dimension's directory.
- The brief.md from this dimension's directory.
- Any prior design-implications.md from earlier dimensions of this
  engagement (cross-dimension pattern check).
- The client repo's existing UI/UX docs via `github_read_file`
  when relevant.

DO NOT read more of the client repo than is needed to verify the
brief's UX-related claims. Design's job here is interpretation, not
investigation.

## What this skill does NOT do

- Does NOT propose new findings about the dimension — the brief
  is the source of truth. If you think a finding is wrong, flag it
  in "What's MISSING," don't overwrite it.
- Does NOT produce mockups, wireframes, or design assets. This
  skill is words-only; design assets are a separate workflow.
- Does NOT exceed 1 page (excluding the numbered lists).

## Illustrating this artifact

This artifact frequently carries a **decision tree** (the choice
points the research surfaces) or an **implications-to-action map**.
Both render cleanly as Mermaid flowcharts. Default to a `mermaid`
fence; the deliverable is internal-to-design and brand polish is
overkill. See [`illustrate-doc`](../illustrate-doc/SKILL.md).

## Verification

Done when:

1. File exists at the resolved shadow path.
2. Frontmatter is complete with `references` listing the criteria
   + brief files you actually read.
3. Stance section is one sentence.
4. At least one Design choice OR one Design risk is identified
   (otherwise call it out as a clean UX-free pass and exit).
5. Every choice/risk references a specific finding from the brief.
6. "What's MISSING" section exists, even if empty (state "nothing
   missing — brief covered the UX surface" explicitly).

## Persist to the shadow repo (Design gear owns this)

After write_file lands the document, persist it to the shadow's git
history. The file is not "done" until it's committed.

Use the `commit_shadow_artifact` tool — one deterministic call:

```text
commit_shadow_artifact(
  paths=["engagements/<client-repo>/research/<dimension>/design-implications.md"],
  message="research/<dimension>: Design implications v1"
)
```

Local commit only — do NOT push.
