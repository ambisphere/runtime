# Local daemon architecture and lifecycle

**Status:** draft · **Scope:** the single long-running local process that owns all entity state and is the sole writer to the per-entity append-only event log; the `StorageDriver` abstraction (SQLite/WAL default) over which both the log and the derived component view live; entity lifecycle and hibernation (cold/warm; wake on event/alarm/query); the always-resident cross-entity index that lets attention/rollups rank without waking cold entities; the **physical realization of the envelope spec's ingestion pipeline** (durable log append, then projection), with the **projection-write atomicity** property and the post-commit reducer-failure handling; two-layer crash recovery; the daemon-as-broker (a thin local UDS/loopback IPC seam — *not* a message-broker product, see § terminology — with capability-gated write ingest, cursor-resumable read subscription); single-instance enforcement and external supervision (launchd/systemd) · **Companion to:** `specs/VISION.md`, `specs/SRS.md`, `RFP.md` (§ "Local-First Philosophy", "Local daemon patterns", "Context persistence", "Performance constraints") · **Sequenced:** sixth among the follow-on specs (after the attention-bus, reducer/state-component, event-envelope, and entity-identity specs; before the renderer, action/capability, privacy, adapter, persona, and bundle specs) per ADR-0001 and issue #4 · **Conforms to:** ADR-0001 (foundational paradigm + directionality invariant + Rust core); the attention-routing spec (the always-resident summary index this spec owns is what the bus walks); the reducer/state-component spec (this spec owns the *physical* storage of checkpoints/snapshots/provenance and the projection-write atomicity reduction relies on; the reducer spec owns the reduction-outcome taxonomy — `Updated`/`Unchanged`/`Rejected(Defect)` — and the `degraded` component representation, which this spec references but does not redefine); the semantic-event-envelope spec (this spec *implements* the durability and ordering contract `submit` requires — including the **commit-then-reduce ordering**, which this spec implements verbatim and does **not** override — the "owned by the daemon spec" deferrals land here); the entity-identity spec (this spec stores the handle/address/edge tables and maintains the summary index the rollups walk) · **Sibling notes:** `specs/drafts/runtime-paradigm-and-specs-guidance.md`, `specs/drafts/actor-model-prior-art.md`, `specs/drafts/persona-prior-art.md`, `specs/drafts/implementation-language-guidance.md`

This spec defines the **host**: the one process that realizes everything the upstream specs describe at the storage and lifecycle layer. It is where the abstractions become a running program. The envelope spec defines `submit` and says "durability is owned by the daemon spec"; this spec implements that durability. The reducer spec defines snapshots and checkpoints as pure functions and says "the daemon spec owns their physical storage"; this spec stores them. The attention spec describes ranking "over the always-resident summary index"; this spec maintains that index. The identity spec defines handles, addresses, and edges; this spec persists them and resolves them at ingestion.

It owns no domain semantics, no event types, no reducer bodies, no attention math, no component schemas. It owns the *machine* those run on: a sole-writer process, a swappable storage engine, a lifecycle that lets thousands of mostly-idle entities cost almost nothing, and a local broker that lets producers write and observers read without either becoming an authority.

## Goals and non-goals

### Goals

- Define the daemon as a **single long-running local process** that is the **sole writer** of the per-entity append-only log and the only mutator of the derived component view.
- Define the **`StorageDriver`** seam: a language-neutral-in-spirit, Rust-trait-in-practice abstraction behind which SQLite/WAL is the default, so reducers/queries never see SQL and the engine is swappable.
- Implement the **envelope spec's ingestion pipeline as written**: durable log append (`fsync`-on-commit before ack), then projection (reduction) strictly downstream of that commit. Define the **projection-write atomicity** property — the per-event projection write (component upserts + provenance + checkpoint advance + summary-index delta) commits or aborts as one storage transaction — and the **post-commit reducer-failure handling** (deterministic `Rejected(Defect)` vs exceptional reducer-panic ⇒ `degraded`). This spec does **not** redefine the envelope's commit ordering; see § ingestion pipeline.
- Define **entity lifecycle and hibernation**: cold ↔ warming ↔ warm/active ↔ cooling ↔ cold, with wake on inbound event, persistent alarm, or a query that needs live derivation.
- Define the **always-resident cross-entity index** (identity / kind / edges / last-known attention summary) so the attention bus and rollups rank and aggregate **without waking cold entities** — the move that resolves the attention-vs-isolation tension at the storage layer.
- Define **two-layer crash recovery**: SQLite WAL auto-replay (storage layer) + application rebuild from the last verified snapshot watermark (projection layer).
- Define the **daemon-as-broker**: a local-only endpoint (Unix domain socket preferred, `127.0.0.1` loopback fallback); capability-gated addressed write ingest (`submit`); an SSE-style one-way **cursor-resumable** read subscription; a reserved bidirectional control channel.
- Define **single-instance** enforcement (advisory lock + socket bind) and **external supervision** delegation (launchd/systemd), with a **bounded graceful drain** on `SIGTERM`.
- Give concrete schemas/interfaces (fenced) and **acceptance criteria** that make the durability, atomicity, hibernation, recovery, and single-instance invariants testable.

### Non-goals (adopt/reject framing — rejections carried from the guidance)

