---
name: triage-decomposition
description: Decompose a parent work item into 2-6 independently shippable child work items. Use this skill on parent work items that bundle multiple deliverables (e.g. "respond to an RFP", "ship an iteration", "audit and remediate a repo") where each child can be picked up by a separate pipeline run. Output is a list of proposed child work items, each with a title, rationale, and evidence reference to source documents. Use a different skill (gherkin-feature-drive, repo-audit, rfp-response) for single-deliverable work items.
side: client
contract:
  kind: methodology
  inputs: []
  outputs: []
  verify:
    - skill-frontmatter
---

# Triage Decomposition

This skill is the canonical use of the `triage` capability. It takes a
parent work item and produces N children that are independently shippable
through the standard plan → build → verify → review pipeline.

## Purpose and boundaries

The skill commits to:

- Reading the parent body and any documents it references
- Producing 2-6 child work items grounded in evidence from those documents
- Each child being independently shippable in ≤1 day of work
- Each child having a clear single-deliverable outcome

It does **not** commit to:

- Implementing any of the children (that's per-child pipeline work)
- Coordinating between children (children must be independent; if they're
  not, the parent isn't decomposed enough — keep refining)
- Suggesting a build order (the operator schedules)

## Inputs

Required:

- **Parent work item** — the work item being triaged. Its body is the
  scope statement.

Implicit:

- Any documents the parent body references (RFP, design doc, audit
  findings, etc.) must be readable via `read_file` from the workspace.

## Output

The `submit_triage` tool call with `proposed_work_items` populated.
Each item has:

- **title** (required) — short imperative ("Add CLI entrypoint",
  not "We should add a CLI"). ≤80 characters.
- **rationale** — why this child unblocks progress on the parent.
- **evidence** — specific file paths or quoted lines from documents
  that justify this item.

The kernel materializes each proposed item as a child work item on
the same surface.

## Workflow

### Step 1: Read the parent

The parent body is the scope statement. Don't summarize it — internalize
it. List explicitly what the parent commits to producing.

### Step 2: Read referenced documents

If the parent body references files (`docs/rfp-product-design.md`,
`features/cli_workflow_trigger.feature`, an audit findings doc),
`read_file` each one. Build an evidence index keyed by document.

### Step 3: Identify the natural decomposition axis

Most parents decompose along one of three axes:

- **By deliverable** — "respond to RFP" decomposes into one child per
  required document (cover letter, approach, portfolio, engagement,
  README). This is the most common.
- **By scenario** — a multi-scenario feature decomposes into one
  child per scenario (rarely needed; usually one feature = one child).
- **By domain** — an audit's remediation list decomposes into one
  child per domain (deps, ci, docs, tests, license, code).

Pick one axis. Don't mix axes in the same triage.

### Step 4: Write the proposed work items

For each child:

- **title** — what gets built. Concrete file paths when applicable.
- **rationale** — which part of the parent's scope this child satisfies.
- **evidence** — the specific sentence or section from a source document
  that justifies including this child. If you can't cite evidence, the
  child is speculative and should be dropped or refined.

Target 2-6 children. Fewer than 2 means the parent didn't need
decomposition. More than 6 means the children aren't independent —
refine them into a hierarchy (decompose the parent into 3 phases,
then triage each phase separately).

### Step 5: Call submit_triage

The submit_triage tool's `proposed_work_items` array carries the
final list. The kernel materializes each as a child work item on the
parent's surface.

## Illustrating this artifact

A triage decomposition with 4+ children benefits from a
**parent → children DAG** showing inter-child dependencies (if
any) so downstream pipelines can parallelize correctly. Default
to a `mermaid` flowchart; triage outputs are operational and
brand polish would distract. See
[`illustrate-doc`](../illustrate-doc/SKILL.md).

## Failure modes to avoid

- **Fabricated evidence.** Every child must cite a real path or quote.
  No invented citations.
- **Cross-dependent children.** If child B's plan starts with "first
  finish child A", you haven't decomposed — child B is a continuation
  of child A. Merge them or reorder.
- **Over-decomposition.** "Create the directory" is not a shippable
  child; it's a build step inside a real deliverable.
- **Under-decomposition.** A child titled "Implement everything in the
  spec" defeats the point. If you're tempted to write that, the parent
  scope is too broad and the operator should split it before triage.
- **Title bloat.** Titles >80 characters indicate the child is doing
  too much. Refine the scope or split.

## Verification

The triage is complete when:

- `submit_triage` was called with 2-6 items
- Every item has a non-empty title ≤80 characters
- Every item has rationale + evidence (not blank)
- The kernel materializes the children as separate work items on the
  parent's surface, queryable via `loswfx work list`
