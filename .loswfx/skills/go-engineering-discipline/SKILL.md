---
name: go-engineering-discipline
description: "Use when implementing or evolving Go code the LOSWF way and the operator wants the full discipline loaded: problem + solution statement, incremental TDD/BDD, clean architecture, SOLID, and structural review. Orchestrates in-repo skills such as gherkin-feature-drive, writing-tests, code-quality-review, and charm-tui, and can deepen with global Go specialist skills when present. Do not use for a single isolated feature file, test-only task, or diff review; use the narrower member skill instead."
side: client
contract:
  kind: methodology
  inputs: []
  outputs: []
  verify:
    - skill-frontmatter
---

# Go Engineering Discipline

This is the **umbrella methodology** for Go delivery. It does not
restate the detailed procedures its member skills already own — it
sequences them into one loop and states the principles that hold across
all of them. When a step has a dedicated skill, this skill points there
rather than duplicating it. It points at two kinds of member: in-repo
loswfx skills that own each loop and gate, and global Go specialist
skills that deepen a single dimension (style, patterns, performance,
test mechanics, TUI components) — see the precedence note below for how
they relate.

## Purpose and boundaries

The skill commits to:

- Forcing a **problem statement paired with a solution statement** before
  any code is written
- Driving delivery through **incremental TDD/BDD** — outer BDD loop
  (behavior the engagement owes), inner TDD loop (units that satisfy it)
- Holding **clean code, clean architecture, and SOLID** as merge gates,
  not aspirations
- Composing — not replacing — `gherkin-feature-drive`, `writing-tests`,
  and `code-quality-review`

It does **not** commit to:

- Re-implementing what the member skills do (it delegates)
- "While we're here" scope — every change ties to the stated problem
- Big-bang delivery — work lands in the smallest shippable increments

## Member skills (the procedures this skill orchestrates)

In-repo members (relative links) own the loop; **global** members are
referenced by name and invoked via the Skill tool — they live in the
operator's global catalog, not this repo, so they carry no relative
link and may be absent in a bare engagement environment. The in-repo
members always cover the loop on their own; the global skills *deepen*
specific dimensions when present.

| Loop / gate | Skill | Owns |
|---|---|---|
| BDD outer loop | [`gherkin-feature-drive`](../gherkin-feature-drive/SKILL.md) | Turning a `.feature` into the minimal code + a verification command that exercises every scenario. |
| TDD inner loop | [`writing-tests`](../writing-tests/SKILL.md) | Behavior-first tests, fakes over mocks, interfaces at the seams, deterministic + isolated. |
| Test mechanics | `golang-testing` *(global)* | Concrete Go test toolkit behind the inner loop: table-driven cases, parallel tests, fuzzing, goleak, fixtures, coverage. |
| TUI test mechanics | `go-testing` *(global)* | Bubble Tea / teatest patterns for exercising interactive TUI surfaces. |
| Structural gate | [`code-quality-review`](../code-quality-review/SKILL.md) | The maximalist review that blocks correct-but-structurally-worse changes. |
| Implementation craft | `go-implementor` *(global)* | Production-grade idiomatic Go implementation — handlers, error handling, observability. |
| Code style | `golang-code-style` *(global)* | Line breaking, declarations, control-flow clarity, comment discipline. |
| Design patterns | `golang-design-patterns` *(global)* | Functional options, constructor APIs, error cascading, lifecycle/graceful shutdown, resilience, DI. |
| Performance | `golang-performance` *(global)* | If-X-bottleneck-then-Y optimization: allocation, CPU, memory layout, GC, pooling, caching — only once a benchmark names the bottleneck. |
| TUI implementation | [`charm-tui`](../charm-tui/SKILL.md) | Charm v2 (bubbletea/bubbles/lipgloss/huh v2) model contract, components, shared palette, interactive-or-static fallback, Bubble Tea unit testing. |
| TUI component design | `tui-component-design` *(global)* | Bubble Tea v2 component organization, state management, async commands, visual modes. |
| Sizing the increment | [`iteration-plan`](../iteration-plan/SKILL.md) · [`effort-pointing`](../effort-pointing/SKILL.md) | Breaking the solution into 5-15 shippable items, pointed by complexity not time. |
| Landing the work | [`incremental-commit-all`](../incremental-commit-all/SKILL.md) | Staging meaningful incremental commits until the tree is clean. |

