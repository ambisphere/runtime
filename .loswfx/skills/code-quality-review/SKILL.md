---
name: code-quality-review
description: Maximalist code-quality review of a branch or PR — refuses cosmetic polish, demands structural reframing. Use when an operator wants a deliberately harsh review for abstraction quality, file-size sprawl, anti-spaghetti enforcement, and missed code-judo opportunities. Approval requires both behavior correctness AND absence of available simplifications, not just one. Output is a markdown deliverable at proposals/<client>/code-quality/<repo>-<branch>.md with prioritization weighted toward structural regressions. Sister skill to pr-review (the conservative variant) — both cite docs/CODE-JUDO.md. Use this skill when the operator says "harsh review", "thermo-nuclear review", "code-quality review", or asks to deliberately surface missed simplifications. Do NOT use as the default review skill (use pr-review), to post to GitHub (read-only — operator relays), or as a substitute for repo-audit on a fresh engagement.
side: client
max_iterations: 50
contract:
  kind: deliverable
  inputs:
    - kind: layer-3
      path: clients/{repo}/**
      required: true
  outputs:
    - path: proposals/{repo}/code-quality/*.md
      required: true
  verify:
    - skill-frontmatter
    - truthful-status
---

# Code Quality Review

A deliberately maximalist review skill. Adapted from the
Cursor team-kit's `thermo-nuclear-code-quality-review`
pattern. Sister to [`pr-review`](../pr-review/SKILL.md);
both cite [`docs/CODE-JUDO.md`](../../docs/CODE-JUDO.md).

## Purpose and boundaries

The review commits to:

- Reading every file in the diff
- Producing severity-tagged findings prioritized by structural
  impact (not alphabetical, not file order)
- Demanding explicit reasoning when a clearly available
  code-judo move is being passed up
- Refusing approval when behavior is correct but structural
  regression is present
- Naming the pattern (file-size growth, spaghetti, abstraction
  leak) rather than vague "could be cleaner" feedback

It does NOT commit to:

- Posting to GitHub (read-only; operator relays)
- Code changes (remediation is the author's job)
- Approving on correctness alone (the bar is higher than
  `pr-review`'s)
- Acting as the default review skill — `pr-review` stays the
  default; this skill is the explicit-invocation maximalist
  variant

## The bar (different from pr-review)

`pr-review` approves when:
- No bugs
- No broken contracts
- Tests adequate
- Style conforms

This skill **also requires**:
- No structural regression introduced
- No missed code-judo move when a plausible path is visible
- No file pushed past the 1000-line presumptive boundary
  without a decomposition note
- No ad-hoc branching tangling an existing flow
- No bespoke helper duplicating a canonical utility
- No feature logic leaking into a shared path

If those are present, the verdict is `request-changes` even
when the code works. The operator picks this skill knowing
the bar is higher.

## Inputs

Required:

- **Branch or PR reference** — `<owner>/<repo>#<pr-n>` for a
  GitHub PR, or a local branch name + base ref. Accepts
  both so this skill runs pre-PR (`git diff main...HEAD`)
  or post-PR (`gh pr diff`).

Optional:

- **Review focus** — a one-line note ("structural pass",
  "watch for boundary leaks", "verify nothing crossed 1k
  lines"). Defaults to "full maximalist review".
- **Skip categories** — explicit waiver for a category if
  the operator knows the context requires the relaxation
  ("skip file-size: this is generated code"). Each skip
  appears in the deliverable with the operator's
  justification.

## Output

A single markdown file at
`proposals/<client>/code-quality/<repo>-<branch>.md`:

```
# Code Quality Review — <repo> <branch or #pr-n>

| Field | Value |
|---|---|
| Client | <client> |
| Repository | <owner>/<repo> |
| Branch/PR | <branch> / #<n> |
| Author | @<gh-handle> |
| Review date | YYYY-MM-DD |
| Reviewer | LOSWF Agency (maximalist) |
| Focus | <focus> |
| Skips | <none / list> |

This review is a document, not posted comments. The bar is
maximalist (per docs/CODE-JUDO.md); approval requires absence
of structural regression AND no obvious missed simplification.

## Verdict

**<approve | request-changes | comment>** — one paragraph
justification referencing the most decisive findings.

## Findings (prioritized)

### 1. Structural regressions
| ID | Severity | Files | Finding |
|---|---|---|---|

### 2. Missed simplifications (code-judo opportunities)
| ID | Severity | Files | Finding |
|---|---|---|---|

### 3. Spaghetti / branching growth
| ID | Severity | Files | Finding |
|---|---|---|---|

### 4. Boundary / abstraction / type leaks
| ID | Severity | Files | Finding |
|---|---|---|---|

### 5. File-size / decomposition
| ID | Severity | Files | Finding |
|---|---|---|---|

### 6. Modularity / canonical-helper reuse
| ID | Severity | Files | Finding |
|---|---|---|---|

### 7. Legibility / maintainability
| ID | Severity | Files | Finding |
|---|---|---|---|

## Recommended next steps

At most three items. Lead with the largest structural finding.
```

Note: the seven prioritized sections are mandatory section
headers. A section with no findings reads "No findings." but
the header stays so the operator scans the same shape every
time.

## Workflow

### Step 1: Load diff context

```sh
# For a PR:
gh pr view <owner>/<repo>#<n>
gh pr diff <owner>/<repo>#<n>
gh api repos/<owner>/<repo>/pulls/<n>/files

# For a local branch:
git diff <base>...HEAD
git diff --stat <base>...HEAD
```

Build an inventory: files changed, additions, deletions,
the largest files in the diff.

### Step 2: Compute file-size deltas

For every file in the diff, run `wc -l` before and after.
Flag every file the change pushes past 1000 lines. Flag
every file that grew by more than 200 lines in one diff.
These are presumptive blockers — the author must either
decompose the file or justify the growth explicitly.

### Step 3: Read every file in full

Not just the hunks. A 5-line edit can be wrong because of
what the surrounding 50 lines do; a structural finding is
wrong unless the reviewer understands the file's existing
shape.

### Step 4: Score per prioritization order

Walk the seven categories in order. For each finding, ask
the question that defines the category:

- **Structural regressions:** Did this diff make the local
  architecture worse (more coupling, more state, harder to
  scan)?
- **Missed simplifications:** Is there a code-judo move
  (per `docs/CODE-JUDO.md`) that would delete a whole
  category of complexity?
- **Spaghetti growth:** Does this add ad-hoc conditionals,
  scattered special cases, or one-off branches in unrelated
  flows?
- **Boundary leaks:** Did feature-specific logic land in a
  shared path? Did types lose precision (`any`, `unknown`,
  unnecessary optionality, cast-heavy)?
- **File size:** Did a file cross 1000 lines or grow by
  more than 200?
- **Modularity / canonical reuse:** Did the diff duplicate
  an existing helper instead of reusing it? Did logic land
  in the wrong package/module?
- **Legibility:** Are names, structure, comments clear?
  (Always lowest priority — never the lead finding.)

### Step 5: Tag severity

- **`blocker`** — must not merge as-is. Bug, broken
  contract, security issue, regression, *or any structural
  finding category 1-4 above that the author hasn't
  justified*.
- **`request-changes`** — should not merge as-is but the
  fix may warrant a follow-up. File-size growth past 1000
  lines without decomposition; spaghetti additions to
  existing flows; missed code-judo with a clear path.
- **`nit`** — minor style, naming, or polish. Author can
  address or defer. Never a blocker.

Note: this skill's `blocker` bar is **higher** than
`pr-review`'s. A correct-but-spaghetti-growing change is a
blocker here; it would be `request-changes` in `pr-review`.

### Step 6: Write the verdict

- **`approve`** — no findings in categories 1-4; categories
  5-7 findings are at most `request-changes` and the
  author has signaled a follow-up plan.
- **`request-changes`** — at least one `blocker` or
  `request-changes` in categories 1-4. Author iterates
  before merge.
- **`comment`** — informational. Used when the operator is
  asking for a structural sanity-check on early-draft work.

### Step 7: Self-check

- Every category 1-7 has a section header (even if "No findings.")
- Every finding cites file path + line range
- Every category 1-4 finding includes the code-judo or
  alternative-structure phrasing — never a vague "could
  be cleaner"
- The recommended-next-steps list is ≤3 items
- The literal phrase "This review is a document, not posted
  comments" appears

## Review-comment library

Concrete phrasings to reach for, not vague suggestions:

- "this pushes `<file>` past 1000 lines. can we decompose
  into `<sub-module>` first?"
- "this adds another special-case branch into an already
  busy `<function>`. can we move this behind its own
  abstraction?"
- "this works, but it makes the surrounding code more
  spaghetti. let's keep the behavior and restructure the
  implementation — see `docs/CODE-JUDO.md`."
- "this feels like feature logic leaking into a shared
  path. can we isolate it in `<feature module>`?"
- "this abstraction seems unnecessary. can we just keep the
  direct flow?"
- "why does this need a cast / optional here? can we make
  the boundary more explicit instead?"
- "this looks like a bespoke helper for something we
  already have in `<canonical location>`. can we reuse the
  canonical one?"
- "i think there's a code-judo move here that makes this
  much simpler. can we reframe so these branches
  disappear?"
- "this refactor moves complexity around, but doesn't
  delete it. is there a way to make the model itself
  simpler?"

## Failure modes to avoid

- **Approving on correctness alone.** Behavior-correct ≠
  structurally-sound. The bar is both.
- **Bikeshedding.** A finding in category 7 (legibility)
  is never the lead. If categories 1-4 are clean, the
  verdict tends toward approve.
- **Vague feedback.** "This could be cleaner" is not a
  finding. "This pushes `<file>` past 1000 lines —
  consider extracting `<concrete suggestion>`" is.
- **Posting to GitHub.** Read-only. The deliverable is the
  document; the operator relays.
- **Substituting for `pr-review` by default.** This skill
  is the explicit-invocation maximalist variant. Default
  reviews still use `pr-review`.

## Verification

The review is complete when:

- The output file exists at the canonical path
- The verdict is one of approve / request-changes / comment
- All seven category headers are present (even with "No
  findings.")
- Every category 1-4 finding cites a code-judo or
  alternative-structure phrasing
- The recommended-next-steps list is ≤3 items
- File-size presumptive blockers are surfaced or the operator
  has waived them with justification in the Skips field

## See also

- [`docs/CODE-JUDO.md`](../../docs/CODE-JUDO.md) — the
  canonical pattern reference both review skills cite.
- [`skills/pr-review/SKILL.md`](../pr-review/SKILL.md) —
  the conservative sibling. Same shape, lower bar.
- [`skills/repo-audit/SKILL.md`](../repo-audit/SKILL.md) —
  the engagement-opening read-only audit. Different scope
  (whole repo, not a diff).
- Cursor team-kit's `thermo-nuclear-code-quality-review` —
  the upstream pattern this skill adapts.
