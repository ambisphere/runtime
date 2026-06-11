---
name: market-scout
description: >
  Comparative product/market research with adversarial fact-checking.
  Evaluates and ranks N candidates (tools, models, vendors, competitors)
  against an explicit weighted rubric, fanning out web searches per
  candidate, verifying every claim by 3-vote adversarial review, and
  emitting a cited scorecard. Use when the agency must pick or justify a
  choice between alternatives BEFORE producing client-facing artifacts —
  e.g. which OpenRouter model to drive the pipeline, which library/vendor
  to adopt, or a competitive landscape scan. Output is an agency-internal
  markdown scorecard in the shadow repo under
  engagements/<repo>/research/market-scout/. PRIVATE — never shipped to a
  client. For a single-topic narrative note use (research-brief); for live
  repo signal use (harvester). This skill is the deep-research fan-out
  harness specialized for head-to-head comparison.
max_iterations: 60
side: shadow
output_dir: engagements/{repo}/research/market-scout
rubric:
  - id: frontmatter
    description: "starts with YAML frontmatter block (--- delimiters)"
    pattern: '(?s)\A\s*---\n.*?\n---'
  - id: subject
    description: "states the comparison subject"
    pattern: '(?i)subject'
  - id: ranking_table
    description: "contains a ranked scorecard / comparison table"
    pattern: '\|.*\|'
  - id: weighted_score
    description: "reports a weighted score per candidate"
    pattern: '(?i)weighted'
  - id: citations_min_3
    description: "cites at least 3 source URLs"
    pattern: '(?s)(https?://.*){3,}'
  - id: caveats
    description: "includes a caveats / limitations section"
    pattern: '(?i)caveat|limitation'
---

# market-scout

A two-layer skill. **This file is only the launcher and scope gate** — the
fan-out/verify/score engine is the named workflow
`.claude/workflows/market-scout.js` (modelled on the `deep-research`
harness). Your job here is to scope the comparison well, run the workflow,
then persist the result as a committed shadow artifact.

## 1 — Scope gate (do this BEFORE running anything)

A comparison is only as good as its rubric. If the request is missing any
of the following, ask 2–3 sharp clarifying questions first — do not guess:

- **Candidates** — the specific alternatives to compare (or a clear field
  to infer them from). "Compare some databases" is too vague.
- **Criteria + weights** — what actually matters, in priority order. Reuse
  an existing agency rubric if one applies (e.g. the MODEL-PANEL protocol
  for model selection).
- **Constraints** — budget, region, license posture, must-have
  capabilities, the incumbent/baseline to beat.

When the request is already specific (a known rubric, named candidates),
skip the questions and proceed.

## 2 — Run the workflow

Pass a structured object when you have one (preferred — it pins the rubric
so the workflow doesn't re-derive it):

```
Workflow({
  name: "market-scout",
  args: {
    subject: "Single all-rounder model to drive the loswfx pipeline",
    candidates: [{ name: "deepseek-v4-pro" }, { name: "glm-5.1" }, ...],
    criteria: [
      { id: "tool-use", label: "Reliable read-only tool use, no refusals", weight: 5, check: "function-calling benchmarks; refusal reports" },
      { id: "json", label: "Emits parseable structured JSON", weight: 4 },
      { id: "price", label: "OpenRouter $/Mtok", weight: 3 },
      ...
    ]
  }
})
```

Or pass a free-form brief string and let the Scope phase derive candidates
and a rubric:

```
Workflow({ name: "market-scout", args: "Rank current OpenRouter all-rounders to replace deepseek-v4-pro for the loswfx pipeline, weighting tool-use reliability highest…" })
```

It runs in the background (Scope → Search → Fetch → Verify → Score) and
returns a structured object: `{ subject, candidates, criteria, summary,
ranking[], matrix[], caveats, openQuestions[], refuted[], sources[], stats }`.
Watch live with `/workflows`.

## 3 — Persist the scorecard (required)

Shadow-side artifacts must be git-committed by the producing run — a
returned object is not a deliverable until it lands on disk. After the
workflow completes:

1. Resolve the engagement repo and write the report to
   `engagements/<repo>/research/market-scout/<subject-slug>-<YYYY-MM-DD>.md`
   in the **shadow repo** (never the client tree).
2. Render the markdown to satisfy this skill's `rubric`: YAML frontmatter,
   a **subject** line, a **ranked scorecard table** (candidate × criterion
   with weighted totals), the executive **summary**, a **caveats** section,
   the refuted-claims list (for transparency), and the cited **sources**.
3. `git add` + `git commit` the file in the shadow repo.

## Notes

- The workflow is the reusable engine; this skill is the policy around it.
  To tune fan-out width, votes, or fetch budget, edit the consts at the top
  of `.claude/workflows/market-scout.js` — not this file.
- Verification is adversarial and defaults to refuting on uncertainty, so a
  thin-evidence run will legitimately return few confirmed claims. That is
  signal, not failure — surface it in caveats rather than padding the
  scorecard.
