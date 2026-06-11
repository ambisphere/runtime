---
name: milestone-grinder
description: "Use when running the LOSWFX milestone delivery loop end-to-end as an artifact-driven state machine: execute the active MILESTONE plan with TDD, record tracking/evidence, write closeout, update roadmap/snapshot, promote the next plan, and merge one milestone branch in order. Supports stepped and auto modes with halt rules. Do not use for a fresh milestone with no planning draft, blocked plans, broken main, or scope invented beyond the plan."
side: shadow
max_iterations: 200
contract:
  kind: deliverable
  inputs:
    - kind: layer-4
      path: docs/milestones/MILESTONE-*-PLAN.md
      required: true
  outputs:
    - path: docs/milestones/MILESTONE-*-TRACKING.md
      required: true
    - path: docs/milestones/MILESTONE-*-EVIDENCE.md
      required: true
    - path: docs/milestones/MILESTONE-*-CLOSEOUT.md
      required: true
    - path: docs/milestones/MILESTONE-*-PLANNING-DRAFT.md
      required: true
    - path: docs/ROADMAP.md
      required: true
    - path: docs/PROJECT-DEVELOPMENT-SNAPSHOT.md
      required: true
  verify:
    - skill-frontmatter
    - truthful-status
    - evidence-linked-closeout
    - roadmap-derived-from-closeout
    - real-execution
---

# milestone-grinder

The operator's LOSWFX milestone loop, encoded as a deterministic
skill.

The loop exists because a practiced workflow that depends on memory
will decay. This skill preserves the working pattern:

1. deliver the active milestone through TDD;
2. commit + push after each verified scope item;
3. maintain tracking and evidence as work happens;
4. close only when Definition of Done is proven;
5. review the closeout/evidence before promotion;
6. derive roadmap and snapshot updates from closeout;
7. finalize the next milestone plan;
8. repeat.

The skill is a conductor. It may delegate planning, building,
review, publishing, and retrospective work to specialized skills or
agents, but this document owns the state machine, artifact contract,
halt rules, and promotion semantics.

## Purpose and boundaries

This skill commits to:

- Detecting the active milestone from repository artifacts.
- Executing the current `MILESTONE-N-PLAN.md` exactly as scoped.
- Using TDD for each Primary Scope item.
- Committing and pushing after each passing validator cycle for a
  scope item.
- Maintaining `TRACKING`, `EVIDENCE`, and ledger events throughout.
- Writing closeout only from verified evidence.
- Updating roadmap/snapshot only from closeout content.
- Promoting the next plan only after open questions are resolved.
- Running forward only.

It does NOT commit to:

- Inventing scope beyond the PLAN.
- Resolving ambiguous scope by guessing.
- Performing cross-milestone refactors.
- Retro-editing old milestone artifacts unless explicitly directed.
- Recovering from broken `origin/main`.

## State model

Milestone artifacts form the source of truth:

