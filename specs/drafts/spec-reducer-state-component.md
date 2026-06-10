# Reducers, state components and provenance

**Status:** draft · **Scope:** the pure deterministic reducer contract `reduce(prevState, event) -> {nextState, provenance}`; the canonical-value serialization the contract hashes and replays against; the component/facet model (including the canonical `attention` facet); the closed list of core-owned component types; the shared declarative predicate + field-path mini-language; W3C PROV-shaped lineage as a first-class reduction output; the fact/narration firewall (narrated projection separate, tagged, never a reducer input); per-projection checkpoints, rebuildability, and snapshot-as-pure-function-of-a-log-prefix. **The reducer-failure / ingest-atomicity contract is *owned by the daemon spec*; this spec defers to it and restates the resulting reducer outcome enum so the two never diverge.** · **Companion to:** `specs/VISION.md`, `specs/SRS.md`, `RFP.md` (§ "State reduction models", "State reducers") · **Sequenced:** third among the follow-on specs (after the attention-bus spec, before the event-envelope spec) per ADR-0001 and issue #4 · **Conforms to:** ADR-0001 (foundational paradigm + directionality invariant — **currently `Proposed`; this spec conforms to it provisionally and re-pins on ADR acceptance**, see § "ADR status"); the attention-routing spec (the `attention` facet shape is fixed there and produced here); the daemon-architecture spec (owner of the ingest-atomicity-and-reduction-failure contract and the physical storage of checkpoints/snapshots/provenance) · **Sibling notes:** `specs/drafts/runtime-paradigm-and-specs-guidance.md`, `specs/drafts/actor-model-prior-art.md`, `specs/drafts/persona-prior-art.md`, `specs/drafts/implementation-language-guidance.md`

This spec defines the **projection layer**: how the per-entity append-only event log — the single source of truth (ADR-0001 invariant 1) — is folded by pure, deterministic reducers into typed, read-only **component state**, and how every reduction emits **provenance** so any derived value can answer "where did this come from?". It fixes the canonical serialization that makes "byte-identical replay" a real, testable property, the component/facet model the read side (renderers, the attention bus) queries, the lineage vocabulary, the firewall between deterministic fact and AI narration, and the checkpoint/snapshot/rebuild machinery that makes the whole projection rebuildable from the log.

It is the seam-facing read-side spec. Per the ADR-0001 directionality invariant, nothing here is written directly: components are produced **only** by replaying events through reducers. There is no `setComponent` API, no component the renderer can mutate, and no path by which narration reaches a reducer or the log. The reducer is the *only* writer of component state, the log is its *only* input, and provenance is its co-equal output.

## Goals and non-goals

### Goals

- Define the reducer signature `reduce(prevState, event) -> {nextState, provenance}` as a **pure, total, deterministic** function with no IO/clock/RNG and no randomized-map iteration.
- Pin a **canonical value serialization** (deterministic CBOR, RFC 8949 §4.2) and define the concrete types (`CanonicalValue`, `ComponentType`, `EntityState`, `ReducerRegistry`) the contract depends on, so "byte-identical" and content-hashing (`valueHash`/`stateHash`, BLAKE3) are well-defined and testable.
- Define the **component/facet model**: state as a set of independently-addressable typed components, each owned by exactly one reducer, the `attention` facet among them (its fields fixed by the attention spec, produced here).
- Fix the **closed list of core-owned component types** (`ambisphere.attention`, `ambisphere.identity`, `ambisphere.lifecycle`, `ambisphere.approvals`) so core-component creep is bounded by one authoritative enumeration.
- Define the **shared declarative predicate + field-path mini-language** that action preconditions, persona slots/rules, bundle `where` clauses, and renderer hints all reference (one grammar, not four).
- Make **provenance a first-class, required output** of every reduction, modelled on W3C PROV-DM (entity / activity / agent; `wasGeneratedBy` / `wasDerivedFrom` / `wasAttributedTo`).
- Specify the **fact/narration firewall**: a narrated projection that reads facts, is explicitly tagged `narrated`, carries model/prompt provenance, is never a reducer input, and is never written to the log.
- Specify **per-projection checkpoints** (last-applied position) so views are rebuildable and idempotent.
- Specify **snapshot** as a *pure function of a log prefix*, verifiable against replay, never a second source of truth.
- Give concrete schemas/interfaces (fenced) and **acceptance criteria** that make the invariants testable (replay-equality, firewall isolation, snapshot ≡ replay).

### Non-goals (adopt/reject framing — rejections carried from the guidance)

- **Not** the owner of the ingest-atomicity / reduction-failure contract. *When* reduction runs relative to the durable commit, whether the commit is atomic over `event + deltas + provenance + checkpoint`, and what happens when a reducer panics are **owned by the daemon spec**; this spec only states the reducer-side outcome enum and the `degraded` marker so the two agree. (Reject: three specs each describing the pipeline differently — see § "reduction outcomes and the ingest contract".)
- **Not** a general-purpose database or query engine exposed to renderers. The read side gets typed projections, the attention query, and the declarative predicate mini-language; it does not get SQL/Datalog. (Reject: a query engine surface.)
- **Not** a mandate that adopters event-source *their own* systems. Adapters translate native events into the envelope; what happens inside Khaos/GitHub is their business. (Reject: forcing event-sourcing on adopters.)
- **Not** a transactional rollback engine in the actor sense. Correctness comes from pure total reducers + an append-only log + replay, not from compensating transactions. (Reject: actor-style reduction-with-rollback as a paradigm freebie — confirmed not free by `actor-model-prior-art.md`.)
- **Not** runtime AI fact-checking or an LLM-judge in core. Untraceable narration is treated as hallucination structurally (it cannot reach a reducer), not policed at runtime. (Reject: LLM-as-core-dependency.)
- **Not** a new provenance standard. We adopt the W3C PROV triad as vocabulary; we do not serialize full RDF/OWL. (Reject: reinventing provenance; reject full PROV-O/RDF.)
- **Not** a place for vendor concepts. Core ships zero *domain* component names, *domain* event types, or reducer logic; the only component *shapes* core fixes are the closed core-owned list (below), and the only event types core reserves are the ADR-0001 runtime-meta allowlist. Domain reducers are registered per entity-kind by bundles in the examples/adapter layer. (Reject: `khaos.*`/`loswf.*` in core.)
- **Not** the event envelope itself. This spec consumes events and states what a reducer requires of them (the determinism-relevant fields); the envelope spec defines the wire shape, and the daemon spec stamps and commits it.

## Prior art (citations kept visible)

