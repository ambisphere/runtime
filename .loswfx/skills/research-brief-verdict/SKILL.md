---
name: research-brief-verdict
description: Validate a draft research brief against the Product gear's acceptance criteria. Use this skill in the Product role as the closing phase of a research-tandem workflow, after Research has drafted the brief and Design has (optionally) added implications. Output is a markdown verdict at engagements/<client-repo>/research/<dimension>/verdict.md inside the shadow repo. PRIVATE — agency-internal. The verdict either accepts the brief (downstream consumers may use it) or returns specific revision requests Research must address before re-submission.
max_iterations: 30
side: shadow
output_dir: engagements/{repo}/research
contract:
  kind: verdict
  inputs:
    - kind: layer-4
      path: engagements/{repo}/research/*.md
      required: true
  outputs:
    - path: engagements/{repo}/research/*/verdict.md
      required: true
  verify:
    - shadow-persistence
    - skill-frontmatter
---

# Research Brief Verdict (Product gear, review capability)

This skill is the **Product gear's** closing move in a research-tandem
workflow. Product reads the brief and any design-implications doc,
checks both against the acceptance criteria it set in phase 1, and
issues a verdict: accept, or return with specific revision requests.

## Why Product owns the verdict

In the tandem-group pattern, the gear that sets the acceptance bar
is the gear that validates against it. Product set the criteria;
Product is the only gear with the standing to say "this brief meets
the bar" or "this brief misses criterion 4." If Research validated
its own output, the bar drifts to whatever the model produced.

Product's verdict is the moment the engagement either accepts the
brief as input to downstream skills (rfp-response, engagement-plan)
or sends it back to Research for revision.

## Output destination

```
<shadow-root>/engagements/<client-repo>/research/<dimension>/verdict.md
```

Use the `shadow:` prefix: `write_file` with
`path: "shadow:engagements/<client-repo>/research/<dimension>/verdict.md"`.

## Required shape of the output

Every verdict MUST include, in this order:

1. **Frontmatter** — `phase: product:review`, `dimension`, `date`,
   `author` (LOSWF Agency Product gear + operator handle), `engagement`,
   `inputs` (paths of acceptance-criteria.md, brief.md, and
   design-implications.md if present), `verdict` (one of: `accepted`,
   `revisions-requested`, `rejected`), `mechanical_summary` (a brief
   like "6/6 mechanical checks passed" from eval_artifact).
2. **Summary** — one sentence. The headline verdict.
3. **Mechanical compliance** — quote the eval_artifact report's
   one-line summary (e.g. "6/6 checks passed" or "4/6 — failed:
   evidence_table_min_3, open_questions_section"). When any
   mechanical check failed, list each failing check ID + the
   detail line eval_artifact returned. This section comes before
   the criterion table because mechanical failure pre-empts
   substantive review.
4. **Criterion-by-criterion check** — a table with three columns:
   `criterion`, `status` (pass/fail/partial), `evidence` (where in
   the brief you saw it satisfied, or what's missing). One row per
   criterion in the acceptance-criteria document. When a criterion
   maps to a mechanical check that failed, mark it `fail` and
   reference the eval check ID in the evidence column.
5. **Verdict** — `accepted`, `revisions-requested`, or `rejected`.
   Accept only when every mechanical check passed AND every
   criterion passes (or partials are explicitly accepted with
   rationale). Mechanical FAIL means verdict cannot be `accepted`
   regardless of substantive content. Reject is rare — reserved
   for briefs whose investigation was so off-target a re-do is
   cheaper than revision.
6. **Revision requests** (when verdict ≠ accepted) — numbered list.
   Each: which criterion or mechanical check needs more, what
   specifically should be added or changed, what evidence is
   required. These become the next Research run's input.
7. **Design read** (when design-implications.md exists) — one
   paragraph. Did Design surface choices/risks Product agrees the
   downstream consumers need to know? Reference design-implications
   findings by number when accepting them.
8. **Downstream signal** (when verdict = accepted) — bullets
   naming which downstream skills can now consume this brief and
   what they should be alert to (e.g., "rfp-response: lean on
   finding 3 for stack-tradeoff section; flag open question OQ-2
   for client conversation before final submission").

## How to do the verdict — call eval_artifact FIRST

Product's review pass is structured as **mechanical compliance
first, judgment second**. Mechanical compliance is deterministic
agency-DevOps work the kernel does for you; judgment is the part
that justifies a Product gear.

**Step 1 — call `eval_artifact`** on the brief BEFORE reading it
yourself:

```text
eval_artifact(
  skill="research-brief",
  path="shadow:engagements/<client-repo>/research/<dimension>/brief.md"
)
```

This returns a structured pass/fail report against the
research-brief skill's declared rubric (frontmatter present,
thesis section present, evidence table size, numbered-findings
count, implications section, open-questions section, etc.). The
report is the ground truth for whether the brief is shape-
compliant. Treat its FAIL lines as automatically-failing
criteria in your verdict table — you do not need to re-derive
them.

If a brief fails any mechanical check, the verdict cannot be
`accepted` — the brief is not even shape-compliant, so substantive
review is moot until Research fixes the shape.

**Step 2 — read the three inputs** to do the substantive review
the rubric cannot do (does the brief actually answer the
acceptance criteria? are the findings grounded in real evidence?
do the implications make sense for downstream consumers?):

- The acceptance-criteria.md (set by Product earlier).
- The brief.md (Researcher's draft).
- The design-implications.md (Designer's contribution, if present).

For acceptance criteria that have no corresponding mechanical
check, Product MUST evaluate them by reading the brief — those are
the judgment-required criteria.

**Step 3 — SPOT-CHECK 2-3 evidence citations** from the brief by
reading the cited file (with `read_file` or `github_read_file`).
Confirm the cited content actually says what the brief claims.

DO NOT investigate the dimension yourself. Your job is validation,
not independent fact-checking. If you suspect a finding is wrong,
request revision with "Research should verify finding N against
source X" — don't go verify it yourself.

## What this skill does NOT do

- Does NOT produce findings, evidence, or claims about the
  dimension. Findings belong to Research.
- Does NOT rewrite the brief. Revision belongs to Research's next
  run.
- Does NOT exceed 1 page excluding the criterion table.
- Does NOT accept a brief that's "mostly good." Either every
  criterion passes (with documented rationale for any partials) or
  the verdict is revisions-requested.

## Verification

Done when:

1. `eval_artifact` was called on the brief AND its report is
   surfaced in the verdict's Mechanical compliance section.
2. File exists at the resolved shadow path.
3. Frontmatter is complete, including `verdict` and
   `mechanical_summary`.
4. The criterion-by-criterion table has one row per acceptance
   criterion (no skips).
5. Verdict field matches the table AND the mechanical report:
   any mechanical FAIL or criterion fail means the verdict
   cannot be `accepted`.
6. When verdict ≠ accepted, at least one revision request exists.
7. When verdict = accepted, at least one downstream consumer is
   named with concrete signal.

## Persist to the shadow repo (Product gear owns this)

After write_file lands the verdict, persist it to the shadow's git
history. The verdict is the closing record of this iteration of the
tandem — it MUST reach git so the revision loop (or the acceptance
record) is auditable.

Use the `commit_shadow_artifact` tool — one deterministic call:

```text
commit_shadow_artifact(
  paths=["engagements/<client-repo>/research/<dimension>/verdict.md"],
  message="research/<dimension>: Product verdict — <verdict-value>"
)
```

Local commit only — do NOT push.

After write_file + commit + submit_review, the work item's
lifecycle moves to either "brief accepted for downstream use" or
"Researcher should re-run this dimension with the revision requests
as input."
