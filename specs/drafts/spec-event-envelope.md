# Semantic event envelope and ingestion

**Status:** draft · **Scope:** the semantic event envelope (a CloudEvents-shaped immutable fact addressed to one entity), its three-part split — ENVELOPE / PAYLOAD / RUNTIME-ASSIGNED — the single capability-gated `submit(event)` write path, the daemon-as-sole-ordering-authority (per-entity monotonic `sequence` + `ingestTime`), at-least-once delivery with dedupe (a concrete v1 retention default) yielding effective exactly-once apply, the fact-vs-command distinction (events are facts; actions are a separate primitive whose *results* become fact events), schema-on-read with an upcast-at-replay evolution policy, and a small closed allowlist of core-reserved `ambisphere.*` control/audit event types · **Companion to:** `specs/VISION.md`, `specs/SRS.md`, `RFP.md` (§ "Semantic event ingestion", "Semantic event systems") · **Sequenced:** fourth among the follow-on specs (after the attention-bus and reducer/state-component specs, before the entity-identity and daemon specs) per ADR-0001 and issue #4 · **Conforms to:** ADR-0001 (foundational paradigm + directionality invariant; *provisional* until ADR-0001 is ratified — see open questions); the attention-routing spec (the `attention` facet shape); the reducer/state-component spec (the `ReducibleEvent` contract — this spec *produces* the wire/storage event that the reducer spec *consumes*, and fixes `seed` non-optional for it); the daemon-architecture spec (which **owns** the ingest atomicity + reduction-failure contract this spec defers to — reduce-in-memory then atomic append+reduce) · **Sibling notes:** `specs/drafts/runtime-paradigm-and-specs-guidance.md`, `specs/drafts/actor-model-prior-art.md`, `specs/drafts/persona-prior-art.md`, `specs/drafts/implementation-language-guidance.md`

This spec defines the **write-side seam**: the shape of a semantic event, how it is submitted, how the daemon stamps the non-determinism that makes downstream reducers replay byte-identically, and how the per-entity append-only log — the single source of truth (ADR-0001 invariant 1) — is written. It is the one place producers touch the system, and the one place where "now", identifiers, and ordering become facts.

It sits directly above the reducer/state-component spec: that spec defines `ReducibleEvent` (the determinism-relevant fields a reducer may read); this spec defines the full envelope on the wire and on disk, and guarantees that every field `ReducibleEvent` requires (`event_id`, `sequence`, `occurred_at`, `ingest_at`, `seed`, `source`, `capability_ref`) is stamped here at ingestion, before any reducer runs. Producers *propose*; the daemon *assigns*. Nothing downstream may depend on a value a producer asserted about ordering or time.

## Goals and non-goals

### Goals

- Define a **semantic** (not log-text) event: an immutable, append-only, capability-gated **fact** addressed to exactly one entity.
- Split the envelope three ways with crisp ownership: **ENVELOPE** (producer-proposed domain-agnostic metadata), **PAYLOAD** (bundle-defined, schema-on-read), **RUNTIME-ASSIGNED** (daemon-stamped: per-entity `sequence`, `ingestTime`, durable position, `eventId`, `seed`).
- Make the daemon the **sole ordering authority**: per-entity total order only; no global cross-entity order; producers may *not* assign `sequence` or trusted time.
- Define **`submit(event)`** as the *only* write path, capability-gated at the boundary (ADR-0001 invariant 5).
- Specify **at-least-once delivery + dedupe** on a producer-supplied `dedupeKey`, yielding **effective exactly-once apply** (idempotent consumer).
- Draw the hard line: **events are facts; commands/actions are a separate primitive** (owned by the action/capability spec) whose *results* re-enter as fact events; **narration is never a fact** (ADR-0001 invariant 6).
- Specify **schema-on-read** with `dataschema` resolved against the bundle, and a decisive **schema-evolution / upcast-at-replay** policy (the log is never rewritten).
- Give concrete schemas/interfaces (fenced) and **acceptance criteria** making the invariants testable (sole-ordering, dedupe idempotence, replay-equality of stamped fields, firewall).

### Non-goals (adopt/reject framing — rejections carried from the guidance)

