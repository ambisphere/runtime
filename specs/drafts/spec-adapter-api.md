# Adapter and plugin API

**Status:** draft · **Scope:** the adapter layer as an anti-corruption layer (ACL) between external vendor systems and the runtime — the one narrow stable inbound port (`submit` envelopes; optionally `subscribe` to projection state), source-offset idempotency, the capability/credential boundary an adapter presents, the fact-vs-narration discriminator, the opaque namespaced payload the core never branches on, the SemVer + negotiated version handshake that freezes the public contract, a Rust reference adapter SDK over a language-neutral wire spec, and WASM/WIT named as a future untrusted-adapter path only · **Companion to:** `specs/VISION.md`, `specs/SRS.md`, `RFP.md` (§ "Multi-application integration", issue #5 §§ 3, 6, 10, 11) · **Sequenced:** tenth among the follow-on specs (derived from two concrete adapters, not in the abstract — per the guidance) · **Conforms to:** ADR-0001 (foundational paradigm + directionality invariant); the semantic-event-envelope spec (this spec's adapters *produce* the envelope and consume `SubmitAck`); the daemon-architecture spec (`submit`/`subscribe` planes, capability gating, framing, and the shared § terminology definition of "broker" = the thin local IPC seam only — no message-broker machinery); the envelope spec's closed core-reserved `ambisphere.*` type allowlist (this spec's vendor-neutrality lint references that single allowlist, not a re-derived "zero types" rule, and the daemon — not the adapter — stamps the provenance `capabilityRef`); the entity-identity spec (`EntityAddress` compound-segment list); the reducer/state-component and attention-routing specs (the `attention` scalars adapters map domain severity into); the action/capability spec and the privacy/credential spec (the capability + credential boundary an adapter rides on) · **Sibling notes:** `specs/drafts/runtime-paradigm-and-specs-guidance.md`, `specs/drafts/actor-model-prior-art.md`, `specs/drafts/persona-prior-art.md`, `specs/drafts/implementation-language-guidance.md`

This spec defines how an **external vendor system becomes a source of facts** for the runtime without the runtime ever learning the vendor's vocabulary. An adapter is an **anti-corruption layer** (DDD; Microsoft / AWS prescriptive guidance, cited below): a defensive translator that lives in an *external* bounded context, reads native vendor events, and emits the semantic event envelope addressed to an entity. Translation is **one-directional into the runtime**: vendor → envelope. The runtime never speaks vendor; the adapter never writes runtime components, never asserts ordering or time, and never sees another adapter's facts unless separately read-authorized.

The adapter API is therefore not a new data model — it is a **thin contract over the envelope** plus the discipline that keeps vendor concepts out of core. Everything load-bearing already exists in upstream specs; this spec composes them into the one stable, versioned port a third party can build against without forking the runtime, and records the rules (idempotency, payload opacity, the narration firewall, the credential boundary) that make that port safe.

## Goals and non-goals

### Goals

- Define the adapter as an **anti-corruption layer**: vendor systems are external bounded contexts; adapters translate native events into the envelope and **never the reverse**.
- Specify **one narrow stable inbound port**: an adapter `submit`s `ProposedEvent`s (the envelope spec's only write path) and **optionally** `subscribe`s to outbound projection state (the daemon read plane), and does nothing else.
- Specify **source-offset idempotency**: an adapter carries the vendor's native offset/cursor so re-delivery and reconnect-with-backfill are safe, mapping onto the envelope's `dedupeKey` to yield effective exactly-once apply.
- Make the **fact-vs-narration discriminator** explicit at the adapter boundary: ordinary adapters emit only **facts**; only a declared **egress/narration adapter** may write narration, and only through the narration store, never the log (ADR-0001 inv. 6).
- Keep the **payload opaque and namespaced**: vendor fields ride in `data` under a bundle-owned `dataschema`; core never branches on payload internals, ships zero *domain* `type`s, and permits only the envelope spec's closed core-reserved `ambisphere.*` allowlist as core `type` literals (ADR-0001 inv. 8; envelope spec core-reserved allowlist).
- Specify the **capability + credential boundary** an adapter presents: the adapter holds the secret; only an opaque `capabilityRef` travels; credentials never enter state, components, or the log (ADR-0001 inv. 7).
- Define a **SemVer + negotiated version handshake** so the envelope/port is a frozen public contract with explicit forward/backward-compatibility rules.
- Define a **Rust reference adapter SDK** *and* a **language-neutral wire spec** so no adapter is forced to depend on the SDK (polyglot adapters — implementation-language guidance).
- Name **WASM Component Model / WIT** as the **future path for untrusted third-party adapters** only — not adopted in v1.
- Give concrete schemas/interfaces (fenced) and **acceptance criteria** making the ACL invariants testable.

### Non-goals (adopt/reject framing — rejections carried from the guidance)

- **Not** a vendor SDK in core, and **not** Khaos/LOSWF code anywhere in core. Vendor adapters live under `examples/adapters/`. (Reject: a vendor dependency in the runtime.)
- **Not** a second event or data model. The adapter API *is* the envelope plus rules; it introduces no parallel schema. (Reject: an adapter-specific event type.)
- **Not** a network authorization protocol. Capabilities are internal local-first authority; an adapter that talks to a remote vendor authenticates to that vendor with the vendor's own credentials, held by the adapter. (Reject: a cross-org auth handshake in core.)
- **Not** a mandatory plugin sandbox / WASM runtime in v1. v1 adapters are trusted out-of-process producers. (Reject: requiring a sandbox now; WASM is future-only.)
- **Not** a remote/cloud sync layer or a centralized credential store. (Reject: cloud machinery — ADR-0001 local-first.)
- **Not** distributed-commit or two-phase-commit across adapters. Each `submit` is independently durable; there is no cross-adapter transaction. (Reject: distributed commit / free rollback.)
- **Not** the AI provider / prompt / summarization stack. An AI provider is *just another capability-gated remote adapter*; redaction (privacy spec) governs the egress boundary. (Reject: defining the model stack here.)
- **Not** an outbound *command* channel that lets the runtime drive the vendor. Action execution against a vendor is owned by the action/capability spec; an action's *result* re-enters as a fact event via `submit`. The adapter port is inbound-facts plus optional read. (Reject: a runtime→vendor write API in this spec.)

## Prior art (citations kept visible)

- **Anti-corruption layer (DDD; Microsoft Azure Architecture Center; AWS Prescriptive Guidance; DDD Practitioners).** Adopt: the ACL as a defensive translator between bounded contexts that don't share semantics — the layer "translates requests one subsystem makes to the other" and "prevents external concepts from leaking into your codebase," structured as **adapter (protocol/auth/retries) → translator (model mapping) → facade (clean domain operations)**. Map directly: our adapter is the protocol/auth/retry tier, the **translator emits the envelope**, and the **facade is `submit`** (one operation, in the runtime's language). Reject: heavyweight per-pair ACL infrastructure and over-abstraction before two real adapters exist (the guidance: derive the API from two concrete adapters). learn.microsoft.com/azure/architecture/patterns/anti-corruption-layer; docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/acl.html; ddd-practitioners.com (anticorruption-layer).
- **Macaroons (Birgisson et al. 2014; libmacaroons) + object-capability / POLA (Dennis & Van Horn 1966; E; Spritely Goblins).** Adopt: authority is a **possessed, attenuable, unforgeable** token, not a role; an adapter presents a capability that authorizes *emit to this entity scope* and nothing more (POLA). Third-party caveats are the model for human-approval discharge on egress. Reject: cloud-distributed framing and a full ocap object graph in v1 (the contract stays ocap-shaped; v1 may verify an RBAC-degenerate single-principal token — ADR-0001 inv. 5). The capability *format* is owned by the action/capability spec; this spec only specifies how an adapter *presents* one.
- **RivetKit `ActorDriver`/`ManagerDriver` + compound keys (`actor-model-prior-art.md`).** Adopt: the **driver-abstraction-as-port** precedent (write integrations once against a narrow port) and injection-safe **compound-key addressing** (never interpolate untrusted vendor data into a delimited key — use the `EntityAddress` segment list). Reject: RBAC permission hooks as the capability model, serverless execution, and Rivet cloud.
- **CloudEvents v1.0 + idempotent consumer / at-least-once + dedupe (Kafka, AWS EventBridge; envelope spec).** Adopt: assume the vendor transport is **at-least-once**; carry the vendor's native offset so re-delivery maps to the envelope's producer-stable `dedupeKey`; `source` + `dedupeKey` uniqueness yields exactly-once *apply*. Reject: distributed exactly-once delivery.
- **SemVer 2.0.0 + consumer-driven contract testing (Pact / Pactflow).** Adopt: the **envelope/port as a long-lived SemVer'd contract**; a negotiated handshake at attach (akin to LSP capability negotiation, daemon spec) where the daemon advertises supported `specversion`s and the adapter selects one; contract tests are the conformance mechanism — the adapter records what it emits, the daemon verifies it can ingest it. Reject: a central Pact Broker / deploy-gating infrastructure (local-first: the contract test suite ships with the spec). semver.org; docs.pact.io; pactflow.io.
- **WebAssembly Component Model + WIT + WASI Preview 2 (wasmtime; "Building Native Plugin Systems with WebAssembly Components").** Cited as the **future untrusted-adapter path**: components expose typed interfaces via WIT and run under **capability-based sandboxing** — "a component can only do what the host explicitly gives it… a malicious plugin can crash its own sandbox but can never touch the host's pointers." This is the right substrate for *untrusted third-party* adapters later; **not adopted in v1** (trusted out-of-process producers first). docs.wasmtime.dev/security.html; tartanllama.xyz/posts/wasm-plugins; component-model.bytecodealliance.org.
- **DDIA stream–table duality / event sourcing (Kleppmann ch. 11).** Adopt: source-offset + idempotency, the envelope as the long-lived contract, the vendor as an upstream change-data-capture source folded into facts. Reject: two-phase commit and the assumption that rollback is free.

## Conformance to ADR-0001

| Invariant | How this spec honors it |
|---|---|
| (1) Log is source of truth; components derived, read-only | An adapter's only mutation is `submit`, which appends a fact to the log. An adapter **never** writes a component, a rollup, or an edge directly — those are derived downstream. The optional `subscribe` is read-only. |
| (2) Directionality | The adapter sits on the **write boundary** for facts and the **read boundary** for projection state — the two data planes of the daemon's thin local **IPC seam** (the daemon spec's § terminology defines "broker" as *only* this seam — two data planes plus one control channel, no topics/exchanges/fan-out/external pub/sub; this spec adopts that definition by reference and never implies message-broker machinery). It never queries across entities on the write side and never holds write authority on the read side (POLA). The log is the single seam; the adapter touches only its two ends. |
| (3) Determinism | An adapter proposes `occurredAt` (vendor valid time) but **never** asserts `sequence`, `ingestTime`, `eventId`, or `seed` — the daemon stamps all non-determinism at ingestion. Re-running an adapter from the same source offset produces the same envelopes, so re-ingestion deduplicates rather than diverging. |
| (4) Per-entity total order only | An adapter addresses each event to one `EntityAddress`; it makes **no** claim about cross-entity order and is given none. Within one entity, the daemon (not the adapter) assigns `sequence`. |
| (5) Capability-shaped authority | An adapter must present a capability authorizing *emit to this entity kind/scope*; the check is at the boundary. The capability is attenuable and unforgeable; v1 may verify a single-principal token. Manifest flags an adapter declares (e.g. `destructive` on an action it backs) are UX hints, never the security boundary. |
| (6) Fact/narration firewall | An ordinary adapter's `ProposedEvent` has **no narration field** (structural). Only an adapter that declares the `egress.narration` role may write narration, and only via the narration store (never `submit`, never the log). |
| (7) Credentials never in state/log | The adapter **holds the vendor secret** (OS keychain or daemon-encrypted store, per the privacy spec). The adapter presents its capability as the `submit(cap, event)` argument — never as a field on `ProposedEvent`; the daemon records an opaque `capabilityRef` for provenance after authorizing. Only the daemon-assigned `capabilityRef` and the producer-set `source` travel on the stamped envelope. A credential never appears in `data`, in a component, or on the log. |
| (8) Vendor neutrality | Vendor `type` values, severity vocabulary, and payload schemas are **bundle-owned**; they live under `examples/adapters/`. Core fixes only ENVELOPE + RUNTIME shapes, never branches on `data` internals, and ships zero *domain* `type`s. The single exception is the envelope spec's closed, audited **core-reserved `ambisphere.*` allowlist** (egress audit, attention/focus/edge/entity/approval verbs the runtime's own reducers emit) — these are runtime control/audit facts, not vendor content. This spec's vendor-neutrality lint (AC 4) references **exactly** that allowlist; it does not re-derive a "zero types" rule. |
| (9) Cross-language seams | The adapter port is the **language-neutral envelope over a length-prefixed CBOR/JSON local RPC** (daemon spec framing). The Rust reference SDK is a convenience, not a requirement — an adapter in any language emits the same bytes. |