- **Event sourcing / CQRS projections — Kleppmann, *DDIA* ch. 11 (stream–table duality), and the projection/read-model literature (eventsourcing.readthedocs.io, event-driven.io, Azure/AWS event-sourcing guidance).** Adopt: the log is the table of record and component state is a *materialized view*; projections track a **checkpoint** (last-applied offset) and apply events **idempotently** (upsert keyed on offset); read models are **rebuildable** by dropping and replaying. Reject: broker-centric delivery (Kafka/partitions), async cross-process projectors, distributed event-store machinery — the daemon projects synchronously in-process (ADR-0001 local-first).
- **RFC 8949 (Concise Binary Object Representation, CBOR), §4.2 "Deterministically Encoded CBOR".** Adopt: a single canonical byte encoding for component `data` so two folds of the same log produce *byte-identical* values and `valueHash`/`stateHash` are stable. Reject: JSON-as-canonical (no canonical float/key rule), and CBOR's non-deterministic modes.
- **BLAKE3 (cryptographic hash).** Adopt: content hashing of canonical bytes for `valueHash`, `priorValueHash`, `stateHash`, `reducerSetVersion`. (Any fixed, collision-resistant hash would do; BLAKE3 is pinned for cross-spec consistency with the daemon/bundle specs.)
- **W3C PROV-DM (PROV Data Model, W3C Recommendation 2013).** Adopt: the three core types **entity / activity / agent** and the relations **`wasGeneratedBy`** / **`wasDerivedFrom`** / **`wasAttributedTo`**. Mapping below. Reject: full RDF/OWL/PROV-O serialization and the PROV-N notation — we use a compact JSON record. w3.org/TR/prov-dm, w3.org/TR/prov-o.
- **Datomic / XTDB (accumulate-only facts, as-of queries, bitemporal valid-vs-transaction time).** Adopt: the log is *accumulate-only*; point-in-time/**as-of** reads (decay/recency are computed at query time against an explicit `as_of`, never in the reducer); the distinction between **occurred-at** (event/valid time) and **ingest-at** (transaction time, Datomic's `:db/txInstant`). Reject: adopting the products, Datalog as the renderer surface, or full bitemporal storage in v1. docs.datomic.com/transactions/model.html.
- **Redux reducers (the purity discipline).** Adopt: `(prevState, action) -> nextState` purity — no side effects, same input ⇒ same output, never mutate the previous state. Reject: a single global store and the JS-runtime assumptions.
- **LLM attribution / grounding research (e.g. arXiv 2411.01022 on citation-grounded generation).** Adopt the structural stance: **untraceable narration is hallucination**; narration must cite the factual components it summarizes, and the firewall is structural rather than a runtime check. Reject: an LLM-judge fact-checker as a core dependency.
- **RivetKit durable state (`actor-model-prior-art.md`).** Confirms durable per-entity state is production-proven, **and** that transactional rollback / event-sourcing is *not* a free property of the actor model — it must be specced explicitly, which this spec does (pure total reducers + append-only log + replay).

## ADR status

ADR-0001 is itself `Proposed`/`draft` at the time of writing while every follow-on spec, including this one, cites its numbered invariants as binding. This is a known suite-wide inconsistency (it is flagged identically across the nine specs). The resolution is not owned here: ADR-0001 must resolve to a single status and publish the canonical numbered invariant list this spec's conformance table anchors to. Until then, every "ADR-0001 inv. N" reference in this spec is **provisional** and will be re-pinned when the ADR is accepted. Two ADR amendments this spec *depends on* (and which the cross-spec findings require) are called out explicitly:

- **Amendment A (invariant 8 — event types).** Invariant 8 as worded ("core ships zero … event types") is contradicted by required runtime-meta events emitted/handled by *core* reducers (`ambisphere.egress.performed`; `approval.requested|granted|denied|expired`; `entity.registered|renamed|rehomed`, `edge.added|removed`; the `attention.*` / `focus.modeChanged` verbs). The ADR must be amended once to distinguish **domain event types (zero in core)** from a small **enumerated runtime-meta allowlist** core reserves, and list that allowlist. This spec references that allowlist rather than carving its own exception (see conformance table and § attention facet).
- **Amendment B (closed core-component list).** The set of component *shapes* core fixes must be a single closed enumeration declared closed-by-ADR (see § "core-owned component types"). This spec proposes the list; the ADR ratifies it; identity/daemon/persona/bundle specs reference it rather than each introducing core components ad hoc.

## Conformance to ADR-0001

| Invariant | How this spec honors it |
|---|---|
| (1) Log is source of truth; components derived, read-only | Components are produced *only* by `reduce` over the log; there is no direct-write API; every component is rebuildable by replay. |
| (2) Directionality | Reducers run on the read-projection side of the seam; their *only* input is logged fact events (plus the stamped reducer context, § purity rule 7); ECS-shaped query is read-only; capability/actor semantics are not visible here. |
| (3) Determinism | `reduce` is pure/total/deterministic — no clock, RNG, IO; non-determinism is read from event fields stamped at ingestion; values are encoded as **deterministic CBOR** (§ canonical value), never `HashMap`-ordered. Replay is byte-identical (required test). |
| (4) Per-entity total order only | A reducer folds one entity's stream in `sequence` order; it never reads another entity's stream. Cross-entity rollups are a read-side query concern (attention spec), not a reducer input. |
| (5) Capability-shaped authority | Reducers perform no authorization (that is the write boundary). Provenance records a *capability/credential reference* (the agent), never a secret. Read of components is separately gated upstream. |
| (6) Fact/narration firewall | Reducers produce only `kind: "factual"` state; narration is a separate projection, tagged `narrated`, never a reducer input, never logged (§ firewall). |
| (7) Credentials never in state | Provenance carries a `capabilityRef` (opaque handle), never a credential; reducers cannot emit secrets because they never receive them. |
| (8) Vendor neutrality | Core defines the reducer *contract*, the canonical-value rule, and the closed core-component shapes; zero *domain* component names, *domain* event types, or reducer bodies. Core-reserved event types are exactly the **ADR-0001 runtime-meta allowlist** (Amendment A), not an open set. Bundles register per-kind reducers in the examples/adapter layer; core never branches on `payload`/`ext` or `khaos.*`/`loswf.*`. |
| (9) Cross-language seams | The component projection, provenance, and canonical encoding are language-neutral (deterministic CBOR); the reducer registry is a host concept; a bundle could ship reducers in any host-supported form (Rust/host-native in v1; WASM/WIT a future path, open question) without changing the contract. |

## Canonical value, and the concrete types the contract depends on

"Byte-identical replay" and content hashing are meaningless without a pinned encoding. This section fixes it. Everything a reducer puts in `data`, and every value the system hashes, is a **`CanonicalValue`** with one and only one byte representation.

### `CanonicalValue` and its serialization

```rust
/// The only value type a reducer may place in component `data`. It has exactly one
/// byte encoding (deterministic CBOR, RFC 8949 §4.2). Hashing/equality are over those bytes.
pub enum CanonicalValue {
    Null,
    Bool(bool),
    /// Integers are exact, two's-complement, range i128/u128. NO arbitrary-precision bignum in v1.
    Int(i128),
    UInt(u128),
    /// Strings are UTF-8, normalized to Unicode NFC. No lone surrogates. Length-prefixed.
    Text(String),
    /// Opaque byte strings (e.g. embedded hashes). Length-prefixed.
    Bytes(Vec<u8>),
    /// Ordered, deduplicated map. Keys are CanonicalValue; iteration/encoding order is the
    /// RFC 8949 §4.2.1 bytewise lexicographic order of the *encoded keys*. Duplicate keys are illegal.
    Map(CanonicalMap),
    /// Ordered list; element order is significant and preserved.
    Array(Vec<CanonicalValue>),
    /// Decimal with fixed scale, encoded as (mantissa: i128, scale: u8) — i.e. value = mantissa * 10^-scale.
    /// There is NO IEEE-754 float in CanonicalValue (floats have no portable canonical form). A reducer
    /// that needs "0.62" stores Decimal{ mantissa: 62, scale: 2 }. (See attention scalars, below.)
    Decimal { mantissa: i128, scale: u8 },
    /// RFC 3339 timestamp normalized to UTC with fixed precision (nanoseconds, no offset, 'Z').
    /// Stored as Text on the wire but a distinct variant so reducers can't smuggle a non-normalized string.
    Timestamp(NormalizedRfc3339),
}
```

Canonicalization rules (normative — these are what the replay-equality and hash tests assert against):

1. **Encoding = deterministic CBOR (RFC 8949 §4.2).** No JSON on the authoritative path. The illustrative JSONC in this spec is for human reading only; the bytes that are hashed/stored are CBOR.
2. **Map key ordering** = §4.2.1 bytewise lexicographic ordering of the *encoded* keys. Maps are constructed and iterated in that order regardless of host map type. Raw `HashMap` iteration is forbidden in reducers (it silently breaks byte-equality — the `implementation-language-guidance.md` determinism caveat).
3. **No floats.** IEEE-754 has no portable canonical form (NaN payloads, ±0, subnormals). Where the domain needs a fraction, reducers use `Decimal{mantissa,scale}`. Attention's `[0,1]` unit scalars are `Decimal` with a fixed `scale` declared by the attention spec.
4. **Integers** are encoded in the shortest CBOR form (§4.2.1 "preferred serialization"); the in-core representation is exact `i128`/`u128`. No platform-width ints leak into `data`.
5. **Strings** are UTF-8 normalized to **Unicode NFC** before encoding; lone surrogates are rejected. This removes the "same text, different bytes" hash hazard.
6. **Timestamps** are normalized to UTC, `Z`, nanosecond precision before encoding. Reducers *stamp* timestamps from the event (§ purity rule 5); they never invent them.
7. **No tags beyond the above.** The canonical subset is closed; a reducer cannot emit an arbitrary CBOR tag. (Keeps the encoder's deterministic mode small and auditable.)

```rust
/// Content hash of a CanonicalValue = BLAKE3 over its deterministic-CBOR encoding.
/// This is the basis for valueHash / priorValueHash / stateHash and for dedupe.
pub fn value_hash(v: &CanonicalValue) -> Hash { blake3(encode_canonical_cbor(v)) }
```

### The remaining concrete types

```rust
/// Namespaced component identifier. Reverse-DNS-ish; lowercased; validated against the
/// declared-component registry of the active bundle set. Core-owned types are the closed list below.
pub struct ComponentType(pub String);   // e.g. "ambisphere.attention", "example.workflow"

/// One typed component value. `data` is opaque to core (vendor neutrality); core hashes it
/// but never inspects its internals. `kind` is ALWAYS Factual for reducer output.
pub struct Component {
    pub component_type: ComponentType,
    pub schema_version: u32,
    pub data: CanonicalValue,        // deterministic-CBOR canonical; never HashMap-ordered
    pub kind: Kind,                  // == Kind::Factual for all reducer output
    pub status: ComponentStatus,     // Live | Degraded{cause} — see § reduction outcomes
}

pub enum Kind { Factual }            // reducers can construct only Factual; Narrated is a *different* type

pub enum ComponentStatus {
    Live,                            // normal: produced by a successful reduction
    Degraded { cause: String },      // a reducer-bug panic prevented update; value is the last-good value
}                                    // (the daemon sets Degraded; a reducer never returns it — see below)

/// An entity's full state: an ORDERED map component_type -> Component.
/// Ordering is the canonical map order (so hashing EntityState is deterministic).
pub struct EntityState(pub CanonicalMap /* keyed by ComponentType */);

