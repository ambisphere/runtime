---
name: remotion-render
description: >
  Render a Remotion composition to MP4/WebM/ProRes/PNG-sequence via the
  bundled `.loswf/tools/render_remotion.py` wrapper. Use when an agent
  has authored or modified Remotion code and needs to produce a real
  video artifact for review, shipping, or shadow-side archive. Two
  required inputs: a Remotion project root with package.json + src/,
  and a composition ID registered in that project. Output is a video
  file at the requested path + a sibling receipt JSON capturing
  duration, size, exit code, codec, props hash. Do NOT use this to
  author Remotion code (use the `remotion-author` skill), to preview
  interactively (use `npx remotion studio` on the operator's
  workstation), or in environments without Node 16+ on PATH.
side: shadow
contract:
  kind: deliverable
  inputs:
    - kind: layer-4
      path: docs/assets/*.tsx
      required: true
  outputs:
    - path: docs/assets/*.mp4
      required: true
  verify:
    - skill-frontmatter
---

# remotion-render

Thin invocation skill for the bundled Remotion render primitive.
Wraps `npx remotion render` with tier presets, composition-ID
pre-validation, props-as-tempfile (Windows-safe), and a structured
receipt JSON. Mirrors the `image-generate` shape — small primitive,
honest receipt.

For authoring philosophy (BEATS, specs-as-blueprints): see the sibling
[`remotion-author`](../remotion-author/SKILL.md) skill.

## Purpose and boundaries

This skill commits to:

- Invoking `npx remotion render` against a project root + composition
  ID, with the codec + concurrency + quality flags resolved from a
  named tier preset.
- Pre-validating the composition ID against `npx remotion compositions
  --quiet` so the failure mode "comp ID typo" is caught before the
  ~minute-scale render starts.
- Materializing `--props` as a tempfile per the Remotion docs (inline
  JSON strings aren't supported on Windows shells).
- Writing a receipt JSON alongside every render — schema
  `loswf-remotion-render-receipt-v1`. Captures the command, props
  sha256, duration, exit code, stderr tail.

It does NOT commit to:

- Authoring Remotion compositions, components, or specs. Different
  skill.
- Lambda / cloud rendering. The wrapper is local-only by design. Add
  Lambda behind a flag if a real use case appears; until then, the
  one extra dependency on AWS credentials isn't worth carrying.
- Running `npm install` for the target project. The wrapper assumes
  the project is installable and that the operator has run
  `npm install` (or that node_modules is otherwise present).

## Inputs

Required:

- **`--project <dir>`** — path to the Remotion project root. Must
  contain `package.json`. Typically also contains `src/` and
  `remotion.config.ts`.
- **`--composition <id>`** — the composition ID as registered in
  `src/Root.tsx` (or wherever the entry file calls
  `<Composition id="..."  ...>`).
- **`--out <path>`** — output file path. Extension should match codec
  (`.mp4` for h264/h265, `.webm` for vp9, `.mov` for prores, `.png`
  for png sequences).

Optional:

- **`--props-file <path.json>`** — JSON object to inject as the
  composition's runtime props. Tool reads the file once, validates
  it's a JSON object, hashes it for the receipt, then passes
  `--props=<absolute path>` to `npx`.
- **`--tier preview|default|max|prores-4444-xq`** — quality/speed
  preset. Default: `default`.
  - `preview` — fast draft, h264 + jpeg-quality 70. For iteration.
  - `default` — balanced, h264 + jpeg-quality 85. Most ship paths.
  - `max` — h264 + jpeg-quality 100 + yuv420p. Larger files, slower.
  - `prores-4444-xq` — ProRes 4444 XQ for downstream editing.
    Output should be `.mov`.
- **`--codec`** — override the tier's codec (e.g. force vp9 on a
  preview tier).
- **`--concurrency N`** — parallel workers. Lower this if the render
  OOMs.
- **`--frames START-END`** — frame range. Default: full duration.
- **`--entry src/index.ts`** — composition entry path inside the
  project. Defaults to `src/index.ts`.
- **`--no-validate-comp-id`** — skip the pre-check. Faster on
  repeated renders against the same project; errors get less helpful.

Environment:

- **`npx` on PATH** — wraps Node's executable runner. The wrapper
  exits 2 with a clear message if missing.
- **No API keys.** Local render is free; nothing is sent off-machine.

## Outputs

- The rendered video file at `<--out>`.
- A sibling receipt at `<--out>.receipt.json` with schema
  `loswf-remotion-render-receipt-v1`. Fields:
  - `id` (uuid), `started_at` / `finished_at` (ISO 8601),
    `duration_sec`, `ok`, `error`, `exit_code`.
  - `tool.command` — the full `npx` argv that ran.
  - `project`, `entry`, `composition`, `tier`, `tier_doc`, `codec`,
    `concurrency`, `frames`.
  - `out`, `out_size_bytes`.
  - `props_file` + `props_sha256` when props were injected.
  - `stderr_tail` — last 1.2k of stderr on failure.

## Workflow

### Step 1: Confirm the project is installable

Before invoking the tool, ensure `node_modules/` is populated:

```bash
cd <project-dir>
npm install
```

The wrapper does not run this for you. If `node_modules/` is missing,
the comp-ID pre-check (which runs `npx remotion compositions`) will
fail.

### Step 2: Discover composition IDs (optional)

If the composition ID is unknown, list them first:

```bash
npx --yes remotion compositions <project-dir>/src/index.ts --quiet
# emits space-separated IDs
```

### Step 3: Render

```bash
.loswf/tools/render_remotion.py \
  --project examples/remotion-demo \
  --composition LoswfxIntro \
  --out .loswf/state/remotion/intro.mp4 \
  --tier default
```

On success the tool prints a single JSON line:

```json
{"ok": true, "out": "...", "receipt": "....receipt.json",
 "duration_sec": 12.4, "size_bytes": 481102, "tier": "default",
 "composition": "LoswfxIntro"}
```

### Step 4: Verify

Inspect the receipt:

```bash
cat <out>.receipt.json | python3 -m json.tool | head
```

- `exit_code: 0` and `ok: true` mean the render finished cleanly.
- `out_size_bytes` should be sane for the duration + codec + tier.
  A 3-second h264 default-tier render at 1080p is usually 200–800 KB;
  if you see 1 KB, something rendered empty.
- `stderr_tail` carries the most informative error string on
  failure — read it first.

### Step 5: Promote

PNG outputs and per-render artifacts default to `.loswf/state/...`
(gitignored — shadow). To ship a render in a deliverable, `mv` it to
`docs/assets/` or the engagement output path and update references.

## Failure modes to avoid

- **Running without `npm install`.** The comp-ID pre-check will fail
  with a confusing module-not-found message. Always install first.
- **Composition ID typo.** Without `--no-validate-comp-id` the pre-
  check catches this; with it, you'll burn the full render before
  Remotion complains.
- **Output extension mismatching codec.** Naming the output `.mp4`
  while passing `--codec=vp9` produces a malformed file. Match
  extension to codec.
- **`--frames` outside duration.** A composition registered with
  `durationInFrames=90` will fail on `--frames=0-200`. Read
  `Root.tsx` first.
- **OOM on long renders.** Default concurrency is high. Drop to
  `--concurrency=2` on machines with <16GB RAM, or render in slices
  via `--frames` and concatenate downstream.
- **First-run Chromium download.** Remotion bundles Chromium via
  Puppeteer; the first render after `npm install` downloads ~150MB.
  Allow the first render extra time + bandwidth, or pre-warm via
  `npx remotion versions`.

## Verification

The render produced a usable output when:

- The file at `<--out>` exists and is non-trivial in size
  (`out_size_bytes` in the receipt > 1KB for video, > 100B for a
  single PNG).
- The receipt's `ok: true` and `exit_code: 0`.
- For Mermaid-style structural diagrams converted to Remotion: every
  scene listed in your authoring spec made it into the rendered
  video. Spot-check with `--frames=<scene_start>-<scene_start+1>` if
  in doubt.
- The receipt is committed to the audit trail (or kept in
  `.loswf/state/remotion/` for shadow-side records).

## References

- Bundled tool: `.loswf/tools/render_remotion.py`.
- Sister skill: `skills/remotion-author/SKILL.md` — authoring
  philosophy + spec linter.
- Remotion CLI: https://www.remotion.dev/docs/cli/render
- Tier presets are derived from the `rendering-guide` in
  RinDig/Content-Agent-Routing-Promptbase.