## The adapter as anti-corruption layer

An adapter is three tiers (the DDD/Microsoft ACL structure), all living **outside** the runtime in the adapter's own bounded context:

```
  EXTERNAL BOUNDED CONTEXT (vendor)        |  RUNTIME BOUNDED CONTEXT (core)
  ----------------------------------------- | -----------------------------------
  ┌───────────┐  ┌────────────┐  ┌────────┐ |  ┌──────────────────────────────┐
  │  ADAPTER  │→ │ TRANSLATOR │→ │ FACADE │ →→→ │ submit(cap, ProposedEvent)   │
  │ protocol/ │  │ vendor →   │  │ envelope│|  │   → SubmitAck (the only       │
  │ auth/     │  │ EntityAddr │  │ builder │ |  │     write path; envelope spec)│
  │ retry/    │  │ + payload  │  │         │ |  └──────────────────────────────┘
  │ offset    │  │ + scalars  │  │         │ |  ┌──────────────────────────────┐
  └───────────┘  └────────────┘  └────────┘ |  │ subscribe(readCap, …) (opt.)  │
        ↑ vendor native events                 │   → FrameStream (read plane)  │
                                            |  └──────────────────────────────┘
```

- **Tier 1 — adapter (protocol/auth/retry/offset).** Speaks the vendor's transport (SSE, JSON-RPC socket, webhook, FS-watch, REST poll). Holds the vendor credential. Tracks the vendor's native offset/cursor. This is the only tier that knows the vendor wire.
- **Tier 2 — translator (vendor → envelope).** Maps a native event to: an `EntityAddress` (compound segment list, injection-safe — identity spec); a bundle-owned reverse-DNS `type`; an opaque `data` payload under a `dataschema`; the attention scalars/severity mapping (attention spec — core ships none); the `occurredAt` from the vendor's event time; a producer-stable `dedupeKey` derived from the vendor offset. This tier is where domain knowledge lives and where it stops — nothing past the facade is vendor-aware.
- **Tier 3 — facade (`submit`).** One operation, in the runtime's language: append a fact. The adapter never calls `setComponent`, never writes an edge, never asserts order. The facade is the envelope spec's `submit` and nothing else.