/// Maps event_type -> the reducers that declare handles() true, with a TOTAL deterministic
/// iteration order over ComponentType (never registry hash order). Holds the stamped reducer
/// context (the attentionMap and any declarative reducer-input data) keyed by reducerSetVersion.
pub struct ReducerRegistry { /* component_type -> Box<dyn Reducer>, ordered; + declarative context */ }

pub type Hash = [u8; 32];            // BLAKE3-256
pub struct CapRef(pub String);       // opaque capability handle — NEVER a credential
pub struct Seed(pub u128);           // 128-bit entropy, ALWAYS stamped at ingestion (see ReducibleEvent)
```

## The reducer contract

A reducer is a **pure, total, deterministic** function that folds one event into one component's state and emits provenance for what it produced.

```rust
// Core = Rust per ADR-0001. Language-neutral by intent; this is the normative shape.

/// What a reducer is allowed to read from an event. Determinism-relevant fields ONLY.
/// All non-determinism (time, ids, seeds) is already stamped here at ingestion (envelope spec).
pub struct ReducibleEvent<'a> {
    pub event_id: Ulid,                 // stable id, assigned at ingestion
    pub entity: EntityHandle,           // opaque internal handle (not the address)
    pub sequence: u64,                  // per-entity monotonic order — the determinism key
    pub event_type: &'a str,            // namespaced semantic type (bundle-owned or runtime-meta allowlist)
    pub occurred_at: NormalizedRfc3339, // event/valid time (stamped; never read from a clock here)
    pub ingest_at: NormalizedRfc3339,   // transaction time (stamped at ingestion)
    pub source: &'a str,                // adapter/source id (PROV agent basis)
    pub capability_ref: Option<CapRef>, // who was authorized to emit (provenance only, never a secret)
    pub seed: Seed,                     // 128-bit entropy — ALWAYS present (envelope always-stamps; see note)
    pub payload: &'a CanonicalValue,    // bundle-defined; core never branches on its internals
    pub ctx: &'a ReducerContext,        // stamped declarative reducer-input (e.g. attentionMap); see rule 7
}
```

> **`seed` is non-optional and always stamped (resolved with the envelope spec).** The envelope spec stamps a 128-bit `seed` at ingestion for *every* event (its "always-stamp" lean, adopted here normatively). The wire/on-disk form is a 0x-prefixed lowercase hex string of exactly 32 hex digits (`"0x9f3c…"`, 16 bytes big-endian); the in-core form is `Seed(u128)`. The previous `Option<u128>` is replaced by non-optional `Seed`: a reducer that needs no entropy simply ignores it, but every reducer reads the *identical* seed bytes on replay, removing the optional-vs-always / string-vs-u128 interop defect at this seam.

```rust
pub struct Reduction {
    pub next: Component,        // the new component value (replaces prev for this component_type)
    pub prov: Provenance,      // first-class lineage output (required, see § provenance)
}

/// THE contract. Pure. Total. Deterministic. No IO/clock/RNG. Never mutates `prev`.
pub trait Reducer {
    fn component_type(&self) -> ComponentType;
    fn handles(&self, event_type: &str) -> bool;   // declarative interest (pure)
    fn reduce(&self, prev: Option<&Component>, ev: &ReducibleEvent) -> ReduceOutcome;
}

