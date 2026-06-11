---
name: pr-review
description: Review one open pull request on a client repository and produce a structured review document containing per-file comments, severity-tagged findings, and an overall verdict. Use this skill when a client opens a PR and LOSWF Agency is asked to provide review feedback. Output is a markdown file at proposals/<client>/reviews/<repo>-pr-<n>.md. Read-only — no comments are posted to the PR itself; the document is the deliverable the operator manually relays. Use a different skill (repo-audit) for whole-repo assessment without a specific PR; use code-review (future) for inspecting a branch that isn't yet a PR.
side: client
contract:
  kind: deliverable
  inputs:
    - kind: layer-3
      path: clients/{repo}/**
      required: true
  outputs:
    - path: proposals/{repo}/reviews/*.md
      required: true
  verify:
    - skill-frontmatter
---

# Pull Request Review

This skill performs a structured review of one open PR on a client
repository. The deliverable is a markdown document; posting comments
to the PR itself is an operator action, not part of this skill.

## Purpose and boundaries

The review commits to:

- Reading every file in the PR's diff
- Producing per-file comments tied to specific line ranges
- Severity-tagging each comment (`blocker` / `request-changes` / `nit`)
- An overall verdict (`approve` / `request-changes` / `comment`) with
  justification

It does **not** commit to:

- Posting comments to GitHub (operator-only; the document is a
  hand-off)
- Code changes (`pr-review` is read-only; remediation is the PR
  author's job)
- Merging or rejecting decisions (those are the client's call)

## Inputs

Required:

- **PR reference** — `<owner>/<repo>#<pr-number>` reachable via
  `gh pr view` and `gh pr diff`.

Optional:

- **Review focus** — a one-line note on what to weight ("focus on
  security", "focus on docs", "focus on API surface stability").
  Defaults to "full review."

## Output

A single markdown file at `proposals/<client>/reviews/<repo>-pr-<n>.md`
with this structure:

```
# PR Review — <repo> #<n>: <pr title>

| Field | Value |
|---|---|
| Client | <client> |
| Repository | <owner>/<repo> |
| PR | #<n> |
| Author | @<gh-handle> |
| Review date | YYYY-MM-DD |
| Reviewer | LOSWF Agency |
| Focus | <focus or "full review"> |

This review is a document, not posted comments. The operator will
relay findings to the PR.

## Summary

Three sentences: (1) what the PR does, (2) overall posture, (3) the
verdict in one sentence.

## Verdict

**<approve | request-changes | comment>** — one paragraph justification
referencing the most decisive finding IDs.

## Per-file findings

### <relative/path/to/file>

| ID | Severity | Lines | Finding |
|---|---|---|---|
| R-<file>-1 | <severity> | L42-45 | Concrete observation tied to specific lines. |

## Cross-cutting findings

Comments that span multiple files: API contract drift, naming
inconsistencies, missing test coverage for the changed surface.

| ID | Severity | Files | Finding |
|---|---|---|---|

## Recommended next steps

At most three items. Order: things that block merge first, then
suggested improvements, then nits.
```

## Workflow

### Step 1: Load PR context

```sh
gh pr view <owner>/<repo>#<n>
gh pr diff <owner>/<repo>#<n>
gh api repos/<owner>/<repo>/pulls/<n>/files
```

Build an inventory: files changed, additions, deletions, the PR
description, the author's stated intent.

### Step 2: Read each changed file in full

The diff shows the change in isolation. The full file shows the change
in context. Both matter — a 5-line edit can be wrong because of what
the surrounding 50 lines do.

### Step 3: Score per-file findings

For each file, ask:

- Does the change do what the PR description claims?
- Does the change introduce bugs (off-by-one, nil deref, race, etc.)?
- Does the change break the file's existing contract (renamed export,
  changed signature, removed documented behavior)?
- Does the change have appropriate tests? If the file is in a tested
  package, the change should be tested.
- Does the change follow the repo's stated conventions (CONTRIBUTING.md,
  CODE_OF_CONDUCT.md, language style guides)?

Tag each finding with severity:

- **`blocker`** — must not merge as-is. Bug, broken contract, security
  issue, or regression that the PR author can fix in this PR.
- **`request-changes`** — should not merge as-is but the fix may
  warrant a follow-up PR. Architectural concerns, design smells,
  testing gaps.
- **`nit`** — minor style or naming, no impact on correctness. The
  author can choose to address or not.

### Step 4: Score cross-cutting findings

Comments that span multiple files: did the PR change a function's
signature without updating all call sites? Did it add a new dependency
without bumping the lockfile? These go in the cross-cutting section.

### Step 5: Write the verdict

- **`approve`** — no blockers, no request-changes findings. Nits are
  OK to leave for follow-up.
- **`request-changes`** — at least one request-changes or blocker
  finding. Author should iterate before merge.
- **`comment`** — neutral. Used when the review is informational
  (e.g. early draft PR seeking direction).

### Step 6: Self-check

- Every file in the PR's diff has a section in "Per-file findings"
  (even if "No findings.")
- Every finding has an ID, severity, and line range
- The recommended-next-steps list is ≤3 items
- The literal phrase "This review is a document, not posted comments"
  appears

## Failure modes to avoid

- **Posting to the PR.** This skill produces a document; the operator
  relays. Never `gh pr review --comment` from within the skill.
- **Approving without reading.** "LGTM" without per-file findings is
  not a review.
- **Bikeshedding nits as blockers.** Severity is calibrated for impact,
  not personal preference.
- **Inventing test coverage.** Don't claim "this is tested" unless
  you read the test file and confirmed it.

## Verification

The review is complete when:

- The output file exists at `proposals/<client>/reviews/<repo>-pr-<n>.md`
- The verdict is one of approve / request-changes / comment
- Every changed file in the PR appears in the per-file findings
- The recommended-next-steps section has ≤3 items
