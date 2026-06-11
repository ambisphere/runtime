---
name: gherkin-feature-drive
description: Implement a single Gherkin feature file end-to-end against a target codebase, producing the minimal code needed to satisfy the feature's Background and all its Scenarios. Use this skill when the client has provided a `.feature` file (Cucumber/Gherkin syntax) and wants a working implementation. Output is whatever code files the feature requires plus a verification command that exercises every scenario. Use a different skill for non-Gherkin specs, multi-feature work (use `triage-decomposition` first), or for review of existing feature implementations (use `code-review`).
side: client
contract:
  kind: methodology
  inputs: []
  outputs: []
  verify:
    - skill-frontmatter
---

# Gherkin Feature Drive

This skill implements one `.feature` file. The Gherkin scenarios *are* the
specification — the build must satisfy every `Given` / `When` / `Then`
clause, and the verification command is the literal check that proves it.

## Purpose and boundaries

The skill commits to:

- Reading the Gherkin file before writing any code
- Producing the smallest code surface that satisfies every scenario
- Emitting a verification command that exercises every scenario in
  a single shell-compatible chain

It does **not** commit to:

- Implementing features beyond what the scenarios specify (no
  "while we're here" additions)
- Refactoring existing code that the feature doesn't touch
- Adding tests beyond what the verification command exercises
  (separate skill: `test-coverage-fill`)

## Inputs

Required:

- **Feature file** — a `.feature` file in the workspace or referenced
  by absolute path the agent can read

## Output

Whatever code files the feature requires. Most commonly for a CLI feature:

- The binary entrypoint (`cmd/<binary>/main.go` or `bin/<binary>`)
- A `go.mod` / `package.json` / language manifest if not present
- Subcommand or handler files per Scenario

Plus: a verification command on the `agent.build.applied` event that
chains every scenario's assertions.

## Workflow

### Step 1: Read the feature

Use `read_file` on the feature file. List every Scenario heading.
For each Scenario, list:
- The `When` actions (commands to invoke)
- The `Then` assertions (literal substrings to grep for, exit codes,
  file existence)

### Step 2: Identify CLI shape

If the scenarios invoke commands like `gitugh workflow run hello`,
note: that is binary=gitugh, subcommand1=workflow, subcommand2=run,
arg=hello. The implementation must match the EXACT command structure.
Do not collapse multi-word subcommand paths into a single-word command.

### Step 3: Identify required fixtures

If a scenario opens with `Given a workflow execution with id "exec-1"
exists at state/executions/exec-1.json`, that's a fixture the
verification command must create. The implementation does not need
to create that file at runtime — the verify command will.

### Step 4: Build

Write the code that satisfies every scenario. Prefer one file per
distinct subcommand handler. Keep the surface minimal — every line of
code should tie back to a scenario assertion.

For Go specifically:
- `go.mod` must exist at workspace root for any `go build` invocation
- Slice fields that JSON-marshal must be initialized to `[]T{}` not
  `nil` (nil marshals to `null`, not `[]`)
- Every imported package must be used
- For CLI dispatch, switch on `os.Args[1]` then `os.Args[2]` for
  two-level commands; do not collapse to one level

### Step 5: Write the verification command

The verification is a single shell chain that exercises every scenario.
Patterns to use:

- **For each `Then stdout contains "X"`**: chain a `grep -q 'X'` step.
- **For each `And the process exits with code 0`**: the `&&` chaining
  enforces this implicitly (any non-zero exit short-circuits).
- **For each `And stdout contains one of "A", "B", "C"`**: use
  `grep -qE '(A|B|C)'`.
- **For each `And a file exists at path/to/file`**: use
  `ls path/to/file >/dev/null 2>&1` or
  `compgen -G 'path/to/file' >/dev/null` for glob patterns.
- **For fixture preconditions** (`Given a workflow execution with id
  "exec-1" exists at state/executions/exec-1.json`): the verification
  command MUST create the fixture first with `mkdir -p` and
  `echo ... >`.

### Step 6: Self-check

Before completing:

- Every Scenario's `When` and `Then` clauses are covered by the
  verification command
- The verification command starts with executables in
  `policy.allowedCommands` (typically `go`, `mkdir`, `echo`, `grep`,
  `test`, `ls`)
- No `cd <subdir>` prefixes — use working-directory-aware tooling
- For Go: prefer `go run ./cmd/<name>` over `go build && ./binary`
  to sidestep the binary-path question

## Failure modes to avoid

- **Collapsing two-level subcommands.** `gitugh workflow run hello`
  is binary=gitugh, sub1=workflow, sub2=run. NOT binary=gitugh,
  sub=run, arg=hello.
- **Anchored grep on substring scenarios.** "Then stdout contains X"
  means `grep -q 'X'`, NOT `grep -q '^X$'`. The anchored form requires
  the line to be exactly X.
- **Combining independent contains assertions into one regex.**
  `Then stdout contains 'exec-1'` and `And stdout contains one of
  'succeeded','failed','running'` are TWO independent grep steps,
  not `grep -qE 'exec-1.*(succeeded|failed|running)'`.
- **`wc -l | grep '^N$'`.** `wc -l` has leading whitespace on
  macOS/BSD. Use `test $(... | wc -l) -eq N` or pipe through
  `tr -d ' '` first.
- **`test -f <glob>`.** `test -f` is broken when the glob matches
  multiple files (too many args, exit 2) or zero (literal glob isn't
  a file). Use `ls P >/dev/null 2>&1`.

## Verification

The build is complete when:

- All files referenced by the feature scenarios exist
- The verification command chains assertions for every scenario
- The verification command exits 0 when run from the workspace root