Translation is **strictly one-directional into the runtime.** An adapter may *read back* projection state via `subscribe` (e.g. to drive a vendor-side UI or to detect that a fact it emitted has been reduced), but it **never** translates runtime state back into vendor writes through this port — that is an *action* (action/capability spec), separately capability-gated, whose result re-enters as a fact.

## The inbound port — emit envelopes

The write side of the adapter port is exactly the envelope spec's `submit`, with adapter-specific obligations layered on. No new write operation is introduced.

```rust
/// The ONLY write path (envelope spec). An adapter constructs a ProposedEvent in the TRANSLATOR
/// tier and submits it through the FACADE. The daemon stamps all RUNTIME-assigned fields.
fn submit(cap: &CapabilityRef, event: ProposedEvent) -> Result<SubmitAck, SubmitError>;

/// What the ADAPTER fills in (a constrained view of the envelope's producer-PROPOSED region).
/// All other envelope fields are daemon-assigned; the adapter MUST NOT set them. This shape is
/// byte-for-byte the envelope spec's `ProposedEvent` — it carries NO capability and NO capabilityRef.
/// The adapter presents its authority as the separate `cap` argument to `submit(cap, event)`; the
/// daemon records the provenance `capabilityRef` ITSELF after authorization (never producer-trusted).
pub struct ProposedEvent {
    pub specversion: SpecVersion,        // negotiated at attach (see version handshake)
    pub r#type: String,                  // bundle-owned, reverse-DNS, past-tense (e.g. "com.khaos.workflow.blocked")
    pub source: SourceRef,               // stable adapter/source identity (e.g. "adapter:github:org/repo")
    pub entity: EntityAddress,           // compound SEGMENT LIST (identity spec) — never a joined string
    pub subject: Option<String>,         // optional finer subject within the entity
    pub occurred_at: Timestamp,          // vendor VALID time (proposed; daemon stamps trusted ingestTime)
    pub dedupe_key: DedupeKey,           // REQUIRED, producer-stable, derived from the SOURCE OFFSET (see below)
    pub datacontenttype: String,         // e.g. "application/cbor" | "application/json"
    pub dataschema: Option<SchemaRef>,   // bundle-owned payload schema id+version (schema-on-read)
    pub data: OpaquePayload,             // vendor fields — CORE NEVER BRANCHES ON THIS
    pub traceparent: Option<String>,     // W3C trace context, optional
    pub redaction: Option<RedactionHint>,// privacy hint (privacy spec owns enforcement)
    pub correlation: Option<Correlation>,// causedBy: links an action RESULT back to its command (action spec)
    // NO capability_ref here. The capability is the `submit` argument; `capabilityRef` is a
    // RUNTIME-ASSIGNED provenance field the daemon stamps after authorization (envelope spec).
}
```

