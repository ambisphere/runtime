---
name: story-writer
description: Derive new, high-value user stories for the LOSWFX factory and express each as a high-quality Gherkin `.feature` file written from a named persona's point of view (defaulting to the Operator). The skill reads the existing stories (`internal/e2e/features/*.feature`), the product state (ARCHITECTURE, capability map, ROADMAP), and the project state (PROJECT-DEVELOPMENT-SNAPSHOT, in-flight milestones) to find capability gaps worth a story, then writes INVEST-shaped features with persona narrative, declarative scenarios, and happy/error/edge coverage. Output is one or more `.feature` files plus a short rationale tying each to a persona need and a roadmap/gap signal. It is the authoring counterpart to `gherkin-feature-drive` (which implements a feature). Do NOT use it to implement a feature (use `gherkin-feature-drive`), to write tests for existing code (use `writing-tests`), or to produce prose acceptance criteria for an existing item (use `research-acceptance-criteria`).
side: client
output_dir: docs/stories
contract:
  kind: deliverable
  inputs:
    - kind: layer-3
      path: internal/e2e/features/*.feature
      required: false
  outputs:
    - path: docs/stories/*.feature
      required: true
  verify:
    - skill-frontmatter
---

# Story Writer

This skill **authors** stories; it does not implement them. It looks at
who uses LOSWFX, what the factory can already do, and where the roadmap
is heading — then writes the next valuable story as a Gherkin feature a
builder can pick up. The scenarios *are* the spec; quality means a
builder (and `gherkin-feature-drive`) can act on them without a meeting.

## Purpose and boundaries

The skill commits to:

- Writing every story from a **named persona's** point of view, with the
  classic narrative — *As a `<persona>`, I want `<capability>`, so that
  `<value>`* — defaulting to the **Operator** persona
- **Grounding** each story in real state: existing features it must not
  duplicate, a roadmap/snapshot signal it advances, a capability gap it
  closes
- Producing **INVEST-shaped** stories and **declarative** Gherkin (intent,
  not keystrokes)
- Ranking the derived stories by **value** and naming the rationale

It does **not** commit to:

- Implementing anything (that is `gherkin-feature-drive`)
- Inventing personas, surfaces, or commands not grounded in the repo
- Restating an existing feature with new words (dedupe first)
- Writing imperative UI-script scenarios ("click here, type there")

## Personas (who the story is for)

The persona is the *user of LOSWFX*, not a capability area. Default to
the Operator unless the operator names another.

| Persona | Who they are | What they want from the factory |
|---|---|---|
| **Operator** (default) | The human running the factory — `loswfx` on their machine, driving engagements, approving work, watching the loop. | Trust, glanceability, low-ceremony control, recoverable failure. |
| **Partner / Client** | The owner of the engaged repository whose product the factory builds against. | Deliverables that fit their product, no leakage of agency internals. |
| **Foreman** (agent persona) | The autonomous loop coordinating builders within a cycle. | Clear dispatch, honest validators, safe halting. |

When the operator says only "write stories," assume **Operator**. When
they name a persona ("from the partner's view"), adopt it and tag the
feature accordingly (`@operator`, `@engagement`, `@foreman`).

## Inputs the skill examines (in order)

1. **Existing stories** — `internal/e2e/features/*.feature`. Read the
   tags and feature titles to learn the persona vocabulary and the
   established step phrasings (`Given a fresh LOSWFX repository`,
   `When I run "loswfx …"`, `Then the output contains …`). **Reuse that
   step vocabulary** where it fits so the story is implementation-ready.
   These are also the dedupe set — a new story must not restate one.
2. **Product state** — `docs/ARCHITECTURE.md`,
   `docs/LOSWF-AGENCY-CAPABILITY-MAP.md`, `docs/ROADMAP.md`. What the
   factory does today and where it is deliberately heading.
3. **Project state** — `docs/PROJECT-DEVELOPMENT-SNAPSHOT.md` and the
   in-flight milestone plan(s). What is shipping next — a story that
   advances the current arc is worth more than a tangent.

A story earns its place only if it pairs a **persona need** with a
**state signal** (a roadmap line, a capability gap, a snapshot
"next-in-flight"). No signal → no story.

## Output

One `.feature` per story, written to `docs/stories/<slug>.feature`
(operator may redirect). Each file:

- Opens with persona/area tags (`@operator`, `@smoke`, …)
- A `Feature:` line + a short narrative block: *As a `<persona>`, I want
  `<capability>`, so that `<value>`.*
- A `Background:` for shared preconditions (only what every scenario
  needs)
- Declarative `Scenario:` blocks covering **happy path, the primary
  error path, and at least one edge** — named by behavior

Plus a **rationale block** (top-of-file comment or a companion note)
naming, per story: the persona need, the state signal it advances, and
why it is valuable now. Close with a **ranked list** when more than one
story is produced.

## The Gherkin quality bar

A high-quality feature here is:

- **Declarative, not imperative.** `When the operator approves the
  pending work item` — not `When I press "a" then "enter"`. Express
  intent; let the builder choose the mechanism.
- **One capability per feature.** A feature that needs "and also" in its
  title is two stories.
- **Persona-grounded value.** The `so that` clause states real value to
  the named persona, not "so that the test passes."
- **Behavior-named scenarios.** "Scenario: approval refuses when no work
  is pending" — not "Scenario: test 3."
- **Coverage, not exhaustion.** Happy + primary error + one meaningful
  edge. Don't enumerate every flag; do cover the failure the persona
  will actually hit.
- **Background discipline.** Only truly shared `Given`s go in
  `Background`; scenario-specific setup stays in the scenario.
- **No implementation leakage.** Scenarios assert observable behavior
  (output, exit status, files, state), never internal function names.

## Workflow

### Step 1 — Adopt the persona

Default Operator; otherwise the one the operator named. Write down the
persona's goal and the frustration this story relieves — one line each.

### Step 2 — Survey existing stories

Glob `internal/e2e/features/*.feature`. List the persona tags and
feature titles. This is both the **style guide** (step vocabulary to
reuse) and the **dedupe set** (titles you must not restate).

### Step 3 — Read the state

Skim `ROADMAP.md` "Current Position" + the active arc, and
`PROJECT-DEVELOPMENT-SNAPSHOT.md` "next in flight." Note the capability
map gaps. Collect candidate stories where a persona need meets a state
signal.

### Step 4 — Derive and rank candidates

For each candidate, state: persona need · capability gap · state signal ·
value. Drop any candidate missing a signal or duplicating an existing
feature. Rank by value to the persona × alignment with the current arc.

### Step 5 — Write the feature(s)

For the top candidate(s), write the `.feature` per the quality bar.
Reuse the established step phrasings from Step 2 so the story is
ready for `gherkin-feature-drive`. Keep scenarios declarative.

### Step 6 — Self-check

- Persona narrative present (`As a … I want … so that …`)
- Tagged with the persona/area tag used elsewhere
- Happy + error + edge scenarios, each named by behavior
- No scenario restates an existing feature's behavior
- Every scenario is declarative (no keystroke scripting, no internal
  symbols)
- Rationale names the persona need **and** the state signal
- Stories ranked when more than one

## Failure modes to avoid

- **Persona-less stories.** A feature with no `As a … so that …` is a
  test plan, not a story. State who benefits and why.
- **Signal-less invention.** A capability nobody on the roadmap or in a
  persona's frustration asked for is speculation. Pair every story with
  a state signal.
- **Duplicating an existing feature.** Read `internal/e2e/features/`
  first; a renamed restatement adds nothing.
- **Imperative scenarios.** Keystroke scripts couple the story to one UI
  and rot. Assert behavior.
- **Multi-capability features.** "and also" in the title means split it.
- **Implementing instead of authoring.** This skill stops at the
  `.feature`. Implementation is `gherkin-feature-drive`.

## See also

- [`skills/gherkin-feature-drive/SKILL.md`](../gherkin-feature-drive/SKILL.md)
  — the implementation counterpart; consumes the features this skill writes.
- [`skills/go-engineering-discipline/SKILL.md`](../go-engineering-discipline/SKILL.md)
  — the delivery loop these stories feed (BDD outer loop).
- [`skills/research-acceptance-criteria/SKILL.md`](../research-acceptance-criteria/SKILL.md)
  — prose acceptance criteria for an existing item (different output shape).
- [`docs/ROADMAP.md`](../../docs/ROADMAP.md) ·
  [`docs/PROJECT-DEVELOPMENT-SNAPSHOT.md`](../../docs/PROJECT-DEVELOPMENT-SNAPSHOT.md)
  — the state signals every story must trace back to.
- `internal/e2e/features/*.feature` — the existing stories and the step
  vocabulary to reuse.
