---
name: remotion-author
description: >
  Author a Remotion composition or scene spec in the BEATS-blueprint
  style. Use when an agent needs to produce a new Remotion video — a
  scene file, a composition entry, or the spec markdown that drives a
  build. The skill encodes the "specs are code blueprints, not prose"
  discipline lifted from the ICM animation-studio reference
  (RinDig/Content-Agent-Routing-Promptbase). The bundled linter
  `.loswf/tools/lint_remotion_spec.py` enforces the structural
  invariants (BEATS const per scene, monotonic frames, durations sum
  to total, component references resolve). Do NOT use this to render
  the final video (use `remotion-render`), to author non-Remotion
  motion graphics, or to write narrative prose specs — the whole
  point is that the spec is executable intent, not creative writing.
side: shadow
contract:
  kind: deliverable
  inputs: []
  outputs:
    - path: docs/assets/*.tsx
      required: true
  verify:
    - skill-frontmatter
---

# remotion-author

The discipline behind authoring Remotion code that an agent can
reliably translate from spec to working composition. Adapted from
the animation-studio workspace in
[RinDig/Content-Agent-Routing-Promptbase](https://github.com/RinDig/Content-Agent-Routing-Promptbase),
which proved the pattern in production: agents that wrote prose
specs produced inconsistent video; agents that wrote BEATS blueprints
produced near-deterministic results.

Sister skill: [`remotion-render`](../remotion-render/SKILL.md)
invokes the bundled `.loswf/tools/render_remotion.py` against output
authored here.

## Purpose and boundaries

This skill commits to:

- A spec format that reads as **executable intent** — every scene
  carries a TypeScript `const BEATS` constant that names every
  animation event with a frame stamp.
- A component-reference discipline — JSX-tagged components in spec
  bodies must resolve to a `component-registry.md` (a markdown index
  of available React components with their prop shapes).
- A linter (`.loswf/tools/lint_remotion_spec.py`) that catches
  structural violations before render — missing BEATS blocks,
  out-of-window frame numbers, duration math errors, unresolved
  component refs.

It does NOT commit to:

- Inventing components. The spec author works against an existing
  registry; new components are added through a separate agent flow
  that updates the registry first.
- Narrative quality. The linter doesn't read prose; an editor pass
  is still required for tone, pacing, story.
- Render execution. Use `remotion-render` for that.

## The cardinal rule

> **Specs are code blueprints, not prose. The builder agent
> translates, not interprets.**

This is the single load-bearing decision. Every other rule below
follows from it.

A spec that reads as a paragraph about what should happen creates
ambiguity at every frame the builder picks. A spec that reads as a
table of components, props, frame stamps, and timing constants
produces a near-deterministic build because there's nothing left to
interpret. The cost is some authoring overhead; the payoff is repeatable,
diff-able, lint-able specs.

## Inputs

Required:

- **A scene narrative or beat structure** — what the video is *about*
  in plain text. The agent's job is to compile this into the BEATS
  form.
- **A target composition shape** — fps, duration in frames, target
  resolution (1080×1920 vertical short-form is common).
- **A component registry** — markdown file naming the React
  components available, with prop shapes. Lives alongside the
  Remotion project (e.g. `examples/remotion-demo/docs/component-registry.md`).
  Default builtins (Sequence, Series, AbsoluteFill, etc.) don't
  need to be listed.

Optional:

- **A project-specific design system** — color tokens, typography
  scales, motion presets — codified in `docs/design-system.md` next
  to the registry. The spec's components reference these tokens by
  name.

## Spec format

Front-matter (YAML) is required:

```yaml
---
composition: ClipName            # matches <Composition id=...>
fps: 30
duration_frames: 90              # MUST equal sum of scenes[*].duration_frames
scenes:
  - name: hook
    duration_frames: 30
  - name: core
    duration_frames: 45
  - name: closing
    duration_frames: 15
---
```

Body structure:

```markdown
# Clip: <title>

## Source script

`path/to/upstream/script.md` (or "n/a" for atomic specs)

## Components used

- `LoswfxLogo`: animated mark, props `{ frame, scale }`
- `MonospaceCaption`: chyron under main visual, props `{ text, frame, range }`

## Scene 1 — hook (frames 0–30)

The lights-out factory mark fades in from the dark canvas. By frame
12 it's at full opacity; an amber sweep crosses left-to-right between
frames 14 and 24 ("the factory is awake").

Render:

  <LoswfxLogo frame={frame} scale={spring({frame, fps, config: {damping: 12}})} />
  <MonospaceCaption text="lights out." frame={frame} range={[14, 24]} />

```typescript
const BEATS = {
  LOGO_FADE_IN_START: 0,
  LOGO_FADE_IN_END: 12,
  AMBER_SWEEP_START: 14,
  AMBER_SWEEP_END: 24,
  HOLD_END: 30,
} as const;
```

## Scene 2 — core (frames 30–75)

...
```

### What the linter checks

The bundled `.loswf/tools/lint_remotion_spec.py` enforces:

- **`SPEC_HAS_FRONTMATTER`** — required keys `composition`, `fps`,
  `scenes` (with `duration_frames` per scene).
- **`SPEC_FRONTMATTER_DURATION_MATCHES`** — `duration_frames` (if
  present) equals the sum of scene durations.
- **`EVERY_SCENE_HAS_BEATS`** — every scene in front-matter has a
  matching `## Scene N — <name>` heading and a
  ```` ```typescript const BEATS = { … }``` ```` block under it.
- **`BEATS_FRAMES_MONOTONIC`** — entries in a BEATS const are
  non-decreasing in source order.
- **`BEATS_FRAMES_WITHIN_SCENE`** — every BEATS frame value lies in
  `[scene_start, scene_start + scene_duration)`.
- **`BEATS_DENSITY_REASONABLE`** — at least 3 BEATS entries per
  second of scene duration. Warn-only by default;
  `--strict-density` promotes to error.
- **`COMPONENTS_RESOLVE`** (when `--registry` is passed) — every
  capitalised JSX-tag in the body resolves to a `### <Name>` heading
  in the registry markdown (plus a small builtin set: Sequence,
  Series, AbsoluteFill, Composition, Audio, Video, Img, Loop, Freeze,
  OffthreadVideo, IFrame, Still).

## Workflow

### Step 1: Lock the timing

Decide fps + total duration first. Decompose into scenes such that
`sum(scenes[*].duration_frames) == duration_frames`. This is the
spine; everything else hangs off it.

For short-form vertical (TikTok/Reels): 30 fps, 30 frames per second
of screen time. A 3-second clip = 90 frames; a 15-second clip = 450.

### Step 2: Identify components

Read the component registry. List every component the scene will
use in a "Components used" section. If a component you need doesn't
exist, **stop** — author it in the Remotion project first (this is
not the agent's job in a single spec pass; surface as a finding
and exit).

### Step 3: Author scenes

For each scene:

1. Write a one-paragraph narrative describing what happens.
2. Inline the JSX-prop strings for every visual element. These don't
   have to compile — they describe component invocations the
   builder will translate.
3. End the scene with a `const BEATS = { … } as const;` block in a
   ```` ```typescript ```` fence. Name every animation event with a
   frame stamp. Aim for 3–4 events per second of scene duration.

### Step 4: Lint

```bash
.loswf/tools/lint_remotion_spec.py \
  --spec path/to/clip-spec.md \
  --registry path/to/component-registry.md
```

Fix violations and re-run until clean.

### Step 5: Hand off

The spec is now ready for a build agent (or human builder) to
translate into Remotion code: `src/compositions/<Project>/<Clip>/
{ index.tsx, timing.ts, scenes/Scene*_Name.tsx, components/* }`.

The translation is mechanical: BEATS becomes a `timing.ts` constant,
scenes become files, JSX-prop strings become real React.

## Failure modes to avoid

- **Prose narratives instead of BEATS.** A scene reading "The logo
  fades in slowly and then a caption appears" lints fine if the
  BEATS block is present but produces drift on every build. Every
  visual event in the prose must have a corresponding BEATS entry.
- **Floating frame numbers.** Hardcoding a frame number in scene
  3 that doesn't relate to scene 3's window. Use `BEATS_FRAMES_WITHIN_SCENE`
  — the linter catches it.
- **Unregistered components.** Inventing `<NeonGlowText>` because
  it would look cool. The registry is the contract; if the
  component doesn't exist, ship a registry-extension finding first.
- **Drift between front-matter and scene headings.** Six scenes in
  front-matter but only five `## Scene N` headings. Linter catches
  this as `EVERY_SCENE_HAS_BEATS`.
- **CSS transitions.** Remotion forbids them — `useCurrentFrame()`
  + `interpolate()` + `spring()` are the supported timing primitives.
  Don't put `transition: opacity 0.3s` in a component prop string.

## Verification

A spec is ready for build when:

- `lint_remotion_spec.py --spec <path> --registry <path>` exits 0.
- Every component referenced in the body appears in "Components
  used" (cross-check during review).
- Every scene's `const BEATS` block has at least 3 entries per
  second of scene duration.
- The BEATS frame values across scenes form a strictly increasing
  sequence (linter checks within-scene monotonicity; the
  cross-scene case follows from the within-scene window check).

## References

- Bundled linter: `.loswf/tools/lint_remotion_spec.py`.
- Sister skill: [`remotion-render`](../remotion-render/SKILL.md).
- Origin pattern: animation-studio in
  [RinDig/Content-Agent-Routing-Promptbase](https://github.com/RinDig/Content-Agent-Routing-Promptbase)
  — see `workflows/02-specs/CONTEXT.md` and the per-clip spec files
  under `short-form/`.
- Remotion docs: https://www.remotion.dev/docs
