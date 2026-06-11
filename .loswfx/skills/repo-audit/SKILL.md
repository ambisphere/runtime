---
name: repo-audit
description: Perform a read-only health audit of a client repository and produce a markdown findings report. Use this skill as the default first deliverable of a new agency engagement — before touching any code, before proposing a roadmap, before opening any PR. The audit assesses dependencies, build/CI configuration, documentation coverage, test posture, license + governance, and surface-level code health. Output is a single markdown report under proposals/<client>/audit/<repo>.md scoped strictly to observations and findings (no fixes, no PRs, no code changes). Use a different skill (dependency-bump, docs-refresh, test-coverage-fill) for remediation.
max_iterations: 50
side: client
contract:
  kind: deliverable
  inputs:
    - kind: layer-3
      path: clients/{repo}/**
      required: true
  outputs:
    - path: proposals/{repo}/audit/*.md
      required: true
  verify:
    - truthful-status
    - skill-frontmatter
---

# Repository Audit

This skill produces a **read-only health audit** of a single client
repository. It is the LOSWF Agency's default opening move on a new
engagement: before proposing work, the agency observes.

## Purpose and boundaries

The audit produces evidence, not action. It commits to:

- A concrete, repository-specific picture of the asset's current state
- Findings tagged by domain (deps / build-ci / docs / tests / license / code)
- Severity calibration (`blocker` / `attention` / `note`) per finding
- A short prioritized recommendation list at the end

It does **not** contain:

- Code changes (a separate skill performs each remediation)
- Open PRs or branches (the audit is observation, not intervention)
- Roadmap-level recommendations (`engagement-plan` skill owns that)
- Praise, marketing language, or vague reassurance

## Inputs

One required input:

- **Target repository** — `<owner>/<repo>` reachable via `gh api` /
  `git clone`. The agent has read access; no write operations are
  performed by this skill.

Optional inputs:

- **Client context** — name of the client (used in the report header
  and output path). Defaults to the repository owner.
- **Engagement scope** — a one-line statement of why this audit is
  being performed. Defaults to "initial engagement audit."

## Output

A single markdown file at `proposals/<client>/audit/<repo>.md`
matching the template at `references/audit-template.md`. The path
convention groups all artifacts for a given engagement under the
client's proposals tree, parallel to how the design-RFP response
landed under `proposals/loswf/`.

## Workflow

### Step 1: Load the template

Read `references/audit-template.md` first. It defines section order,
table schemas, and the severity vocabulary. Work from the template,
not from memory.

### Step 2: Gather observations

Use only **read-only operations**. The valid surfaces:

- `gh api repos/<owner>/<repo>` (via `run_command`) — repository
  metadata (default branch, visibility, language, latest push)
- `github_read_file(owner, repo, path)` — single-file content with
  automatic base64 decode. Use this for any file the audit needs to
  read in the CLIENT repo. NEVER use `read_file` for client content —
  `read_file` is workspace-only and will silently shadow a same-named
  local file.
- `gh api repos/<owner>/<repo>/contents/<path>` (via `run_command`) —
  use for DIRECTORY listings (`github_read_file` is single-file only)
- `gh api repos/<owner>/<repo>/commits` (via `run_command`) — recent
  commit history
- `gh issue list --repo <owner>/<repo>` — open issues
- `gh pr list --repo <owner>/<repo>` — open PRs
- `gh release list --repo <owner>/<repo>` — releases

Do not clone the repo unless asked. The audit is a surface-level view;
deep code analysis belongs to a separate skill (`code-review`).

For each domain below, gather enough evidence to score it with a
severity. Write the evidence as part of the finding — a finding without
evidence is a guess.

#### Domain 1: Dependencies

- For Node: read `package.json`, count direct dependencies, identify
  unpinned ranges (`^`, `~`) on dependencies critical to the build.
- For Go: read `go.mod`, check Go version, count direct require lines.
- For Python: read `requirements.txt` / `pyproject.toml`.
- For Ruby: read `Gemfile` / `Gemfile.lock`.

Flag: lockfile drift (lockfile newer than package manifest), missing
lockfile when one is expected, deprecated runtime versions
(Node < 18, Go < 1.21, Python < 3.10).

#### Domain 2: Build + CI

- Read `.github/workflows/*.yml` if present.
- Identify build, test, lint, deploy workflows.
- Check action versions (deprecated actions are an attention finding).
- Check runner OS / version pins.

Flag: no CI configured, deprecated action versions, missing test
workflow.

#### Domain 3: Documentation

- Read `README.md` — is it informative? Does it cover install, run, deploy?
- Look for `CONTRIBUTING.md`, `LICENSE`, `CODE_OF_CONDUCT.md`.
- Check `docs/` directory if present.

Flag: missing README, README that doesn't explain how to run the
project, no LICENSE file.

#### Domain 4: Tests

- Look for `test/` or `tests/` or `*_test.go` or `__tests__/` or
  `spec/` directories.
- If a test script is declared in `package.json` / `Makefile`,
  note it.
- Estimate test density qualitatively (no tests / sparse / present /
  comprehensive).

Flag: no tests, no test-runner configured, tests present but no CI
gate.

#### Domain 5: License + governance

- Check `LICENSE` file exists and is one of the standard SPDX
  identifiers.
- Check `.github/CODEOWNERS` exists for repos with multiple
  contributors.

Flag: no license, ambiguous license, missing CODEOWNERS for shared
repos.

#### Domain 6: Code health (surface)

- Look at recent commit cadence — daily, weekly, dormant?
- Count open issues and PRs.
- Check if the default branch shows recent activity.

Flag: dormant for >90 days with open issues / PRs, default branch
behind contributors' branches, large unreviewed PRs.

### Step 3: Score severity

Apply this vocabulary consistently:

- **`blocker`** — actively prevents the engagement from proceeding
  safely. Example: no LICENSE on a repo we're being asked to ship
  artifacts into.
- **`attention`** — does not block work but should be addressed in the
  first few engagement cycles. Example: deprecated GitHub Action
  version with a known June 2026 sunset.
- **`note`** — observation worth recording but not requiring action
  within this engagement. Example: README mentions a feature that the
  current code doesn't implement (might be roadmap, might be drift).

Severity is per finding, not per domain. A domain can contain
findings at multiple severities.

### Step 4: Write the report

Follow `references/audit-template.md` exactly. Populate header
metadata (client, repo, branch, audit date), the per-domain finding
tables, and the closing prioritized recommendation list.

The recommendation list is at most five items, each one line, ordered
by severity then by remediation effort. Each recommendation names the
finding ID it addresses.

### Step 5: Self-check before submitting

Before the build is complete, verify:

- The output file exists at `proposals/<client>/audit/<repo>.md`.
- Every domain section has at least one finding (an empty domain
  should explicitly say "No findings.").
- Every finding has an ID (`F<domain>-<n>`, e.g. `F-deps-1`).
- The recommendation list references finding IDs from the body.
- The report contains the literal phrase "This audit is read-only —
  no code changes were proposed in this document."

## Illustrating this artifact

A repo audit benefits from a **findings severity matrix** when ≥5
findings land, or a **findings-by-domain** breakdown (dependencies /
build-CI / docs / tests / license / code-health) when the audit
spans multiple domains. Default to a `mermaid` pie or quadrant
chart; the audit is client-facing so brand polish is usually NOT
warranted (the data does the work). See
[`illustrate-doc`](../illustrate-doc/SKILL.md).

## Failure modes to avoid

- **Marketing-grade praise.** "Excellent codebase!" / "world-class
  CI." The audit is operational, not flattering. Observations only.
- **Speculation without evidence.** If you didn't read the file,
  don't claim the project does or doesn't have it. Use the gh API
  to verify.
- **Recommendations the audit didn't justify.** Every recommendation
  ties to a finding ID; findings without recommendations are fine,
  recommendations without findings are out of scope.
- **Crossing the read-only boundary.** This skill does not open
  PRs, push branches, or modify files in the client repo. If the
  agent finds itself wanting to fix something, that is signal to
  invoke a different skill — never extend this one to remediate.
