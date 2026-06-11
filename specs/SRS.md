# Ambisphere Runtime — Software Requirements Specification (stub)

> This top-level SRS remains a stub. The requirements it once anticipated are now being drafted as a dependency-ordered design-spec suite under [`drafts/`](drafts/) — see the [design spec index](drafts/DESIGN-SPEC-INDEX.md) and [ADR-0001](drafts/ADR-0001-runtime-paradigm-and-language.md), which fixes the paradigm, per-tier language, and the canonical invariants the specs conform to. Those drafts clear review and promote to `specs/`; this SRS will then be rewritten as their consolidated index rather than a placeholder.

## 1. Purpose

Define the requirements for an open ambient runtime: a local-first, daemon-oriented layer that lets software systems express state, attention, and intent through persistent contextual entities, independent of any specific renderer, persona system, transport protocol, or AI provider.

This SRS is the long-form companion to [`VISION.md`](VISION.md). Where VISION sets the principles and non-goals, the SRS records the concrete requirements, interfaces, and invariants the runtime must satisfy.

## 2. Scope

The scope below is now drafted across the design-spec suite in [`drafts/`](drafts/). Each area maps to one or more component specs:

- Entity lifecycle and persistence — [daemon architecture](drafts/spec-daemon-architecture.md), [reducers/state/provenance](drafts/spec-reducer-state-component.md)
- Semantic event ingestion — [event envelope](drafts/spec-event-envelope.md)
- State reduction model — [reducers, state components and provenance](drafts/spec-reducer-state-component.md)
- Renderer interface — [renderer observation/projection contract](drafts/spec-renderer-contract.md)
- Persona projection (optional) — [persona projection](drafts/spec-persona-projection.md)
- Attention routing — [attention routing and interruption policy](drafts/spec-attention-routing.md)
- Human-in-the-loop interaction — [action and capability manifest](drafts/spec-action-capability.md) (durable approval-requested state)
- Local daemon architecture — [daemon architecture and lifecycle](drafts/spec-daemon-architecture.md)
- Cross-platform behavior — [daemon architecture](drafts/spec-daemon-architecture.md) (packaging/supervision), [implementation language guidance](drafts/implementation-language-guidance.md)
- Entity identity & relationships — [entity identity and hierarchical graph](drafts/spec-entity-identity-graph.md)
- Adapters & privacy boundary — [adapter API](drafts/spec-adapter-api.md), [privacy/credential boundary](drafts/spec-privacy-credential-boundary.md)
- Packaging of all of the above — [entity bundle and package format](drafts/spec-entity-bundle-format.md)

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

Each of these now has a home in the draft suite (residual unknowns live as open questions inside those specs):

- What is the minimum viable entity state model? — [reducers/state](drafts/spec-reducer-state-component.md), [identity](drafts/spec-entity-identity-graph.md)
- What event shapes does the daemon accept? — [event envelope](drafts/spec-event-envelope.md)
- How are renderers discovered and registered? — [renderer contract](drafts/spec-renderer-contract.md)
- What persistence guarantees does the daemon offer? — [daemon architecture](drafts/spec-daemon-architecture.md)
- How do multiple applications share an entity surface? — [identity](drafts/spec-entity-identity-graph.md), [privacy boundary](drafts/spec-privacy-credential-boundary.md), [action/capability](drafts/spec-action-capability.md)
- What is the security model for cross-application event publishing? — [action/capability](drafts/spec-action-capability.md), [adapter API](drafts/spec-adapter-api.md), [privacy boundary](drafts/spec-privacy-credential-boundary.md)

These drafts go through factory review before promotion to `specs/` and before any implementation begins.
