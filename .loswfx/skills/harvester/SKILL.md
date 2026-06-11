---
name: harvester
description: Periodically scan a client repository for actionable signals (TODOs, failing CI, stale PRs, dependency advisories, upstream changelog drift, test coverage gaps) and file the highest-quality up to 5 GitHub issues that capture real follow-on work. Use this skill on a regular cadence (weekly or per-iteration) to keep the backlog grounded in live signals rather than memory. Output is a harvest report at proposals/<client>/harvests/<YYYY-MM-DD>.md plus the actual filed issues. Use a different skill (repo-audit) for the opening-engagement health check, or (retrospective) for synthesis of our own pipeline runs.
max_iterations: 80
side: shadow
output_dir: engagements/{repo}/harvests
contract:
  kind: deliverable
  inputs:
    - kind: layer-3
      path: clients/{repo}/**
      required: true
  outputs:
    - path: engagements/{repo}/harvests/*.md
      required: true
  verify:
    - shadow-persistence
    - skill-frontmatter
---

# Harvester

This skill is the **Operations & Continuity** gear's external-signal
scanner. It complements the retrospective skill: the retro reads
LOSWFX's own ledger; the harvester reads the client's live signals
(GitHub state, dep manifests, upstream changelogs).

Adopted from the loswf/loswf2 harvester role with adaptation for
the LOSWFX skill convention.

## Purpose and boundaries

The harvester commits to:

- Scanning a fixed set of signal sources per run
- Deduping candidates via stable Work-Keys (hash of source + path + concept)
- Filing at most 5 high-quality issues per run — quality over volume
- Citing the URL or path that justifies every issue
- Honoring per-engagement ignore lists (labels, authors, paths)

It does **not** commit to:

- Closing existing issues — only creating
- Harvesting from issues already in the pipeline (already-labeled
  `factory:phase:*` work items)
- Speculating about issues without ledger or live evidence
- Auto-prioritizing — every harvested issue enters at the default
  triage queue; classification is intake's job

## Inputs

Required:

- **Target repository** — `<owner>/<repo>` reachable via `gh`
- **Client name** — used in the output report path

Optional:

- **Time window** — how far back to scan commits (default: 30 days)
- **Ignore list** — labels / authors / paths to skip

## Output

Two deliverables:

1. **Harvest report** at `proposals/<client>/harvests/<YYYY-MM-DD>.md`
   summarizing every candidate considered, dedupe rejections, and
   filed issues.
2. **Filed GitHub issues** — up to 5, each with a stable Work-Key in
   the body for future dedupe.

## Workflow

### Step 1: Establish scope

Use `gh api repos/<owner>/<repo>` to confirm access and resolve the
default branch. Load any per-engagement ignore list (paths the
operator has flagged, authors to skip, labels that mean "out of
scope for harvest").

### Step 2: Scan signal sources in order

Time-budget aware — stop scanning when you've identified 10 candidates
or hit the 80-iteration cap. Sources in order:

1. **Recent commits** — `gh api repos/<owner>/<repo>/commits` (cap
   30 days). Scan commit messages and (via `gh api .../commits/<sha>`)
   touched files for TODO / FIXME / XXX / HACK / NOTE comments.
2. **Failing CI runs** — `gh run list --repo <owner>/<repo> --branch
   <default> --status failure --limit 10`. Each unique failing
   workflow is a candidate.
3. **Stale PR review threads** — `gh pr list --repo <owner>/<repo>`
   plus `gh pr view <n> --comments` for any PR with unaddressed
   review comments older than 7 days.
4. **Vision / roadmap gaps** — if the repo has a vision or roadmap
   doc, read it and compare to the current open-issues list. Items
   in vision but not in the backlog are candidates.
5. **Dependency advisories** — read the package manifest (`package.json`,
   `go.mod`, etc.) and for each direct dep, check GitHub Advisories
   via `gh api graphql` or web search for CVEs filed in the last
   90 days against that exact package.
6. **Upstream changelog drift** — for the same direct deps, check
   the upstream repo's recent releases for "breaking" or "deprecated"
   keywords in release notes.
7. **Test coverage gaps** — if a `coverage.out` or equivalent is
   present, identify files with no test coverage and flag the
   highest-traffic ones (most-edited in recent commits).

### Step 3: Compute Work-Keys

For each candidate, compute a stable hash:

`Work-Key = sha256(source + ":" + file_path + ":" + concept)[:12]`

Where:
- `source` is the signal source (commit / ci / pr / vision / dep-cve /
  changelog / coverage)
- `file_path` is the path the issue would touch (or empty for
  cross-cutting)
- `concept` is the short concept noun (e.g. "wc-pipe-grep",
  "react-19-breaking", "missing-test-for-foo")

Before filing: `gh issue list --repo <owner>/<repo> --search "<Work-Key>"`.
If a match exists (open or closed within 30 days), SKIP — store the
key in the report's dedupe-rejections section.

### Step 4: File the top 5

Rank candidates by:

1. Severity (CVE > breaking-change > failing-CI > stale-PR > TODO >
   coverage-gap)
2. Recency (newer > older)
3. Impact-on-default-branch (touches active code > touches dormant
   code)

For the top 5: `gh issue create` with:

- `--title` — imperative, ≤80 chars
- `--body` — context block (what was observed), evidence URLs,
  Work-Key for dedupe, optional acceptance criteria
- `--label factory:type:bug` for advisories / failing CI;
  `factory:type:chore` for upgrades + TODOs; `factory:type:feature`
  for vision-gap candidates

Apply `factory:type:*` (best guess). Leave size / phase blank — that's
intake's job.

### Step 5: Write the harvest report

Follow the report template. Include every candidate considered,
whether or not it was filed. Dedupe rejections are part of the
audit trail.

### Step 6: Self-check

- ≤5 issues filed
- Every filed issue has its Work-Key in the body
- Every candidate in the report cites a source URL or path
- The report's "Issues filed" section's URLs resolve

## Output report template

```
# Harvest Report — <client>/<repo>

| Field | Value |
|---|---|
| Repository | <owner>/<repo> |
| Harvest date | YYYY-MM-DD |
| Window | last <N> days |
| Author | LOSWF Agency |

## Issues filed

| # | Title | Type | Source | URL |
|---|---|---|---|---|

## Candidates considered (not filed)

| Source | Candidate | Why not filed |
|---|---|---|

## Dedupe rejections

| Work-Key | Matched existing issue |
|---|---|
```

## Failure modes to avoid

- **Volume over quality.** 50 small TODO-derived issues drown the
  backlog. 5 well-scoped issues advance it. The cap is hard.
- **Stale advisories.** If a CVE is older than 90 days and no upstream
  fix exists, the bug isn't actionable — skip.
- **Speculative test gaps.** "This file has no tests" is not a finding
  unless the file is in the active code path. Use commit frequency
  as a proxy for activity.
- **Crossing the file boundary.** This skill files issues; it does
  NOT propose fixes inline or open PRs. Remediation is per-issue
  pipeline work.

## Verification

The harvest is complete when:

- The output report exists at the named path
- ≤5 issues filed (count visible via the report's table)
- Every filed issue has a Work-Key embedded in its body
- The candidate-rejections section is non-empty (a harvester that
  considers nothing isn't doing the job)