- **Not** a distributed / replicated / clustered datastore. No replication, partitioning, sharding, quorum, or consensus. (Reject: distributed machinery — ADR-0001 local-first.)
- **Not** a cloud control plane or scale-to-zero serverless host. Hibernation is *local* disk-resting, not request-driven cloud cold-start. (Reject: RivetKit's serverless transport, Rivet cloud — `actor-model-prior-art.md`.)
- **Not** a bespoke process supervisor. The OS init system supervises the daemon; the daemon supervises only its own internal tasks. (Reject: a hand-rolled supervisor / init-system coupling beyond a thin notify shim.)
- **Not** a general-purpose message queue or broker product. The broker is a thin local seam over `submit` and the cursor stream; no topics, no fan-out exchange semantics, no external pub/sub. (Reject: Kafka/Redis/NATS as a dependency.)
- **Not** a single hard-wired storage engine. SQLite is the *default behind a driver*; nothing above the driver knows SQL. (Reject: hardcoding SQLite into reducer/query/identity code.)
- **Not** the definitions it hosts. The attention algorithm, the event envelope, the reducer language, the capability model, the identity scheme are sibling specs. This spec references their contracts and stores their data; it does not redefine them. (Reject: re-litigating upstream contracts here.)
- **Not** a place for vendor concepts. The daemon ships zero domain kinds/types/actions; it never branches on `payload` internals or `khaos.*`/`loswf.*`. (Reject: vendor leakage into the host.)

## Prior art (citations kept visible)

- **SQLite WAL mode (sqlite.org/wal.html; sqlite.org/forum process-vs-OS durability).** Adopt: WAL as the default embedded engine — **fully automatic crash recovery** from power-loss/hard-reset with no application action; readers don't block writers; a monotonic position usable as an observer cursor; checkpointing to bound WAL growth. Adopt the **explicit durability decision**: WAL with `synchronous=NORMAL` is durable across *application* crashes but a transaction may roll back on OS-crash/power-loss; `synchronous=FULL` `fsync`s the WAL on every commit and is durable across OS crash *given the storage device honestly flushes its cache* (the cited sqlite.org/forum thread is explicit that power-loss durability ultimately depends on hardware honoring the flush — see § durability boundary). We require **`synchronous=FULL` for the event log's append+commit** (the envelope's "`fsync`-on-commit before ack" contract) and permit `NORMAL` only for purely-derived projections that are rebuildable. Reject: `synchronous=OFF` for the log (sqlite.org notes commits are then not durable — `avi.im/blag/2025/sqlite-fsync`); reject hardcoding SQLite above the `StorageDriver`. (sqlite.org/wal.html; sqlite.org/forum/info/9d6f13e346231916; sqldocs.org/sqlite-write-ahead-logging.)
- **RivetKit lifecycle + hibernation (`actor-model-prior-art.md`; rivet.dev/docs).** Adopt: the hook vocabulary `createState`/`onCreate`/`onWake`/`onSleep`/`onDestroy`, a configurable `sleepTimeout`, `keepAwake` to hold off sleep, wake-on-message and **persistent alarms** that survive restart, and the **driver abstraction** ("write actors once, plug in any backend") as the precedent for `StorageDriver`. Adopt the **state-vs-vars discipline**: durable state is persisted, `vars` (live handles, caches) is ephemeral and lost on every sleep/wake/crash — mapped here to "warm-only working set vs durable log/components." Reject: serverless/HTTP-request execution, the coordinator super-actor as the cross-entity answer, RBAC-as-the-model, Rivet cloud.
- **DDIA — storage engines, stream–table duality, fault tolerance (Kleppmann, *DDIA* ch. 3, 11, 12).** Adopt: the **log-structured append-only** store as the system of record and the component view as a **materialized view / secondary derived data**; checkpoints + idempotent apply for rebuildable read models; **design-for-faults** (assume crash mid-operation; make recovery a first-class path, test it). The always-resident summary index is a *secondary index* over derived data (DDIA "derived data"), maintained synchronously alongside the primary projection. Reject: distributed storage, leader/follower replication, partitioning — none apply to a single local host.
- **SSE resumable streams (HTML Living Standard, EventSource `Last-Event-ID` / `id:` field).** Adopt: a **one-way, cursor-resumable** observation channel — the server emits monotonically-id'd events; a client that reconnects presents its last id and resumes without gaps. We map the SSE event `id` to the storage `logPosition`. Reject: WebSockets on the read path (bidirectional, heavier, no built-in resume); external pub/sub for fan-out.
- **Unix domain sockets (man unix(7)); loopback TCP fallback.** Adopt: UDS for local IPC — filesystem-permission-gated, no network exposure, lower overhead than loopback TCP; **`127.0.0.1` loopback as the fallback** where UDS is awkward (some Windows contexts, some sandboxes). Reject: binding any non-loopback interface by default (local-first privacy — RFP §10 via issue #5).
- **systemd / launchd supervision (freedesktop.org sd_notify; man launchd.plist; deterministic.space "writing a daemon").** Adopt: **external supervision** — the init system owns restart-on-crash, start-at-boot/login, and resource limits; the daemon implements a thin readiness/liveness shim (`sd_notify(READY=1)` on Linux; a launchd-friendly foreground-run + `KeepAlive` on macOS) and a **bounded graceful drain** on `SIGTERM`. Adopt **socket activation** as an optional path (init holds the listening socket, hands it to the daemon — also how launchd works). Reject: a bespoke supervisor, PID-file-based self-restart loops, and init-system coupling beyond the notify shim (the daemon must run un-supervised too, e.g. in a dev `foreground` mode).
- **Object-capability / POLA (ADR-0001 inv. 5; action-capability guidance).** Adopt: the broker's write side is **capability-gated at the boundary and only there**; an observer connection carries a (separately-gated) *read* capability and gets **zero** write authority by default. Reject: ambient authority on either channel; a login/identity server (the v1 single-principal keychain is RBAC-degenerate but ocap-shaped).

## Conformance to ADR-0001

| Invariant | How this spec honors it |
|---|---|
| (1) Log is source of truth; components derived, read-only | The durable log append (`commit_append`) is the only mutation of record and is what `submit` acks; the component view, provenance, checkpoints, snapshots, and the summary index are **all** derived projections (`commit_projection`, strictly downstream) behind the `StorageDriver`, droppable and rebuildable from the log. The projection may legitimately lag the log; it is never the source of truth. No API mutates a component directly. |
| (2) Directionality | The broker has exactly two data planes: **write** (`submit`, capability-gated, log-only) and **read** (cursor stream over the materialized view, separately gated). Capability checks live on the write boundary only; ECS-shaped queries live on the read side only; the log is the single seam. The daemon never queries across entities on the write path. |
| (3) Determinism | The daemon is the single place non-determinism is sampled (envelope spec: `ingestTime`, `eventId`, `sequence`, `seed` stamped at ingestion). Reducers run inside the daemon but are handed only stamped events; the daemon supplies them no clock/RNG/IO. Replay from the log is byte-identical (recovery and rebuild rely on this). |
| (4) Per-entity total order only | `sequence` is assigned under a **per-entity write lock**; the daemon is the sole authority. No global cross-entity order is stored or exposed. The `logPosition` cursor is a *storage* position for resumable observation, **not** a cross-entity logical order. |
| (5) Capability-shaped authority | Both broker planes are capability-gated; renderers/observers get no write authority by default (POLA). v1 may verify an RBAC-degenerate single-principal token; the contract stays ocap-compatible. The daemon holds capabilities; it never holds credentials. |
| (6) Fact/narration firewall | The daemon stores narrated projections in a **separate store** (reducer spec) that is never on the log, never an input to reduction, and never produced by a reducer the daemon runs. The cursor stream tags narrated frames distinctly; surfaces can subscribe factual-only. |
| (7) Credentials never in state/log | Neither the log, the component tables, the snapshot, nor the summary index ever stores a credential — only opaque `capabilityRef`s travel (envelope spec). The daemon's own secrets (if any) live in the OS keychain, never in entity storage. |
| (8) Vendor neutrality | The daemon ships zero domain kinds/types/reducers; it loads them from bundles (bundle spec) into the examples/adapter layer. Core daemon code never reads `payload` internals or `khaos.*`/`loswf.*`. |
| (9) Cross-language seams | The broker speaks a language-neutral framed protocol (CBOR/JSON envelopes over UDS/loopback). Renderers (Swift/Kotlin/TS/Go) and adapters (polyglot) interoperate without linking the Rust core. |

## Architecture overview

One process. Inside it, a small number of long-lived subsystems and a population of mostly-dormant entities.

```
                          ┌───────────────────────────────────────────────────────────┐
                          │                    ambisphered (Rust)                       │
                          │                                                             │
   adapters ──submit──▶   │  ┌──────────┐   ┌───────────────┐   ┌──────────────────┐    │
   (polyglot)             │  │  IPC seam│──▶│  Ingest core  │──▶│  StorageDriver   │    │
                          │  │  (UDS /  │   │ validate→auth │   │  (SQLite/WAL     │    │
   renderers ◀─cursor──   │  │ loopback)│   │ →resolve→dedup│   │   default)       │    │
   (best/platform)        │  │          │   │ →assign→APPEND │   │  ┌────────────┐  │    │
                          │  └──────────┘   │ +commit (fsync)│  │  │ event log  │  │    │
                          │       ▲         └───────┬───────┘   │  ├────────────┤  │    │
                          │       │ read         ack │  then     │  │ components │  │    │
                          │       │                  ▼ reduce    │  ├────────────┤  │    │
                          │  ┌────┴──────┐   ┌─────────────────┐ │  │ provenance │  │    │
                          │  │  Cursor   │◀──│  Projection /   │ │  ├────────────┤  │    │
                          │  │  fan-out  │   │  reducer host   │ │  ├────────────┤  │    │
                          │  └───────────┘   └────────────────┘ │  │ checkpoints│  │    │
                          │                                      │  │ snapshots  │  │    │
                          │  ┌──────────────────────────────┐    │  ├────────────┤  │    │
                          │  │ Always-resident summary index│◀───┼──│ edges/ids  │  │    │
                          │  │ (id/kind/edges/attn summary) │    │  └────────────┘  │    │
                          │  └──────────────────────────────┘    └──────────────────┘    │
                          │  ┌──────────────────────────────┐                            │
                          │  │  Lifecycle / alarm scheduler │  (cold↔warm, persistent    │
                          │  │  (sleep, wake, hibernation)  │   alarms, sleepTimeout)    │
                          │  └──────────────────────────────┘                            │
                          └───────────────────────────────────────────────────────────┘
                                 ▲ supervised by launchd/systemd (restart, start, drain)
```

Three things are *always resident* regardless of entity hibernation: the **IPC seam** (the local broker — see § terminology), the **ingest core**, and the **summary index** (+ its lifecycle scheduler). Everything per-entity (component working set, in-memory reducer state) is **paged in on wake and dropped on sleep** — the durable truth is always on disk in the log.

### Terminology: "broker" means a thin local IPC seam, nothing more

This spec, the renderer contract, and the adapter API all use "broker" for the daemon's local IPC surface. To prevent the term from being read as a licence for message-broker machinery (a non-goal in ADR-0001 and below), this is the normative, shared definition all three specs reference:

> **broker (in Ambisphere)** = the daemon's single thin local IPC seam over UDS/loopback, exposing exactly two data planes (`submit` write, cursor-resumable read) plus one reserved control channel. It has **no topics, no exchanges, no fan-out routing, no external pub/sub, no durable queue beyond the event log itself, and no network listener beyond loopback.** Any such feature is ADR-gated and out of scope. Where ambiguity is possible this spec prefers the phrase **IPC seam**; "broker" is retained only as the established shorthand for that seam.

## The `StorageDriver` seam

Everything that persists goes through one trait. Nothing above it knows SQL. This is what makes "SQLite default, swappable engine" real and keeps reducers/queries/identity SQL-free (ADR-0001 inv. 1 risk: "keep SQL behind the StorageDriver so reducers/queries never leak SQL").

```rust
/// The single persistence seam. SQLite/WAL is the default impl; alternatives
/// (e.g. a pure-memory test driver, or a future redb/fjall driver) implement the same trait.
/// Nothing above this trait constructs SQL. All methods are within ONE process (no network).
pub trait StorageDriver: Send + Sync {
    /// Open/create the store at `path`; run migrations; recover (WAL replay happens here,
    /// transparently, before this returns — layer-1 recovery). Returns the recovered watermark.
    fn open(path: &StorePath, opts: StorageOpts) -> Result<RecoveredState, StorageError>;

    /// STEP A — the durable write of record. Append the fully-stamped event to the log AND
    /// record its dedupe entry, in ONE storage transaction, fsync-on-commit (synchronous=FULL)
    /// BEFORE this returns Ok. On any error nothing is on the log. THIS is what `submit` waits
    /// for; ack ⇒ this returned Ok (envelope spec § ingestion order, step "append + commit").
    /// Reduction is NOT part of this call — it is strictly downstream (envelope spec, step 8).
    fn commit_append(&self, append: LogAppend) -> Result<Committed, StorageError>;

    /// STEP B — the projection write, downstream of (and after) commit_append. Apply ONE
    /// event's reduction outputs (component upserts, provenance rows, checkpoint advance,
    /// summary-index delta) in ONE storage transaction. All-or-nothing for THIS event's
    /// projection: either every output for the event lands or none does (projection-write
    /// atomicity, § ingestion pipeline). It NEVER touches the log (the event is already durable).
    /// Idempotent: re-applying an event whose sequence <= checkpoint.appliedThrough is a no-op
    /// (reducer spec checkpoint discipline), so this is safe to re-run during recovery.
    /// May run synchronous=NORMAL (it is rebuildable from the log).
    fn commit_projection(&self, proj: ProjectionWrite) -> Result<Projected, StorageError>;

    /// Append-only read of one entity's log slice in `sequence` order (for replay/rebuild).
    fn read_log(&self, entity: EntityHandle, from_seq: u64, limit: usize)
        -> Result<Vec<StoredEvent>, StorageError>;

    /// Tail the storage log by durable position (the observer cursor; powers the read stream).
    /// Returns events with monotonic `logPosition` strictly greater than `after`.
    fn read_from_position(&self, after: u64, limit: usize)
        -> Result<Vec<StoredEvent>, StorageError>;

    /// Read a derived component (materialized view). Pure read; no reduction triggered.
    fn read_components(&self, entity: EntityHandle) -> Result<EntityState, StorageError>;

    /// Snapshot lifecycle (bodies are pure functions owned by the reducer spec; this only stores).
    fn put_snapshot(&self, snap: Snapshot) -> Result<(), StorageError>;
    fn latest_snapshot(&self, entity: EntityHandle, reducer_set: ReducerSetVersion)
        -> Result<Option<Snapshot>, StorageError>;

    /// Per-projection checkpoint read (rebuild/resume; reducer spec owns semantics).
    fn checkpoint(&self, projection: ProjectionId, entity: EntityHandle)
        -> Result<Option<Checkpoint>, StorageError>;

    /// The always-resident summary index — a derived secondary view, maintained inside
    /// commit_projection (Step B) so it is written atomically with the components it summarizes.
    fn read_summary_index(&self, q: SummaryQuery) -> Result<Vec<EntitySummary>, StorageError>;

    /// Identity/edge tables (entity-identity spec owns the schema; daemon stores it).
    fn resolve_address(&self, addr: &EntityAddress) -> Result<Option<EntityHandle>, StorageError>;
    fn read_edges(&self, q: EdgeQuery) -> Result<Vec<Edge>, StorageError>;

    /// Persistent alarms (survive restart; power lifecycle wake-on-alarm).
    fn put_alarm(&self, alarm: Alarm) -> Result<(), StorageError>;
    fn due_alarms(&self, as_of_ingest_clock: Timestamp) -> Result<Vec<Alarm>, StorageError>;
    fn clear_alarm(&self, id: AlarmId) -> Result<(), StorageError>;

    /// Flush + checkpoint the WAL (bound its growth; called on cadence and on clean sleep).
    fn maintenance(&self, op: MaintenanceOp) -> Result<MaintenanceReport, StorageError>;
}
```

```rust
/// Step A input: what becomes durable BEFORE submit acks (envelope spec's "append + commit").
/// No reduction output here — reduction has not run yet.
pub struct LogAppend {
    pub event: StoredEvent,        // fully RUNTIME-stamped (envelope spec)
    pub dedupe_entry: DedupeEntry, // dedupeKey -> (eventId, sequence), per envelope step 6
}

/// Step B input: the projection write for ONE already-durable event, run AFTER its commit_append.
/// The reducer host has run the (pure) reducers against the prior projected state and assembled
/// these deltas; commit_projection writes them atomically. This is rebuildable from the log.
pub struct ProjectionWrite {
    pub for_sequence: u64,                         // the (already durable) event this projects
    pub for_log_position: u64,                     // links the projection to its log row
    pub component_upserts: Vec<ComponentUpsert>,   // from reducers (may be empty)
    pub provenance_rows: Vec<ProvenanceRecord>,    // co-equal reducer output (reducer spec)
    pub checkpoint_advances: Vec<Checkpoint>,      // appliedThrough = for_sequence
    pub summary_delta: Option<SummaryDelta>,       // keeps the always-resident index in sync
    pub degraded: Vec<DegradedComponent>,          // set ONLY on reducer panic (see § ingestion pipeline)
}
```

### Default driver: SQLite/WAL

- **Tables.** One append-heavy `event_log(log_position INTEGER PK AUTOINCREMENT, entity_handle, sequence, event_id, ingest_time, payload BLOB, ...)` with a unique index on `(entity_handle, sequence)` and on `(source, event_id)`/`dedupe_key`; per-component-type projection tables (or one `components(entity_handle, component_type, schema_version, data BLOB, kind, value_hash)`); `provenance`; `checkpoints`; `snapshots`; identity/`edges`; `alarms`; and the `summary_index`.
- **Durability.** `journal_mode=WAL`. **`synchronous=FULL` for the connection that runs `commit_append`** (the envelope contract: `fsync`-on-commit before ack). The projection connection (`commit_projection`) **may** run `synchronous=NORMAL`, because the projection is reconstructable from the log on recovery (DDIA derived-data discipline). Never `synchronous=OFF` for anything. The precise durability boundary is stated in § durability boundary — it is **not** an unconditional "durable across power loss" claim.
- **Cursor.** `event_log.log_position` (monotonic rowid) is the durable observer cursor — it is a *storage* order, used only for resumable streaming, never exposed as a cross-entity logical order (ADR-0001 inv. 4).
- **Determinism caveat (impl-language guidance).** Reducers run inside the daemon must never iterate a randomized-order map; the daemon's reducer host hands components in deterministic (`BTreeMap`/`IndexMap`) order and the replay-equality property test guards it.

## The ingestion pipeline (append, then project)

This section is the physical realization of the **envelope spec's** ingestion order. **The envelope spec is the single owner of the commit-ordering and reduction-failure contract; this spec implements it verbatim and does not redefine it.** (A previous draft of this spec "tightened" the envelope's wording into an atomic `append + reduce`. That was an architecture-process error — a downstream spec silently overriding a ratified upstream one — and is removed. The stronger atomic-append+reduce model is now an explicit cross-spec decision flagged in § open questions, to be settled in the envelope spec + ADR, not here.)

### The ordering, as the envelope spec fixes it

> **append + commit (durable, fsync, ack) → THEN reduce (project, downstream).** The fully-stamped event and its dedupe entry are committed and `fsync`'d in one storage transaction (`commit_append`); `submit` acks only after that returns. Reduction runs **strictly after** the durable commit (envelope spec step 8) and is **not** part of `submit`'s durability contract. The producer never sees a reduction error.

What this spec adds *underneath* that contract, without changing it:

- **Projection-write atomicity (this spec's property).** For a single already-durable event, all of its projection outputs — component upserts, provenance rows, checkpoint advance, summary-index delta — are written in **one** storage transaction (`commit_projection`), all-or-nothing. The projection can therefore lag the log (between `commit_append` and `commit_projection`), but it is never *partially* applied for an event, and the checkpoint never advances past what was actually written. This is the weaker, honest property that the commit-then-reduce ordering permits — not the cross-event atomicity the earlier draft claimed.
- **The actor model gives no transactional rollback for free** (`actor-model-prior-art.md`); we do not need it here, because the log is the truth and the projection is rebuildable. Consistency comes from idempotent, checkpointed re-projection (DDIA derived-data discipline), not from one giant transaction.

### Reduction-failure taxonomy (unified with the envelope and reducer specs)

There are exactly three outcomes, each owned by an existing upstream spec; this spec references them and does not invent a parallel model:

1. **Pre-durable rejection (envelope spec).** Malformed envelope, unauthorized, unknown entity, dedupe hit, backpressure — rejected by the ingest core **before any append**. Nothing is written; the producer gets a typed `SubmitError` (or, for a dedupe hit, the *original* `SubmitAck`). Reduction never runs.

2. **Deterministic reducer outcome (reducer spec).** Once the event is durable, the reducer host runs each interested reducer. A reducer is **pure and total over well-formed events** and returns one of the reducer spec's three outcomes — `Updated` / `Unchanged` / `Rejected(Defect)`:
   - `Updated`/`Unchanged` are projected normally.
   - **`Rejected(Defect)`** is the reducer spec's first-class, **deterministic** outcome for a well-formed-but-semantically-unprojectable event (e.g. a payload version a reducer predates). Per the reducer spec, the daemon leaves that component **unchanged**, writes the reducer spec's **defect provenance record** (`activity:"reduce", outcome:"rejected", reason`), and **advances the checkpoint** so the fold stays advanceable. A defect replays identically (it is deterministic), so it is not a "failure" of the pipeline — it is a recorded, auditable gap signalling "ship a new reducer version + re-project." The daemon does **not** mark the component `degraded` for a defect.

3. **Exceptional reducer panic (bundle bug) — the only non-deterministic failure.** If a registered reducer *panics* (a bundle bug, not a modelled outcome), the daemon: (a) catches the panic at the reducer-host boundary, (b) leaves the event **already durably on the log** (it was committed in Step A before reduction ran — no special handling needed; the fact is never at risk), (c) marks that entity's component projection **`degraded`** for the affected `component_type` (see § the degraded component state), (d) advances the checkpoint past the event **only for the components that did project**, holding the degraded component's sub-checkpoint back so re-projection is well-defined, and (e) emits a `projection.degraded` diagnostic on the control channel. The log is never blocked by a bad reducer; the *view* degrades, never the *truth*, and re-projection (drop + replay) recovers it once the bundle is fixed.

So the producer-facing `submit` never returns a reduction error under any of the three; the difference is entirely on the read side, where a component is either current, defect-flagged-stale (deterministic), or `degraded` (after a panic).

### The degraded component state

`degraded` is a **read-side projection state**, not a daemon-private flag. For it to be queryable and surfaceable it must be a real value in the component/projection model.

> **Ownership note (cross-spec).** The `degraded` representation — its schema, how it appears in `EntityState`, and how renderers/the attention bus must treat a degraded component — **belongs in the reducer/state-component model**, alongside `Rejected(Defect)`'s defect provenance. This spec uses it but does **not** own its schema. Until the reducer spec adds it, `degraded` is provisional; this is flagged in § open questions. The daemon's only owned responsibility is the *mechanism*: catch the panic, mark the component degraded via the projection write, emit the diagnostic, and re-project on demand.

```rust
/// Set ONLY on a reducer PANIC (case 3 above), carried in ProjectionWrite.degraded.
/// A deterministic Rejected(Defect) does NOT produce this — it produces the reducer spec's
/// defect-provenance record instead. The `degraded` *component representation* is owned by the
/// reducer/state-component model (see ownership note); this struct is the daemon-side signal.
pub struct DegradedComponent {
    pub entity: EntityHandle,
    pub component_type: ComponentType,
    pub at_sequence: u64,          // the event whose reduction panicked
    pub cause: ReducerFault,       // panic message / location, for the diagnostic (never a secret)
}
```

## Durability boundary (what "ack ⇒ durable" actually guarantees)

The envelope contract is "ack ⇒ durable fact on the log." This section states the **precise boundary** so the guarantee is honest and the acceptance test is well-defined (resolving the finding that an unconditional "durable across power loss" claim is unattainable on commodity hardware).

- **Guaranteed: durable across process crash and OS crash, given an honest flush.** With `synchronous=FULL`, SQLite issues an `fsync` of the WAL before `commit_append` returns; once acked, the event survives an `ambisphered` process kill (`SIGKILL`) and an OS-level crash/reboot, **provided the storage stack actually persists on flush**. WAL auto-replay on next `open()` restores it (layer-1 recovery).
- **Not unconditionally guaranteed: power loss.** True power-loss durability depends on the **storage device honoring the flush** (no volatile, un-backed write cache that lies about completion) and on the filesystem/driver propagating the barrier. SQLite's own forum (cited above) is explicit that this is a hardware/OS property, not something the application can promise. We therefore state the boundary as: *power-loss durable iff the device honors flush; on hardware that lies about flush, a small window of acked-but-lost writes is possible* — the same caveat that applies to every fsync-based system. We do not claim to defeat lying hardware.
- **Mitigation, not a promise.** Deployments that need stronger power-loss guarantees use battery-backed/PLP storage or a journaled filesystem with barriers enabled; that is an operational choice, not a daemon feature.
- **What the acceptance test injects (made concrete).** Acceptance #2 has two distinct injections: (a) a **process-crash test** — `SIGKILL` `ambisphered` immediately after ack, restart, assert the event is present (this exercises the application-crash guarantee and is fully deterministic in CI); and (b) an **honest-flush OS-crash simulation** — run against a storage layer that models `fsync` faithfully (e.g. a test `StorageDriver` or a FUSE/loopback device that discards only *un-flushed* pages on simulated crash, never flushed ones) and assert acked events survive. The test does **not** claim to simulate lying hardware; it asserts the guarantee *given* an honest flush, which is exactly the boundary stated above.

## Entity lifecycle and hibernation

Entities are mostly idle for hours (RFP "Context persistence"; ambient = long gaps between events). The daemon must make a dormant entity cost ~nothing while making wake transparent. We adopt RivetKit's vocabulary and add the cold/warm storage distinction.

### States

```
        ┌────────┐   wake trigger    ┌──────────┐  warmed   ┌───────────────┐
        │  COLD  │ ───────────────▶  │ WARMING  │ ────────▶ │  WARM/ACTIVE  │
        │ (disk  │                   │ (paging  │           │ (working set  │
        │  only) │ ◀──────────────── │  in)     │           │  in memory)   │
        └────────┘    cooled         └──────────┘           └───────┬───────┘
            ▲                                                       │ sleepTimeout
            │                          ┌──────────┐  idle elapsed   │ elapsed &
            └───────────────────────── │ COOLING  │ ◀───────────────┘ no keepAwake
               snapshot+flush, drop      │ (snapshot │
               working set                │ +flush)   │
                                         └──────────┘
```

- **COLD.** Nothing in memory. The entity exists only as rows on disk (log + last snapshot + summary-index entry). Costs one summary-index row. The vast majority of entities sit here.
- **WARMING.** A wake trigger arrived. The daemon loads the latest valid snapshot (reducer spec: `snapshot ⊕ tail ≡ replay`) and replays the log tail past `snapshot.throughSequence` to reconstruct the in-memory working set. `onWake` bundle hook (if any) fires.
- **WARM/ACTIVE.** Working set resident. Subsequent events for this entity reduce against in-memory prior state (fast path). `keepAwake(promise)` holds off sleep while long work is in flight (RivetKit).
- **COOLING.** `sleepTimeout` elapsed with no activity and no `keepAwake`. The daemon writes a fresh snapshot (clean-sleep snapshot bounds future replay), flushes, fires `onSleep`, and drops the working set.
- **back to COLD.** Memory reclaimed.

### Wake triggers (exactly three)

1. **Inbound event.** A `submit` addressed to a cold entity warms it (resolve → warm → reduce). The append is durable regardless of warm state; warming is only needed to compute the *in-memory* prior state for the reduction fast path. (On a cold entity the daemon may also reduce directly from snapshot+tail without a full "warm" if the event is the only pending work — an optimization, not a contract.)
2. **Persistent alarm.** A bundle scheduled a future wake (`schedule.at`/`after`, RivetKit alarms; stored via `put_alarm`, survives restart). At due time the scheduler warms the entity and delivers the alarm as an internal trigger that the bundle turns into a `submit` (alarms cause facts via the normal write path — they are not a back door to component mutation).
3. **Query needing live derivation.** Most reads are served from the **materialized view without waking anything** (that is the whole point of the summary index). A query warms an entity **only** if it needs derivation the stored view cannot answer (e.g. an as-of read at a `sequence` no snapshot covers). Whether such a query *may* force a warm is policy: **v1 default = yes, but the warm is read-only and the entity cools immediately after.** (Open question on a "never-warm, view-only" strict mode.)

```rust
pub struct LifecycleConfig {
    pub sleep_timeout: Duration,          // idle before COOLING (RivetKit sleepTimeout; default 30s)
    pub snapshot_on_clean_sleep: bool,    // default true (bounds future replay)
    pub max_warm_entities: usize,         // working-set memory budget; LRU-cool beyond it
    pub warm_on_query: WarmOnQuery,       // Allow (default) | Deny (strict view-only)
}
enum WakeTrigger { InboundEvent, Alarm(AlarmId), QueryNeedingDerivation { as_of: Cursor } }
```

### Why this resolves the attention-vs-isolation tension

Ambient runtimes have a structural conflict: the attention bus must rank **across all entities**, but most entities are cold and waking them all to rank them is fatal. The resolution is at the storage layer:

> The **always-resident summary index** holds the *minimum* the bus and rollups need — never the full entity state — so cross-entity ranking and `child-of` rollups read the index and **wake nothing**.

## The always-resident cross-entity index

A secondary derived view (DDIA secondary index over derived data), kept in memory and on disk, updated **inside `commit_projection`** (the same downstream projection write as the components it summarizes) so it is always consistent with what has been projected. It is the storage answer to "no coordinator super-actor" (`actor-model-prior-art.md`).

```rust
/// One row per LIVE entity, resident regardless of hibernation. The ONLY cross-entity
/// structure. Domain-neutral: holds the attention spec's scalars (it fixes the facet),
/// identity/kind/edge adjacency (identity spec), and recency — never domain payload.
pub struct EntitySummary {
    pub entity: EntityHandle,
    pub address: EntityAddress,           // for display/scope filtering (identity spec)
    pub kind: KindRef,                     // ambisphere.identity component (identity spec)
    pub lifecycle: LifecycleState,         // Cold | Warming | Warm | Cooling
    // --- attention summary (attention spec OWNS these field meanings; we only cache them) ---
    // NORMATIVE: every field here is DECAY-INVARIANT. No `rung`, no `score` is ever cached —
    // those are as_of-dependent and are ALWAYS computed at query time by the attention bus from
    // these inputs + as_of (attention spec "identical rankings for identical (view, as_of)").
    pub attn: AttentionSummary {           // last-known scalars, stamped by the attention reducer
        urgency: f32, importance: f32, actionability: f32,  // raw scalars (decay-invariant)
        decay_params: DecayParams,         // halfLife/curve/floor — the decay SHAPE, not a result
        state: AttentionState,             // dormant|active|awaiting-human|acknowledged|resolved|expired
        ceiling: Rung,                     // per-entity cap (decay-invariant policy, not a computed rung)
        anchor_time: Timestamp,            // for query-time decay (attention spec computes decay, not us)
        last_event_time: Timestamp,
    },
    // --- graph adjacency for rollups (identity spec OWNS child-of/instance-of) ---
    pub parent: Option<EntityHandle>,      // single-parent child-of (identity spec v1 default)
    pub child_count: u32,
    pub rollup: RollupSummary,             // DECAY-INVARIANT child-of aggregate ONLY (see below);
                                           // never a cached rollup rung/score
    // --- recency ---
    pub last_sequence: u64,                // current per-entity sequence (gap-free; envelope)
    pub last_log_position: u64,            // for cursor coordination
}

/// The materialized child-of rollup. NORMATIVE (co-fixed with the attention + identity specs):
/// it caches ONLY decay-invariant aggregates — never a computed rung/score, because those are
/// as_of-dependent and would go stale. The bus computes the rolled-up rung at query time from
/// these aggregates + as_of, exactly as it does for a leaf entity.
pub struct RollupSummary {
    pub contributing_count: u32,           // children currently contributing to the aggregate
    pub max_child_scalars: AttentionScalars, // max raw urgency/importance/actionability over children
    pub min_child_anchor_time: Timestamp,  // oldest contributing anchor (so decay is computed honestly)
    pub max_child_ceiling: Rung,           // the strongest cap any child may reach (policy, invariant)
    // NO rung. NO score. NO decayed value. All computed at query time.
}
```

- **What lives here:** identity, kind, lifecycle state, the attention **raw scalars + decay params + anchor/last-event times + state + ceiling** (all decay-invariant), `child-of` adjacency + a **decay-invariant** rollup aggregate, recency. Domain-neutral; **no payload, no full component state.**
- **What does not:** full entity components, narration, credentials, anything domain-specific, **and crucially no `rung` or `score`** at either the leaf or the rollup level. To go deeper than the summary, a consumer queries the entity (which may warm it).
- **Consistency:** updated atomically with the projection write that changed it (`summary_delta` in `ProjectionWrite`, written inside `commit_projection`), so once a projection lands the bus never reads a summary that disagrees with it. (Because the summary is derived, like every other projection it can lag the log between `commit_append` and `commit_projection`; it is never *inconsistent* with what has been projected.) Rebuilt with the projections on a reducer-set change.
- **Decay and rung are query-time.** The index stores only decay-invariant inputs; the bus computes decay, score, and rung against an explicit `as_of` at query time (attention spec inv. 2/3). The daemon **never** computes decay or rung and never mutates the summary on a timer. This is what makes `read_summary_index` return identical rankings for identical `(view, as_of)` — the guarantee the attention, identity, and persona specs all depend on.
- **The contract the attention spec relies on:** `read_summary_index(SummaryQuery{ scope, min_rung, as_of, limit, ... })` returns ranked-candidate summaries **without waking any cold entity**. This is the storage realization of `what_matters_now`.

## Two-layer crash recovery

Two independent layers, each correct on its own, composing to "no committed fact is ever lost and the view is always reconstructable."

**Layer 1 — storage (automatic).** SQLite WAL replays on `open()` with no application action (sqlite.org/wal.html). Any log append that was `fsync`'d before the crash (every acked event, because `synchronous=FULL`) is present after recovery; any half-written transaction is rolled back atomically. After `open()` returns, the **log is correct and durable.**

**Layer 2 — projection (application).** The component view, provenance, and summary index are derived and **may legitimately lag the log** — that is the expected steady state under commit-then-reduce: an event is durable (`commit_append`) before its projection (`commit_projection`) lands, and a crash in that window leaves the event on the log with no projection yet. This is not corruption; it is exactly what recovery exists to close. The per-projection checkpoint records `appliedThrough`, so on startup the daemon re-projects every event between each checkpoint and the log watermark — idempotently (re-applying `sequence <= appliedThrough` is a no-op). The only states recovery must reconcile are: (a) events committed to the log but not yet projected (the normal lag window), and (b) components left `degraded` by a reducer panic (re-projected if the bundle was fixed, else re-marked degraded deterministically). On startup the daemon:

```
recover():
  recovered = StorageDriver::open(path)        # layer 1: WAL replay; log is now authoritative
  watermark = max committed log_position
  for each projection P:
     cp = checkpoint(P)                          # last appliedThrough per entity
     if cp behind watermark for any entity:      # the normal commit-then-reduce lag window,
                                                 # plus any degraded/never-projected components
         load latest valid snapshot (reducerSetVersion-matched)
         replay log tail past snapshot.throughSequence through reducers
         commit_projection(deltas) per event     # idempotent: sequence <= appliedThrough is a no-op
     verify snapshot.stateHash == hash(project(log[0..through]))   # snapshot⊕tail≡replay
  rebuild summary index from current projections (cheap; it is small)
  resume broker; signal readiness to supervisor (sd_notify READY=1)
```

- **Idempotent re-apply** (reducer spec: `sequence <= appliedThrough` is a no-op) makes recovery safe to run any number of times.
- **Snapshot verification.** A snapshot is a pure function of a log prefix (reducer spec inv. 8); recovery verifies `stateHash` before trusting it and falls back to full replay-from-zero if it mismatches (e.g. corrupted snapshot) — the log is always sufficient.
- **`SIGKILL` safety.** Under hard kill mid-reduction (between `commit_append` and `commit_projection`), the in-memory working set is lost but the event is already durable; layer 1 guarantees the log is intact to the last ack; layer 2 re-projects the lagging tail. The property test (below) injects kills at every step, *including* the commit-then-reduce window, and asserts the rebuilt view equals a clean replay.

## The daemon as broker

The local IPC seam (see § terminology — "broker" here is *only* this thin seam). Two data planes (write, read) + one reserved control channel. Local-only by default.

### Channel taxonomy (resolving the channel-set inconsistency)

Two different things were being conflated under "channels"; this spec separates them, and the renderer contract is the owner of the first:

- **Observation channels (renderer contract owns the fixed set).** The renderer contract fixes **exactly three** observation channels — `state | attention | persona` — and declares them not redefinable downstream. A `subscribe` request selects a subset of *these three* (`ObservationChannelSet`). This spec does **not** add a fourth observation channel.
- **The control channel (broker construct, not an observation channel).** `control` is **not** one of the renderer's observation channels. It is a separate, reserved bidirectional broker channel (operator commands, diagnostics, drain requests, interactive control). It is established by a distinct connection/handshake, not by a `subscribe` over the read plane. Earlier drafts (and the persona spec's citation) listed a four-element `state | attention | persona | control` set; that conflation is corrected here — `control` is broker-only and distinct. (Cross-spec note: the persona spec should cite the renderer's **three** observation channels, not four; flagged in § open questions.)

### Endpoint

- **Default: Unix domain socket** at a fixed per-user path (e.g. `$XDG_RUNTIME_DIR/ambisphere/d.sock` on Linux, `~/Library/Application Support/ambisphere/d.sock` on macOS — exact path owned by the bundle/SRS). Filesystem permissions (`0600`, owner-only) are the first gate.
- **Fallback: `127.0.0.1` loopback TCP** on a fixed port, only where UDS is awkward (some Windows/sandboxed contexts). **Never** a non-loopback bind by default (local-first privacy; issue #5 §10).
- **Framing:** length-prefixed CBOR (JSON permitted for debugging) — a language-neutral framed protocol so any-language renderers/adapters interoperate without linking core (ADR-0001 inv. 9). Socket activation (init holds the socket, hands the fd over) is supported but optional.

### Write plane — capability-gated ingest

The broker exposes exactly the envelope spec's `submit` — no other write path exists (no `setComponent`, no append API).

```rust
/// Write plane. The ONLY mutation entry point. Capability-gated at this boundary and ONLY here.
fn submit(cap: &CapabilityRef, ev: ProposedEvent) -> Result<SubmitAck, SubmitError>;
// SubmitAck / SubmitError are defined by the envelope spec. The daemon implements the
// envelope's normative ingestion order EXACTLY: validate → authorize(cap) → resolve(address→handle)
// → dedupe → assign RUNTIME → commit_append(append + dedupe, fsync) → ack → [downstream] reduce.
// ack ⇒ durable fact on the log (envelope inv. 3). Reduction is strictly after ack (envelope step 8).
```

The daemon performs the **authorize** step against the presented capability (v1: verify a single-principal signed-scope token; the check stays ocap-shaped). It performs **resolve** against the identity tables (`resolve_address`). It performs **dedupe** against the dedupe index inside the same store. Then `commit_append` (the durable write `submit` waits on). **Reduction (`commit_projection`) runs strictly after the ack**, downstream of durability, per the envelope spec — it is never on the `submit` latency path and never affects the `submit` result.

### Read plane — cursor-resumable subscription

A one-way, SSE-shaped stream (HTML EventSource resumability). Separately capability-gated for *read* (ADR-0001: read authority is distinct from write; attention spec inv. 4 — reads may return redacted/coarsened facets).

```rust
/// Read plane. One-way, resumable. Observer presents a read capability and a resume cursor;
/// the daemon streams matching frames with monotonic logPosition ids. Renderers/attention
/// surfaces are PASSIVE observers (renderer contract); they hold NO write authority (POLA).
fn subscribe(cap: &ReadCapabilityRef, req: SubscribeRequest) -> Result<FrameStream, SubscribeError>;

pub struct SubscribeRequest {
    pub resume_from: Option<u64>,       // last logPosition the client saw (SSE Last-Event-ID); None = snapshot+tail
    pub scope: SubscriptionScope,       // by entity / kind / predicate over the materialized view (read side only)
    pub channels: ObservationChannelSet, // the renderer contract's THREE observation channels:
                                         // state | attention | persona. `control` is NOT here —
                                         // it is a separate broker channel, not an observation
                                         // channel (see § channel taxonomy and § control channel).
    pub include_narration: bool,        // default false — surfaces can subscribe FACTUAL-ONLY (firewall)
}

pub enum Frame {
    /// Initial snapshot of matched view (so a new observer is immediately correct), then deltas.
    Snapshot { at_position: u64, entities: Vec<ProjectedEntity> },
    /// Incremental change, id'd by durable logPosition for gap detection + resume.
    Delta { position: u64, entity: EntityHandle, change: ProjectedChange },
    /// Narrated projection — tagged distinctly; only delivered if include_narration (firewall).
    Narrated { position: u64, entity: EntityHandle, projection: NarratedProjection },
    /// Keepalive / heartbeat so a slow link can detect liveness without data.
    Heartbeat { position: u64 },
}
```

- **Resumability.** The frame `position` is the storage `logPosition`. A reconnecting observer sends `resume_from = last_seen_position`; the daemon replays frames with `position > resume_from` (via `read_from_position`). Gap-free monotonic ⇒ the observer can detect a missed frame and request a cheap full resync (renderer contract: snapshot + delta + monotonic version + resync).
- **Backpressure / slow observer.** For ambient *state*, latest-wins coalescing is correct (renderer guidance) — a slow observer may receive a coalesced delta or be told to resync rather than blocking the daemon. The read plane **never** applies backpressure to the **write** plane (a slow renderer cannot stall ingestion — directionality: read and write are separate planes).
- **No cross-entity order is implied.** `logPosition` orders the *stream*, not entities (ADR-0001 inv. 4); two entities' events interleave in storage order only.
- **Read-side projection, not raw components.** Frames carry *projected* view-models (renderer contract), and the read capability may coarsen/redact (privacy spec) — the broker is the enforcement point for read authority.

### Control channel — reserved, bidirectional

A single reserved bidirectional channel — **distinct from the three observation channels** (§ channel taxonomy); it is not selectable via `subscribe` and is established by its own handshake. It carries interactive control/chat and operator commands (health, focus-mode change, drain request, `projection.degraded` diagnostics) and **no ambient write authority** — any state change it triggers still flows through `submit` as a capability-gated fact (e.g. a focus-mode change emits `focus.modeChanged`, attention spec inv. 5). Chat retrieval reads via the read plane. This keeps the directionality invariant intact even for the interactive surface.

## Single-instance enforcement and external supervision

### Single instance

> Exactly one daemon may own a given store. Two writers would violate the sole-writer invariant (ADR-0001 inv. 4 — the daemon is the sole ordering authority).

Enforced by **two independent mechanisms** (defense in depth):

1. **Advisory file lock** on a lockfile beside the store (`flock`/`fcntl`). A second daemon that cannot take the lock exits with a clear "already running (pid N)" error. The lock is held for the process lifetime and released by the OS on death (so a crashed daemon's lock frees automatically — no stale-PID problem).
2. **Socket bind.** Binding the UDS path (or loopback port) fails if another instance holds it; combined with the lock this catches both "same store, different socket" and "same socket, different store" misconfigurations.

A stale UDS file from an unclean exit is reclaimed safely: the starting daemon, holding the advisory lock, knows no live owner exists and may unlink + rebind.

### External supervision (launchd / systemd)

The daemon does **not** supervise itself. Restart-on-crash, start-at-login/boot, and resource limits are the init system's job (deterministic.space; freedesktop.org).

- **Linux / systemd.** Ship a user `.service` unit, `Type=notify`; the daemon calls `sd_notify(READY=1)` only **after** recovery completes and the broker is accepting connections (so dependents start in order). `Restart=on-failure`. Optional `ambisphered.socket` for socket activation (init holds the listening socket). `TimeoutStopSec` bounds the drain.
- **macOS / launchd.** Ship a `LaunchAgent` plist; the daemon runs in the foreground (launchd-friendly), `KeepAlive` for restart, `RunAtLoad`. launchd's native socket-handoff mirrors socket activation.
- **Un-supervised / dev mode.** A `foreground` run mode for development and for environments without an init system; readiness is logged rather than notified.

### Graceful drain on `SIGTERM`

```
on SIGTERM:
  stop accepting NEW submits (return Backpressure/ShuttingDown for new writes)
  finish in-flight commit_append calls (each is already atomic; let them fsync) and let
    in-flight commit_projection calls finish (or leave the lag for recovery — it is safe)
  honor keepAwake promises up to a bounded budget (LifecycleConfig drain budget, default 5s)
  snapshot warm entities (clean-sleep snapshots → fast next start)
  flush + WAL checkpoint (maintenance)
  close broker; release socket + advisory lock
  exit 0  (within TimeoutStopSec / launchd budget; SIGKILL on overrun is SAFE by layer-1/2 recovery)
```

The drain is **bounded** (the supervisor will `SIGKILL` on overrun); correctness never depends on the drain completing — it is purely an optimization for fast restart. A `SIGKILL` mid-drain is recovered by the two-layer recovery above. A liveness/health probe (over the control channel and/or a `sd_notify(WATCHDOG=1)` ping) lets the supervisor detect a **wedged** (not crashed) daemon — the guidance top-risk "a wedge is harder to detect than a crash."

## Acceptance criteria

Each maps to an upstream invariant and is mechanically testable.

1. **Sole writer / single instance.** Starting a second daemon on the same store fails fast (advisory lock + socket bind); the first remains the only writer. Killing the first frees the lock and the second can then start.
2. **Durability boundary (ack ⇒ durable, precisely).** Two injections (§ durability boundary): (a) `SIGKILL` the process immediately after a successful `Appended` ack, restart, assert the event is present at the acked `sequence`/`logPosition` (application-crash guarantee, deterministic in CI); (b) an **honest-flush** OS-crash simulation that discards only *un-flushed* pages (never flushed ones) and asserts acked events survive. The test asserts the stated boundary — *durable across process/OS crash given an honest flush* — and does **not** claim power-loss durability against lying hardware.
3. **Projection-write atomicity (per event).** Fault injection inside a single `commit_projection` proves that event's projection write is all-or-nothing: either every output for the event (components + provenance + checkpoint advance + summary delta) lands or none does, and the checkpoint never advances past what was written. (This is the weaker, correct property under commit-then-reduce; it is **not** a claim that append+reduce is one transaction.)
4. **Commit-then-reduce lag is recoverable.** A crash injected in the window *between* `commit_append` and `commit_projection` leaves the event durable with no projection; restart re-projects it idempotently and the resulting view equals a clean replay. (This asserts the ordering this spec actually implements — the envelope's commit-then-reduce — not atomic ingest.)
5. **Failure taxonomy (three outcomes, no fourth).** (a) A pre-durable rejection writes nothing and returns a `SubmitError`. (b) A reducer returning `Rejected(Defect)` (reducer spec) leaves its component unchanged, writes a **defect provenance record**, advances the checkpoint, returns **no** reduction error to the producer, and replays **identically** (deterministic) — and does **not** mark the component `degraded`. (c) A reducer that **panics** leaves the event durable (it was already committed), marks the component `degraded`, emits `projection.degraded`, loses no fact, returns no reduction error, and re-projects cleanly after the bundle is fixed (drop + replay).
6. **Two-layer recovery / replay-equality.** `SIGKILL` at every ingestion step (including the commit-then-reduce window), then restart: layer-1 WAL replay + layer-2 projection rebuild reconstruct a view byte-identical to a clean replay-from-zero (`snapshot ⊕ tail ≡ replay`; reducer spec). Snapshot `stateHash` mismatch falls back to full replay and still converges.
7. **Summary index caches only decay-invariant values.** A static/property test asserts `EntitySummary`/`RollupSummary` contain no `rung`/`score`/decayed field; two `read_summary_index` calls with the same `(view, as_of)` return identical rankings, and changing only `as_of` changes the rung purely via query-time computation (attention spec parity).
8. **Hibernation transparency.** An entity cold for an arbitrary interval, then sent an event, produces the identical committed result as one that stayed warm (wake is transparent). A cold entity costs only its summary-index row (measured memory delta ≈ one row).
9. **Wake triggers.** Each of the three triggers (inbound event, due alarm surviving a restart, query-needing-derivation) warms the correct entity and only that entity; a query answerable from the view wakes nothing.
10. **Cross-entity ranking wakes nothing.** `read_summary_index` / `what_matters_now`-shaped queries over N mostly-cold entities return ranked candidates with **zero** entity warms (assert warm-count == 0). This is the attention-vs-isolation resolution, tested.
11. **Cursor resumability.** An observer that disconnects and reconnects with `resume_from = last_position` receives exactly the frames it missed, gap-free; a forced gap triggers a resync. A slow observer never stalls the write plane.
12. **Directionality at the broker.** There is no write path but `submit`; the read plane carries no write authority; the control channel's state changes all flow through `submit` as facts. A renderer connection cannot mutate a component (attempted direct write is unrepresentable in the protocol).
13. **Channel taxonomy.** A `subscribe` request can select only the renderer contract's three observation channels (`state | attention | persona`); `control` is not selectable on the read plane (a test asserts `ObservationChannelSet` has exactly three variants and the control channel is reached only via its own handshake).
14. **Capability gating.** `submit` without a valid capability returns `Unauthorized` and writes nothing; `subscribe` enforces a separate read capability and can return a redacted/coarsened projection.
15. **`StorageDriver` swappability.** The full conformance suite passes against both the SQLite/WAL driver and an in-memory test driver, proving nothing above the trait depends on SQLite.
16. **Bounded drain + supervised restart.** `SIGTERM` drains within the budget and snapshots warm entities; `SIGKILL` on overrun still recovers; under systemd `Type=notify`, `READY=1` is sent only after the broker accepts connections; the watchdog detects a wedged daemon.
17. **Vendor neutrality.** A lint/test asserts core daemon code never references `payload` internals, `khaos.*`/`loswf.*`, or any domain kind/type, and references core-owned component types only via the ADR/reducer-spec closed list (§ open questions); all reducers/kinds are bundle-loaded.

## Open questions

- **Snapshot cadence + log compaction/retention.** Full-audit retention vs truncate-behind-verified-snapshots pull opposite ways (guidance top-risk "unbounded log growth"). What is the default cadence (every N events? on clean sleep only? both?) and the minimum-lineage retention policy that preserves "why is this blocked?" provenance while bounding disk? Needs a DDIA spike at realistic Khaos/LOSWF event rates. Cross-ref: reducer spec (snapshot purity), envelope spec (dedupe-index retention).
- **One shared partitioned log vs per-entity logs (physical).** The ordering contract is per-entity regardless (envelope inv. 4); whether the default driver uses one `event_log` table partitioned by handle or one table-per-entity is a measured storage choice (write amplification, open-handle cost, vacuum behavior). Leaning: one table, indexed by `(entity_handle, sequence)`.
- **`warm_on_query` strict mode.** Should a "never-warm, view-only" mode be first-class for privacy/perf-critical deployments (a query that the view cannot answer simply fails rather than waking a cold entity)? v1 default allows the read-only warm; the strict mode is unspecified.
- **Summary-index contents, co-designed with the attention bus.** Exactly which scalars/edges live resident is a joint decision with the attention spec (which is sequenced first and fixes the facet). Is the rollup summary stored materialized in the index, or recomputed from resident child summaries on query? Leaning: materialized **decay-invariant** `child-of` rollup updated in `commit_projection` (never a cached rung/score — see § the always-resident cross-entity index).
- **Where the capability check sits relative to append.** Reject-before-append (chosen here, matching envelope ingestion order) vs log-then-validate-with-audit-of-attempts (would record unauthorized attempts as facts for security audit). v1 rejects before append; an opt-in attempt-audit log is an open question.
- **Backpressure / fairness across noisy adapters.** The write plane has one queue; a fairness/priority policy across adapters (so a chatty CI adapter cannot starve a low-rate approval adapter) is unspecified. Cross-ref: envelope spec (`Backpressure` contract).
- **Reducer execution isolation depth.** v1 catches reducer panics at the host boundary (degraded-component path). Should untrusted third-party bundles run in a WASM sandbox (adapter guidance cites WIT/Component Model as a *future* path) rather than in-process? Out of scope for v1; flagged for the bundle/adapter specs.
- **Watchdog semantics.** Should the daemon use `sd_notify(WATCHDOG=...)` with `WatchdogSec` so systemd hard-restarts a wedged daemon, and what is the macOS/launchd equivalent (there is no native watchdog ping)? Needs a per-platform decision in the supervision packaging.
- **Multi-store / multi-tenant on one host.** v1 assumes one store per daemon (clean sole-writer). Whether one host process may own several independent stores (e.g. per-namespace isolation) or that must be separate daemons is open; leaning separate daemons for invariant clarity.

### Cross-spec contract decisions surfaced by review (must be settled in the owning spec, not here)

These are items an earlier draft resolved by silently overriding an upstream spec. They are deliberately **not** decided in this downstream spec; each names its rightful owner. Until settled, this spec conforms to the *existing* upstream wording.

- **Append+commit ordering: commit-then-reduce (current) vs atomic append+reduce (recommended by review). [Owner: envelope spec + ADR-0001.]** This spec now implements the envelope spec's commit-then-reduce ordering verbatim (durable append + ack, then downstream reduction; projection may lag), and provides only per-event projection-write atomicity. The adversarial review recommends the **stronger** model — event + reduction outputs committed in one storage transaction — because it removes the lag window and gives stronger read-side consistency. That change is legitimate only if the **envelope spec amends step 8** (reduction commits atomically with the append, still pure, still no producer-facing reduction error) **and ADR-0001 adds one sentence fixing the commit point**, after which all three specs state it identically. This spec is written to be re-pointed at that model with minimal edits (`commit_append` + `commit_projection` collapse back into one `commit_ingest`), but it will not adopt it unilaterally. Recommended resolution: adopt atomic append+reduce upstream, then update this spec to match.
- **The `degraded` component representation. [Owner: reducer/state-component spec.]** This spec needs `degraded` to be a real, queryable read-side state (set on reducer panic). Its schema, its appearance in `EntityState`, and the rule that renderers/the bus must treat a degraded component as flagged-stale belong in the reducer/component model, next to `Rejected(Defect)`'s defect provenance. The reducer spec's `ReduceOutcome` enum (`Updated`/`Unchanged`/`Rejected(Defect)`) is the authoritative deterministic taxonomy; `degraded` is the *exceptional* (panic) outcome and must be added there with matching acceptance criteria. Until then, `degraded` here is provisional.
- **Persona spec's channel citation. [Owner: persona spec / renderer contract.]** The persona spec cites a four-element `state | attention | persona | control` channel set; per § channel taxonomy the renderer contract fixes **three** observation channels and `control` is a broker-only construct. The persona spec should be corrected to cite the three observation channels; the renderer contract should state explicitly that `control` is not one of them.
- **Closed list of core-owned component types. [Owner: ADR-0001 or reducer spec.]** This spec references core-owned components (`ambisphere.identity`, an `ambisphere.lifecycle`-style state, the `attention` facet) but several specs each introduce core components ad hoc while claiming minimalism. A single **closed, ADR-fixed enumeration** of core-owned component types (attention, identity, lifecycle, approvals) should exist and be referenced by the identity, daemon, persona, and bundle specs rather than each adding to it. Acceptance #17 already anchors the daemon's vendor-neutrality lint to that list once it exists.
- **ADR-0001 status. [Owner: ADR-0001.]** This spec, like the other eight follow-ons, declares "Conforms to: ADR-0001" and cites numbered invariants as binding, yet ADR-0001 is itself marked draft/Proposed. The suite cannot be implementation-ready while its foundational ADR is unaccepted and lacks a canonical numbered-invariant list. ADR-0001 must resolve to a single status and publish the invariant anchor the nine conformance tables cite; until then this spec's conformance table is provisional.