Adapter obligations on this port:

- **Address with a segment list, not a string.** The adapter builds `entity` as `[namespace, kind, local-id, …]` (identity spec). Vendor ids go into individual segments — never interpolated into a delimited string (RivetKit injection lesson). The adapter does **not** invent the `entityHandle`; resolution `address → handle` happens at ingestion (identity/envelope specs).
- **Own a namespace.** An adapter declares the `namespace`(s) it may address and the `type` prefix(es) it may emit at attach; the daemon validates each `submit` against the adapter's capability scope. An adapter cannot emit into another vendor's namespace.
- **Keep `data` opaque.** The adapter is the *only* component that understands `data`; core treats it as bytes-with-a-schema-id. Reducers (in the same bundle) read it on the read side. Core never branches on it.
- **Map severity into scalars, not vocabulary.** Core ships zero severity/kind vocabulary (attention spec inv. 9). If the adapter's facts should influence attention, the bundle's *reducer* maps domain severity into the `attention` facet's `[0,1]` scalars — the adapter emits the fact; the reducer (not the adapter) computes the scalars. The adapter never writes the `attention` component directly.

## Source-offset idempotency

The vendor is an at-least-once source: a webhook may be redelivered, a poll may overlap, an adapter may crash mid-batch and resume. The adapter makes **apply** exactly-once by deriving the envelope's required `dedupeKey` from the **vendor's native, stable offset**:

```
dedupe_key = stable_fn(source, vendor_offset)
   where vendor_offset is the vendor's own monotonic identity for the native event:
     GitHub  → delivery GUID / event id            (X-GitHub-Delivery)
     Kafka-like → (partition, offset)
     FS-watch → (path, inode, mtime, size) or content hash
     poll    → vendor's resource updated_at + id
```