/// The reducer-side outcome enum. Two outcomes only. There is NO `Rejected`/defect variant:
/// a TOTAL reducer cannot fail on a well-formed event (see § reduction outcomes). The only
/// abnormal path — a reducer-bug PANIC — is caught by the daemon at the host boundary and is
/// NOT a value a reducer returns.
pub enum ReduceOutcome {
    Updated(Reduction),   // produced a new value + provenance
    Unchanged,            // event not relevant to this component; state and prov unchanged
}
```

### Purity and totality rules (normative)

1. **No ambient inputs.** A reducer may read only `prev` and `ev` (where `ev` includes the *stamped* `ev.ctx`, rule 7). No `now()`, `Instant`, `SystemTime`, `rand`, environment, filesystem, network, or global mutable state. Enforced by review + the determinism test; in Rust, reducers run with no capabilities passed in.
2. **Deterministic encoding only.** Every value a reducer constructs in `data` is a `CanonicalValue` and is hashed/stored as deterministic CBOR (§ canonical value). No `HashMap` iteration, no IEEE-754 float, no non-NFC string.
3. **Never mutate `prev`.** `prev` is borrowed read-only; `next` is a fresh value. (Redux discipline.)
4. **Total over well-formed events.** For any event the envelope accepted, `reduce` returns `Updated` or `Unchanged`; it never returns an error and **must not panic** on a structurally valid event. Malformed/unauthorized events are rejected at the write boundary *before* the log append (envelope spec), so they never reach a reducer. A panic is a *bundle bug*, handled by the daemon (§ reduction outcomes), not a contractual outcome.
5. **Order is `sequence`, not time.** A reducer folds events in per-entity `sequence` order. It MAY *read* `occurred_at`/`ingest_at` and stamp them into state/provenance (e.g. `anchorTime`, `lastEventTime`), but it MUST NOT *branch on wall-clock comparisons against "now"* — there is no "now" in a reducer. Recency/decay are query-time concerns (DDIA/Datomic as-of; attention spec § decay).
6. **Single writer per component.** Each `component_type` is produced by exactly one reducer. Two reducers never write the same component; this keeps provenance unambiguous (one activity per value) and the projection composable.
7. **Stamped declarative context is part of `ev`, and is versioned into `reducerSetVersion` (resolves the `attentionMap` purity hazard).** Some *core* reducers (notably the attention reducer) consult **declarative data a bundle ships** — e.g. the `attentionMap` (bundle spec) that maps a domain event into the attention scalars. That data is neither `prev` nor the raw event, so reading it naively would violate rule 1 *and* create a replay hazard: changing a bundle's `attentionMap` would change derived scalars with no logged fact. The contract closes this:
   - The declarative reducer-input data (`attentionMap` and any sibling declarative inputs a core reducer consults) is part of the **`reducerSetVersion`** — the bundle spec's `reducerSetVersion = blake3(sorted over reducer bindings of (componentType, reducerVersion, module-digest **and declarative-input-digest**))`. **This spec requires the declarative-input-digest term**; the bundle spec must include `attentionMap` (and any other declarative reducer-input) in that hash even though it is `.toml` data, not a module. (Cross-spec fix folded in here; the bundle spec's `reducerSetVersion` derivation is amended to add the declarative-input term.)
   - The reducer reads that data only as `ev.ctx` (the **stamped reducer context** for the `reducerSetVersion` in force at the event's ingest), so from the reducer's point of view it *is* `(prev, ev)` and rule 1 holds.
   - Because the data is in `reducerSetVersion`, and the envelope stamps `reducerSetVersion` at ingest, a change to `attentionMap` **bumps `reducerSetVersion`, invalidates snapshots, and forces deterministic re-projection** (§ snapshot, § schema evolution). Replaying an old log under a new `attentionMap` is therefore *not expected* to be byte-identical to the original — it is an intended re-projection under a new (versioned) reducer set, gated by the replay-equality-across-versions rule, not an accidental drift. Replay under the *same* `reducerSetVersion` remains byte-identical.

### Composition: per-entity reduce

The entity's full state is the set of its components. Applying one event runs every interested reducer; each owns its component; the daemon commits the union **atomically with the event append** (the storage-transaction property — *owned by the daemon spec*, not a reducer concern; see § reduction outcomes).

```rust
/// Apply ONE event to ONE entity's state. Pure given (state, event, registry).
/// `registry` maps event_type -> the reducers that declare handles() true, iterated in a
/// total order over ComponentType (never registry hash order; ADR-0001 inv. 3).
/// This is the in-memory pre-commit computation; the daemon decides how/whether to commit it.
pub fn apply_event(
    state: &EntityState,
    ev: &ReducibleEvent,
    registry: &ReducerRegistry,
) -> AppliedEvent {
    let mut next = state.clone();
    let mut provs = Vec::new();
    for reducer in registry.interested_ordered(ev.event_type) {
        match reducer.reduce(state.get(&reducer.component_type()), ev) {
            ReduceOutcome::Updated(r) => { next.insert(r.next.component_type.clone(), r.next); provs.push(r.prov); }
            ReduceOutcome::Unchanged => {}
        }
    }
    AppliedEvent { state: next, provenance: provs, applied_through: ev.sequence }
}