### When global guidance conflicts, loswfx conventions win

The global Go skills are written for the broad Go ecosystem, not for
loswfx. Where their idiom contradicts a repo convention, the in-repo
skill and repo convention take precedence:

- **Mocks vs. fakes** — `golang-testing` and `go-testing` reach for
  testify suites/mocks. loswfx uses **stdlib `testing` + hand-written
  fakes** (testify is not a direct dependency; zero test files import
  it). Follow [`writing-tests`](../writing-tests/SKILL.md): fakes over
  mocks.
- **Charm version** — `tui-component-design` / `go-testing` may show
  legacy `github.com/charmbracelet/*` v1 APIs. loswfx is **charm.land
  v2 only**; v1 modules are forbidden (they break the cellbuf/lipgloss
  v2 stack). Follow [`charm-tui`](../charm-tui/SKILL.md).
- **Architecture** — take patterns from `golang-design-patterns` only
  when they serve the inward-pointing capability shape in
  [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) /
  [`docs/CAPABILITY-PATTERN.md`](../../docs/CAPABILITY-PATTERN.md), not
  as a reason to add framework-y indirection.

## Canonical references (the principles, grounded in repo docs)

- [`docs/FOUNDATIONS.md`](../../docs/FOUNDATIONS.md) — small, bounded,
  observable loops with explicit input/output/acceptance criteria. The
  philosophy this whole skill operationalizes.
- [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) +
  [`docs/CAPABILITY-PATTERN.md`](../../docs/CAPABILITY-PATTERN.md) — the
  clean-architecture shape: dependencies point inward, IO at the edges,
  one capability = one type in one file behind a stable interface.
- [`docs/CODE-JUDO.md`](../../docs/CODE-JUDO.md) — restructure so whole
  categories of complexity disappear, rather than polishing the shape.
- [`docs/CODE-SMELLS.md`](../../docs/CODE-SMELLS.md) — the running smell
  log; record what you notice while testing even when you don't fix it.

## Principles (the standing bar for every increment)

### Clean code
- Names say what, not how. A reader understands intent without the body.
- Small functions, one reason to change. Comment density matches the
  surrounding code — explain *why*, never narrate *what*.
- No dead branches, no speculative generality, no "while we're here."

### Clean architecture
- Dependencies flow **inward**. The core (domain logic) depends on
  interfaces it owns (ports); adapters at the edge depend on the core.
- IO — filesystem, network, DB, clock, randomness, env, process exec —
  lives at the boundary behind an interface, never threaded through the
  core. (This is exactly what makes the `writing-tests` fakes possible.)
- One bounded concern per package/file. New feature logic does not leak
  into a shared path.

### SOLID (stated in Go idiom)
- **S** — one type / one file / one reason to change. (The
  `CAPABILITY-PATTERN.md` shape is the local exemplar.)
- **O** — extend by adding a new implementation of an existing
  interface, not by adding a branch to a switch in shared code.
- **L** — every implementation of an interface honors the same contract;
  fakes used in tests are substitutable for real adapters.
- **I** — small, role-specific interfaces (`io.Reader`-sized), defined
  by the consumer, not fat "manager" interfaces.
- **D** — the core depends on abstractions; concrete adapters are wired
  at the edge. Constructors take interfaces.

## The loop

### Step 0 — Define the problem, pair it with a solution

Before any code, write two short statements (in the work-item body or
the PR description):

- **Problem** — what is broken / missing / costly, in observable terms.
  "Users can't X because Y" — not "we should add Z."
- **Solution** — the smallest change that resolves the problem, named as
  a behavior. This is the contract the increments must satisfy.

If the problem can't be stated crisply, stop and clarify — do not
proceed to code. A vague problem produces speculative architecture.

### Step 1 — Size the increment

Use [`iteration-plan`](../iteration-plan/SKILL.md) +
[`effort-pointing`](../effort-pointing/SKILL.md) to break the solution
into the smallest shippable items. Each item must be deliverable and
verifiable on its own. Order by dependency, not by appeal.

### Step 2 — BDD outer loop (behavior owed)

