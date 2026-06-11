---
name: swift-engineering-discipline
description: >
  The umbrella methodology for building Swift software the LOSWF way —
  define the problem and pair it with a solution, then deliver it through
  incremental test-first iteration that holds the line on clean code,
  clean architecture, and SOLID principles, applied in Swift idiom. Use
  this skill when an engagement is implementing or evolving Swift /
  SwiftPM / Apple-platform code (libraries, executables, daemons, apps)
  and the operator wants the full discipline loaded. It orchestrates the
  language-neutral member skills — gherkin-feature-drive (BDD outer loop),
  writing-tests (TDD inner loop), code-quality-review (structural gate) —
  and adapts them to Swift's tooling (swift build, swift test,
  XCTest/Swift Testing, SwiftPM targets). Do NOT use it to implement a
  single feature file in isolation (use gherkin-feature-drive), to only
  add tests (use writing-tests), or to review a diff (use
  code-quality-review).
side: client
contract:
  kind: methodology
  inputs: []
  outputs: []
  verify:
    - skill-frontmatter
---

# Swift Engineering Discipline

The **umbrella methodology** for Swift delivery — the Swift sibling of
`go-engineering-discipline`. It does not restate the procedures its member
skills own; it sequences them into one loop and states the principles that
hold across all of them, in Swift idiom. When a step has a dedicated skill,
this skill points there rather than duplicating it.

## Purpose and boundaries

The skill commits to:

- Forcing a **problem statement paired with a solution statement** before
  any code is written.
- **Test-first** delivery: red → green → refactor, using `swift test`
  (XCTest or the Swift Testing framework) as the inner loop.
- Holding the **structural bar** every increment: correct AND no
  structural regression.

It does **not** commit to a specific app architecture (MVVM, TCA, etc.) —
that is a per-engagement design decision surfaced in planning.

## The loop (summary)

0. **Define problem, pair with solution.** Crisp problem in observable
   terms; smallest solution named as behavior. No crisp problem → stop and
   clarify.
1. **Size the increment** — `iteration-plan` + `effort-pointing` into the
   smallest shippable units (a type, a protocol conformance, one target).
2. **BDD outer loop** — express behavior as scenarios; hand `.feature`
   implementation to `gherkin-feature-drive`.
3. **TDD inner loop** — red → green → refactor per `writing-tests`, using
   `swift test`. Tests first, never backfilled to a coverage number.
4. **Structural gate** — clear the `code-quality-review` bar.
5. **Land it** — `incremental-commit-all`; commit + push often. Loop to 1
   until the solution statement is satisfied.

## Standing bar (Swift idiom)

- **Clean code** — names say intent; small single-responsibility
  functions; prefer `struct` + value semantics; make illegal states
  unrepresentable with the type system (enums with associated values,
  non-optional where possible).
- **Clean architecture** — dependencies point inward; IO (network, disk,
  platform APIs) lives at the edge behind protocols the core owns. The
  core is platform-agnostic and testable without a device.
- **SOLID (Swift idiom)** — one type/file/reason (S); extend via new
  conformances/extensions not new branches (O); protocol witnesses
  substitute for adapters (L); small, consumer-defined protocols (I); core
  depends on protocol abstractions, not concrete platform types (D).
- **Concurrency** — prefer structured concurrency (`async`/`await`,
  actors) over ad-hoc dispatch; isolate shared mutable state in actors.
- **Errors** — typed `throws`/`Result` over sentinel values; never
  `try!`/force-unwrap on a path that can fail in production.

## Toolchain

- Build: `swift build`. Test: `swift test`. These must be on
  `policy.allowedCommands` (stack-aware onboarding seeds this).
- SwiftPM layout: a `Package.swift` manifest with explicit library vs
  executable targets; sources under `Sources/<target>/`, tests under
  `Tests/<target>Tests/`.
- Pin `swift-tools-version` and the platform minimums in the manifest.

## Member skills

`gherkin-feature-drive`, `writing-tests`, `code-quality-review`,
`iteration-plan`, `effort-pointing`, `incremental-commit-all`. The same
language-neutral discipline as `go-engineering-discipline`; only the
tooling and idiom differ.