/// Full fold: a projection is a left-fold of apply_event over a log prefix.
/// state(n) = events[0..n].fold(EMPTY, apply_event)   — the table half of stream-table duality.
pub fn project(events: &[ReducibleEvent], registry: &ReducerRegistry) -> EntityState { /* fold */ }
```

The key identity, which the whole rebuild/snapshot story rests on:

> **`state(N) = fold(apply_event, EMPTY, log[0..N])`** — entity state is a pure deterministic function of a log prefix **and the `reducerSetVersion` in force**. Nothing else can produce it.

### Reduction outcomes and the ingest contract (reconciled — daemon-owned)

The earlier draft defined a third reducer outcome, `Rejected(Defect)`, with a "defect provenance" record, for a well-formed-but-semantically-unprojectable event. The daemon spec, which physically implements ingest, instead defines `ReduceOutcome::Ok | Degraded` and handles failure as a *reducer-bug panic* → commit the event alone + mark the component `degraded` + emit `projection.degraded`. Two specs described the same pipeline incompatibly. **Resolution: the daemon spec is the single owner of the ingest-atomicity-and-reduction-failure contract; this spec adopts its model and drops `Rejected(Defect)`/defect-provenance entirely.** The unified, normative model (identical wording must appear in the daemon and envelope specs):

1. **Reduction is pre-commit and atomic.** The daemon runs reducers **in memory against the prior state first**, inside the same logical ingest, and commits **`event + component-deltas + provenance + checkpoint` as ONE storage transaction** (all-or-nothing). There is no observable state in which a committed event lacks its normal reduction. *(Owner: daemon spec. This supersedes the envelope spec's "reduction is downstream of durable commit" wording; the envelope spec is amended to reference this model and keeps only its producer-facing guarantee that `submit` never returns a reduction error.)*
2. **A total reducer cannot "fail" on a well-formed event.** Malformed/unauthorized events never reach a reducer (rejected at the write boundary, envelope spec). A schema-version a reducer predates is handled by **upcasting at read time** (§ schema evolution) — a pure event-shape transform that runs *before* the reducer, so the reducer always sees a shape it can fold. There is therefore **no deterministic "rejected" outcome and no defect-provenance record**; version mismatch is an upcasting concern, not a reducer outcome.
3. **The only abnormal path is a reducer-bug panic.** If a registered reducer panics (a bundle defect), the daemon: (a) catches the panic at the reducer-host boundary; (b) **still commits the event to the log alone** (the fact is real and must not be lost); (c) marks that component's value **`ComponentStatus::Degraded{cause}`**, retaining the last-good value; (d) emits an internal `projection.degraded` diagnostic on the control channel; (e) leaves the event available for re-projection once the bundle is fixed (drop + replay). The log is never blocked by a bad reducer; the *view* degrades, never the *truth*.
4. **`degraded` is defined here as a component-model concept.** `ComponentStatus::Degraded{cause}` is a property of a `Component` (above). A degraded component renders as flagged-stale (its last-good `data` with a degraded marker) — "fail to a flagged-stale value, never corrupt". It is cleared by re-projection. Renderers/persona MUST be able to render a degraded component as stale-but-present (it never silently disappears).
5. **Producer-facing contract is unchanged.** `submit` never returns a reduction error in either path (normal commit, or panic → event-alone + degraded). This is the envelope spec's producer guarantee, preserved.

So there are exactly two durable outcomes per `submit`: **event+reduction committed atomically** (normal), or — only under a reducer bug — **event committed alone, component marked degraded** (truth preserved, view rebuildable). The reducer-side enum is correspondingly `Updated | Unchanged`; `Degraded` is a daemon-set status, never a reducer return value.

## The component / facet model

State is **not** one blob; it is a set of independently-addressable **components** (facets), each a self-contained typed value with its own schema version and its own owning reducer. This is the read-side ECS shape (entities are handles; state is a set of typed components; renderers/the attention bus iterate by component presence) — *query ergonomics only*, never a freely-mutable world (ADR-0001's rejection of the ambient-authority component store).

```jsonc
// EntityState = an ordered map of component_type -> Component (human-readable view; canonical bytes are CBOR).
// Example (illustrative — domain kinds are NOT core; bundles declare them):
{
  "ambisphere.attention": { "schemaVersion": 1, "kind": "factual", "status": "live", "data": { /* attention facet */ } },
  "ambisphere.lifecycle": { "schemaVersion": 1, "kind": "factual", "status": "live", "data": { "phase": "active", "since": "2026-06-10T00:00:00.000000000Z" } },
  "example.workflow":     { "schemaVersion": 2, "kind": "factual", "status": "live",
                            "data": { "phase": "running", "progress": { "mantissa": 62, "scale": 2 }, "blockedReason": null } }
  // a NARRATED projection (e.g. "example.summary") is NOT stored here — see § firewall
}
```

Component design rules:

- **One owner.** Exactly one reducer produces each `component_type` (single-writer). Provenance is therefore unambiguous: each component value points to the one activity that made it.
- **Self-contained.** A component is meaningful without joining others (DDIA document-model locality). Cross-component derivations are *new components* produced by their own reducer reading the events, **not** a reducer reading another reducer's output (reducers read events, not each other's state — that would make ordering and provenance ambiguous).
- **Schema-versioned per component.** `schemaVersion` is per component, so one facet can evolve without re-versioning all (§ schema evolution).
- **`kind` is always `factual` for reducer output.** A narrated value is never a stored component; it is a separate projection produced outside any reducer (§ firewall).
- **Core ships zero *domain* component types.** The only component *shapes* core fixes are the closed core-owned list below.

### Core-owned component types (closed list — Amendment B)

To stop core-component creep while every spec claims minimalism, the set of component *shapes* core owns is a **single closed enumeration**, declared closed-by-ADR (Amendment B). No spec may introduce a `ambisphere.*` component outside this list without an ADR change. Identity, daemon, persona, and bundle specs reference this list rather than each defining core components ad hoc.

| Core component type | Shape owned by | Produced by | Notes |
|---|---|---|---|
| `ambisphere.attention` | attention-routing spec | core attention reducer (this spec) | unit-scalars + enums; firewall-clean; stamps temporal anchors, never computes decay |
| `ambisphere.identity` | entity-identity spec | core identity reducer | display name / address / kind metadata; folded from the `entity.*` runtime-meta events |
| `ambisphere.lifecycle` | this spec (minimal) | core lifecycle reducer | coarse `{phase, since}`; folded from lifecycle runtime-meta events |
| `ambisphere.approvals` | action/capability spec | core approvals reducer | folded from the `approval.*` runtime-meta events |

The reducers for these are provided by the **`ambisphere.core` base bundle** (bundle spec) — they are core *code*, domain-neutral, and branch on no `khaos.*`/`loswf.*`. All other components (`example.workflow`, etc.) are bundle-declared and bundle-reduced. (The list is closed; widening it is an ADR decision, not a per-spec one.)

### The `attention` facet (produced here; shape owned by the attention spec)

The attention spec fixes the `attention` component v1 fields and declares them **canonical and not redefinable**. This spec is where that component is **produced** — by a core, domain-neutral reducer over the attention verbs the attention spec defines (`attention.snoozed`, `attention.deferred`, `attention.acknowledged`, `attention.resolved`, `focus.modeChanged` — all on the runtime-meta allowlist, Amendment A) plus whatever domain events a bundle maps into the scoring scalars via its `attentionMap`. The reducer obeys the firewall (`kind` always `factual`), the determinism rule (it **stamps** `anchorTime`/`lastEventTime` from the event; it **never** computes decay — query-time, attention spec § decay), the canonical-value rule (unit scalars are `Decimal{mantissa,scale}`, never floats), and purity rule 7 (it reads the bundle's `attentionMap` only via the stamped `ev.ctx`).

```rust
/// Core-provided (ambisphere.core bundle), domain-neutral. Produces the attention facet whose
/// fields are FIXED by spec-attention-routing.md. This spec does NOT redefine those fields; it
/// guarantees they are produced by a pure reducer and that the attentionMap is read deterministically.
struct AttentionReducer;
impl Reducer for AttentionReducer {
    fn component_type(&self) -> ComponentType { ComponentType("ambisphere.attention".into()) }
    fn handles(&self, t: &str) -> bool {
        matches!(t, "attention.snoozed" | "attention.deferred" | "attention.acknowledged"
                  | "attention.resolved" | "focus.modeChanged")
        // plus bundle domain events the attentionMap (read via ev.ctx) routes into the scalars
    }
    fn reduce(&self, prev: Option<&Component>, ev: &ReducibleEvent) -> ReduceOutcome {
        // 1. fold the verb (or the attentionMap entry matching ev.event_type from ev.ctx) into scalars (pure)
        // 2. STAMP decay.anchorTime / provenance.lastEventTime from ev.occurred_at (clock-free)
        // 3. unit scalars are Decimal{mantissa,scale}; kind = Factual ALWAYS
        // ...returns Updated(Reduction{ next, prov }) or Unchanged
        unimplemented!()
    }
}
```

How a bundle maps a domain event into the attention scalars (e.g. LOSWF `ci.failed` → high `urgency`+`importance`+`actionability`) is **declarative `attentionMap` data** the bundle ships (bundle spec), read by the core reducer via the stamped `ev.ctx` and versioned into `reducerSetVersion` (purity rule 7) — never core branching on `loswf.*` (ADR-0001 inv. 8; attention spec § write-side commands).

## The declarative predicate + field-path mini-language

Several specs need to express "a predicate over component state" and "a reference to a declared factual field": action preconditions (`{component, path, op, value}`), persona slots/rules (`{ref: "workflow.phase"}`, `where = "phase == 'blocked'"`), bundle `where` clauses (`"phase == 'blocked'"`), brace interpolation (`"{loswf.workflow.blockedReason}"`), and renderer hints. As written across the suite these are **three mutually-incompatible grammars** for one conceptual operation. This spec is the **single owner of one canonical mini-language**; the action, persona, bundle, and renderer specs reference it instead of each inventing syntax.

### Field paths

A **field path** addresses a value inside the factual projection:

```
field-path := component-type "." segment ("." segment)*
component-type := <a declared ComponentType, e.g. "ambisphere.attention" | "example.workflow">
segment := identifier | index            // identifier = map key (NFC); index = non-negative integer for Array
```

- Resolution is over `EntityState` (factual only; never narration, never an event, never a capability).
- A path resolving to a missing key/index is `Null` (not an error) — predicates treat `Null` per the op table below.
- Component types are **dotted but unambiguous**: the resolver splits on the *first* run that matches a declared `ComponentType`, then treats the remainder as `segment`s (so `loswf.workflow.blockedReason` = component `loswf.workflow`, path `blockedReason`).

### Predicates

A **predicate** is a structured object (canonical form) with an optional string sugar:

```jsonc
// canonical structured form (what action manifests use directly):
{ "path": "example.workflow.phase", "op": "eq", "value": "blocked" }