```text
PLANNING-DRAFT
  -> PLAN
  -> TRACKING
  -> EVIDENCE
  -> CLOSEOUT
  -> REVIEWED
  -> ROADMAP/SNAPSHOT
  -> NEXT PLAN
  -> MERGED (branch lands on main; next milestone branches off it)
````

Ledger events mirror the artifact state:

* `state.milestone-grinder.started`
* `state.milestone-grinder.scope-complete`
* `state.milestone-grinder.evidence-updated`
* `state.milestone-grinder.closed`
* `state.milestone-grinder.reviewed`
* `state.milestone-grinder.promoted`
* `state.milestone-grinder.merged`
* `state.milestone-grinder.reopened`
* `state.milestone-grinder.halted`
* `state.milestone-grinder.cycle-complete`

On resume, reconstruct state from disk first, then ledger.

## Inputs

Required:

* **active milestone** — auto-detected as the highest-numbered
  `docs/milestones/MILESTONE-<N>-PLAN.md` without a matching completed
  `docs/milestones/MILESTONE-<N>-CLOSEOUT.md`.

Optional:

* **`--milestone <N>`** — override active milestone detection.
* **`--mode stepped|auto`** — default `stepped`.
* **`--max-cycles N`** — auto mode only. Default `1`.
* **`--halt-on-warning`** — treat validator warnings as halts.

## Active milestone detection

Resolve the next action by artifacts:

1. If `MILESTONE-N-PLAN.md` exists and no completed
   `MILESTONE-N-CLOSEOUT.md` exists, run Phase 1.
2. If `MILESTONE-N-CLOSEOUT.md` exists, evidence exists, and
   `MILESTONE-(N+1)-PLANNING-DRAFT.md` exists but
   `MILESTONE-(N+1)-PLAN.md` does not, run Phase 2.
3. If `MILESTONE-(N+1)-PLAN.md` exists with `Status: Ready`, the
   next invocation advances to N+1.
4. If artifacts conflict, halt and surface the exact conflict.

## Branch, commit, and merge discipline

Full autonomy means the grinder lands its own work: **one milestone, one
branch, merged to `main` before the next milestone starts.** The grinder
opens *and merges* the PR — merging is part of the loop, not a handoff.

Branch rule (prevents the stacked-branch conflict trap):

* Cut **one branch per milestone off the latest `main`**:
  `git fetch origin && git checkout -b claude/m<N>-<theme> origin/main`.
* **Never stack a milestone branch on an unmerged branch.** If milestone N
  isn't on `main` yet, N+1 does not start — the chain must land in order.
  (Stacking N+1 on N's branch is the #1 cause of merge conflicts when N
  merges and `main` moves; see Phase 3.)
* All of one milestone's work — delivery, closeout, and the Phase 2
  promotion of N+1 — rides the **same branch** and lands in one merge.

"Commit + push often" means:

* Commit after every scope item reaches green validation.
* Push immediately after each such commit.
* Commit closeout/evidence/draft together after milestone DoD passes.
* Commit roadmap/snapshot/promotion together after Phase 2 passes.
* Do not squash milestone work.
* Do not batch unrelated scope items into one commit.

Commit message formats:

```text
M<N> <letter>: <scope one-liner>
milestone: close <N>, draft <N+1>
milestone: promote <N+1> plan
milestone: reopen <N>
```

## Phase 0 — Preflight

Before delivery or promotion:

1. Fetch latest refs.
2. Confirm working tree status.
3. Confirm `origin/main` builds:

   * `go build ./...`
   * `go test ./...`
   * `loswf validate`
4. Confirm milestone PLAN frontmatter:

   * `Status` is not `Blocked`.
   * `Status` is `Ready` for delivery.
   * Definition of Done is measurable.
   * Primary Scope references existing files/symbols or explicitly
     creates them.
5. Ensure `docs/milestones/MILESTONE-N-TRACKING.md` exists; scaffold if absent.
6. Ensure `docs/milestones/MILESTONE-N-EVIDENCE.md` exists; scaffold if absent.
7. Write `state.milestone-grinder.started`.

If preflight fails, halt.

## Phase 1 — Deliver

For active milestone N:

1. Read `docs/milestones/MILESTONE-N-PLAN.md`.
2. For each Primary Scope item:

   1. Write the failing test first.
   2. Implement until the specific test passes.
   3. Run validators:

      * focused test
      * `go test ./...`
      * `loswf validate`
   4. If validators pass, commit:
      `M<N> <letter>: <one-liner>`
   5. Push.
   6. Append to `docs/milestones/MILESTONE-N-TRACKING.md`:

      * scope item
      * commit SHA
      * tests added/changed
      * validator outcome
      * summary
   7. Append to `docs/milestones/MILESTONE-N-EVIDENCE.md`:

      * commit SHA
      * relevant files
      * test names
      * validator command output summary
      * artifacts produced
      * DoD bullets advanced
   8. Write `state.milestone-grinder.scope-complete`.

## Phase 1.5 — Close and review

When every DoD bullet is satisfied:

0. **Real-execution gate (M171).** If the milestone declares a "closes on
   live-execution evidence" DoD bullet (every Real-Execution Arc milestone
   does), the `real-execution` validator must be green on the milestone's
   ledger — no proof-tagged scope item may have run on the fake adapter. A
   fake-green proof halts the close. (`loswfx practices check real-execution`.)
1. Verify `docs/milestones/MILESTONE-N-EVIDENCE.md` contains evidence for every
   DoD bullet.
2. Write `docs/milestones/MILESTONE-N-CLOSEOUT.md` from evidence only:

   * Status
   * Delivered
   * Validation
   * Evidence links
   * Retrospective
   * Carry-forward
   * Validator Notes
3. Scaffold `docs/milestones/MILESTONE-(N+1)-PLANNING-DRAFT.md` from template.
   Populate only Goal, Context, and Carry-forward candidates from
   N's closeout.
4. Commit:
   `milestone: close <N>, draft <N+1>`
5. Push.
6. Run milestone review:

   * closeout claims are backed by evidence;
   * validation section maps to every DoD bullet;
   * no roadmap/snapshot claims are introduced yet.
7. Write `state.milestone-grinder.closed`.
8. Write `state.milestone-grinder.reviewed`.

In `stepped` mode, stop here.

In `auto` mode, continue only if review passes.

## Phase 2 — Promote

For closed milestone N and draft N+1:

1. Update `docs/ROADMAP.md`.

   * Move N to completed.
   * Link N closeout.
   * Use only the one-sentence summary and carry-forward items from
     N closeout.
   * Update Current Position from Delivered/Validation evidence.
   * Add Roadmap Themes only if supported by closeout or existing
     roadmap direction.

2. Update `docs/PROJECT-DEVELOPMENT-SNAPSHOT.md`.

   * Bump snapshot date.
   * Set Last Shipped to N closeout.
   * Set Next In Flight to N+1 draft/plan.
   * Remove stale claims contradicted by closeout evidence.

3. Promote N+1.

   * Read `docs/milestones/MILESTONE-(N+1)-PLANNING-DRAFT.md`.
   * Resolve every open question.
   * Remove all `[?]` markers.
   * Convert carry-forward candidates into concrete Primary Scope.
   * Ensure Definition of Done is measurable.
   * Rename to `docs/milestones/MILESTONE-(N+1)-PLAN.md`.
   * Set `Status: Ready`.
   * Scaffold `docs/milestones/MILESTONE-(N+1)-TRACKING.md`.
   * Scaffold `docs/milestones/MILESTONE-(N+1)-EVIDENCE.md`.

4. Commit:
   `milestone: promote <N+1> plan`

5. Push.

6. Write `state.milestone-grinder.promoted`.

Proceed to **Phase 3 — Land**. A milestone is not done until it is merged
to `main`; the stepped/auto stop-or-advance decision happens there.

## Phase 3 — Land (merge to main)

The grinder lands its own work. A milestone branch that sits unmerged is
the source of the stacked-branch conflicts this phase exists to prevent.

1. **Open the PR** (if not already open) from the milestone branch to
   `main`:

   ```bash
   gh pr create --base main --head claude/m<N>-<theme> \
     --title "M<N>: <theme>" --body "<closeout summary + DoD evidence>"
   ```

2. **Wait for required checks** to pass (CI runs the same
   `./scripts/check.sh`). Poll until green:

   ```bash
   gh pr checks <pr> --watch
   ```

   If a required check fails, treat it as a delivery defect: fix on the
   branch, push, re-poll. Do not merge red.

3. **Resolve conflicts if `main` moved.** If the PR is `CONFLICTING`,
   integrate `main` and resolve on the branch (never force the merge):

   ```bash
   git fetch origin && git merge origin/main   # or: git rebase origin/main
   # resolve, then:
   ./scripts/check.sh && git push
   ```

   If conflicts can't be resolved cleanly (semantic conflict, ambiguous
   intent), **halt** and surface the conflicting files — do not guess.

4. **Merge** once green and mergeable, then delete the branch:

   ```bash
   gh pr merge <pr> --squash --delete-branch
   ```

   Use the repo's prevailing merge style (squash unless the project
   merges with merge-commits). Squash keeps `main` history one-commit-
   per-milestone; the branch's incremental commits are preserved in the
   PR.

5. **Sync local `main`** so the next milestone branches off the just-
   landed state:

   ```bash
   git checkout main && git pull origin main
   ```

6. Write `state.milestone-grinder.merged` (records the merged SHA + PR).

In `stepped` mode, stop here — the milestone is delivered, closed,
promoted, and **on `main`**. The next `goal` invocation cuts a fresh
branch off `main` for N+1.

In `auto` mode:

* Cut N+1's branch off the now-updated `main` (branch discipline).
* If N+1 PLAN existed before this run and passed preflight, it may be
  executed.
* If N+1 PLAN was created during this run, do not execute it unless a
  separate review gate marks it executable.
* If `--max-cycles` is exhausted, stop.
* Otherwise advance to N+1 and re-enter Phase 0.

## Reopen procedure

If a milestone was closed but later evidence proves DoD was not met:

1. Set closeout status to `Reopened`.
2. Add a Reopen section explaining:

   * failed claim;
   * missing/invalid evidence;
   * validator failure or regression;
   * next required action.
3. Write `state.milestone-grinder.reopened`.
4. Commit:
   `milestone: reopen <N>`
5. Push.
6. Resume Phase 1 for N.

Do not promote N+1 while N is reopened.

## Halt conditions

Halt on:

* **Broken main** — preflight build/test/validate fails on
  `origin/main`.
* **Plan ambiguity** — DoD is unmeasurable, scope references unknown
  targets, or intent conflicts with repository state.
* **TDD exhaustion** — same scope item fails to reach green after
  either:

  * 10 validator cycles, or
  * repeated implementation attempts with no new evidence of progress.
* **Validator hard error** — any hard validator failure.
* **Validator warning with `--halt-on-warning`.**
* **Evidence gap** — closeout claim lacks evidence.
* **Promotion gap** — planning draft still contains open questions,
  risks without mitigation, or `[?]` markers.
* **Auto safety gate** — auto mode attempts to execute a plan created
  during the same run without review approval.
* **Merge check failure** — a required PR check (CI) is red and a fix on
  the branch hasn't turned it green.
* **Unresolvable merge conflict** — `main` moved and the conflict is
  semantic / ambiguous (not a mechanical resolve). Surface the conflicting
  files; do not guess the resolution or force the merge.
* **Max cycles reached.**
* **Manual interrupt.**

On halt:

1. Write `state.milestone-grinder.halted`.
2. Include:

   * milestone number;
   * current phase;
   * exact halt reason;
   * last completed artifact;
   * next pending action;
   * whether working tree is clean.
3. Do not invent recovery.
4. Resume by re-invoking the skill.

## Failure modes to avoid

* Skipping evidence.
* Writing optimistic closeouts unsupported by commits/tests.
* Treating roadmap updates as new planning space.
* Promoting drafts with unresolved questions.
* Squashing milestone commits.
* Editing roadmap/snapshot during Phase 1.
* Running auto mode on exploratory plans.
* Executing a plan generated by the same auto run without review.
* Retro-editing old milestone artifacts during forward delivery.
* **Stacking a milestone branch on an unmerged branch.** N+1 must branch
  off `main` *after* N has merged — never off N's branch. Stacking is the
  root cause of the cascade where merging N rebases the world and every
  downstream PR conflicts. One milestone, one branch, merged before the
  next.
* **Leaving a milestone's PR unmerged and moving on.** A milestone isn't
  done until Phase 3 lands it on `main`. An unmerged PR is an open
  liability, not a delivered milestone.
* **Merging red or force-merging a conflict.** Required checks must be
  green and conflicts mechanically resolved + re-validated before merge.

## Workflow

### Stepped

```bash
loswf skill milestone-grinder
# Phase 1 + close/review runs, then stops.

