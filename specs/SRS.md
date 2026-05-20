# Ambisphere Runtime — Software Requirements Specification (stub)

> This is a placeholder. The runtime is at concept/RFP stage. The first round of factory work will expand individual sections here as decomposed specs land under `specs/`.

## 1. Purpose

Define the requirements for an open ambient runtime: a local-first, daemon-oriented layer that lets software systems express state, attention, and intent through persistent contextual entities, independent of any specific renderer, persona system, transport protocol, or AI provider.

This SRS is the long-form companion to [`VISION.md`](VISION.md). Where VISION sets the principles and non-goals, the SRS records the concrete requirements, interfaces, and invariants the runtime must satisfy.

## 2. Scope

Not yet drafted — see open questions below. At minimum, the SRS will eventually cover:

- Entity lifecycle and persistence
- Semantic event ingestion
- State reduction model
- Renderer interface
- Persona projection (optional)
- Attention routing
- Human-in-the-loop interaction
- Local daemon architecture
- Cross-platform behavior

## 3. Definitions

To be expanded as terms stabilize. Initial seeds:

- **Ambient entity** — a persistent contextual presence representing workflow state, operational health, system attention, agent activity, or human-in-the-loop interaction.
- **Renderer** — any system that translates entity state into a visible representation. Pluggable; the runtime makes no assumptions about its technology.
- **Persona projection** — an optional layer that maps entity state to expressive characteristics (mood, voice, posture, etc.). Not required for an entity to exist.

## 4. Validation configuration

The factory's validation gates for this repo are documented in `.loswf/config.yaml` under `validate:`. They are doc-shape checks, not code tests, and each is `command -v`-gated so that absent tools cause skips rather than failures.

Current gates:

1. **spec-presence** — `specs/VISION.md` and `specs/SRS.md` must exist.
2. **markdown-lint** — runs `markdownlint` against `README.md`, `RFP.md`, `specs/`, `docs/` when installed.
3. **link-check** — runs `lychee --offline` against the same set when installed.

Install hints:

- `brew install markdownlint-cli`
- `brew install lychee`

Strict gating is opt-in: install the tool and the guard activates automatically.

## 5. Open questions

- What is the minimum viable entity state model?
- What event shapes does the daemon accept?
- How are renderers discovered and registered?
- What persistence guarantees does the daemon offer?
- How do multiple applications share an entity surface?
- What is the security model for cross-application event publishing?

Each of these is expected to become its own spec under `specs/` before any implementation begins.