// string sugar (what bundle/persona `where` clauses use) — parses to the structured form:
"example.workflow.phase == 'blocked'"
"ambisphere.attention.urgency >= 0.8"      // 0.8 parses to Decimal{mantissa:8,scale:1}
```

```
predicate := { path, op, value? } | conjunction | disjunction | negation
conjunction := { "all": [predicate, ...] }
disjunction := { "any": [predicate, ...] }
negation    := { "not": predicate }
```

Op set (closed in v1):

| `op` | meaning | value typing |
|---|---|---|
| `eq` / `ne` | canonical-value equality / inequality | any `CanonicalValue` (compared by canonical bytes) |
| `lt` / `le` / `gt` / `ge` | ordered comparison | `Int`/`UInt`/`Decimal`/`Timestamp` only; type-mismatch ⇒ predicate is `false` (not an error) |
| `exists` / `absent` | path resolves non-`Null` / `Null` | no `value` |
| `in` | membership in a value `Array` | `value` is an `Array` |
| `prefix` | `Text` starts-with | `value` is `Text` |

Value typing: literals are parsed to `CanonicalValue` (numbers with a decimal point → `Decimal`; quoted → `Text` NFC; `true`/`false`/`null` → `Bool`/`Null`). `eq` is **canonical-byte equality**, so `0.80` and `0.8` compare equal only after normalization to the same `Decimal{mantissa,scale}` — the predicate parser normalizes both sides.

### Slot / brace resolution

A **slot** is how persona/renderer templates pull a factual value into presentational text:

```jsonc
{ "ref": "example.workflow.blockedReason" }   // resolves the field-path to a CanonicalValue, rendered as text
{ "text": "Blocked — needs a look" }          // static authoring-time literal (no field access)
```

Brace interpolation (`"{loswf.workflow.blockedReason}"`) is sugar for a `{ref}` over a field path and resolves identically. **A slot may reference only a declared *factual* field** (firewall, § narration). There is no slot type that carries model output; narration is reached only via `narration.ref` into the separate store (persona spec).

This mini-language is **read-side and declarative only**. It never writes, never reaches a reducer's logic (predicates are evaluated by the read plane / action precondition checker, not inside `reduce`), and references only declared factual fields — so it cannot become a firewall hole. The action precondition evaluator, persona slot/rule resolver, bundle `where` parser, and renderer-hint field references all use this one grammar. (Cross-spec fix folded in here; those specs reference this section.)

## Provenance — lineage as a first-class output

Every `Updated` reduction emits a **provenance record** alongside the value. Provenance is not an afterthought log line; it is a co-equal output of `reduce` and is what lets the system answer "**why is this entity blocked / why is this value what it is?**" by walking back through the events and reductions that produced it. Modelled on W3C PROV-DM, compacted to JSON (we adopt the triad and relations; we reject RDF/OWL serialization).

```jsonc
// Provenance v1 — emitted with every Updated reduction. W3C PROV-DM mapping in comments.
{
  "schemaVersion": 1,

  // --- the activity: this reduction (PROV: Activity) ---
  "activity": "reduce",
  "reducer": { "componentType": "example.workflow", "reducerVersion": 3 },
  "outcome": "updated",            // updated (the only provenance outcome — there is no "rejected")

  // --- the generated entity: the component value produced (PROV: wasGeneratedBy) ---
  "generated": {
    "componentType": "example.workflow",
    "schemaVersion": 2,
    "valueHash": "blake3:..."      // BLAKE3 over deterministic-CBOR of the produced `data` (verify + dedupe)
  },

  // --- derivation: the inputs this value came from (PROV: wasDerivedFrom) ---
  "wasDerivedFrom": {
    "event": { "eventId": "ulid", "sequence": 4217, "eventType": "ci.failed",
               "occurredAt": "2026-06-10T...Z", "ingestAt": "2026-06-10T...Z" },   // valid vs txn time
    "priorValueHash": "blake3:... | null",   // the component value before this reduction
    "reducerSetVersion": "rsv:..."           // the reducer set (incl. attentionMap digest) in force
  },

  // --- attribution: the responsible agent (PROV: wasAttributedTo) ---
  "wasAttributedTo": {
    "source": "adapter.loswf.github",   // the adapter/source that emitted the event (PROV: SoftwareAgent)
    "capabilityRef": "capref:opaque"    // the authority under which it was emitted — NEVER a credential
  },

  // --- the firewall tag: reducer output is ALWAYS factual ---
  "kind": "factual"
}
```

PROV-DM mapping, kept explicit:

| PROV-DM concept | Ambisphere binding |
|---|---|
| `Entity` | a component value (`generated`); and the prior value / input event (`wasDerivedFrom`) |
| `Activity` | the reduction (`activity: "reduce"`, with `reducerVersion` + `reducerSetVersion`) |
| `Agent` (`SoftwareAgent`) | the source adapter + the `capabilityRef` it acted under (`wasAttributedTo`) |
| `wasGeneratedBy` | component value ← reduction (`generated` ← `activity`) |
| `wasDerivedFrom` | component value ← input event + prior value + reducer set |
| `wasAttributedTo` | component value ← source/capability |

Provenance design decisions:

- **Granularity = per component value per reduction (resolved).** Decided: **per-component-value-per-reduction** is the v1 minimum — coarse enough to be cheap, fine enough to answer "why is *this facet* what it is?" by walking `wasDerivedFrom.event` chains. Per-field provenance is deferred (open question); a reducer MAY add an optional `fields: { field: priorEventId }` map when a single value fuses several events, but it is not required.
- **Lineage is walkable.** `generated.valueHash` + `wasDerivedFrom.priorValueHash` chain successive values; `wasDerivedFrom.event.sequence` indexes into the log; `wasDerivedFrom.reducerSetVersion` records the reducer set (so a value derived under an old `attentionMap` is auditable). "Why is this blocked?" = walk the provenance chain back to the `*.blocked`-shaped event(s) (which event types those are is bundle-defined; core does not know "blocked").
- **No secrets, ever.** `capabilityRef` is an opaque handle (ADR-0001 inv. 7). A reducer cannot leak a credential because it never receives one.
- **Two times, carried not invented.** `occurredAt` (valid time) and `ingestAt` (transaction time) come from the event (Datomic's `:db/txInstant`-vs-event-time distinction). v1 stores both but does **not** offer full bitemporal valid-time *correction*; reducers key determinism on `sequence`. Full bitemporal as-of is an open question.
- **Provenance is itself derived/rebuildable.** It is a function of the same fold; replaying the log under the same `reducerSetVersion` re-derives identical provenance (provenance records are part of the replay-equality test).
- **There is no "defect"/"rejected" provenance.** The earlier draft's defect-provenance record is removed (§ reduction outcomes); a reducer-bug panic is signalled by `ComponentStatus::Degraded` + the daemon's `projection.degraded` diagnostic, not a provenance record. Provenance records exist only for `Updated` reductions.

### Where provenance is stored

Provenance is a derived index alongside the component projection, keyed by `(entity, componentType, sequence)`. It is **not** on the log (the log holds facts/events, not reductions) and **not** authoritative (it is rebuildable). The daemon spec owns its physical storage (a `provenance` projection table behind the StorageDriver) and commits it atomically with the event + component deltas + checkpoint (§ reduction outcomes). Like all projections it has a checkpoint and is dropped/rebuilt with the components it explains.

## The fact / narration firewall

The single most important structural boundary in this spec (ADR-0001 inv. 6; guidance top-risk "fact/narration firewall erosion"). Stated as an absolute:

> **Reducers produce only factual state. AI narration is a separate, explicitly-tagged, non-authoritative projection that *reads* facts. It is never an input to any reducer and is never written to the event log.**

The firewall is **structural, not procedural** — narration cannot enter a reducer because of the type system, not because a guideline says so:

1. **Type-level isolation.** `Reducer::reduce` takes a `ReducibleEvent` whose only payload source is the log (+ stamped `ctx`). There is no `narration` field on `ReducibleEvent`, no constructor that produces one from model output, and `Component.kind` produced by a reducer is statically `Kind::Factual` (the enum has no other variant). A narrated value is a *different type* (`NarratedProjection`, below) that is never accepted by `apply_event`.
2. **Narration reads, never writes, the log.** A narrator consumes the *factual projection* (components + provenance) as input and produces a separate output. It has no write capability to the log (POLA; only ingestion-side capability-gated `submit(event)` writes, and narration is not an event).
3. **Narration is separately stored and tagged.** Narrated projections live in their own store, never in `EntityState`, always carrying `kind: "narrated"` and their own provenance (model, prompt template, the factual component versions cited).
4. **Only egress adapters may emit narration.** Narration is produced at the egress boundary (an AI-egress adapter), tagged, and may be rendered by surfaces that opt in — but a surface MUST be able to render **factual-only** (ignore the narrated projection entirely), and MUST render `degraded` factual components as flagged-stale (§ reduction outcomes).
5. **Narration cites only declared factual fields.** A narrated value records which factual component values it summarized (`grounds`), so an untraceable narration is detectable as hallucination (arXiv 2411.01022 stance). Template slots reference declared factual fields via the slot grammar (§ mini-language); this is enforced at bundle-authoring/egress (bundle spec L4), not at runtime in core.

```jsonc
// NarratedProjection — produced OUTSIDE any reducer, by an egress adapter. NEVER on the log,
// NEVER in EntityState, NEVER an input to reduce(). Always kind:"narrated".
{
  "schemaVersion": 1,
  "entity": "entityHandle",
  "kind": "narrated",                 // the firewall tag — never "factual"
  "text": "CI failed on the release branch; one review is blocked awaiting approval.",
  "grounds": [                        // which FACTUAL component values this narration cites (field-path grammar)
    { "componentType": "example.workflow", "valueHash": "blake3:...", "sequence": 4217 },
    { "componentType": "ambisphere.attention", "valueHash": "blake3:...", "sequence": 4219 }
  ],
  "narrationProvenance": {            // distinct from factual provenance
    "model": "modelRef:opaque",       // a reference, never a credential
    "promptTemplate": "tmpl:workflow-summary@2",
    "producedAt": "2026-06-10T...Z",  // egress wall-clock is FINE here — narration is not deterministic
    "egressAdapter": "adapter.ai.summary"
  }
}
```

Why narration may read the clock and need not be deterministic, while reducers may not: narration is **non-authoritative and non-replayed**. It is not part of `state(N) = fold(...)`; dropping every narrated projection changes no factual state and breaks no rebuild. Determinism is required precisely and only of the things on the authoritative path (reducers, components, provenance). This is the clean line the firewall draws.

## Checkpoints, rebuildability, and snapshots

### Per-projection checkpoint

Each projection (the component store, and the provenance index) tracks a **checkpoint**: the last `sequence` applied per entity (and a global watermark for crash recovery). Checkpoints make application **idempotent** and **resumable** (DDIA/event-sourcing read-model discipline), and are committed atomically with the event + deltas + provenance (§ reduction outcomes; daemon spec).

```jsonc
// Checkpoint — per (projection, entity). Lets apply be idempotent and resumable.
{
  "projection": "components",          // or "provenance"
  "entity": "entityHandle",
  "appliedThrough": 4219,              // last sequence folded into this projection for this entity
  "stateHash": "blake3:...",          // BLAKE3 over deterministic-CBOR of the resulting EntityState
  "reducerSetVersion": "rsv:...",     // the reducer set this checkpoint was produced under
  "updatedIngestAt": "2026-06-10T...Z"
}
```

- **Idempotent apply.** An event with `sequence <= appliedThrough` is a no-op (replay-safe; at-least-once ingestion + dedupe ⇒ effective exactly-once apply, per envelope guidance).
- **Resumable rebuild.** On restart, a projection resumes from `appliedThrough`; the daemon two-layer recovery (WAL replay + application rebuild from the checkpoint watermark) is owned by the daemon spec and relies on these checkpoints + deterministic reducers.

### Rebuildability (the guarantee that justifies the design)

Any projection is **droppable and rebuildable** purely from the log (under a known `reducerSetVersion`):

```
rebuild(projection, reducerSetVersion):
  drop(projection)                                  # components/provenance are derived; safe to delete
  for entity in entities:                           # per-entity total order (ADR-0001 inv. 4)
    state := EMPTY
    for ev in log[entity] in sequence order:
      ev := upcast_for(reducerSetVersion, ev)       # pure event-shape upcast at read (§ schema evolution)
      state := apply_event(state, ev, registry)     # pure fold
    write(projection, entity, state,
          checkpoint{ appliedThrough: last_sequence, stateHash: hash(state), reducerSetVersion })
