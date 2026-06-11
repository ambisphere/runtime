---
name: research-acceptance-criteria
description: Define the acceptance criteria for a research-brief work item BEFORE any investigation begins. Use this skill in the Product role at the start of a research-tandem workflow. Output is a markdown file at engagements/<client-repo>/research/<dimension>/acceptance-criteria.md inside the shadow repo. PRIVATE — never shipped to the client. The criteria become the contract the Researcher gear executes against and the bar the Product review pass validates the brief against. Use a different skill (research-brief) for the actual investigation, or (research-brief-verdict) for the post-investigation validation.
max_iterations: 25
side: shadow
output_dir: engagements/{repo}/research
contract:
  kind: criteria
  inputs:
    - kind: layer-4
      path: proposals/{repo}/product-brief.md
      required: false
  outputs:
    - path: engagements/{repo}/research/*/acceptance-criteria.md
      required: true
  verify:
    - shadow-persistence
    - skill-frontmatter
---

# Research Acceptance Criteria (Product gear)

This skill is the **Product gear's** opening move in a research-tandem
workflow. Product defines what good looks like BEFORE Research starts
investigating. Without this step, Research is free to interpret the
brief however it likes — which is how single-capability research
runs drift into vague, model-flavored output.

## Why Product owns this step

The 7-gear org chart's Product gear is responsible for goals,
acceptance criteria, and ensuring the agency delivers what the
engagement actually needs. Research is a method gear — it knows HOW
to investigate, but not WHY this specific investigation matters or
what counts as a complete answer.

Hand Research a target without criteria and you get a brief that
*looks* thorough but doesn't actually serve downstream consumers
(rfp-response, engagement-plan, prd-v1). Hand it criteria and you
get focused investigation.

## Output destination

Per the kernel's resolution, the output lands at:

```
<shadow-root>/engagements/<client-repo>/research/<dimension>/acceptance-criteria.md
```

where `<dimension>` comes from the work item's body (e.g.,
`technical-landscape`, `competitive-scan`). **Never write into the
client workspace.** This is agency-internal scaffolding.

Use the `shadow:` write-path prefix: call `write_file` with
`path: "shadow:engagements/<client-repo>/research/<dimension>/acceptance-criteria.md"`.

## Required shape of the output

Every acceptance-criteria document MUST include, in this order:

1. **Frontmatter** — `phase: product:plan`, `dimension`, `date`,
   `author` (LOSWF Agency Product gear + operator handle if relevant),
   `engagement` (client/repo), `feeds` (downstream skills that will
   consume the eventual brief).
2. **Why this research** — 2-3 sentences. What decision does the
   downstream consumer need to make that this brief will inform? If
   you can't name a downstream decision, the research probably
   shouldn't happen.
3. **Acceptance criteria** — a numbered list of 5-10 specific
   criteria the brief MUST satisfy. Each criterion is testable: a
   reviewer can read the brief and definitively say yes/no. Examples
   of the right shape:
   - "Names the actual technologies in use today (not just what the
     architecture doc proposes)."
   - "Identifies any dependency whose maintenance status is unclear
     or whose last release is >12 months old."
   - "States at least one specific risk from each of: dependency
     rot, missing CI, architecture-doc-vs-code divergence."
   - "Open Questions list contains only questions that genuinely
     require client conversation — not investigation we should
     have done ourselves."
4. **Out of scope** — 2-5 bullets naming what this brief should
   NOT attempt. This prevents scope creep into adjacent dimensions.
5. **Downstream consumers and what they need** — one short
   paragraph per consumer skill (rfp-response, engagement-plan,
   etc.) describing what they will pull from this brief.

## Tools

This skill is a Product-gear PLAN capability — read-only by design.
You should read:

- The work item body (already in your prompt).
- The client repo's docs and code via `read_file`, `glob`,
  `github_read_file`. Just enough to know what's THERE so criteria
  are grounded.
- Any prior research briefs in the shadow repo (read via
  `read_file` with the kernel-resolved shadow path) — for context
  on what the engagement has already established.

DO NOT investigate the dimension itself — that's Research's job.
Your job is to know enough to set the bar; resist the temptation
to start producing findings.

## What this skill does NOT do

- Does NOT produce findings, evidence, or claims about the
  dimension. That's the Researcher's deliverable, not Product's.
- Does NOT exceed 1 page (excluding the numbered criteria list).
- Does NOT speculate about open questions Research will surface —
  the whole point is that Research will discover them.

## Verification

The criteria document is done when:

1. The destination file exists at the resolved shadow path.
2. Frontmatter is complete.
3. The "Why this research" section names a specific downstream
   decision.
4. There are 5-10 numbered acceptance criteria, each testable.
5. Out-of-scope section has 2-5 bullets.
6. At least one downstream consumer is named with what they need.

## Persist to the shadow repo (Product gear owns this)

After write_file lands the criteria, the Product gear MUST persist
it to the shadow's git history. The file is not "done" until it's
committed — otherwise downstream gears clone a working tree without
the criteria they're meant to execute against.

Use the `commit_shadow_artifact` tool — one deterministic call,
agency DevOps primitive:

```text
commit_shadow_artifact(
  paths=["engagements/<client-repo>/research/<dimension>/acceptance-criteria.md"],
  message="research/<dimension>: Product acceptance criteria v1"
)
```

Local commit is gear-autonomous. **Do NOT push to remote** —
push is operator-gated; the operator runs `git push` themselves
once they've reviewed the commit.

After write_file + commit, call `submit_plan` (or the capability's
submit tool) with the file path and a one-sentence summary. The
Researcher gear's next invocation will read this file as its
primary input.