- The same vendor event, re-delivered, yields the **same** `dedupeKey` → the daemon's dedupe step returns the **original** `SubmitAck` and appends nothing (envelope spec inv. 5). Re-running an adapter from an earlier offset is therefore safe and idempotent.
- The adapter **persists its own high-water offset** *after* it receives an `Appended | Deduplicated` ack — never before. On restart it resumes from the last acked offset (at-least-once + dedupe = effective exactly-once). The adapter's offset store is adapter-local state, never runtime state.
- **Backfill on first connect** (e.g. importing GitHub issue history) is the same mechanism replayed from offset zero: each historical event gets a stable `dedupeKey`, so a second backfill is a no-op. The adapter declares whether it is push-only or supports pull/backfill in its manifest.
- If the vendor has **no stable offset**, the adapter MUST synthesize one deterministically (content hash of the canonicalized native event) so the same observation maps to the same key. A non-deterministic `dedupeKey` (e.g. wall-clock) is a conformance failure — it would let duplicates through.

## The fact-vs-narration discriminator

The firewall is **structural at the adapter boundary** (ADR-0001 inv. 6; reducer spec § firewall):

- An **ordinary adapter** emits only **facts**. `ProposedEvent` has no narration field and cannot be built from model output; an ordinary adapter therefore *cannot* introduce narration even by mistake.
- Narration is written **only** by an adapter that declares the `egress.narration` role in its manifest, and **only** to the **narration store** (a separate store, reducer spec) — never via `submit`, never onto the log, never as a reducer input. The AI provider that *generates* narration is one such egress adapter; it is capability-gated and bound by the privacy spec's egress redaction.

```rust
/// The ONLY narration write path. Distinct from submit; produces a NarratedProjection (reducer spec)
/// in the separate narration store. Requires the egress.narration role + capability.
fn emit_narration(cap: &EgressCapabilityRef, n: NarratedProjection) -> Result<(), EgressError>;

pub struct NarratedProjection {
    pub kind: NarrationKind,             // ALWAYS "narrated" — can never be "factual"
    pub entity: EntityHandle,
    pub grounds: Vec<EventId>,           // the FACTUAL events this narration is grounded in (required, ≥1)
    pub text: String,                    // model output — never authoritative, never re-ingestable as a fact
    pub narration_provenance: NarrationProvenance, // model id, prompt ref, confidence, egress-redaction record
}
```

- `grounds` is **required and non-empty**: narration that cites no factual event is, by definition, ungrounded (the guidance's "untraceable narration = hallucination"). Surfaces may render `text` only alongside the facts in `grounds`, and must be able to render factual-only with narration suppressed.
- An egress narration adapter is also subject to the privacy spec: state egresses to the model **only** after per-entity-kind redaction, and what was sent is recorded in `narration_provenance`.

## The opaque, namespaced payload

`data` is the **only** vendor-aware region of an event, and the boundary that keeps vendor concepts out of core:

- **Core never deserializes `data`.** It is bytes plus a `datacontenttype` and an optional `dataschema` id. Core validates only the fixed ENVELOPE structure (envelope spec inv. 8); it never reads a field inside `data` and never makes a control-flow decision on its contents.
- **Schema-on-read, bundle-owned.** The reducer in the *same bundle* that owns the `type` deserializes `data` against `dataschema` on the read side. Breaking payload changes are handled by the bundle's registered upcasters at read time; the log is never rewritten (envelope/reducer specs).
- **Namespaced `type`.** The `type` is reverse-DNS and bundle-owned (`com.khaos.…`, `dev.loswf.…`). Core ships zero *domain* `type` values; the only `type` literals permitted in core are the envelope spec's closed **core-reserved `ambisphere.*` allowlist** (the runtime's own control/audit facts — egress audit, attention/focus/edge/entity/approval verbs). Adapters MUST NOT emit under the reserved `ambisphere.*` prefix (it is reserved to core). A lint/conformance check asserts core code contains no `khaos.*`/`loswf.*` literal, no other literal domain `type`, and no `match` on `data` internals; it allowlists the same `ambisphere.*` set the envelope spec defines and nothing more — vendor leakage into core is a top risk (the guidance) and is enforced, not requested.

## The capability and credential boundary

Two distinct things travel with an adapter, and only one of them is ever serialized into the runtime:

| Thing | Held by | Travels into runtime? | On the log? |
|---|---|---|---|
| **Vendor credential** (GitHub token, daemon socket secret) | the adapter (OS keychain / daemon-encrypted store, privacy spec) | **never** | **never** |
| **Capability** (authority to emit to a scope) | presented by the adapter on each `submit` | yes, verified at the boundary | **no** — only an opaque `capabilityRef` is recorded for provenance |

- The adapter authenticates to the *vendor* with the vendor's credential, in the adapter's own process. That secret never crosses into the runtime.
- The adapter authenticates to the *runtime* by presenting a **capability** authorizing *emit to namespace/kind X*. The capability is possessed, attenuable, unforgeable (macaroons / ocap lineage); v1 may verify a single-principal signed-scope token, but the contract stays ocap-compatible (ADR-0001 inv. 5). The capability *format and granting ceremony* are owned by the action/capability spec; this spec specifies only that an adapter **presents** one per `submit` and that the daemon checks it at the boundary.
- The **daemon** records a **`capabilityRef`** on the stamped envelope — an opaque handle for provenance/audit (W3C PROV `wasAttributedTo`, reducer spec), assigned by the daemon *after* it authorizes the `submit` capability, **never proposed by the adapter** and **never the capability bytes or the credential**. The adapter does not set `capabilityRef`; it presents its capability as the `submit(cap, event)` argument and the daemon derives the provenance handle. "Why was this fact accepted?" is answerable from the daemon-recorded `capabilityRef`; the secret is not recoverable from the log.