```

Because `apply_event` is pure and reducers are deterministic, `rebuild` is a function of the log + `reducerSetVersion` alone. This is the property that makes schema evolution survivable (ship a new reducer set, re-project) and makes the audit story true (the projection is never authoritative; the log is).

### Snapshot — a pure function of a log prefix

A snapshot is a **cached fold result at a known offset**, taken solely to bound replay cost. It is *not* a second source of truth and *must* be verifiable against replay (guidance top-risk "snapshot drift").

```jsonc
// Snapshot — cached EntityState at a log prefix. PURE function of (log[entity][0..throughSequence], reducerSetVersion).
{
  "schemaVersion": 1,
  "entity": "entityHandle",
  "throughSequence": 4219,            // the log prefix this snapshot folds exactly
  "reducerSetVersion": "rsv:...",     // the reducer set used (incl. attentionMap digest — purity rule 7)
  "state": { /* EntityState */ },
  "stateHash": "blake3:...",          // MUST equal hash(fold(log[entity][0..throughSequence]) under this rsv)
  "takenIngestAt": "2026-06-10T...Z"
}
```

Normative snapshot rules:

1. **Snapshot ≡ replay.** For any snapshot, `stateHash == hash(project(log[entity][0..throughSequence]))` *under the snapshot's `reducerSetVersion`*. A **snapshot-equality test** asserts this; a failing equality is a correctness defect, not a tolerated drift.
2. **Snapshots are disposable.** Deleting all snapshots changes nothing but replay cost. They are never the input to anything authoritative; rebuild ignores them or uses them only as a verified fast-forward.
3. **Reducer-set-versioned.** A snapshot records `reducerSetVersion`. If the reducer set changed (new reducer version, schema evolution, **or an `attentionMap`/declarative-input change** — purity rule 7), the snapshot is **invalid for the new set** and is discarded — you re-project from the log (or from an older snapshot taken with a compatible set). This prevents a stale snapshot from masking a reducer-set change.
4. **Fast-forward, not bypass.** Loading a snapshot then applying `log[entity][throughSequence+1..]` MUST equal a full replay (`snapshot ⊕ tail ≡ replay`) under the same `reducerSetVersion` — covered by the equality test. The snapshot only skips already-folded prefix work.
5. **Cadence is a daemon concern.** *When* to snapshot and log compaction/retention behind snapshots are owned by the daemon spec; this spec only fixes that whatever it does, the snapshot remains a pure verifiable function of (log prefix, `reducerSetVersion`).

## Schema and reducer evolution

Long-lived logs outlive reducer code (DDIA "data outlives code"; guidance top-risk "schema/reducer evolution debt"). The strategy:

- **Reducers are versioned** (`reducerVersion`, recorded in provenance and folded into `reducerSetVersion`). Changing reducer logic bumps the version.
- **Components are per-facet schema-versioned** (`schemaVersion`), so one facet evolves without touching others.
- **Declarative reducer-input data is versioned too.** `attentionMap` and any sibling declarative reducer input are part of `reducerSetVersion` (purity rule 7). Changing them is a reducer-set change with the same re-projection consequences as changing reducer code.
- **Upcasting at replay, not migration of the log.** The log is immutable (accumulate-only). Old events are read by new reducers; where an old event shape is no longer directly reducible, an **upcaster** (a pure event-shape transform registered by the bundle) maps `eventType@vN -> eventType@vN+1` *at read time*, before the reducer sees it. The log is never rewritten. **This is also where a "reducer predates this schema version" situation is handled** — by upcasting, not by a reducer rejection (§ reduction outcomes). (Event-sourcing upcasting pattern; chosen over log-rewrite to preserve the immutable-fact guarantee.)
- **Re-projection on reducer-set change.** Bumping `reducerSetVersion` ⇒ snapshots for the old set are invalidated (snapshot rule 3) and the projection is rebuilt from the log (optionally from an older compatible snapshot). Because rebuild is pure, this is safe and verifiable.
- **Replay-equality across versions is the gate.** A reducer-set change ships only if, for the corpus of recorded test logs, the new set's output is either intended-different (a recorded migration) or byte-identical — never accidentally different. (Replay-equality property test, ADR-0001 inv. 3.)

Bitemporal scope for v1 (resolved narrowly): the system records both `occurredAt` and `ingestAt` and supports **as-of-transaction-time** reads via snapshots/replay at a `sequence`. Full **valid-time correction** (re-asserting that a past fact was different than recorded) is **out of scope for v1** (open question); corrections in v1 are *new appended events*, not edits to the past (accumulate-only, Datomic-style).

## Acceptance criteria

1. **Reducer purity.** `reduce` is pure/total/deterministic: a harness runs each registered reducer with no clock/RNG/IO available and asserts identical output for identical `(prev, ev)` (where `ev` includes the stamped `ev.ctx`); a lint/review gate forbids `now()`/`rand`/`HashMap`-iteration/IEEE-float inside reducers.
2. **Canonical encoding is fixed and byte-stable.** Encoding any `CanonicalValue` twice yields identical bytes; map key order, NFC string normalization, `Decimal` (no float), shortest-int form, and UTC-nanosecond timestamps are all asserted by golden vectors. `value_hash`/`stateHash` are stable across runs and platforms.
3. **Replay-equality (byte-identical) under a fixed reducerSetVersion.** Folding a recorded log twice under the same `reducerSetVersion` produces byte-identical `EntityState` *and* byte-identical provenance (`stateHash` and `valueHash`es match). Covers the attention facet's `anchorTime`/`lastEventTime` stamping and its `attentionMap`-driven scalars.
4. **reducerSetVersion captures declarative input.** Changing a bundle's `attentionMap` changes `reducerSetVersion` (the declarative-input-digest term, purity rule 7); a replay under the new version re-projects deterministically and discards old-version snapshots; a replay under the *same* version is byte-identical. (Joint with the bundle spec's `reducerSetVersion` derivation.)
5. **Single-writer.** No two registered reducers declare the same `component_type`; each component value's provenance points to exactly one activity.
6. **Components read-only / derived.** There is no API that writes a component except the reducer-over-log path; an `EntityState` is reproducible solely by `project(log)` under its `reducerSetVersion` (ADR-0001 inv. 1).
7. **Provenance present and walkable.** Every `Updated` reduction emits a provenance record with `wasGeneratedBy`/`wasDerivedFrom`/`wasAttributedTo` (incl. `reducerSetVersion`); a chain walks back to the originating event(s) and no `capabilityRef` resolves to a credential.
8. **Reduction outcomes match the daemon contract.** The reducer enum is exactly `Updated | Unchanged`; there is no `Rejected`/defect path; a well-formed event never panics; a deliberately-panicking test reducer causes the daemon to commit the event alone and set `ComponentStatus::Degraded` + `projection.degraded`, and re-projection clears it. (Cross-checked against the daemon spec's reducer-bug-isolation criterion.)
9. **Firewall (structural).** (a) `ReducibleEvent` has no narration field and cannot be constructed from model output; (b) a reducer cannot produce `kind: "narrated"` (the enum has no such variant); (c) a `NarratedProjection` is never present in `EntityState` and never on the log; (d) the system renders correctly with all narrated projections deleted, and renders `degraded` components as flagged-stale.
10. **Checkpoint idempotence.** Re-applying an event with `sequence <= appliedThrough` is a no-op; resuming from a checkpoint yields the same `stateHash` as a full replay under the same `reducerSetVersion`.
11. **Snapshot ≡ replay.** For every snapshot, `stateHash == hash(project(log[0..throughSequence]))` under the snapshot's `reducerSetVersion`, and `snapshot ⊕ tail ≡ full replay`. A snapshot taken under a now-changed `reducerSetVersion` is discarded, not used.
12. **Rebuildability.** Dropping the component and provenance projections and rebuilding from the log reproduces byte-identical state, provenance, and `stateHash`es under the same `reducerSetVersion`.
13. **Core-component closed list.** Core contains exactly the four core-owned component shapes (`attention`, `identity`, `lifecycle`, `approvals`) and zero domain reducer bodies; a lint gate asserts no `ambisphere.*` component outside the list and no `khaos.*`/`loswf.*` reference or `payload`/`ext` branch in core; an `examples/` bundle demonstrates a domain reducer + `attentionMap`.
14. **Predicate mini-language is shared.** Action preconditions, persona slots/rules, bundle `where`, and renderer-hint field references all parse to the one grammar (§ mini-language); a conformance test feeds the same predicate string/struct through each consumer and asserts identical resolution against a fixed `EntityState`.
15. **Attention facet conformance.** The core attention reducer produces exactly the `attention` v1 fields fixed by the attention spec, with `kind == "factual"`, scalars as `Decimal` (no float), stamping (not computing) temporal anchors, reading `attentionMap` only via `ev.ctx`; no field is redefined here.

## Open questions

- **Per-field provenance.** v1 fixes provenance at per-component-value granularity, with an optional `fields` map. Whether "why is this blocked?" needs per-field lineage for fused values — and the storage cost — is open; the optional map is the hedge.
- **Full bitemporal valid-time correction.** v1 records both times but supports only as-of-transaction-time reads; corrections are new appended events. Whether adopters need true valid-time re-assertion and a bitemporal index is open (Datomic/XTDB-style), deferred for cost.
- **Cross-entity rollup determinism — boundary with the attention spec.** The attention spec computes parent rollups at query time over the always-resident summary index (deterministic given `as_of`). Whether any *factual* (non-attention) cross-entity rollup component should exist — and if so, whether it is a reducer over a merged stream (needs a defined merge order, which per-entity-total-order does not give) or strictly a read-side query — is unresolved. Leaning: no reducer reads across entities; cross-entity facts are read-side query results, not stored components.
- **Reducer registration form across languages.** Core is Rust; reducers are registered per kind by bundles. Whether bundles may ship reducers in a non-Rust/sandboxed form (WASM component, per adapter-API guidance's future WIT path) or must be Rust/host-native in v1 is open; the *contract* (pure, total, `reduce`) is language-neutral regardless.
- **Snapshot cadence and compaction interplay.** Resolved that snapshots are pure/verifiable; *when* to take them and whether the log may be compacted behind a verified snapshot (preserving minimum lineage for the audit story) is co-owned with the daemon spec and not fixed here.
- **`actionability` source (carried from the attention spec).** The attention facet's `actionability` is reducer-set in v1; once the action/capability spec lands it could be *computed* from "are there capability-authorized actions whose preconditions hold?" (expressible in the predicate mini-language) — cleaner but couples the read projection to the action manifest. Open, jointly with the action spec.
- **`degraded` operator surfacing.** A reducer-bug panic marks a component `degraded` and emits `projection.degraded` (daemon spec). How that is surfaced to operators (an attention signal? a health endpoint?) and whether a degraded component should ever block a *bundle upgrade* gate is co-owned with the daemon/bundle specs and unspecified here.
- **ADR-0001 amendments this spec depends on.** Amendment A (runtime-meta event-type allowlist) and Amendment B (closed core-component list) are *proposed* here but must be ratified in ADR-0001; until then both are provisional (§ ADR status). The exact membership of the runtime-meta allowlist (does it include `ambisphere.egress.performed` and `focus.modeChanged` verbatim?) is owned by the ADR, cross-referenced from privacy/action/identity/attention specs.
- **Decimal scale policy.** v1 forbids IEEE floats and uses `Decimal{mantissa,scale}`. Whether a global default scale (e.g. unit scalars at `scale=4`) should be pinned, or each component declares its scale in its `schemaVersion`, is open — leaning per-component-declared, with the attention spec pinning the attention scalars' scale.
