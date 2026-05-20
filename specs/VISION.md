# Ambisphere Runtime — Vision

## Purpose

Explore whether ambient entities — persistent, lightweight, contextual presences — can become a reusable interaction primitive for agentic, asynchronous, operationally complex software, the way windows, notifications, and chat once did.

This repository starts from philosophy and runtime concepts, not implementation. Its primary output at this stage is specs, research notes, and proposals that interrogate the runtime model. Code, if it appears, exists to test a hypothesis the specs have already proposed.

## Principles

1. **Renderer-agnostic.** The runtime makes no commitment to sprites, Live2D, vectors, 3D, native widgets, or any other rendering substrate. Renderers are pluggable consumers of runtime state.
2. **Persona-agnostic.** Ambient entities are not mascots, avatars, or assistants by default. The runtime treats persona as one optional projection over entity state, not a built-in concept.
3. **Domain-agnostic.** The runtime must serve both creative and operational use cases — storytelling, CI/CD, observability, accessibility, education, research — without privileging any of them in its core model.
4. **Local-first and daemon-oriented.** The default deployment shape is a long-running local daemon that owns entity state and brokers events. Cloud dependence is opt-in and must be called out explicitly.
5. **Specs before code.** Architectural choices are proposed, reviewed, and recorded as specs before implementation. Open questions live inside specs as open questions, not as undocumented code decisions.
6. **No transport, AI, or framework lock-in.** Event ingestion, AI providers, rendering frameworks, and UI toolkits are all decoupled. Any experiment that introduces a hard dependency must justify the scoped choice and propose how to abstract it later.
7. **Glanceable over interruptive.** Ambient entities exist to make state legible without demanding attention. The runtime should make it easier to express "this is the situation" than "stop and look at this."

## Non-goals

The project is **not** attempting to define or build:

- A single rendering standard
- A single transport protocol
- A mandatory AI stack
- A specific personality system
- A centralized cloud platform
- A virtual companion product
- A VTuber framework
- A game engine
- A chatbot platform

These are explicitly out of scope. Proposals that drift toward any of them should be reframed or rejected.

## Prior art and inspiration

Persona authoring in this runtime draws on existing ambient-companion projects — chiefly **codex-pets**, the **hatch-pet** authoring skill, and **claude-buddy** — as foundational inspiration. The runtime adopts their separation between *authoring* (a skill that produces a self-contained entity bundle) and *runtime* (a host that consumes the bundle and reduces semantic events into state), but rejects the parts of those projects that violate the principles above: spritesheet-as-truth, hardcoded presentational state vocabularies, single-vendor path or image-generation lock-in, and vendor-identity-derived persona determinism.

See `specs/drafts/persona-prior-art.md` for the full treatment — what to adopt, what to reject, and why.