## SemVer and the negotiated version handshake

The adapter port is a **frozen public contract** so a third party can adopt without forking (issue #5 §11). Three independently-versioned surfaces (mirroring the envelope spec's three versions) are negotiated or declared:

1. **`specversion`** — the ENVELOPE/core contract (SemVer). Negotiated at attach.
2. **`dataschema` version** — the bundle's payload type version. Declared per event; resolved on read by the owning bundle.
3. **adapter-protocol version** — the wire framing/RPC version (daemon spec). Negotiated at attach.

```rust
/// Sent by the adapter when it attaches; the daemon replies with the negotiated result.
/// LSP/Pact-style: advertise what you support, agree on a common version, degrade gracefully.
fn attach(req: AttachRequest) -> Result<AttachAck, AttachError>;

pub struct AttachRequest {
    pub adapter_id: String,                       // stable adapter identity
    pub adapter_version: SemVer,                  // the adapter build's own version (informational)
    pub supported_specversions: Vec<SpecVersion>, // envelope versions the adapter can emit
    pub supported_protocol: VersionRange,         // wire/RPC versions the adapter speaks
    pub declared_namespaces: Vec<Namespace>,      // namespaces it will address (validated vs capability)
    pub declared_types: Vec<TypePrefix>,          // reverse-DNS type prefixes it will emit
    pub roles: Vec<AdapterRole>,                  // e.g. [Ingest], [Ingest, EgressNarration]
    pub capabilities: AdapterCapabilities,        // supports_backfill, supports_subscribe, max_payload_bytes, …
    pub capability: CapabilityRef,                // the authority being presented
}

pub struct AttachAck {
    pub negotiated_specversion: SpecVersion,      // the one both sides agreed on
    pub negotiated_protocol: Version,
    pub granted_namespaces: Vec<Namespace>,       // ⊆ declared, ∩ capability scope (may be narrower)
    pub server_specversions: Vec<SpecVersion>,    // for the adapter to log/diagnose
    pub limits: ServerLimits,                     // max_payload_bytes, rate hints (backpressure, envelope spec)
}
```

SemVer compatibility rules for the contract:

- **PATCH** — editorial/clarification only; no field changes. Always compatible.
- **MINOR** — **additive** only: new optional ENVELOPE fields, new error variants an old adapter can treat as "unknown error." Old adapters keep working (tolerant reader); the daemon ignores unknown *optional* fields from a newer adapter within the same MAJOR.
- **MAJOR** — breaking: a removed/renamed field or a changed required-field meaning. A daemon MAY support multiple MAJORs concurrently; if it cannot satisfy any version the adapter offers, `attach` fails with `UnsupportedSpecVersion` (never a silent partial). The adapter then fails fast rather than emitting events a mismatched daemon would misread.
- **Conformance** is consumer-driven-contract-style (Pact): the spec ships a contract test corpus of canonical envelopes; an adapter passes if its emitted bytes ingest cleanly, and a daemon passes if it ingests the corpus and round-trips the negotiated handshake. No central **Pact broker** (the deploy-gating service) — the corpus is the contract (local-first). (Note: "Pact broker" here is the testing-service sense and is unrelated to the daemon's local IPC seam, which the daemon spec calls "broker" only in its narrow § terminology meaning — see below.)

## Optional outbound — subscribe to projection state

An adapter MAY (if `supports_subscribe` and separately read-gated) subscribe to the daemon's read plane — the read data plane of the daemon's local IPC seam (daemon spec `subscribe`; "broker" in the daemon/renderer specs means *only* that seam, per the daemon spec's shared § terminology definition — no topics, no fan-out, no external pub/sub) — to observe projection state, e.g. to confirm its facts reduced, to drive a vendor-side status surface, or to react to focus-mode changes.

```rust
/// Optional, READ-ONLY, separately capability-gated. Same FrameStream the renderer contract uses.
/// An adapter holds NO write authority on this plane (POLA); it is a passive observer here.
fn subscribe(read_cap: &ReadCapabilityRef, req: SubscribeRequest) -> Result<FrameStream, SubscribeError>;
```

- This is the daemon's existing read plane (snapshot + delta + resume on `logPosition`), **factual-only by default** (`include_narration: false`); an adapter that is not an egress-narration adapter SHOULD never request narration.
- The read capability is **separate** from the write capability (ADR-0001: read authority distinct from write). A subscribing adapter may receive **redacted/coarsened** projections (privacy spec); it is not entitled to raw state.
- Subscribing **never** grants write authority. If observing a projection should cause a vendor write, that is an *action* (action/capability spec), not a use of this port.

## WASM/WIT — the future untrusted-adapter path (not v1)

v1 adapters are **trusted, out-of-process** producers: separate processes that connect over the daemon's local socket and present a capability. Trust is established by the capability and by the adapter being installed by the operator. This is sufficient for first-party vendor adapters (Khaos, LOSWF, GitHub) and bounds v1 effort (the guidance).

For **untrusted third-party** adapters later, the **WebAssembly Component Model + WIT + WASI Preview 2** is the named path (wasmtime; cited above):

- The adapter port (`attach`/`submit`/`emit_narration`/`subscribe`) is expressed as a **WIT world**; an untrusted adapter compiles to a component implementing it.
- The host grants the component **only** the capabilities it needs (the WASI capability model: no ambient filesystem/network/clock/RNG) — a structural fit for POLA and the credential boundary: an untrusted adapter cannot reach a credential the host did not hand it, and "can crash its own sandbox but never touch the host's pointers."
- **Not adopted in v1.** It is recorded here so the v1 port is designed to be WIT-expressible (narrow, typed, capability-passing) and the future sandbox is a drop-in trust tier, not a redesign.

## Worked examples (vendor concepts in the adapter layer only)

Both examples live under `examples/adapters/`; **nothing here is in core.**

### A — GitHub adapter (LOSWF factory facts)

```text
vendor event:  webhook "check_run" {status: completed, conclusion: failure, repo, run_id, …}
tier 1 adapter: verify webhook HMAC (vendor credential, held by adapter); read X-GitHub-Delivery
tier 2 translator:
  entity      = ["dev.loswf", "ci", "org/repo", "run-<run_id>"]   // segment list, injection-safe
  type        = "dev.loswf.ci.failed"                              // bundle-owned, reverse-DNS, past-tense
  occurred_at = check_run.completed_at                             // vendor valid time
  dedupe_key  = stable_fn("adapter:github:org/repo", delivery_guid)
  data        = { conclusion, run_id, html_url, … }                // OPAQUE to core
  // NOTE: no severity vocabulary emitted; the LOSWF reducer maps ci.failed → attention scalars
tier 3 facade: submit(cap, ProposedEvent) → SubmitAck{Appended | Deduplicated}
on ack: persist high-water offset = delivery_guid
```

### B — `khaos-wfl` adapter (workflow daemon over JSON-RPC)

```text
vendor event:  JSON-RPC notify {method: "workflow.blocked", params:{run_id, reason, project}}
tier 1 adapter: connect khaos-wfl local socket (credential held by adapter); cursor = wfl seqno
tier 2 translator:
  entity      = ["com.khaos", "workflow", "<project>", "<run_id>"]
  type        = "com.khaos.workflow.blocked"
  occurred_at = params.ts
  dedupe_key  = stable_fn("adapter:khaos-wfl:<project>", wfl_seqno)
  data        = { reason, project, run_id, … }                     // OPAQUE to core
tier 3 facade: submit(cap, ProposedEvent) → SubmitAck
optional: subscribe(read_cap, scope=entity) to confirm the workflow entity reduced to "blocked"
```

In both, core sees only: a presented capability it checks on the `submit` argument, an `EntityAddress` it resolves, a reverse-DNS `type` it does not interpret, an opaque `data`, and a `dedupeKey` it checks — and the daemon then stamps the provenance `capabilityRef` itself. No `khaos.*`/`loswf.*` symbol exists in core; no core branch reads `data`.

## Reference adapter SDK + language-neutral wire spec

Per the implementation-language guidance: a **Rust reference adapter SDK** ships alongside a **language-neutral wire spec**, so adapters are polyglot and none is forced to depend on the SDK.

- **Wire spec (normative, language-neutral).** The bytes on the daemon socket: length-prefixed CBOR/JSON framing (daemon spec), the `attach`/`submit`/`emit_narration`/`subscribe` RPCs, the envelope schema, the handshake, the error taxonomy. Any language that can speak this wire is a first-class adapter author. This is the actual contract; the SDK is a convenience over it.
- **Rust reference SDK (non-normative convenience).** Helpers for: the `attach` handshake and version negotiation; an `EntityAddress` builder that is injection-safe by construction; a `dedupe_key` helper that refuses non-deterministic inputs; an offset-store trait with a default file-backed impl; the `submit` retry/ack loop with high-water-offset persistence; and the contract-test harness (emit the corpus, assert clean ingest). The SDK enforces the adapter obligations (segment-list addressing, deterministic dedupe, payload-opacity) so a Rust adapter is correct by construction; a non-Rust adapter must uphold the same obligations against the wire spec.
- **Adapter SDK scope is deliberately small** (the guidance: don't over-abstract before two real adapters). It does **not** include a vendor-specific layer; vendor logic is the adapter author's bounded context.

## Acceptance criteria

Each maps to an upstream invariant and is mechanically testable.

1. **One-directional translation.** A conformance test asserts an adapter's only runtime mutation is `submit` (and, for egress role, `emit_narration`): no code path calls `setComponent`, writes an edge, or asserts `sequence`/`ingestTime`/`eventId`. (ADR-0001 inv. 1, 3, 4.)
2. **Source-offset idempotency.** Replaying the same vendor batch (and re-running from an earlier offset) produces byte-identical `dedupeKey`s; the daemon appends once and returns the original `SubmitAck` on every duplicate. A non-deterministic `dedupeKey` is rejected by the SDK helper and flagged by the corpus test. (Envelope inv. 5.)
3. **Backfill safety.** A first-connect backfill followed by a second backfill appends zero new events (every historical event deduplicates). (Idempotency.)
4. **Payload opacity / vendor neutrality (allowlist-scoped).** A lint asserts core contains no `khaos.*`/`loswf.*` literal, no other literal *domain* `type`, and no branch on `data` internals; the **only** permitted `type` literals are the envelope spec's closed **core-reserved `ambisphere.*` allowlist** (§ core-reserved event types in that spec). This is the *same* allowlist the envelope spec's AC 9 and the bundle spec's lint reference — no spec re-derives "zero types." The worked-example adapters pass with all vendor symbols confined to `examples/adapters/`, and no adapter emits under the reserved `ambisphere.*` prefix. (ADR-0001 inv. 8; envelope spec core-reserved allowlist.)
5. **Narration firewall.** An ordinary adapter cannot construct a narration-bearing event (no such field exists). Only an `egress.narration` adapter can call `emit_narration`, which writes to the narration store, never `submit`/the log; the narration carries ≥1 `grounds` event or is rejected; surfaces can render factual-only with narration suppressed. (ADR-0001 inv. 6.)
6. **Credential boundary.** A test scans every accepted envelope and the log for the vendor credential and the capability bytes and finds neither; only the daemon-recorded opaque `capabilityRef` is present; the daemon can answer "why accepted?" from it without recovering a secret. (ADR-0001 inv. 7.)
7. **Capability gating + namespace scoping.** `submit` without a valid capability (the `cap` argument) returns `Unauthorized` and writes nothing; an adapter emitting into a namespace outside its granted scope is rejected; `attach` grants ⊆ declared ∩ capability scope. (ADR-0001 inv. 5.)
8. **Version negotiation.** `attach` selects a common `specversion`/protocol or fails with `UnsupportedSpecVersion` (never a silent partial); a MINOR-newer adapter's unknown optional fields are ignored by an older daemon within the same MAJOR; the contract corpus round-trips. (SemVer / Pact.)
9. **Read plane is read-only.** A subscribing adapter receives factual-only frames by default, may receive redacted/coarsened projections, and gains no write authority from subscribing; a vendor write triggered by an observation goes through the action path, not this port. (ADR-0001 inv. 2; daemon read plane.)
10. **Polyglot parity.** A non-Rust adapter speaking only the wire spec passes the same contract corpus as the Rust SDK adapter (the SDK is convenience, not contract). (Language-neutral seam, ADR-0001 inv. 9.)
11. **WIT-expressibility (design check).** The v1 port (`attach`/`submit`/`emit_narration`/`subscribe`) is expressible as a WIT world with only capability-passing parameters (no ambient authority), so the future untrusted-adapter sandbox is additive. (Future path, not v1 runtime.)

## Open questions

- **Capability token format and granting ceremony.** Macaroons wholesale vs a simpler signed-scope token for v1, and *how* an adapter first acquires its emit capability (daemon keychain grant vs per-bundle capability file vs grant-on-first-use) — owned by the action/capability spec; this spec only assumes a capability is presentable as the `submit` argument. Which wins for v1?
- **Where the vendor credential physically lives** and how an adapter presents a *credential reference* without the daemon ever holding the raw secret (OS keychain vs daemon-encrypted store) — co-owned with the privacy/credential spec. For an in-process/WASM future adapter, who holds the secret?
- **Push vs pull/backfill obligations.** Should the spec *require* backfill support for vendors with queryable history (GitHub issue history on first connect), or leave it adapter-declared? What is the contract for a vendor with no stable offset beyond "synthesize a content hash"?
- **Trust tiering before WASM.** Is there an intermediate trust tier between "trusted out-of-process v1 adapter" and "WASM-sandboxed untrusted adapter" (e.g. a signed-manifest first-party tier)? When does the WASM path become v-next scope?
- **Adapter SDK breadth.** Rust-only first, or a second SDK (TypeScript/Go) to lower the authoring barrier for the common GitHub/CI integrations — and how much vendor-agnostic retry/offset machinery belongs in the SDK vs the wire spec?
- **Egress-narration adapter discovery.** How does the daemon know which adapter holds the `egress.narration` role, and does exactly-one-egress or many-egress apply per entity kind? Co-owned with the persona and privacy specs.
- **Handshake for a daemon that supports multiple envelope MAJORs.** Concrete negotiation precedence when an adapter offers `[v1, v2]` and the daemon supports `[v1, v2, v3]` — newest-common vs adapter-preferred — and whether per-`type` payload-version negotiation is ever needed beyond schema-on-read upcasting.
