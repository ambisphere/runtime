---
name: dependency-bump
description: Identify outdated dependencies in a client repository, assess upgrade risk, and produce a structured upgrade proposal document grouping recommended bumps by safety tier (patch / minor / major). Use this skill after a repo-audit has identified deps as an attention or blocker domain, or when a client asks for a dependency-health pass. Output is a markdown plan at proposals/<client>/dependency-plan/<repo>.md. Read-only — does not modify package manifests or open PRs; remediation PRs are a separate skill step. Use a different skill (repo-audit) for the initial whole-repo assessment.
side: client
contract:
  kind: deliverable
  inputs:
    - kind: layer-3
      path: clients/{repo}/**
      required: true
  outputs:
    - path: proposals/{repo}/dependency-bumps/*.md
      required: true
  verify:
    - skill-frontmatter
---

# Dependency Bump

This skill produces a **dependency upgrade plan** for one client
repository. The plan is what an operator (or a future `apply` skill)
acts on; this skill itself does not modify manifests.

## Purpose and boundaries

The plan commits to:

- An inventory of current dependencies vs. latest available versions
- Risk-tier classification per dependency: `patch` / `minor` / `major`
- Per-dependency notes on breaking changes from changelog/release-notes
- A prioritized upgrade sequence (patches first, minors next, majors last)

It does **not** commit to:

- Modifying `package.json` / `go.mod` / `Gemfile` / etc.
- Opening PRs against the client repo
- Running `npm install` or equivalent (the proposal stays declarative)
- Recommending major version jumps without a paragraph of risk
  justification per dep

## Inputs

Required:

- **Target repository** — `<owner>/<repo>` reachable via `gh api`

Optional:

- **Scope** — `direct-only` (default) or `direct-and-transitive`. Most
  proposals stop at direct deps; transitive bumps are usually a
  lockfile refresh, not a per-dep decision.

## Output

A single markdown file at `proposals/<client>/dependency-plan/<repo>.md`
with this structure:

```
# Dependency Upgrade Plan — <repo>

| Field | Value |
|---|---|
| Client | <client> |
| Repository | <owner>/<repo> |
| Manifest | <package.json / go.mod / etc.> |
| Plan date | YYYY-MM-DD |
| Author | LOSWF Agency |
| Scope | direct-only / direct-and-transitive |

This plan is declarative — no manifests modified, no PRs opened.

## Summary

Three sentences: (1) ecosystem (Node / Go / Python / etc.), (2) overall
posture (current / lagging / stale), (3) the highest-impact recommended
bump.

## Tier 1 — Patches (low risk)

| Dependency | Current | Latest | Notes |
|---|---|---|---|

## Tier 2 — Minors (medium risk)

| Dependency | Current | Latest | Breaking changes | Notes |
|---|---|---|---|---|

## Tier 3 — Majors (high risk)

| Dependency | Current | Latest | Breaking changes | Risk justification |
|---|---|---|---|---|

## Recommended sequence

Numbered list, ordered by risk-tier ascending then by impact descending.
```

## Workflow

### Step 1: Identify the manifest

Use `gh api repos/<owner>/<repo>/contents/<path>` to fetch the dep
manifest. Common locations:

- Node: `package.json`
- Go: `go.mod`
- Python: `requirements.txt`, `pyproject.toml`
- Ruby: `Gemfile`

If multiple manifests exist (monorepo with workspaces), produce one
plan per manifest.

### Step 2: Resolve current versions

Read the manifest. For each direct dep, capture: name, current
version constraint (`^1.2.3`, `~1.2.0`, `1.2.3`, `>=1.0.0 <2.0.0`).

### Step 3: Resolve latest versions

For Node deps: `gh api -X GET /repos/<owner>/<repo>/contents/package.json`
won't help here. Use the `npm view <pkg> version` shell command (if
`npm` is in policy.allowedCommands) OR use the package registry's
HTTP API via `gh api` if a mirror exists. For Go: parse the latest
tag from `gh api repos/<go-module-owner>/<repo>/tags`. For Python:
PyPI JSON API via `curl` (if whitelisted).

If the runtime doesn't whitelist the registry fetch tool, the plan
falls back to: declare current versions and flag "needs registry
check" — a human-in-the-loop sanity check before the upgrade.

### Step 4: Classify risk

For each dep:

- **`patch`** — the version difference is patch-level only (1.2.3 → 1.2.5).
  Risk: very low. Move to Tier 1.
- **`minor`** — minor-level bump (1.2.x → 1.3.x). Read the release
  notes if available. Risk: low to medium. Move to Tier 2.
- **`major`** — major-level bump (1.x → 2.x). MUST read the breaking-
  changes section of the release notes. Risk: high. Move to Tier 3.

For deps with no release notes available, default to one tier higher
than the version arithmetic suggests.

### Step 5: Write the breaking-changes notes

For Tier 2 and Tier 3 deps: a one-paragraph summary of what changes
between current and latest, sourced from the upstream's CHANGELOG.md,
release notes, or migration guide. If you can't find a source, write
"No upstream release notes located — review by hand before applying."
Do not invent breaking changes.

### Step 6: Write the recommended sequence

Numbered list ordering: Tier 1 (all patches, grouped) → Tier 2 in
order of low-impact-first → Tier 3 each as its own step with
explicit "apply in isolation, run full test suite, ship as separate
PR" guidance.

### Step 7: Self-check

- Every dep classified at exactly one tier
- Every Tier 2 / Tier 3 entry has a breaking-changes note (even if
  "None documented" — the absence is a finding)
- The recommended-sequence list references the same dep names that
  appear in the tier tables
- The literal phrase "This plan is declarative — no manifests
  modified, no PRs opened." appears

## Failure modes to avoid

- **Modifying manifests in this skill.** This skill produces a plan.
  Applying it is a separate operation.
- **Inventing breaking changes.** If no release notes are accessible,
  say so — don't speculate.
- **Mass-bumping in Tier 1.** Even patch-level bumps to a
  transitive-heavy package (e.g. webpack, vite, react) can break the
  build. Tier 1 is "ship safely in a single PR"; if a patch has known
  install-time side effects, demote to Tier 2.
- **Skipping the sequence.** Without the recommended-sequence list,
  the plan is a snapshot, not a plan.

## Verification

The plan is complete when:

- The output file exists at `proposals/<client>/dependency-plan/<repo>.md`
- All three tier sections are present (even if empty: write "No
  findings at this tier.")
- A recommended-sequence list is present
- The literal phrase "This plan is declarative — no manifests modified,
  no PRs opened." appears
