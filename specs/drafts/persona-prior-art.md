# Persona authoring — prior art

**Status:** draft · **Scope:** persona creation model, not runtime architecture · **Companion to:** `specs/VISION.md`, `RFP.md`

This note surveys three ambient-companion projects that ship a working persona-authoring or persona-runtime layer. It exists so the Ambisphere Runtime persona model can stand on what already works without inheriting the assumptions those projects bake in.

## Surveyed projects

### codex-pets

**What it is.** A portable pet runtime originating in the OpenAI Codex CLI and reused by Claude Code, Cursor, and Gemini CLI. Pets are installed as static folders under `~/.codex/pets/<name>/`.

**Persona surface.** `pet.json` exposes four fields: `id`, `displayName`, `description`, `spritesheetPath`. The real behavioral contract lives outside the manifest: a fixed nine-state vocabulary — `idle`, `running-right`, `running-left`, `waving`, `jumping`, `failed`, `waiting`, `running`, `review` — that host agents emit and the renderer reacts to.

**Lifecycle.** Bundle is static. Host agents push events; the renderer flips frames. No aging, evolution, or persistent inner state.

**Source.** `github.com/codex-pets/codex-pets` · gallery `github.com/crafter-station/petdex` · first-party `/pet` lives in `openai/codex`.

### hatch-pet

**What it is.** An OpenAI-curated agent skill whose job is to author a brand-new codex-pets-compatible pet from a prompt, brand, or reference images.

**Inputs.** Pet name (optional, inferred), description (optional), reference images, brand or company name (triggers a brand-discovery worker), `style-preset` (`auto | pixel | plush | clay | sticker | flat-vector | 3d-toy | painterly | brand-inspired`), free-form style notes.

**Output.** A package at `${CODEX_HOME:-$HOME/.codex}/pets/<name>/` containing `pet.json`, `spritesheet.webp` (9 rows × 8 frames, the state atlas), and a `qa/` directory with a contact sheet, per-row GIF previews, `review.json`, and `run-summary.json`.

**Relationship to codex-pets.** hatch-pet is the authoring pipeline; codex-pets is the consumer. The skill's output drops directly into the directory the runtime reads.

**Source.** `github.com/openai/skills/blob/main/skills/.curated/hatch-pet/SKILL.md`.

### claude-buddy

**What it is.** A sibling project (different lineage) that adds the persona dimensions codex-pets deliberately omits.

**Persona surface.** Per-buddy `stats` (e.g. WISDOM 56, PATIENCE 1), an explicit `personality` string, `species` (18 including axolotl), `rarity` tiers, deterministic hash-from-account-id generation, name-trigger reactions, and a status-line rendering channel.

**Source.** `1270011/claude-buddy`, `littleben/buddy-companion`, `cpaczek/any-buddy`.

## What Ambisphere adopts

1. **Self-contained entity bundle.** A persona ships as a directory the runtime consumes — manifest, assets, QA artifacts. Authoring and runtime stay separable. This pattern lets a single bundle move between hosts and renderers without rewriting either side.

2. **State vocabulary as contract.** codex-pets' insight is that the *named states* — not the frames, not the manifest — are the actual API between agents and entities. Ambisphere generalizes this: hosts emit semantic events, entity state reducers project those events onto named states, and renderers subscribe to states. The names are the contract; everything above and below is replaceable.

3. **Authoring as a skill, output as a bundle.** The `hatch` pattern — prompt or brand or reference → discovery worker → packaged artifact with QA — is a natural fit for an Ambisphere persona-authoring skill. The artifact-with-QA shape is worth importing wholesale.

4. **Persona depth from claude-buddy.** Stats, personality string, voice prompt, rarity, and behavior triggers cover the dimensions codex-pets leaves implicit. Ambisphere persona schemas should support these fields without requiring them — many domain uses (CI dashboards, observability) will not need voice or rarity at all.

## What Ambisphere rejects

| Pattern | Why rejected |
|---|---|
| Spritesheet-as-truth (`spritesheetPath` in the manifest, fixed atlas geometry) | Couples persona to a single rendering substrate. Violates the renderer-agnostic principle. Ambisphere personas describe state and semantics; rendering is a downstream projection. |
| Nine hardcoded animation states | Too presentational. `running-left` and `waving` are renderer concerns; `working`, `blocked`, `awaiting-human` are runtime concerns. Ambisphere separates the two so an operational entity (CI watcher) and a creative entity (storyteller companion) can share a state model without sharing animation frames. |
| `$CODEX_HOME` / `~/.codex/pets/` path lock-in | Codex-tied. Ambisphere's local-first stance must be vendor-neutral; bundles live under an Ambisphere-owned path (TBD in `specs/SRS.md`) and the daemon brokers access. |
| OpenAI-only image generation in hatch-pet | Violates the no-AI-provider-lock-in principle. Authoring skills must accept pluggable generators; reference-based and human-illustrated bundles must be first-class. |
| Hash-from-account-id determinism (claude-buddy) | Couples persona identity to a vendor account. Ambisphere personas are independent artifacts; identity belongs to the bundle, not the host. |
| Renderer assumed by host CLI | Codex-pets and claude-buddy each assume one rendering channel (terminal sprite, status line). Ambisphere's daemon must publish entity state and let any number of renderers subscribe. |

## Open questions

- What is the minimum persona manifest? Likely: identity (name, slug, version), semantic-state vocabulary (declared, not hardcoded), event-handling hints, optional persona depth (personality, voice, traits) — but *not* renderer fields. Needs a spec under `specs/drafts/`.
- How do renderer bundles attach to persona bundles without the persona depending on them? Sibling directories? Capability declarations? Open.
- Does an authoring skill produce *just* the persona, or does it also produce a default renderer bundle so the persona is immediately visible somewhere? Open — argues both ways.
- How does Ambisphere accept claude-buddy-style depth fields (stats, rarity) without making them mandatory? Schema-level optionality; needs a worked example.

## Citations to keep visible

When the persona-authoring spec lands, the references above must be cited inline so contributors can see exactly what was inherited and what was deliberately discarded. The runtime is better when its lineage is legible.
