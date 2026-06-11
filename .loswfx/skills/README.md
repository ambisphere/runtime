# LOSWF Agency Skills

This directory holds **LOSWF Agency skills** — reproducible competency bundles
that capture how the agency performs specific operations on client
repositories. Each skill is one self-contained directory with a top-level
`SKILL.md` (YAML frontmatter + narrative procedure), optional `references/`
for canonical templates and exemplars, and optional `evals/` for
verification fixtures.

## Why skills

When LOSWFX agents perform agency work — auditing a repo, reviewing a PR,
bumping dependencies, refreshing docs — the methodology should be a
first-class artifact, not crammed into a per-engagement parent work-item
body. Skills are how we capture the "how we do this" so:

1. **Future agents can reproduce the work.** Same skill, same shape of
   output, regardless of which model or engagement runs it.
2. **Quality is auditable.** The skill states what "good" looks like; the
   eval fixtures verify the output matches.
3. **Skills improve over time.** When a real engagement surfaces a gap
   ("our audit missed the unused-dependency check"), the skill gets
   updated and the next engagement benefits.

This pattern follows the convention established by
[gears-playground/Product/skills/](https://github.com/gears-playground/Product/tree/main/skills) —
YAML frontmatter (name + description), narrative procedure, optional
references and evals.

## Skill anatomy

```
skills/<skill-name>/
├── SKILL.md            # YAML frontmatter + the methodology
├── references/         # templates, exemplars, schemas (optional)
│   └── *.md
└── evals/              # fixtures that verify skill output (optional)
    └── *
```

`SKILL.md` frontmatter:

```yaml
---
name: <skill-name>
description: <one-paragraph summary of when to use this skill, what it produces, and how it differs from related skills>
---
```

The description must be specific enough that a planner agent reading
many skill descriptions can pick the right one. Bad: "audits repos."
Good: "performs a read-only repository health audit producing a
findings report covering dependencies, CI configuration, documentation
coverage, and test posture. Use this before committing to recurring
engagement work on a new client repository."

## Current skills

| Skill | What it does |
|---|---|
| [`repo-audit`](repo-audit/SKILL.md) | Read-only health audit of a client repository → markdown findings report. The default first-engagement deliverable. |
| [`rfp-response`](rfp-response/SKILL.md) | Respond to a client RFP with a coherent multi-document proposal grounded in the RFP's specific asks. |
| [`gherkin-feature-drive`](gherkin-feature-drive/SKILL.md) | Implement one `.feature` file end-to-end against a target codebase — minimal code, scenario-grounded verification. |
| [`story-writer`](story-writer/SKILL.md) | Derive new high-value LOSWFX stories from a named persona's view (default Operator) by reading existing features + product/project state, and write them as INVEST-shaped, declarative Gherkin `.feature` files with happy/error/edge coverage and a value rationale. Authoring counterpart to `gherkin-feature-drive`. |
| [`triage-decomposition`](triage-decomposition/SKILL.md) | Decompose a parent work item into 2-6 independently shippable children grounded in evidence from referenced documents. |
| [`pr-review`](pr-review/SKILL.md) | Review one open pull request and produce a per-file structured review document with severity-tagged findings. Read-only; deliverable is a document, not posted comments. |
| [`dependency-bump`](dependency-bump/SKILL.md) | Identify outdated deps in a client repo and produce a tiered upgrade plan (patch / minor / major) with breaking-changes notes. Read-only; remediation is a separate step. |
| [`engagement-plan`](engagement-plan/SKILL.md) | Synthesize prior agency artifacts (audits, RFP responses, discovery) into a sequenced 4-12 week engagement plan with named phases, deliverables-by-skill, risks, and review cadence. |
| [`product-brief`](product-brief/SKILL.md) | Consolidate a client's scattered product docs (vision, RFP, roadmap, architecture) into a single canonical product brief that downstream skills consume as the product reference. |
| [`iteration-plan`](iteration-plan/SKILL.md) | Break an engagement-plan phase (or an audit's remediation list) into one iteration of 5-15 shippable work items with T-shirt sizing, sweep ordering, and a demo/handoff anchor. LOSWF Agency uses "iteration" deliberately — sprints imply a race, iterations imply repeatable cycles. Slow and steady. |
| [`writing-tests`](writing-tests/SKILL.md) | Write tests that validate behavior at stable contracts — fakes over mocks, dependencies at the edges, deterministic + isolated. Adopted verbatim from loswf/loswf. |
| [`go-engineering-discipline`](go-engineering-discipline/SKILL.md) | Umbrella Go delivery methodology — define problem/solution, then deliver via incremental TDD/BDD while holding clean code, clean architecture, and SOLID as merge gates. Orchestrates `gherkin-feature-drive` (BDD), `writing-tests` (TDD), and `code-quality-review` (structural gate); cites CODE-JUDO/CODE-SMELLS/ARCHITECTURE. Load when an engagement wants the full Go discipline, not just one sub-procedure. |
| [`effort-pointing`](effort-pointing/SKILL.md) | Assign relative effort points across agent modes — complexity, uncertainty, integration cost — never time. Pairs with iteration-plan for defensible T-shirt sizing. Adopted from loswf/loswf with iteration-vs-sprint terminology normalized. |
| [`backlog-grooming`](backlog-grooming/SKILL.md) | Groom a backlog through PO-driven clarification, scope tightening, gap/dependency identification, and pointing — producing prioritized iteration-ready items. Sits naturally between audit findings and iteration-plan. Adopted from loswf/loswf. |
| [`incremental-commit-all`](incremental-commit-all/SKILL.md) | Examine git history and working-tree changes, stage and make incremental meaningful commits until the repo is clean. Operational discipline for the build capability. Adopted from loswf/loswf. |
| [`milestone-planner`](milestone-planner/SKILL.md) | Plan the next batch of LOSWFX milestones — review history (carry-forward), roadmap (active arc), vision (FOUNDATIONS/ARCHITECTURE), and snapshot, take operator intention, settle the strategic decisions via `AskUserQuestion`, then draft template-shaped `MILESTONE-<N>-PLANNING-DRAFT.md` files (+ optional arc note) ready for `milestone-grinder` to promote. The upstream complement to the grinder. |
| [`retrospective`](retrospective/SKILL.md) | Read the workspace's ledger and produce a retro report covering recent runs, halt patterns, drift signals, and proposal candidates. Operations & Continuity gear — closes the loop with metrics-grounded synthesis. |
| [`harvester`](harvester/SKILL.md) | Scan a client repository for external actionable signals (TODOs, failing CI, stale PRs, CVEs, upstream changelog drift) and file up to 5 high-quality issues with stable Work-Key dedupe. Operations & Continuity gear — external-signal complement to the retro. Adapted from loswf/loswf2's harvester role. |
| [`proposal-promotion`](proposal-promotion/SKILL.md) | Take proposal candidates from a retro or harvest (or operator drafts) and promote keep / merge / drop into tracked work items, with a per-workspace promotion ledger. Closes the continuous-improvement loop — drift signals become queued work. |

## How agents load a skill

Skills are loaded automatically by the kernel when a work item names
one via `--skill <name>` at creation:

```
loswfx work add "Audit gears-ui" --skill repo-audit --body "Target: gears-playground/gears-ui"
```

The kernel records the skill name on the `work_item.created` event.
On every capability run against that work item, `RunAgentCapability`
resolves the skill via `LoadSkill(root, cfg, name)` and prepends the
`SKILL.md` body to the agent's system prompt (wrapped in a stable
`# Loaded skill: <name>` ... `# End of loaded skill` block so reviewers
can grep prompts).

The kernel emits a `skill.load.attempted` ledger event with
`resolved: true/false` so the audit trail records whether the
methodology actually reached the agent.

**Search path resolution:**

1. If `cfg.Skills.Path` is set (in `.loswfx/config.json`): paths are
   split on `os.PathListSeparator` and searched in order. Workspace-
   local paths typically come first so operators can override
   shipped methodology with engagement-specific tweaks.
2. If unset: defaults to `<workspace>/skills/`.

**Missing skill is soft-fail:** the kernel emits the load-attempted
event with `resolved: false` and the agent runs with body-only
briefing. The work item's body is always the authoritative scope
statement; the skill is methodology, not scope.

## Adding a skill

1. Create `skills/<your-skill>/SKILL.md` with the YAML frontmatter and
   narrative procedure.
2. If the skill produces a structured deliverable (PRD, audit report,
   release notes), add the canonical template under `references/`.
3. If the output has verifiable invariants (must contain section X,
   must reference all phases, etc.), add fixtures under `evals/`.
4. Add an entry to the "Current skills" table above.
5. Open a PR — the change-review gate is on skill quality, not just
   structural correctness.

## Standards

- **No fabricated past clients.** Skills speak in terms of method,
  not invented engagements.
- **No grandiose language.** Agency skills are operational, not
  marketing. "Audits the repository" beats "delivers transformative
  enterprise-grade analysis."
- **Verifiable outputs.** Every skill should declare what successful
  output looks like in a way a downstream verify step can check.
