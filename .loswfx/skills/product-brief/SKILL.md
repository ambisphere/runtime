---
name: product-brief
description: Synthesize a client's existing product documents (vision, RFP, architecture docs, roadmap) into a single concise Product Brief that downstream skills (research-synthesis, prd-v1, iteration-plan) can consume as the canonical product reference. Use this skill at the start of an engagement when the client has multiple scattered documents and the agency needs to consolidate. Output is a single markdown file at proposals/<client>/product-brief.md. Read-only synthesis — the source documents stay authoritative; the brief is a derived reference. Use a different skill (prd-v1) for design-kickoff specifications.
max_iterations: 80
side: client
contract:
  kind: deliverable
  inputs:
    - kind: layer-3
      path: clients/{repo}/**
      required: true
  outputs:
    - path: proposals/{repo}/product-brief.md
      required: true
  verify:
    - truthful-status
    - skill-frontmatter
---

# Product Brief

This skill produces a **canonical product brief** — a single, concise
document downstream agency work can reference instead of re-reading
five scattered client documents every time. The brief is derived;
the source documents remain authoritative.

## Purpose and boundaries

The brief commits to:

- A one-paragraph product description grounded in client language
- The validated business goal and customer goal (separated cleanly)
- The named user personas / segments
- The current scope and out-of-scope items
- The technical/regulatory/operational constraints
- A short index of source documents the brief derives from

It does **not** commit to:

- Functional requirements (those emerge from design and PRD work)
- Detailed user scenarios (separate skill: `user-scenarios`)
- Implementation plans (separate skill: `sprint-plan`)
- Business case / commercial framing (commercial docs are separate)

## Inputs

Required:

- **Source documents** — at least one client document. Most engagements
  have several: vision, RFP, roadmap, architecture, requirements.
  Read all of them.

Optional:

- **Client name** — used in the output path. Defaults to the source
  documents' parent repo name.

## Output

A single markdown file at `proposals/<client>/product-brief.md`:

```
# Product Brief — <client>

| Field | Value |
|---|---|
| Client | <client> |
| Brief date | YYYY-MM-DD |
| Author | LOSWF Agency |
| Source documents | <bulleted paths> |

## Product

One paragraph (3-5 sentences) describing the product in the client's
own framing. Use the client's language for the core noun — if they
call it a "workspace", call it a workspace; do not rewrite as "platform"
or "tool."

## Business goal

One sentence stating what the company gets. An outcome, not an output.
("Reduce operational fragmentation for developer + creator workflows" —
not "ship a UI.")

## Customer goal

One sentence stating what the user gets. An outcome, not an output.
("Operate Git-based workflows without context-switching across five
tools" — not "see issues and PRs in one panel.")

## Users

Bulleted list of named personas / segments derived from source
documents. Each item: persona name + one-sentence description.
Do not invent personas not present in source documents — if the
sources don't name users, write "Source documents do not name
distinct user personas" and stop.

## Scope (this engagement)

What is in scope, derived from the client's own scope declarations.
Bulleted; concrete.

## Out of scope (this engagement)

What the client has explicitly excluded or what is implicit by
omission from their scope. Bulleted.

## Constraints

| Type | Constraint | Source |
|---|---|---|
| Technical | <one-line> | <document:section> |
| Regulatory | <one-line> | <document:section> |
| Operational | <one-line> | <document:section> |

## Source document index

| Document | Path | What it contributes |
|---|---|---|
| <name> | <path> | <one-line: what we drew from it> |

## Open questions

Bulleted list of gaps the source documents do not resolve.
If empty, write "No open questions identified from the source
documents at this synthesis." Open questions are evidence, not
embarrassment — surface them.
```

## Workflow

### Step 1: Inventory the source documents

List every client document available. Source documents live in the
CLIENT'S repositories, not in the local workspace.

**Read them via `github_read_file(owner, repo, path)`, NOT via
`read_file`.** `read_file` is workspace-scoped — if you call it with
a path like `docs/architecture.md`, it will silently read a file by
that name from the LOCAL workspace if one exists, conflating the
local context with the client's content. `github_read_file` goes
through the gh API and explicitly names the client repo, so the
content can't be mistaken.

Use `gh api repos/<owner>/<repo>/contents/<dir>` (via `run_command`)
to discover what files exist, then `github_read_file` to load each
one.

### Step 2: Build the synthesis index

For each source document, note:

- The product description, if it states one
- The business goal language
- The customer goal language
- Named users / personas
- Stated scope and exclusions
- Stated constraints

### Step 3: Populate the brief

Work section by section. For each section, prefer the client's own
language. Quote-by-paraphrase is fine; outright rewrite is a smell
(you may be drifting from what the client actually said).

### Step 4: Identify gaps

Anything you could not find in the source documents goes in the
Open questions section. This is operational — agencies that surface
gaps early ship better engagements.

### Step 5: Self-check

- Every section is populated (no placeholder text remaining)
- The Source document index references each document by path
- The product description uses the client's noun for the product
  (verifiable: grep the brief for the client's term, then grep the
  source documents for the same term — should match)
- No personas appear in Users that aren't in source documents
- The "Out of scope" section is non-empty (every engagement has
  things deliberately excluded)

## Illustrating this artifact

A product brief benefits from one of: a **concept-flow diagram**
(user → action → outcome), a **scope-boundary map** (in-scope vs
out-of-scope as adjacent regions), or a **persona × need matrix**.
Default to a `mermaid` fence. Briefs that will be shared with
external stakeholders (potential customers, partners) may justify a
brand-voiced hero via `.loswf/tools/generate_image.py`. See
[`illustrate-doc`](../illustrate-doc/SKILL.md).

## Failure modes to avoid

- **Inventing personas.** Users that don't appear in source documents
  must not appear in the brief.
- **Marketing rewrite.** "A platform that empowers..." is a smell.
  Use the client's own framing.
- **Empty Open questions.** Almost every set of source docs has gaps.
  An empty Open questions section is usually a missed read.
- **Overlapping with downstream skills.** The brief is *not* a PRD,
  *not* an iteration plan, *not* a research report. It is the one-page
  reference all of those derive from.

## Verification

The brief is complete when:

- The output file exists at `proposals/<client>/product-brief.md`
- All eight top-level sections are present
- The Source document index has at least one row
- The Constraints table has at least one row OR explicitly states
  "No constraints identified from the source documents"
