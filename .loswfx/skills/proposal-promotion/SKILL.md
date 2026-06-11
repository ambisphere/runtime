---
name: proposal-promotion
description: Take improvement proposals surfaced by a retrospective (or by an operator) and promote them into tracked work items in the LOSWFX pipeline. Use this skill at the close of a retro when proposal candidates have been identified, or at any point an operator wants to convert a backlog of drafts into actual queued work. Output is a promotion ledger entry per promoted draft, the actual `loswfx work add` invocations, and a summary report at proposals/<client>/promotions/<YYYY-MM-DD>.md. Use a different skill (retrospective, harvester) to generate the proposal candidates in the first place.
max_iterations: 50
side: shadow
output_dir: engagements/{repo}/promotions
contract:
  kind: deliverable
  inputs:
    - kind: layer-4
      path: engagements/{repo}/retros/*.md
      required: true
  outputs:
    - path: engagements/{repo}/promotions/*.md
      required: true
  verify:
    - shadow-persistence
    - skill-frontmatter
---

# Proposal Promotion

This skill closes the continuous-improvement loop. Retro and
harvester surface candidate work; promotion converts the worthy
candidates into tracked work items the standard pipeline can
consume.

## Purpose and boundaries

The promotion skill commits to:

- Reading proposal drafts (from retros, harvest reports, or
  free-form drafts the operator wrote)
- For each: keep / merge with existing / drop, with reason
- For "keep" candidates: file as a new work item via
  `loswfx work add` with the right skill assignment
- Recording the promotion to a per-workspace
  `proposal-promotions.jsonl` audit log

It does **not** commit to:

- Implementing any of the promoted work (that's pipeline's job)
- Closing existing work items (only creates)
- Reordering the backlog (the new items enter at the default
  intake; prioritization is intake's job)
- Auto-promoting all drafts — every promotion is a deliberate keep
  decision

## Inputs

Required:

- **Proposal source** — one or more of:
  - A retro report at `proposals/<client>/retros/<date>.md`
  - A harvest report at `proposals/<client>/harvests/<date>.md`
  - A draft directory like `proposals/<client>/drafts/*.md`
  - Operator-supplied free-form draft text

Optional:

- **Client name** — for the promotion-log path. Defaults to inferring
  from the source paths.
- **Skill hint per draft** — operator may pre-suggest which skill
  the promoted work item should use; otherwise this skill infers
  from the draft content.

## Output

Three artifacts:

1. **`loswfx work add` invocations** — one per kept proposal. Each
   work item gets the inferred skill assignment.
2. **Promotion log** — appended entries in
   `.loswfx/state/proposal-promotions.jsonl`. One JSON line per
   promotion with timestamp, source draft path, new work-item id,
   skill, decision rationale.
3. **Promotion summary report** at
   `proposals/<client>/promotions/<YYYY-MM-DD>.md` covering kept
   vs. merged vs. dropped with reasons.

## Workflow

### Step 1: Load the proposal drafts

Read every draft referenced by the source path(s). For each, extract:

- Title (the imperative one-line summary)
- Context (what triggered the proposal — drift signal, harvest finding, audit follow-up)
- Acceptance criteria (what "done" looks like)
- Suggested skill (if the draft names one)

### Step 2: Cross-check against existing work items

`loswfx work list --json` to get all current work items. For each
draft:

- **Title overlap**: if a current work item has a substantially
  similar title (case-insensitive substring match on the main verb +
  noun), the draft is a merge candidate.
- **Source overlap**: if a draft's Work-Key (or source citation) is
  already in an existing work item's body, it's a duplicate — drop.

### Step 3: Decide keep / merge / drop

For each draft:

- **keep** if no overlap with existing work items. Proceed to step 4.
- **merge** if there's title or source overlap with an in-flight
  work item. Note the existing item's id and the merge rationale in
  the report; do NOT modify the existing item — that's intake's
  decision to make later.
- **drop** if the draft is stale (referenced data no longer matches
  reality), too vague to act on (no acceptance criteria, no
  evidence), or out of scope (refers to a different client).

### Step 4: For "keep" drafts, file the work item

For each kept draft, infer the skill assignment:

- If the draft addresses an audit finding → `dependency-bump` /
  `(repo write-skill, future)`
- If the draft asks for a research question → `research-brief`
  (when that ships) or fall back to `(manual)` for now
- If the draft proposes a PRD-shaped deliverable → `prd-v1` (when
  it ships)
- If the draft is small / focused → `gherkin-feature-drive` for
  feature-shaped work, `(manual)` for ambiguous shapes
- Unsure: file without a skill (the work item runs body-only)

Then run:

```sh
loswfx work add "<draft title>" --skill <inferred-skill> --body "<draft body>"
```

Capture the returned work-item id.

### Step 5: Log the promotion

Append a JSON line to `.loswfx/state/proposal-promotions.jsonl`:

```json
{
  "timestamp": "<YYYY-MM-DDTHH:MM:SSZ>",
  "source_draft": "<path>",
  "decision": "keep",
  "work_item_id": "<id>",
  "skill": "<skill or empty>",
  "rationale": "<one-line>"
}
```

For merge/drop decisions: same shape, no `work_item_id`, with the
rationale capturing what overlapped or why dropped.

### Step 6: Write the summary report

Follow the template below. Section by section: filed (kept), merged,
dropped. Every row references the source draft path.

### Step 7: Self-check

- Every kept draft has a corresponding work-item id in the report
- Every merged draft cites the existing work item it merges with
- Every dropped draft has a reason
- The promotion log has one line per draft (kept / merged / dropped)

## Summary report template

```
# Proposal Promotion — <client>

| Field | Value |
|---|---|
| Date | YYYY-MM-DD |
| Source(s) | <bulleted paths> |
| Drafts considered | <count> |
| Filed as new work items | <count> |
| Merged with existing | <count> |
| Dropped | <count> |
| Author | LOSWF Agency |

## Filed

| # | Draft | Work item | Skill | Title |
|---|---|---|---|---|

## Merged

| # | Draft | Merged into work item | Rationale |
|---|---|---|---|

## Dropped

| # | Draft | Reason |
|---|---|---|
```

## Failure modes to avoid

- **Mass-promotion.** Filing 20 issues from one retro drowns the
  backlog. Default cap: 5 per promotion run. Operators can re-run if
  they have more to promote.
- **Forgetting the log.** Every decision (keep/merge/drop) lands a
  line in `.loswfx/state/proposal-promotions.jsonl`. The log is the
  audit trail.
- **Inferring skill from thin air.** When a draft doesn't suggest a
  skill and the inference is shaky, file the work item without a
  skill — body-only briefing is the safe default.
- **Promoting stale drafts.** If a draft references a metric that's
  no longer in the recent ledger window, the underlying signal has
  passed. Drop with reason "signal stale".

## Verification

The promotion is complete when:

- The summary report exists at the named path
- The promotion log has one new line per draft considered
- Every filed work item is queryable via `loswfx work list`
- The kept-count plus merged-count plus dropped-count equals the
  total drafts considered
