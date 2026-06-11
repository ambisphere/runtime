---
name: product
description: Produce a product-design deliverable for a partner (mode inventory, mockup, navigation concept, panel layout, journey map, style system). The dispatched draft must reference real surfaces, files, and constraints from the cycle brief — never generic placeholders. Output is a single markdown file under the cycle's shadow drafts directory; the draft is the agency-internal artifact that gets reviewed before any ship gesture.
max_iterations: 20
side: shadow
contract:
  kind: deliverable
  inputs:
    - kind: layer-3
      path: .loswfx/cycle-briefs/{cycle}/*
      required: true
  outputs:
    - path: engagements/{repo}/{cycle}/drafts/*.md
      required: true
  verify:
    - skill-frontmatter
rubric:
  - id: h1_title
    description: "starts with a level-1 markdown heading naming the deliverable"
    pattern: '\A#\s+\S'
  - id: no_tool_narration
    description: "does not contain tool-use narration as the body (e.g. \"let me read X first\")"
    negative_pattern: '(?i)^let me (read|check|look|find)'
  - id: names_real_surface
    description: "references at least one concrete surface, file, library, or component named in the brief — not a generic placeholder"
    negative_pattern: '(?i)^#\s+(file browser|editor|terminal|home dashboard)\s*$'
  - id: sectioned
    description: "has at least 3 H2 sections"
    line_regex: '^##\s+\S'
    min_count: 3
  - id: min_length
    description: "non-trivial body — more than 2KB"
    min_bytes: 2048
---

# Product

Produce one product-design deliverable per dispatch. Output is markdown
the partner's product team will read directly; it must be specific to
their product, their surfaces, their constraints.

## Inputs

The cycle brief arrives in two parts in the user prompt:

1. **`# Cycle brief`** — the FULL original brief the operator submitted.
   It names real surfaces, files, libraries, modes, and constraints.
2. **`# Deliverable`** — names the specific artifact this dispatch is
   producing (e.g. "Mode Inventory", "Operator Journey Map").

Read both. The cycle brief is where the actual product context lives.
The deliverable header tells you which slice of that to write.

## What "complete" means

The acceptance criteria appear in the user prompt under
`# Acceptance criteria`. Walk every criterion before declaring done.
Common rubric checks for product deliverables:

- Top-level heading names the deliverable (no preamble, no tool-use
  narration as the body).
- Names at least one concrete surface, file, library, or component
  from the cycle brief — never a generic placeholder like "File
  Browser" or "Home Dashboard."
- At least three H2 sections; the body is not a stub.
- ≥ 2KB substantive content (not a one-paragraph summary).
- Self-contained: a reader who only saw this draft understands what
  was delivered and why.

## Process

1. Read the cycle brief carefully. Note every named surface, file,
   constraint, library, and reference.
2. If the brief points at real code (e.g. `internal/tui/operator.go`),
   use the read-only tools (`read_file`, `glob`) to read it before
   writing. Reference what you actually saw, not what you imagined.
3. Write the deliverable. Lead with a top-level heading; structure
   the body around the deliverable shape (sitemap, mockup, journey
   map, etc.).
4. Self-verify against the acceptance criteria. Revise within this
   response if any criterion is unmet.
5. If you exceed your output budget, prioritize completeness over
   depth: cover every criterion at least once, then expand the most
   important sections.

## What this skill is NOT for

- Not for code (use the `build` capability instead).
- Not for research synthesis (use `research-brief`).
- Not for engagement-level scope docs (those stay agency-internal,
  not deliverables).

## Voice

Write for the partner's product team, about their product. No
"From X, To Y" framing. No "loswf agency" references. No "response to
RFP" framing. The deliverable is the partner's; it lands unowned-by-
author.