For each increment, express the behavior as scenarios. If a `.feature`
file exists or is warranted, hand the scenario implementation to
[`gherkin-feature-drive`](../gherkin-feature-drive/SKILL.md) — the
scenarios *are* the spec and the verification command is the proof.

The outer loop answers: *does the system do what the solution promised?*

### Step 3 — TDD inner loop (units that satisfy it)

Drive each unit **red → green → refactor** per
[`writing-tests`](../writing-tests/SKILL.md):

1. **Red** — write the failing test that names the behavior ("does X
   when Y"). Extract or confirm the boundary interface the test fakes.
2. **Green** — the minimal code that passes. No more.
3. **Refactor** — now apply [`docs/CODE-JUDO.md`](../../docs/CODE-JUDO.md):
   can a branch, helper, or mode disappear entirely? Tests stay green
   throughout.

Tests are written **first**, never backfilled to satisfy a coverage gate
(that rubber-stamps and over-engineers). Coverage is a side effect of
test-first behavior, not a target.

### Step 4 — Structural gate

Before the increment is "done," run it past the
[`code-quality-review`](../code-quality-review/SKILL.md) bar: behavior
correct **and** no structural regression, no missed code-judo move, no
file pushed past its decomposition boundary, no boundary leak. Correct
is necessary but not sufficient.

### Step 5 — Land it

Commit in meaningful increments via
[`incremental-commit-all`](../incremental-commit-all/SKILL.md) until the
tree is clean. Each commit should map to one coherent step of the
solution. Commit and push often.

Then loop back to Step 1 for the next increment until the solution
statement from Step 0 is fully satisfied.

## Go-specific guardrails

These recur often enough to call out (the first three are lifted from
`gherkin-feature-drive`'s build notes):

- `go.mod` must exist at the build root before any `go build`/`go run`.
- Slice fields that JSON-marshal must be initialized to `[]T{}`, not
  `nil` — `nil` marshals to `null`, not `[]`.
- Every imported package must be used; `gofmt`/`go vet` clean before commit.
- Map iteration is randomized — never let error messages or output depend
  on map order (see the receipt-validation smell in `CODE-SMELLS.md`).
- Constructors take interfaces, return concrete types ("accept
  interfaces, return structs").
- Errors wrap with `%w` and context; the core never depends on
  vendor-specific error types — map them at the adapter edge.

## Self-check

The increment is complete when:

- [ ] A paired problem/solution statement exists and the change traces
      back to it
- [ ] Behavior is proven by a BDD verification command (where applicable)
- [ ] Every unit was driven test-first (red → green → refactor)
- [ ] Tests are deterministic, isolated, and use fakes — no real
      network/filesystem for core behavior
- [ ] The core depends on interfaces; IO sits at the edge
- [ ] No structural regression survives the `code-quality-review` bar
- [ ] `gofmt` / `go vet` clean; commits are incremental and meaningful

## Failure modes to avoid

- **Code before a stated problem.** Architecture invented to solve an
  unnamed problem is speculative by definition.
- **Backfilled tests.** Writing tests after the code to hit a coverage
  number is not TDD — it rubber-stamps the implementation.
- **Approving on correctness alone.** Behavior-correct ≠ structurally
  sound. Run the `code-quality-review` bar.
- **Big-bang delivery.** If the increment can't be stated as one
  shippable, verifiable item, it's too big — split it (Step 1).
- **Duplicating the member skills here.** This skill orchestrates; the
  detail lives in `writing-tests`, `gherkin-feature-drive`, and
  `code-quality-review`. Keep it that way.

## See also

- [`skills/writing-tests/SKILL.md`](../writing-tests/SKILL.md)
- [`skills/gherkin-feature-drive/SKILL.md`](../gherkin-feature-drive/SKILL.md)
- [`skills/code-quality-review/SKILL.md`](../code-quality-review/SKILL.md)
- [`skills/charm-tui/SKILL.md`](../charm-tui/SKILL.md)
- Global specialist skills (invoke via the Skill tool): `golang-code-style`,
  `golang-design-patterns`, `golang-performance`, `golang-testing`,
  `go-implementor`, `go-testing`, `tui-component-design`.
- [`docs/INDEX.md`](../../docs/INDEX.md) — the canonical reading order.