loswf skill milestone-grinder --mode stepped
# Phase 2 promotes the next plan, then stops.

loswf skill milestone-grinder
# Next milestone delivery begins.
```

### Auto

```bash
loswf skill milestone-grinder --mode auto --max-cycles 3
```

Auto chains reviewed phases only. It may promote a next plan, but it
must not execute a newly generated plan in the same run unless an
independent review gate marks it executable.

## Verification

A cycle is valid when:

* `docs/milestones/MILESTONE-N-TRACKING.md` lists each scope item with commit SHA
  and validator result.
* `docs/milestones/MILESTONE-N-EVIDENCE.md` maps every DoD bullet to commits,
  tests, files, validator summaries, and produced artifacts.
* `docs/milestones/MILESTONE-N-CLOSEOUT.md` exists and all claims are backed by
  evidence.
* The closeout has passed review.
* The git log shows incremental scope-tagged commits.
* `docs/ROADMAP.md` reflects N as completed using closeout-derived
  language only.
* `docs/PROJECT-DEVELOPMENT-SNAPSHOT.md` points to N as last shipped
  and N+1 as next in flight.
* `docs/milestones/MILESTONE-(N+1)-PLAN.md` exists with `Status: Ready`.
* `docs/milestones/MILESTONE-(N+1)-PLAN.md` has no `[?]` markers.
* `docs/milestones/MILESTONE-(N+1)-TRACKING.md` exists.
* `docs/milestones/MILESTONE-(N+1)-EVIDENCE.md` exists.
* **The milestone branch is merged to `main`** (Phase 3): the PR is
  closed-as-merged, the branch is deleted, and local `main` is synced.
  `state.milestone-grinder.merged` records the merge SHA + PR number.
* `state.milestone-grinder.cycle-complete` names N and N+1.

## References

* `docs/MILESTONE-TEMPLATE.md`
* `docs/ROADMAP.md`
* `docs/PROJECT-DEVELOPMENT-SNAPSHOT.md`
* Sister skills:

  * [`iteration-plan`](../iteration-plan/SKILL.md)
  * [`retrospective`](../retrospective/SKILL.md)
  * reviewer/validation skill if available
* [[feedback_practices_enforced_not_documented]]
* [[feedback_agent_devops]]
* [[feedback_workflow_shape_per_work_type.md]]