- **Not** a transport or wire protocol. Adapters normalize SSE / JSON-RPC / FS-watch / webhooks into this shape; the envelope is the *translation target*, not a binding. (Reject: a mandated transport binding.) At most a single reference local binding (the daemon socket, owned by the daemon spec).
- **Not** a distributed log or broker. No Kafka, no partitions, no consensus, no external event store. (Reject: distributed event-store machinery — ADR-0001 local-first.)
- **Not** global cross-entity ordering. The aggregate boundary is the entity; ordering is per-entity total order only. The attention bus and rollups read the *materialized view*, not a globally-ordered log. (Reject: a global total order.)
- **Not** the command/action model. Actions, their manifests, capability enforcement depth, preconditions, and approval gates are the action/capability spec. This spec only defines how an action's *result* becomes a fact event. (Reject: folding commands into the event model.)
- **Not** AI narration as a fact. A model output can never be built into a submittable event; the firewall is structural. (Reject: narration-as-event.)
- **Not** structured-logging / log-text ingestion. Turning a log line into a semantic event is an *adapter* responsibility. (Reject: log ingestion in core.)
- **Not** trusting producer-asserted `sequence`/`time`/`eventId`. Those are runtime-assigned. (Reject: the CloudEvents *Sequence* extension's producer-asserted, per-source, lexicographic sequence — see prior art.)
- **Not** valid-time correction (bitemporal write). v1 records both `occurredAt` (valid time) and `ingestTime` (transaction time) but supports only **as-of-transaction-time** reads; correcting the past means appending a new corrective fact, never editing the log. (Reject: in-place valid-time amendment.)

## Prior art (citations kept visible)

- **CloudEvents v1.0 (CNCF).** Adopt: the **envelope-vs-data split** and the core context attributes — `id`, `source`, `specversion`, `type`, `subject`, `time`, `datacontenttype`, `dataschema`, `data`; and the deduplication rule that **`source` + `id` MUST be unique for each distinct event** so consumers may "assume that events with identical `source` and `id` are duplicates." Reject: the HTTP/Kafka/AMQP *binding modes* (we are not a transport); the spec's **silence on ordering and durability** (we add runtime-assigned per-entity `sequence`, a durable log, and an ingestion boundary). github.com/cloudevents/spec — `cloudevents/spec.md`.
- **CloudEvents *Sequence* extension (CNCF).** Examined and **rejected as the ordering mechanism**: its `sequence` is a *String*, *producer-asserted*, *per-`source`*, lexicographically compared. That puts ordering authority in the producer and scopes it to the source, not the entity — the opposite of what determinism needs. We keep the *name* `sequence` but make it a **runtime-assigned `u64`, per-entity, monotonic**. github.com/cloudevents/spec — `cloudevents/extensions/sequence.md`.
- **Event sourcing / DDIA stream–table duality (Kleppmann, *DDIA* ch. 11).** Adopt: the **immutable append-only log as the system of record**; per-aggregate sequence; the event as the unit of truth from which all state is a derived fold; the *change-data-capture / event-log-as-table* identity. Reject: distributed/streaming-broker plumbing — the daemon owns one local log behind a StorageDriver.
- **Domain events vs commands (DDD; Fowler, *What do you mean by "Event-Driven"?*).** Adopt: a **fact is a past-tense statement that something happened** (`ci.failed`, reverse-DNS, immutable, no recipient assumption); a **command is an imperative request that may be rejected** (a separate primitive). The log holds facts; commands live on the action path and only their *results* become facts. Reject: aggregate/repository/saga ceremony in core.
- **Idempotent consumer / at-least-once + dedupe (Kafka, AWS EventBridge, Camel idempotent-consumer; Microsoft `IdempotentConsumer`).** Adopt: assume the *transport* is at-least-once (an adapter may resend on a dropped ack); make *apply* exactly-once by **deduplicating on a key** before append, so a re-submitted event is a no-op. Reject: distributed exactly-once delivery (a known impossibility on an unreliable channel — we get exactly-once *effect*, not delivery).
- **Event upcasting / versioning (Axon upcasters; Event-Driven.io "simple events versioning patterns"; Artium "What is upcasting").** Adopt: **upcast-at-read** — old event bytes are transformed to the current shape by a chain of pure upcasters during deserialization, so reducers only ever see the latest schema; **the log is never rewritten**. Reject: in-place migration of stored events and lazy "tolerant reader only" as the *sole* strategy (we pair a tolerant reader for additive changes with explicit upcasters for breaking ones).
- **RivetKit compound-key addressing (`actor-model-prior-art.md`).** Adopt: hierarchical/compound entity addressing with explicit **key-injection safety** (never interpolate untrusted data into a delimited key). Reject: the assumption that transactional rollback comes free (it does not — correctness is pure reducers + append-only log + dedupe, per the reducer spec).
- **Datomic / XTDB (`actor-model-prior-art.md`, reducer spec).** Adopt: accumulate-only facts; the **occurred-at (valid) vs ingest-at (transaction)** time distinction stamped onto every event; as-of-transaction-time reads in v1. Reject: full bitemporal write-side correction in v1.

## Conformance to ADR-0001

| Invariant | How this spec honors it |
|---|---|
| (1) Log is source of truth; components derived, read-only | `submit(event)` appends to the per-entity append-only log; that append is the *only* mutation **of record**. Components written in the same commit are a **derived** projection of that append (folded by pure reducers), never an independent source of truth — discard them and the log fully rebuilds them. |
| (2) Directionality | This is the **write boundary**. Capability checks live here and only here. `submit` never *reads or queries* a component and never crosses the read/query seam; folding the just-appended event into its derived components inside the same write transaction is the sole writer (the daemon) maintaining its own derived view, not a read on this path. The log is the single seam to the read side. |
| (3) Determinism | All non-determinism is **stamped into the event at this boundary**: `ingestTime`, `eventId` (ULID), per-entity `sequence`, and `seed` (a `u128`, **always** stamped — § seed). Reducers downstream read these as data, never a clock/RNG. Replay of a fixed log is byte-identical because these are frozen at ingestion. Reduction itself is evaluated and committed **atomically with the append** (§ ingestion pipeline), so the non-determinism a reducer reads is exactly what was sampled at this boundary. |
| (4) Per-entity total order only | `sequence` is assigned per entity, monotonic from 1, gap-free, under a per-entity write lock. No global order is offered or computed. |
| (5) Capability-shaped authority | `submit` requires a capability authorizing *emit to this entity (kind/scope)*; checked at the boundary; renderers hold none by default (POLA). The envelope carries an opaque `capabilityRef` for provenance, **never a credential** (inv. 7). v1 may verify an RBAC-degenerate single-principal token; the contract stays ocap-compatible. |
| (6) Fact/narration firewall | A `ReducibleEvent`/submittable event has **no narration field** and cannot be constructed from model output. Narration is a separate non-authoritative projection (reducer spec § firewall); it never enters `submit` and never lands on the log. |
| (7) Credentials never in state/log | The envelope transports a `capabilityRef` (opaque handle) and `source`; never a secret. The adapter holds the credential; the daemon holds the capability; the log holds neither. |
| (8) Vendor neutrality | Core fixes ENVELOPE + RUNTIME-ASSIGNED shapes and ships **zero domain** `type` values, **zero** severity vocabulary, and **zero** `payload` schemas. Core never branches on `payload` internals or `khaos.*`/`loswf.*` types. Bundles own all domain `type`s and `dataschema`s. The single exception is a small, **closed, audited allowlist of core-reserved `ambisphere.*` control/audit types** (§ core-reserved event types) — these are the runtime's own facts (egress audit, attention/focus/edge/entity/approval verbs core reducers depend on), not domain content; the vendor-neutrality lint allowlists exactly that set and nothing else. |
| (9) Cross-language seams | The envelope is a language-neutral CBOR/JSON document; `submit` is a language-neutral local RPC (binding owned by the daemon spec). Any adapter in any language can produce it without linking core. |

## Core-reserved event types (the vendor-neutrality allowlist)

The "core ships zero `type` values" claim was historically too absolute: core reducers and sibling specs already emit and depend on a handful of the runtime's **own** facts (a focus-mode change, an attention recompute, an egress audit), and these must travel the same `submit` path and land on the log like any other fact. They are *not* domain content — they carry no `khaos.*`/`loswf.*` meaning and core never branches on a *payload's* internals.

This spec, as owner of the "zero types" claim, therefore defines a **single, closed, audited allowlist** of core-reserved event types. The `ambisphere.*` prefix is **reserved to core**; bundles MUST NOT declare a `type` under it (bundle spec validation enforces this). The v1 allowlist is exactly:

```
ambisphere.egress.performed        // privacy/credential spec: an egress to an external surface happened (audit fact)
ambisphere.attention.recomputed    // attention spec: an attention recompute/refresh landed (where logged as a fact)
ambisphere.focus.modeChanged       // attention/daemon spec: operator focus-mode change (control surface → fact)
ambisphere.edge.added              // entity-identity spec: a relation edge was created
ambisphere.edge.removed            // entity-identity spec: a relation edge was removed
ambisphere.entity.created          // entity-identity spec: an entity handle was minted
ambisphere.entity.renamed          // entity-identity spec: an entity address changed (handle stable)
ambisphere.approval.granted        // action/capability spec: an approval gate was satisfied
ambisphere.approval.denied         // action/capability spec: an approval gate was refused
```

Rules:

- The list is **closed for v1**: adding a reserved type is a `specversion`-level change to *this* spec, not a per-bundle freedom. Each entry's *payload* `dataschema` is a **core artifact** (shipped by the owning core component / `ambisphere.core` base bundle) so adapters and reducers can validate against it.
- Core-reserved types use the **same envelope contract** as everything else: `specversion = "ambisphere.event/1"`, the three-region ENVELOPE/PAYLOAD/RUNTIME split, daemon-assigned RUNTIME, producer-proposed `occurredAt`/`dedupeKey`/`dataschema`. There is **no** CloudEvents-bare (`"1.0"`) shortcut for core facts — a core fact is a normal semantic event.
- The **vendor-neutrality lint** (acceptance criterion 9) allowlists **exactly** this set: core code may contain these literals and only these; any other literal domain `type` or severity vocabulary in core is a violation. Every sibling spec's vendor-neutrality lint (adapter AC, bundle L4/AC) MUST point at this same allowlist rather than re-deriving "zero types".

A core-reserved fact is a normal semantic event. For example, `ambisphere.egress.performed` (owned by the privacy/credential spec, illustrated here only to fix its shape) is submitted exactly like any other fact — note the runtime envelope `specversion`, the producer-proposed region only, and **no** RUNTIME region (the daemon stamps it):

```jsonc
{
  "specversion": "ambisphere.event/1",                 // NOT CloudEvents-bare "1.0"
  "type": "ambisphere.egress.performed",               // core-reserved (allowlisted)
  "source": "daemon:egress",
  "entity": ["ambisphere","surface","slack-dm-k"],      // the surface the egress targeted
  "occurredAt": "2026-06-10T18:22:06Z",
  "dedupeKey": "egress:slack-dm-k:msg:01J...",
  "datacontenttype": "application/cbor",
  "dataschema": "core:ambisphere.egress.performed.v1",  // a CORE artifact, not a bundle schema
  "redaction": "local-only",
  "data": { "surface": "slack", "redactionApplied": "redact-payload", "byteCount": 412 }
}
```

## The envelope — three-part split

A semantic event is one document with **three regions distinguished by who owns each field**. This is the load-bearing structure: it makes "producers propose, the daemon assigns" a property of the *shape*, not a convention.

```jsonc
// Semantic event v1 — the on-the-wire and on-disk document.
// Three regions: producer-proposed ENVELOPE, bundle-defined PAYLOAD, daemon-stamped RUNTIME.
{
  // ============================================================
  // ENVELOPE  — producer-proposed, domain-agnostic metadata.
  //             CloudEvents-shaped. Core fixes the SHAPE, never the values.
  // ============================================================
  "specversion": "ambisphere.event/1",     // envelope contract version (NOT the payload schema)
  "type":        "ci.failed",              // reverse-DNS, PAST-TENSE, bundle-owned. Core ships none.
  "source":      "adapter:github/acme",    // the producing context (CloudEvents `source`); PROV agent basis
  "entity":      ["loswf","issue","4217"], // ADDRESS: compound segment LIST (not a joined string) — see § addressing
  "subject":     "check:build",            // OPTIONAL sub-scope within the entity (CloudEvents `subject`)
  "occurredAt":  "2026-06-10T18:22:05Z",   // VALID time: when the fact happened in the source (proposed)
  "dedupeKey":   "github:check_run:99812:completed", // producer-stable idempotency key — see § dedupe
  "datacontenttype": "application/json",   // PAYLOAD encoding (CloudEvents)
  "dataschema":  "bundle:loswf@2/ci.failed.v2", // PAYLOAD schema ref, resolved against the bundle (schema-on-read)
  "traceparent": "00-<trace>-<span>-01",   // OPTIONAL W3C Trace Context, for cross-adapter correlation
  "redaction":   "none",                   // egress hint: none | redact-payload | local-only (privacy spec owns policy)
  "correlation": { "causedBy": "ulid|null" }, // OPTIONAL: the eventId or actionId that caused this (see § actions)

  // ============================================================
  // PAYLOAD  — bundle-defined, opaque to core, schema-on-read.
  //            Core NEVER branches on its internals (ADR-0001 inv. 8).
  // ============================================================
  "data": {
    // entirely bundle-owned; validated on read against `dataschema`, never by core logic
    "checkName": "build", "conclusion": "failure", "runUrl": "https://..."
  },

  // ============================================================
  // RUNTIME-ASSIGNED  — stamped by the daemon at ingestion. The daemon is the SOLE authority.
  //                     A producer that sets any of these has them OVERWRITTEN (and is warned).
  // ============================================================
  "runtime": {
    "eventId":     "01J...ULID",           // stable unique id (ULID); the dedupe identity post-ingest
    "entityHandle":"01H...ULID",           // opaque internal handle the address resolved to (identity spec owns resolution)
    "sequence":    4217,                    // PER-ENTITY monotonic u64, from 1, gap-free — the determinism key
    "ingestTime":  "2026-06-10T18:22:05.913Z", // TRANSACTION time: when the daemon committed it (the only trusted clock)
    "seed":        18302628885633695743,   // 128-bit entropy as a u128 (canonical CBOR unsigned / JSON number or 0x-hex string); ALWAYS stamped, so replay is deterministic — see § seed
    "logPosition": 88123,                   // durable monotonic position within the storage log (cursor for observers)
    "reducerSetVersion": "rsv:loswf@2+core@1" // the reducer-set in force at ingest (snapshot tagging; reducer spec § snapshot)
  }
}
```

### Field ownership is the contract

- **ENVELOPE = proposed.** Everything a producer knows. Core validates *structure* (presence/type of the fixed fields) but never the *meaning* of `type`/`data`.
- **PAYLOAD = opaque.** Core treats `data` as bytes with a `dataschema` label. It is validated, if at all, by the bundle's declared schema on read — never by core branching (ADR-0001 inv. 8).
- **RUNTIME = assigned, authoritative, immutable.** Stamped once at append; never proposed-trusted. This is the only region downstream determinism may rely on for `sequence`, time, ids, and entropy.

A reducer (per the reducer spec's `ReducibleEvent`) receives a *flattened, read-only* view drawn almost entirely from RUNTIME plus the determinism-relevant ENVELOPE fields (`type`, `source`, `occurredAt`); it never sees `dedupeKey`, `redaction`, or `traceparent` (operational metadata, not facts to fold).

### `seed` — representation and presence (normative)

`seed` is the per-event entropy a reducer may consume so that any randomness it needs is deterministic on replay. Two things were previously ambiguous; both are now fixed:

- **Representation: a `u128`.** 128 bits, drawn from a CSPRNG at ingestion (step 5). On the wire it is encoded canonically: a CBOR unsigned integer (major type 0, or a bignum if it exceeds 64 bits) in CBOR-canonical form, and a JSON unsigned integer or `0x`-prefixed lowercase hex string in JSON. All encodings denote the same 128-bit value; the canonical CBOR bytes are what the log stores and what hashes/replay compare.
- **Presence: always stamped.** Every event carries a `seed`. This is the decided answer to the old open question (the spec leaned always-stamp; it is now normative). Always-stamp keeps replay trivially deterministic and removes a per-event branch.
- **Consequence for the reducer seam.** Because `seed` is always present, the reducer spec's `ReducibleEvent.seed` is **non-optional** (`u128`, not `Option<u128>`). The reducer spec MUST be updated to match; until then, treat `Option<u128>` as "always `Some`". A reducer that needs no entropy simply ignores it; the value is still on the log for byte-identical replay.

### Addressing (the seam to the identity spec)

`entity` is a **compound segment list**, not a delimited string — this defeats key-injection (RivetKit's documented footgun: never interpolate untrusted data into a `"a/b/c"` key). The identity spec owns the resolution of an address to the opaque `entityHandle` and the namespace/kind rules; this spec only requires:

- the address is a non-empty list of opaque string segments;
- the daemon resolves it to a stable `entityHandle` **before** assigning `sequence` (sequence is per *handle*, not per *address*, so a rename does not reset ordering);
- an unknown address either auto-creates the entity (if the capability authorizes creation of that kind) or is rejected at the boundary — never silently dropped.

## The single write path — `submit(event)`

`submit` is the **only** way to write. There is no `setComponent`, no log-append API, no back door. It is capability-gated, synchronous-to-durable, and the sole place ordering and time become facts.

```rust
// Core = Rust per ADR-0001. Language-neutral by intent; this is the normative shape.

/// The ONLY write path. Capability-gated. Returns only after the event is durably committed.
pub fn submit(cap: &Capability, proposed: ProposedEvent) -> Result<SubmitAck, SubmitError>;

/// What a producer hands in: ENVELOPE + PAYLOAD only. No RUNTIME region.
/// Note: there is deliberately NO `capability_ref` field here — the capability is the
/// separate `cap` argument; `capabilityRef` is daemon-recorded provenance, assigned AFTER
/// authorization, never producer-proposed (the adapter spec must align to this shape).
pub struct ProposedEvent {
    pub specversion: String,            // must match a supported envelope contract version
    pub r#type: String,                 // reverse-DNS past-tense; bundle-owned
    pub source: String,
    pub entity: Vec<String>,            // compound address (segment list)
    pub subject: Option<String>,
    pub occurred_at: Timestamp,         // proposed valid time
    pub dedupe_key: String,             // REQUIRED — the idempotency key (see § dedupe)
    pub datacontenttype: String,
    pub dataschema: String,             // resolved against the bundle on read
    pub traceparent: Option<String>,
    pub redaction: Redaction,           // none | redact-payload | local-only
    pub caused_by: Option<Ulid>,        // correlation to a causing event/action
    pub data: CanonicalValue,           // opaque payload (CBOR-canonical / ordered)
}

pub struct SubmitAck {
    pub event_id: Ulid,                 // assigned
    pub sequence: u64,                  // assigned, per-entity
    pub ingest_time: Timestamp,         // assigned (the trusted clock)
    pub log_position: u64,              // durable cursor
    pub outcome: AckOutcome,            // Appended | Deduplicated (idempotent no-op)
}

pub enum AckOutcome { Appended, Deduplicated }   // Deduplicated returns the ORIGINAL assignment

pub enum SubmitError {
    Unauthorized,          // capability does not authorize emit to this entity/kind/scope
    MalformedEnvelope,     // missing/ill-typed fixed ENVELOPE field — rejected BEFORE the log
    UnknownEntity,         // address unresolvable and capability does not authorize creation
    UnsupportedSpecVersion,
    PayloadTooLarge,       // size guard (daemon spec sets the bound)
    Backpressure,          // ingestion queue saturated; producer should retry with same dedupeKey
    // NOTE: there is no "reduction failed" error here. Reduction runs IN MEMORY against prior
    // state and commits ATOMICALLY with the append (daemon spec's storage-transaction property).
    // Reducers are pure and TOTAL (reducer spec inv. 1), so a well-formed event cannot make
    // reduction "fail"; the producer never sees a reduction error. The only non-normal outcome
    // is a reducer BUG (panic): the daemon then commits the event ALONE and marks that component
    // `degraded` (daemon spec). The fact is never lost; the producer-facing ack is unchanged.
}
```

### The ingestion pipeline (normative order)

The order is load-bearing: **validate → authorize → resolve → dedupe → assign → reduce-in-memory → commit(append+reduction atomically) → ack**.

> **Ownership note (the one reconciliation).** The *durability and atomicity* contract — when reduction runs relative to the durable commit — is **owned by the daemon spec** (it physically implements `commit_ingest`). This spec defers to it and states the same model: the daemon runs the (pure, total) reducers **in memory** against the prior state, then commits **the fully-stamped event AND its component deltas + provenance in one storage transaction** (all-or-nothing). An earlier draft of this spec said "reduction is downstream of the durable commit"; that wording is **superseded here** — there is no longer any divergence between the two specs for an implementer to reconcile. The *producer-facing* contract is unchanged: `submit` returns after the (event + its reduction) is durable, and never returns a reduction error.

1. **Validate envelope structure.** Fixed ENVELOPE fields present and well-typed; `specversion` supported; payload within size bound. Failure ⇒ `MalformedEnvelope`, *no log write*. (This is the "malformed events rejected at the write boundary, never mid-reduction" guarantee the reducer spec relies on.)
2. **Authorize.** The capability must authorize `emit` to this entity address/kind/scope. Failure ⇒ `Unauthorized`. The capability is *checked* here; only its opaque `capabilityRef` is recorded (never the credential, inv. 7). The decision of *whether attempts are themselves logged* is an open question (see below).
3. **Resolve address → `entityHandle`** (identity spec). Unknown + uncreatable ⇒ `UnknownEntity`.
4. **Dedupe.** Under the per-entity write lock, look up `dedupeKey` in the entity's dedupe index. If present ⇒ return the *original* `SubmitAck` with `Deduplicated` (idempotent no-op; nothing is appended). (§ dedupe.)
5. **Assign RUNTIME.** Under the same lock: `sequence = prev + 1`; `eventId = ULID`; `ingestTime = daemon clock` (the single trusted clock in the whole system); `seed = CSPRNG draw` (a `u128`, always stamped — § seed); `logPosition`; `reducerSetVersion`. **This is the only moment non-determinism is sampled.**
6. **Reduce in memory.** Run the registered (pure, total) reducers for this entity against the prior in-memory state and the fully-stamped event, producing the component deltas + provenance. No IO, no durability yet. Because reducers are total over well-formed events (reducer spec inv. 1), this cannot fail for an event that passed step 1; a reducer *bug* (panic) is caught at the host boundary and handled at commit (below) — it never aborts the append.
7. **Commit atomically + durably.** In **one storage transaction** (the daemon spec's storage-transaction property), append the fully-stamped event to the per-entity log, apply the component deltas + provenance, advance the projection checkpoint, update the summary index, and record `dedupeKey → (eventId, sequence)` in the dedupe index; `fsync`-on-commit *before* returning. The transaction lands **event-with-its-reduction or nothing**. Under the reducer-bug exception, the daemon commits the **event alone** and marks the affected component `degraded` (daemon spec) — the fact is preserved, the view is rebuildable by re-projection. This spec requires only that ack implies durable; the physical transaction is the daemon spec's.
8. **Ack.** Return `SubmitAck`. Only now is the producer permitted to consider the fact recorded. The ack carries no reduction outcome — reduction success is implied for a well-formed event (atomic with the append), and a degraded component is an internal diagnostic, not a producer-visible error.

> The seam: **ack ⇒ durable fact on the log (committed atomically with its reduction).** `submit` never *reads or queries* a component — the directionality invariant (ADR-0001 inv. 2) is about the read/query boundary, which `submit` never crosses. Folding the event into components inside the same write transaction is a write-side implementation detail (the daemon is the sole writer of both the log and its derived view), not a read on this path. The log remains the single seam to the read side; for a committed event the component view never lags the log (except a `degraded` component under a reducer bug, which re-projects).

## The daemon is the sole ordering authority

Per-entity total order is a *runtime-assigned* property, not a producer claim.

- **`sequence`** is a `u64`, **per `entityHandle`**, **monotonic from 1**, **gap-free**, assigned under a per-entity write lock (single-writer per entity; the daemon is the only writer of record — daemon spec). Gap-free + monotonic is what lets the reducer fold key on `sequence` and lets observers detect missed events.
- **No global order.** There is deliberately no cross-entity sequence. Two events on different entities have *no* defined relative order. The attention bus and rollups operate on the **materialized view** (and the always-resident summary index, attention spec), never on a globally-ordered log — which is precisely why no global order is needed (issue #4's asymmetry; `actor-model-prior-art.md`: a production actor runtime has no "query all actors" primitive, so cross-entity ordering is not the right tool).
- **`ingestTime` is the only trusted clock.** `occurredAt` is producer-proposed valid time and may be skewed, late, or wrong; reducers may *stamp* it into state/provenance but must never *branch on it versus "now"* (there is no "now" in a reducer — reducer spec rule 5). Recency/decay are query-time as-of computations (attention spec § decay).
- **Out-of-order / late arrival** (a webhook arriving after a later one): the daemon orders by **arrival** (the `sequence` it assigns), recording the producer's `occurredAt` as data. The fold is deterministic on `sequence`; recency that wants event-time uses `occurredAt` at query time. Both times are on every event, by contract — neither is dropped.

### Why runtime-assigned, not producer-asserted (the rejected CloudEvents Sequence)

The CloudEvents *Sequence* extension makes `sequence` a producer-asserted, per-`source`, lexicographically-compared string. We reject that for three reasons: (a) it scopes order to the *source*, but our aggregate boundary is the *entity* (one entity may receive events from several sources); (b) a producer-asserted order is unverifiable and forgeable, breaking the determinism + audit guarantees ADR-0001 inv. 3–4 depend on; (c) at-least-once redelivery would replay producer sequence numbers, defeating dedupe. Runtime assignment under a per-entity lock makes order **authoritative, gap-free, and forge-proof**.

## At-least-once + dedupe = effective exactly-once apply

Adapters live over unreliable transports (a webhook retried, an SSE reconnect replaying the tail, a process restart re-emitting its buffer). We therefore assume **at-least-once submission** and make **apply exactly-once** by deduplication — the idempotent-consumer pattern.

- The producer supplies a **stable `dedupeKey`** derived from the *source's own* notion of the event's identity (e.g. `github:check_run:<id>:<status>`), **not** random per attempt — a retry of the *same* fact must carry the *same* key. This is the CloudEvents `source`+`id` uniqueness rule, relocated to a producer-controlled key so the daemon can dedupe *before* assigning its own `eventId`.
- **Dedupe scope is per entity** (`dedupeKey` unique within `entityHandle`). A re-submitted key returns the **original** `SubmitAck` (`Deduplicated`) and appends nothing — the apply is a no-op, so reducers never double-count.
- **The dedupe index is bounded, with a safe v1 default.** It must retain keys at least as long as a producer might retry. **v1 normative default: retain, per `entityHandle`, the last `N = 1024` dedupe keys AND any key seen within the last `T = 24h` (whichever window is larger), evicting only keys that fall outside *both*.** This bounds the duplicate-risk window the spec must guarantee against. The matching **producer contract** is: a producer's maximum retry horizon for a given fact MUST NOT exceed `T` and MUST NOT span more than `N` later distinct facts on the same entity; a retry within that horizon carries the same `dedupeKey` and is guaranteed a `Deduplicated` no-op. A retry *outside* the horizon is by definition a new submission (effective-exactly-once-apply holds only within the contracted horizon). Defense in depth: reducers SHOULD additionally be idempotent on the semantic key where cheap, but the dedupe index is the primary mechanism. Tuning `N`/`T` per kind/adapter remains an open question; the daemon spec owns the physical store and compaction, but these defaults are normative until it overrides them.
- **Why not distributed exactly-once:** exactly-once *delivery* over an unreliable channel is impossible; exactly-once *effect* via idempotent apply is achievable and is what we guarantee (Kafka/EventBridge stance).

```jsonc
// dedupe index entry (per entity). Maintained transactionally with the append (step 7).
{ "dedupeKey": "github:check_run:99812:completed",
  "eventId": "01J...", "sequence": 4217, "ingestTime": "2026-06-10T18:22:05.913Z" }
```

## Events are facts; actions are a separate primitive

This is a hard architectural line, not a naming convention.

- An **event is a fact**: a past-tense, immutable statement that *something happened* (`workflow.blocked`, `ci.failed`, `review.approved`). It is addressed to an entity, never to a recipient, and cannot be rejected after it is true. Events are the *only* thing on the log.
- A **command/action is a request**: an imperative the daemon *may reject* (`rerun-ci`, `approve-phase`, `open-pr`). Actions, their manifests, capability requirements, preconditions, idempotency flags, and approval gates are owned by the **action/capability spec** — explicitly out of scope here.
- **The bridge:** when an action executes, its *result* re-enters the system as one or more **fact events** via the same `submit` path (e.g. action `rerun-ci` → on completion the adapter submits `ci.rerun.requested` then later `ci.passed`). Those result events carry `caused_by = <actionId|causingEventId>` in `correlation` so lineage is traceable. The action machinery never writes the log directly; it goes through `submit` like any other producer, and is capability-gated identically.

```
 producer/adapter ──submit(fact)──▶ [log] ──reduce──▶ components ──query──▶ read side
                                       ▲
 action/capability spec: invoke(action) ─┘  (action RESULT re-enters as a fact via submit)
        (commands are NOT facts and never land on the log; only their results do)
```

This keeps the log a pure record of *what happened*, never *what was asked* — so a replay reconstructs reality, not intentions, and the directionality invariant holds (the write boundary is `submit`; actions are upstream of it, not a second seam).

### The narration firewall, restated at the write boundary

`ProposedEvent` has **no narration field** and its `data` is bundle-factual. There is no code path by which a model output becomes a submittable event: narration is a separate non-authoritative projection (reducer spec § firewall) that *reads* facts and is never an input to `submit`. Only egress adapters emit narration, and they emit it *outward* to a surface, never *inward* to the log. This is structural (the type lacks the field), not policed at runtime.

## Schema-on-read and evolution (upcast-at-replay)

The log outlives reducer code and bundle versions; an evolution policy must exist **before any log is written** (a named top risk in the guidance). The decisive policy:

### Schema-on-read

- The daemon does **not** validate `data` against `dataschema` on write (it would couple core to bundle schemas and reject events whose schema the daemon doesn't hold). It validates only the **fixed ENVELOPE structure**.
- `dataschema` is a **label resolved against the bundle on read** (by the reducer/upcaster), not by core. Schema-on-read (DDIA document-model flexibility): the log stores bytes + a schema label; meaning is applied when a reducer reads them.

### Versioning surface (three independent versions)

1. **`specversion`** — the ENVELOPE contract (this spec). Changes rarely; core owns it; the daemon supports a known set and rejects unknown (`UnsupportedSpecVersion`).
2. **`dataschema`** (carries the **payload type version**, e.g. `…/ci.failed.v2`) — bundle-owned; the producer asserts which version it wrote.
3. **`reducerVersion` / per-component `schemaVersion`** — owned by the reducer spec; what the *projection* is on.

These are deliberately separate: an old *payload* version can be folded by a new *reducer* version via upcasting, and a *component* schema can evolve without touching the *event* schema.

### Upcast-at-replay (the log is never rewritten)

- **Additive, backward-compatible payload changes** (new optional field): handled by a **tolerant reader** — old events deserialize fine; the reducer treats the missing field as absent. No upcaster needed.
- **Breaking payload changes** (rename, restructure, split, semantic change): the bundle registers a **pure upcaster** `upcast(vN_bytes) -> v(N+1)` chained to the current version. At *read* time (replay/projection/snapshot rebuild), an old event's `data` is run through the upcaster chain before any reducer sees it. The reducer is written against the **latest** schema only.
- **The stored event is immutable.** Upcasting is a read-time transform; the log bytes are never edited (Axon/Event-Driven.io upcasting). This preserves the audit story and the `state(N) = fold(log[0..N])` identity (the fold is over *upcasted* events, deterministically).
- **Re-projection on reducer/upcaster change** is the rebuild mechanism (reducer spec § checkpoints/snapshot): bump `reducerSetVersion`, discard the now-stale snapshot, replay. `runtime.reducerSetVersion` stamped at ingest lets a snapshot be tagged and invalidated correctly. (See the open question on `attentionMap`: the hash backing `reducerSetVersion` must also cover declarative reducer-input data, not just module bytes.)
- **Correcting a wrong past fact** is done by **appending a corrective fact event** (e.g. `ci.failed` followed by `ci.result.corrected`), never by editing or deleting a log entry. v1 is as-of-transaction-time only (Datomic accumulate-only; no valid-time amendment).

```rust
/// Bundle-registered, PURE. Chained to the current version. Runs at READ time only.
/// Core never calls vendor logic here beyond invoking the registered chain (inv. 8).
pub trait Upcaster {
    fn data_schema_from(&self) -> &str;          // e.g. "bundle:loswf@2/ci.failed.v1"
    fn data_schema_to(&self)   -> &str;          // e.g. "bundle:loswf@2/ci.failed.v2"
    fn upcast(&self, data: &CanonicalValue) -> CanonicalValue;  // pure, total, deterministic
}
```

## Worked example (vendor concepts in the adapter layer only)

A GitHub adapter (examples layer) observes a failed check on issue 4217's PR and submits a fact. *Core ships none of these `type`/`payload` shapes; the adapter owns them.*

```jsonc
// ENVELOPE + PAYLOAD as submitted by the adapter (no RUNTIME region):
{
  "specversion": "ambisphere.event/1",
  "type": "ci.failed",                          // adapter-owned, past-tense
  "source": "adapter:github/acme-org",
  "entity": ["loswf","issue","4217"],           // compound address; resolves to a handle
  "subject": "check:build",
  "occurredAt": "2026-06-10T18:22:05Z",
  "dedupeKey": "github:check_run:99812:completed", // stable across webhook retries
  "datacontenttype": "application/json",
  "dataschema": "bundle:loswf@2/ci.failed.v2",
  "redaction": "none",
  "data": { "checkName": "build", "conclusion": "failure",
            "runUrl": "https://github.com/acme/r/runs/99812" }
}
// → daemon validates, authorizes the adapter's capability to emit to loswf:issue/*,
//   resolves the handle, dedupes on the key, assigns runtime{ sequence, ingestTime, seed, eventId },
//   reduces in memory, then commits event+reduction ATOMICALLY, acks. Downstream the bundle's
//   reducer maps it into example.workflow (blocked) and the attention scalars — reducer spec.
```

The same fact arriving twice (webhook redelivery) carries the same `dedupeKey`, is `Deduplicated`, and changes nothing — effective exactly-once apply.

## Acceptance criteria

A conforming implementation MUST satisfy, as automated tests:

1. **Sole ordering authority.** For any sequence of `submit` calls to one entity, assigned `sequence` is monotonic from 1 and gap-free; producer-proposed `sequence`/`eventId`/`ingestTime` (if smuggled in) are ignored and overwritten. Concurrent submits to one entity are totally ordered (per-entity lock).
2. **No global order.** No API returns a cross-entity total order; the only ordering exposed is per-`entityHandle`.
3. **Dedupe idempotence.** Submitting the same `dedupeKey` to the same entity N>1 times appends exactly once; every call returns the *same* `(eventId, sequence)`; the projection is identical to a single submit (no double-count).
4. **Ack ⇒ durable, event-with-reduction atomic.** After a successful `Appended` ack, a simulated crash-and-restart recovers the event on the log at the acked `sequence`/`logPosition`, **and** its component deltas/provenance are present (or, only under the reducer-bug path, the event is present and the component is flagged `degraded`). Fault injection between append and component upsert proves there is no state in which the event exists but a non-buggy reduction did not. (Physical durability/atomicity is the daemon spec's to implement — this is the same property as daemon AC "atomic append+reduce"; this test asserts the producer-facing contract.)
5. **Malformed rejected pre-log.** A structurally-malformed envelope returns `MalformedEnvelope` and writes nothing to the log (verifiable: log length unchanged).
6. **Determinism stamping + always-stamped seed.** Replaying a fixed committed log yields byte-identical `ReducibleEvent`s (the stamped `sequence`/`ingestTime`/`seed`/`eventId` are read from the log, never re-sampled). Every event carries a `u128` `seed` (none absent); the canonical encoding round-trips identically. Feeds the reducer spec's replay-equality test.
7. **Firewall (structural).** It is a *compile-time impossibility* to construct a `ProposedEvent` from a narration/model-output type (no field exists); a test asserts no `submit` path accepts a `kind:"narrated"` value.
8. **Credential never on the log.** No appended event contains a credential/secret; only `source` + opaque `capabilityRef` (provenance) appear. (Static + property test.)
9. **Vendor neutrality (allowlist-scoped).** Core code contains **zero** literal domain `type` values, no severity vocabulary, and never branches on `data`/`payload` internals or `khaos.*`/`loswf.*`. The only `type` literals permitted in core are the closed **core-reserved allowlist** (§ core-reserved event types); a lint/grep gate allowlists exactly that set and flags any other literal type. The same allowlist is the one all sibling vendor-neutrality lints reference.
10. **Upcast-at-read, log immutable.** An event written at payload `vN` is, after registering a `vN→vN+1` upcaster, delivered to the (vN+1) reducer in upcasted form, while the stored bytes remain `vN` unchanged (verifiable: re-read raw == original).
11. **Action-result re-entry.** An action's result reaches the log only via `submit` (no direct-append path exists), carrying `caused_by` correlation; a command itself never appears on the log.
12. **Dedupe horizon honored.** Re-submitting a `dedupeKey` within the v1 retention window (last `N=1024` / `T=24h` per entity) returns the original `(eventId, sequence)` as `Deduplicated`; a key evicted only after the contracted producer horizon. (Bounds the duplicate-risk window AC 3 depends on.)
13. **Core-reserved envelope conformance.** Every core-reserved `ambisphere.*` event validates against this spec's envelope contract (`specversion = "ambisphere.event/1"`, three-region split, daemon-assigned RUNTIME); no core-reserved fact uses a bare CloudEvents `specversion`. Its `dataschema` resolves to a core artifact.

## Open questions

- **Aggregate boundary for a rollup parent.** Does a parent (project/factory) entity get its own event stream, or is its state derived purely from child component state? (Leaning: derive from children at the read side per the attention/identity specs; a parent emits its own facts only for parent-level events.) Cross-ref: entity-identity spec, attention spec § rollup.
- **Thin vs fat default payload.** For externals that cannot be re-queried later (a GitHub check that may be deleted, a transient CI log), event-carried-state-transfer argues for *fat* events; for local re-queryable sources, *thin* is cheaper. Per-kind/adapter choice, or a core default? Cross-ref: adapter spec.
- **Dedupe index retention tuning.** *Decided for v1* (see § dedupe): retain per entity the last `N=1024` keys and any key within `T=24h` (larger window wins), with a matching producer retry-horizon contract. Still open: per-kind/per-adapter overrides and whether the daemon spec's compaction policy should make `N`/`T` configurable. Cross-ref: daemon spec (storage/compaction).
- **Are unauthorized/malformed *attempts* logged?** Rejecting before the entity log keeps the log clean, but an audit of *attempted* unauthorized emits is valuable. Reject-before-append (clean log) vs a separate audit log of attempts (security visibility)? Cross-ref: privacy/credential spec, action/capability spec.
- **Ingestion backpressure / rate-limiting.** What is the queue bound and the producer contract on `Backpressure` (retry-with-same-key is safe by dedupe, but a fairness/priority policy across noisy adapters is unspecified)? Cross-ref: daemon spec.
- **~~`seed` provisioning.~~** *Resolved* (see § seed): a `u128` is **always** stamped, canonical encoding fixed, and `ReducibleEvent.seed` becomes non-optional. (The on-demand byte-saving variant is rejected for v1.) Remaining downstream action: the reducer spec must drop the `Option`.
- **One shared partitioned log vs per-entity logs (physical).** The *ordering contract* is per-entity regardless; whether that is one table partitioned by handle or many is a storage decision. Cross-ref: daemon spec (StorageDriver).
- **`specversion` migration.** When the ENVELOPE contract itself must change (not the payload), do old events need envelope-level upcasting too, or is `specversion` frozen-once-written with a parallel reader? (Leaning: envelope-level upcaster chain, same mechanism as payload.)
- **Capability granularity for `emit`.** Per-entity vs per-kind vs per-namespace vs per-`type` scope on the emit capability — owned by the action/capability + privacy specs, but it constrains what `submit`'s authorize step checks. Cross-ref: action/capability spec.
- **`attentionMap` as a reduction input — replay hazard (cross-spec, must be closed before any log is written).** The declarative `attentionMap` in a bundle (bundle spec) is consumed by the *core* attention reducer, yet it is neither `prev` nor `ev`, so it tensions with the reducer purity rule "a reducer may read only `prev` and `ev`" and creates a replay hazard: changing a bundle's `attentionMap` would change derived attention scalars with no logged fact and no captured version. This spec's position (to be ratified into the reducer + bundle specs): the `attentionMap` (and any declarative reducer-input data core reducers consult) MUST be folded into the `reducerSetVersion` hash — the bundle spec currently hashes `(componentType, reducerVersion, module-digest)` over *modules*, and must extend the hash to cover declarative `.toml` reducer-input data too. Because `runtime.reducerSetVersion` is stamped here at ingest, that capture then either (a) lets the reducer read the `attentionMap` as part of the stamped event context (preserving `(prev, ev)`-purity), or (b) forces a deterministic re-projection on any `attentionMap` change (snapshots tagged with the old version are discarded). The reducer spec's purity section should state this rule so "`(prev, ev)`-only" and the `attentionMap` mechanism stop contradicting. Cross-ref: reducer spec § purity, attention spec, bundle spec § `reducerSetVersion` derivation.
- **Reducer-outcome enum alignment (cross-spec).** This spec and the daemon spec now agree on the ingest model (reduce-in-memory then atomic commit; reducer-bug ⇒ event-alone + `degraded` component). The **reducer spec** still describes a `Rejected(Defect)` outcome + defect-provenance for a "well-formed-but-unprojectable" event, which is a *third* vocabulary. These should converge on one outcome model. This spec's recommendation: keep `Updated`/`Unchanged` as the normal outcomes and use the daemon's `degraded`-component signal (plus its `projection.degraded` diagnostic) as the single failure path for both reducer panics and semantic-unprojectability; if `Rejected(Defect)` is retained, the daemon and this spec's AC 4 must adopt its enum and define `degraded` in terms of it. Owner: the daemon spec (it physically implements the atomicity + failure path); the reducer spec aligns its enum to it. Cross-ref: daemon spec, reducer spec § can-a-reduction-fail.
- **Adapter `ProposedEvent` shape divergence (cross-spec, mechanical).** The adapter spec's `ProposedEvent` carries a producer-supplied `capability_ref` field; **this spec's `ProposedEvent` deliberately has none** — the capability is the separate `cap` argument to `submit(cap, event)`, and `capabilityRef` is daemon-recorded *provenance* assigned after authorization (never producer-trusted). The envelope shape is authoritative: the adapter spec must remove `capability_ref` from `ProposedEvent` and present the capability via the `submit` argument. Flagged for the adapter spec to fix. Cross-ref: adapter spec § inbound port.
- **ADR-0001 status (cross-spec gating).** Every follow-on spec, this one included, declares "Conforms to: ADR-0001" and cites numbered invariants as binding, yet ADR-0001 is itself still "draft"/"Proposed". The suite cannot be implementation-ready while its foundational ADR is unaccepted, and the conformance tables cite invariant numbers that ADR-0001 must actually enumerate. Required: resolve ADR-0001 to a single status and add the canonical numbered invariant list it is cited against (and one sentence fixing the commit point: reduction commits atomically with the append). Until then this spec's conformance table is "conforms to the provisional ADR-0001". Cross-ref: ADR-0001, all sibling specs.
