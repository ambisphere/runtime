---
name: research-brief
description: Produce a focused agency-internal research note on a specific dimension of a client engagement (competitive scan, technical landscape, risk register, prior-art review, user-context note). Use this skill whenever the agency needs deeper preparation BEFORE generating client-facing artifacts (rfp-response, product-brief, engagement-plan). Output is a markdown file inside the shadow repo at engagements/<client-repo>/research/<dimension>-<YYYY-MM-DD>.md. PRIVATE — never shipped to the client. The research informs downstream client-side skills; it doesn't replace them. Use a different skill (retrospective) for synthesis of our own pipeline runs; use (harvester) for live signal scanning of the client repo.
max_iterations: 70
side: shadow
output_dir: engagements/{repo}/research
rubric:
  - id: frontmatter
    description: "starts with YAML frontmatter block (--- delimiters)"
    pattern: '(?s)\A\s*---\n.*?\n---'
  - id: thesis
    description: "contains a one-sentence thesis section"
    pattern: '(?i)thesis'
  - id: evidence_table_min_3
    description: "evidence table has at least 3 source rows"
    min_table_rows: 3
  - id: numbered_findings_3_to_7
    description: "3-7 numbered top-level findings"
    line_regex: '^[0-9]+\.\s+\*\*'
    min_count: 3
    max_count: 7
  - id: implications_section
    description: "names downstream skills the brief feeds"
    pattern: '(?i)implications? for downstream'
  - id: open_questions_section
    description: "lists open questions requiring client conversation"
    pattern: '(?i)open\s+question'
contract:
  kind: deliverable
  inputs:
    - kind: layer-3
      path: clients/{repo}/**
      required: false
    - kind: layer-4
      path: proposals/{repo}/product-brief.md
      required: false
  outputs:
    - path: engagements/{repo}/research/*.md
      required: true
  verify:
    - shadow-persistence
    - skill-frontmatter
---

# Research Brief

This skill is the **Research** gear's primary surface — and it's the
prerequisite for a high-quality client-facing artifact pass. The
agency's improvement over PR#1-style "fast onboarding" comes from
HERE: a deep, evidence-grounded internal note that the operator (and
downstream client-side skills) can lean on.

## Why this skill exists

A client-facing artifact (an audit, a brief, an RFP response, an
engagement plan) is only as good as the preparation underneath it.
Without preparation, every artifact reads like a template with the
client's name swapped in. With preparation, every artifact has
specific observations grounded in evidence the client can verify.

This skill produces one **dimension** of preparation at a time. The
operator queues one work item per dimension; each work item drives one
focused brief. Brief stays SHORT (one page, tightly written) and
EVIDENCE-DENSE (every claim cites a source).

## Output destination

Per the kernel's resolution, the output lands at:

```
<shadow-root>/engagements/<client-repo>/research/<dimension>-<YYYY-MM-DD>.md
```

where `<shadow-root>` is the configured shadow repo's local checkout
(degraded to `.loswfx/agency-shadow/` if shadow is unconfigured).
**Never write into the client workspace.** This artifact is private.

The `<dimension>` is taken from the work item's body — it MUST be
one of:

- `prior-art` — what has been done in this space (open source projects,
  commercial offerings, academic work). Where the client's project sits
  in the landscape. What it can borrow from; where it must differentiate.
- `competitive-scan` — direct and adjacent competitors. Their stated
  positioning, observable strengths, observable gaps. Not marketing
  copy — evidence (URLs, screenshots-of-record described in text,
  product behaviors).
- `technical-landscape` — the technologies the client's project uses
  or could use. Maturity, ecosystem signals (npm downloads, GitHub
  stars trajectory, last-release recency), known limitations, where
  the client's choices align or diverge from the mainstream.
- `risk-register` — what could derail this engagement. Technical risks
  (dependency rot, missing CI, governance gaps), commercial risks
  (scope creep, unclear stakeholders, conflicting RFP signals),
  operational risks (key person, license ambiguity). Each risk has
  likelihood + impact + a mitigation hook.
- `user-context` — who the users of the client's product are. What
  their environments, jobs-to-be-done, accessibility needs, and
  language preferences look like. Drives later UX/PRD work.

## Required shape of the output

Every brief MUST include, in this order:

1. **Frontmatter** — `dimension`, `date`, `author` (LOSWF Agency +
   operator handle if relevant), `engagement` (client/repo).
2. **One-sentence thesis.** What this brief concludes in a sentence.
3. **Evidence table.** Every cited source: URL, accessed-date,
   one-line "what this tells us". Three columns minimum.
4. **Findings.** 3-7 numbered findings. Each finding: claim,
   supporting evidence (back-reference to table), implication for
   downstream artifacts.
5. **Implications for downstream skills.** Explicit: "rfp-response
   should X", "engagement-plan should Y". This is how the brief
   reaches the client-facing surface.
6. **Open questions.** What the brief cannot conclude, with the
   reason (missing data, requires client conversation, requires
   running code). Carried into the next iteration.

## Tools

This skill uses the standard tool palette. Most relevant:

- `read_file` for any local materials (the client's repo, prior
  agency artifacts in the workspace).
- `github_read_file` for the client's GitHub-hosted docs and code
  when those aren't checked out locally.
- `run_command` for `gh` calls (issue/PR inspection) and for `curl`-
  driven web fetches when permitted by policy.
- `write_file` to land the brief at the resolved destination.

## What this skill does NOT do

- Does NOT propose work items. Promotion to tracked work is a
  separate skill (`proposal-promotion`).
- Does NOT post anything to the client (no comments, no PRs, no
  emails). Brief stays in the shadow.
- Does NOT speculate. If evidence is thin, the brief says so and
  the gap goes in Open Questions — it doesn't fabricate.
- Does NOT exceed one page (excluding the evidence table). If a
  dimension needs more, split it into multiple work items with
  narrower scope.

## Illustrating this artifact

Research briefs that synthesize many sources benefit from a
**claim graph** (claims as nodes, support / refutation as edges)
or a **finding-to-implication map**. Internal research is shadow-
side; default to a `mermaid` fence and skip brand polish — the
audience is the agency itself. See
[`illustrate-doc`](../illustrate-doc/SKILL.md).

## Verification

A brief is done when:

1. The destination file exists at the resolved shadow path.
2. The frontmatter has all required fields.
3. Every numbered finding back-references at least one evidence
   row.
4. The "Implications for downstream skills" section names at least
   one downstream skill and what to do.
5. No claim in the brief is uncited.

If any of these fail, the agent loops and corrects rather than
submitting.

## Persist to the shadow repo (Research gear owns this)

After write_file lands the brief, persist it to the shadow's git
history. The brief is not "done" until it's committed — Product's
verdict pass needs to validate against a committed artifact, not a
volatile working-tree file.

Use the `commit_shadow_artifact` tool — one deterministic call:

```text
commit_shadow_artifact(
  paths=["engagements/<client-repo>/research/<dimension>/brief.md"],
  message="research/<dimension>: Researcher brief v1"
)
```

Local commit only — do NOT push.
