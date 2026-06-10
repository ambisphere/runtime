# Runtime design spec — index

**Status:** draft · **Scope:** index of the runtime design-spec suite (ADR-0001 + 11 component specs) · **Companion to:** `specs/drafts/runtime-paradigm-and-specs-guidance.md`, issues #4, #5, #6

This suite was authored by a design team (one specialist per spec, employing the relevant skills) in strict dependency order, then put through a four-lens adversarial architect review (invariants · consistency · non-goals · completeness) and revised against the findings. Every spec declares `Conforms to: ADR-0001` and cites the canonical numbered invariants ADR-0001 fixes. All are `draft` and enter the factory pipeline via issue #6 before promotion to `specs/`.

## The decision of record

- [ADR-0001 — foundational runtime paradigm and per-tier implementation language](./ADR-0001-runtime-paradigm-and-language.md) — **accepted.** Capability-gated actor-write / event-log source-of-truth / ECS-read materialized view, with the directionality invariant and the explicit rejection of an ambient-authority component store. Core daemon = Rust (Swift 6.4 the recorded close alternative); renderers best-per-platform; adapters polyglot. Fixes the numbered invariants (1–9) the specs conform to.

## The spec suite, in dependency order

Critical-path spine (authored sequentially, each binding to the previous one's contract):

1. [Attention routing and interruption policy](./spec-attention-routing.md) — the read-side query contract + normalized `attention` component; explainable cost-benefit ranking; escalation ladder; operator-selected focus modes. Sequenced first per issue #4 (its facet shape dictates the rest).
2. [Reducers, state components and provenance](./spec-reducer-state-component.md) — the pure deterministic reducer contract, the component/facet model, PROV-shaped lineage, the fact/narration firewall, checkpoints/snapshot/rebuild.
3. [Semantic event envelope and ingestion](./spec-event-envelope.md) — CloudEvents-shaped envelope (envelope/payload/runtime-assigned), per-entity total order, capability-gated `submit(event)`, idempotent apply, schema evolution.
4. [Entity identity and hierarchical graph](./spec-entity-identity-graph.md) — opaque handle + injection-safe compound-key alias; kind as metadata; typed edges (`child-of`, `instance-of`); read-side rollups.
5. [Local daemon architecture and lifecycle](./spec-daemon-architecture.md) — single sole-writer process; SQLite/WAL behind a StorageDriver; hibernation; always-resident cross-entity index; crash recovery; UDS broker (write ingest + cursor-resumable read). Owns the ingest-atomicity/reduction-failure contract.

Edge specs (authored in parallel against the frozen core contracts):

6. [Renderer observation and projection contract](./spec-renderer-contract.md) — one-way observation (LSP-style); state/attention/persona channels; snapshot+delta+resync; actions flow through the write side.
7. [Action and capability manifest](./spec-action-capability.md) — declarative MCP-shaped manifest + object-capability enforcement; manifest flags are UX hints, the capability check is the boundary; async approval-requested state.
8. [Local-first privacy and credential boundary](./spec-privacy-credential-boundary.md) — credentials never in state/components/log; adapter-owned egress with pre-egress redaction; separately gated read vs write authority; namespace as trust boundary.
9. [Adapter and plugin API](./spec-adapter-api.md) — anti-corruption layer; narrow inbound port emitting envelopes; source-offset idempotency; opaque namespaced payload; Rust reference SDK + language-neutral wire spec.
10. [Persona projection](./spec-persona-projection.md) — pure optional derived projection; semantic→expressive→frame layers; factual/narrated wall; never gates capability-critical signals.
11. [Entity bundle and package format](./spec-entity-bundle-format.md) — declarative serialization of the other contracts; composition/reference/versioning/validation only; the integration pressure-test.

## Review provenance

Adversarial review surfaced and resolved blocker/major findings across the suite (per-spec actionable counts, all revised): event-envelope 15 · daemon 13 · reducer 12 · action-capability 12 · bundle 12 · privacy 11 · attention 7 · persona 7 · ADR-0001 6 · identity 6 · renderer 5 · adapter 3. The largest cross-spec fixes were: a single atomic append+reduce commit-point invariant (daemon owns it; envelope/reducer defer to it), the "zero domain event types vs a closed runtime-meta allowlist" distinction, and one canonical numbered-invariant table in ADR-0001 as the shared conformance anchor.

## Known follow-ups

- The reducer spec's header still references ADR-0001 as `Proposed` (it conforms "provisionally"); ADR-0001 is now `accepted` — a one-line staleness to fix on next edit.
- The consolidated open questions across the suite (capability-model depth, log partitioning/snapshot cadence, schema-evolution policy before any log is written, read-authority redaction shape, hierarchy rollup determinism, TUI/desktop/packaging choices) remain open by design and are each tagged to the spec that will resolve them.
