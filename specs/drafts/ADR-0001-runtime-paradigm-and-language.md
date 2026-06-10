# ADR-0001: foundational runtime paradigm and per-tier implementation language

**Status:** accepted · **Scope:** ratifies the runtime's computational paradigm and per-tier implementation language as decisions of record, and fixes the canonical numbered invariants the follow-on specs conform to · **Companion to:** `specs/VISION.md`, `specs/SRS.md`, `RFP.md`, issues #4, #5, #6, roadmap #1 · **Sibling notes:** `specs/drafts/runtime-paradigm-and-specs-guidance.md`, `specs/drafts/implementation-language-guidance.md`, `specs/drafts/actor-model-prior-art.md`, `specs/drafts/persona-prior-art.md`

This ADR uses MADR format. It ratifies — it does not re-litigate — the two decisions that issues #4 (foundational paradigm), #5 (vendor adoption requirements), and the eleven-analyst synthesis converged on, and which issue #6 requests as a decision of record. Per VISION principle 5 ("specs before code"), committing to event-sourcing-as-source-of-truth and a core language are significant architectural decisions and must be recorded as an ADR with rationale and visible open questions. Open questions are carried forward, not silently resolved.

## Status

**Accepted** (MADR lifecycle: `Proposed` → **`Accepted`**).

This ADR was previously circulated as `Proposed`. It is now `Accepted`: the two decisions (D1 paradigm, D2 per-tier language) are binding decisions of record, and the nine follow-on specs that declare `Conforms to: ADR-0001` cite a settled foundation. The acceptance gate that the earlier draft deferred is recorded — with owners and concrete artifacts — under "## Acceptance criteria (met at acceptance)" below; each item is now a checkable artifact rather than a vague aspiration. The single contestable sub-decision (core = Rust vs Swift) is recorded as decided with an explicit, dated revision trigger: if team-fluency ratification flips it, this ADR is **superseded by a numbered revision, never edited in place** (so downstream conformance anchors stay stable).

There is exactly one status value for this record: **Accepted**. The header line, this section, and the introductory sentence agree.

## Context

Ambisphere runtime explores whether **ambient entities** — persistent, lightweight, contextual presences — can become a reusable interaction primitive (`RFP.md`, `specs/VISION.md`). The runtime is renderer-agnostic, persona-agnostic, domain-agnostic, local-first/daemon-oriented, and carries no transport/AI/framework lock-in (VISION principles 1–6).

Two coupled decisions block all downstream spec work:

1. **The computational paradigm.** Issue #4 frames the choice as actor model vs ECS vs hybrid and establishes the decisive asymmetry: cross-entity visibility (the attention bus) is the project's core novelty and the one thing actors cannot do without a privileged super-actor or a duplicated index — confirmed empirically against a production actor runtime (RivetKit has no "query all actors" primitive; its only answer is the coordinator-actor anti-pattern; `specs/drafts/actor-model-prior-art.md`). Conversely, capability boundaries and fault isolation are the one thing a flat, freely-mutable ECS cannot do. Issue #5 (Khaos Machine + LOSWFX adopters) constrains the choice with concrete requirements: durable contextual identity, cross-entity rollups and attention routing, capability-gated event/action boundaries, multiple renderers, local-first adapters, persona-as-projection, and a hard factual-state-vs-generated-narration separation (#5 §4).

2. **The implementation language, per tier.** The architecture's IPC seams (a renderer observation contract and an adapter event envelope) are language-neutral by design, which makes a single-language stack neither necessary nor best: no candidate is strongest across the headless core, native renderers, and polyglot adapters at once (`specs/drafts/implementation-language-guidance.md`).

The prior working synthesis used the shorthand "CQRS over an ECS core." That phrasing is the specific thing this ADR must correct, because "ECS core" implies a shared, freely-mutable component store as the system of record — the textbook definition of **ambient authority**, precisely what object-capability security exists to eliminate (Dennis & Van Horn 1966; Miller, *Robust Composition*). You cannot bolt object-capability authority onto a shared-write ECS core without contradicting its semantics.

## Decision drivers

- **Object-capability unforgeability** — authority must be a possessed, unforgeable, attenuable reference, not an identity/role check. This is incompatible with a freely-mutable component store as system of record.
- **Cross-entity visibility** (the attention bus) — the project's hardest novel problem; trivial on an ECS-shaped read side, unsolved in actor runtimes (#4; `actor-model-prior-art.md`).
- **Per-entity isolation, durability, and auditability** — a buggy operational entity must not corrupt another; operational adopters require audit (#5 §4, §10).
- **Fact/narration firewall** — deterministic factual state must be structurally separable from AI-generated narration (#5 §4); narration must never contaminate the system of record.
- **Transactional reduction with rollback** — required, but NOT a free property of the actor model (`actor-model-prior-art.md`); it must be specced explicitly via an event-sourced log committed atomically with its reduction.
- **Local-first, single-daemon discipline** — adopt the patterns (event sourcing, CQRS, ocap, snapshots); reject all distributed/cloud machinery (VISION principle 4).
- **Vendor neutrality** — core ships zero *domain* kinds/types/actions; all Khaos/LOSWF concepts live in the examples/adapter layer (#5 "Relationship to issue #4").
- **For language:** memory safety underwriting capability unforgeability; compile-time enforcement of derived-never-authoritative and the firewall; deterministic-reducer control; embedded-SQLite quality; low idle footprint for an always-on daemon; single-binary distribution; maturity ("do not found on a moving target"); ecosystem (crypto for macaroons, serialization); contributor pool.

## Considered options

### Paradigm

- **Option P1 — Pure actor model.** Entities as actors; addressed message-passing; per-entity isolation. *Pro:* clean event delivery, isolation, ocap-compatible lineages exist (Spritely Goblins). *Con:* no cross-entity query — the attention bus becomes a coordinator super-actor or a duplicated index; multi-entity rendering means reassembling per-actor subscriptions; transactional rollback and capability security are lineage-specific, not free (`actor-model-prior-art.md`).
- **Option P2 — Pure / "CQRS over an ECS core."** Freely-mutable component store as system of record; systems sweep and write. *Pro:* trivial cross-entity queries; persona-as-optional-component; low barrier. *Con:* **rejected** — a shared-write component store is ambient authority; no isolation or security boundary; tick-driven by tradition; failed reducers leave inconsistent components with no transactional guarantee (#4 "ECS weaknesses").
- **Option P3 — Capability-gated actor-write / event-log-source-of-truth / ECS-read materialized view (the hybrid).** Three layers with strict directionality. *Pro:* each paradigm owns the side it is strong on; the log gives transactional reduction-with-rollback, auditability, and the fact/narration firewall simultaneously. *Con:* the hybrid-complexity tax — two representations to keep consistent (issue #4's named risk), mitigated by the directionality invariant and the atomic append+reduce commit point fixed below.

### Core language

- **Rust** — strongest, safest core; ownership/borrow checking enforces read-only-projection and capability invariants at compile time; no GC for an always-on hibernating daemon; `rusqlite` + WAL first-class; mature crypto/serde. Weak at native mobile/desktop GUI (irrelevant to a headless core).
- **Swift 6.3 (6.4 in development)** — co-leader: memory-safe, ADTs, ARC (no GC pauses), actors/`Sendable` for the write side, GRDB for SQLite, and now an officially maintained Android SDK + Static Linux SDK + server-side maturity (Swift 6.3, March 2026 — swift.org/blog/swift-6.3-released; infoq.com/news/2026/04/swift-6-3-android-c-interop). A fully defensible alternative; keeps its home as the flagship Apple renderer regardless.
- **Rejected for core:** C/C++ (memory-unsafety undermines capability unforgeability), Zig (pre-1.0, unstable async/IO — fails "do not found on a moving target"), JVM-Kotlin / Node-TypeScript (footprint/weak invariant enforcement for an always-on system of record), BEAM/Go (no compile-time enforcement of the projection invariant at the strength required).

## Decision

### D1 — Foundational paradigm

Adopt **Option P3**: a **capability-gated, actor-bounded write side over a per-entity append-only event log (the single source of truth), with an ECS-shaped read side as a materialized view of typed components.**

Three layers, with strict directionality:

1. **Write side (command/ingestion) — capability-gated actor semantics per entity.** Each entity owns a logical mailbox; semantic events/actions arrive as addressed, capability-checked commands; the entity is the unit of identity, isolation, and fault containment. Adopt RivetKit's proven lifecycle (`createState`/`onCreate`/`onWake`/`onSleep`/`onDestroy`, `sleepTimeout`, `keepAwake`, compound-key addressing, persistent alarms; `actor-model-prior-art.md`). Capability gating lives here and only here.
2. **Source of truth — per-entity append-only event log + deterministic reducers.** Reducers fold the log into component state. The append of a well-formed event and the commit of its reduction outputs are **one storage transaction** (see "Commit-point invariant" below). This is where event sourcing earns its keep: transactional reduction-with-rollback, auditability (#5 §4), and the factual-vs-narration separation, simultaneously.
3. **Read side — components as a materialized view**, "ECS-shaped" in query ergonomics only: entities are IDs, state is typed components/facets, and renderers + the attention bus are read-only systems iterating entities by component presence.

```text
WRITE (capability-gated, addressed, actor mailbox)
  submit(event) ──▶ [ append-only per-entity event log ]   ◀── single source of truth
                          │  append + reduce commit ATOMICALLY (one storage txn, one fsync)
                          │  (pure, deterministic reducers; replay = byte-identical)
                          ▼
                   [ component materialized view ]          ◀── derived, read-only projection
                          │  (ECS-shaped query only)
                          ▼
READ (passive, subscription-based)  ──▶ attention bus · renderers · rollups · persona
```

**The directionality invariant (the headline rule):** capability/actor semantics live **only** on the write boundary; ECS-shaped query lives **only** on the read side; **the log is the single seam.** Any feature that writes a component directly, or queries across actors on the write side, is violating the model.

**Explicit rejection:** "CQRS over an ECS core" / a freely-mutable component store as the system of record (ambient authority). Components are **never** the authority — stream-table duality means they are a rebuildable projection (Kleppmann, *DDIA* ch. 11/12). This is the single most important framing decision in the ADR.

### Canonical invariants (the conformance anchor)

The following nine invariants are the **canonical, numbered** invariants of this runtime. Every follow-on spec's "Conforms to: ADR-0001" table cites these numbers; they are the single source of truth for invariant numbering across the suite. No spec may renumber or independently redefine them; a spec MAY add its own local invariants, but those are namespaced to that spec (e.g. "envelope spec inv. 5") and never collide with the ADR numbering below.

| # | Invariant | Statement |
|---|---|---|
| **1** | **Log is source of truth; components derived, read-only** | The per-entity append-only event log is the sole system of record. Components/facets/rollups/attention-state/persona/renderer-frames are derived, read-only materialized views, rebuildable by replay. The only write path is `submit`; there is no `setComponent`/`setEdge`/log-append back door. |
| **2** | **Directionality** | Capability/actor semantics live only on the write boundary; ECS-shaped query lives only on the read side; the log is the single seam. The runtime never queries across entities on the write path and never writes a component outside a reducer. |
| **3** | **Determinism of reducers** | Reducers are pure and total: `reduce(prevState, event) -> {nextState, provenance}`, no IO/clock/RNG, no randomized-map iteration (use `BTreeMap`/`IndexMap`, never raw `HashMap` iteration inside reducers or read-side ordering). All non-determinism (time, ids, seeds) is stamped into the event at ingestion; replay is byte-identical (a required property test). |
| **4** | **Ordering & sole writer** | Per-entity total order only; no global cross-entity logical order. The daemon is the sole writer to a given store and the sole authority for `sequence`/`ingestTime`/durable position; producers propose, never assign. Storage/stream position (e.g. `logPosition`) is a resumable cursor, never a cross-entity logical order. |
| **5** | **Capability-shaped authority** | Authority is possessed, attenuable, unforgeable, checked only at the write boundary; read authority is separately gated from write authority; renderers/observers get zero write authority by default (POLA). Manifest flags (`destructive`/`confirmRequired`) are UX hints, never the security boundary. v1 MAY ship an RBAC-degenerate single-principal keychain/signed-scope implementation, but the contract MUST stay ocap-compatible (macaroon-style attenuation; Birgisson et al. 2014). RBAC-with-accounts as the model is rejected. |
| **6** | **Fact/narration firewall** | Factual state is produced only by deterministic reducers. AI narration is a separate, explicitly-tagged, non-authoritative projection that reads facts; it is never an input to any reducer and never written to the log. Surfaces MUST be able to render factual-only; only declared egress/narration adapters may write narration, and only to the narration store. |
| **7** | **Credentials never in state, components, or the log** | Secrets/credentials live with the adapter that holds them. Only an opaque `capabilityRef` (provenance) travels through `submit` and onto the log; no credential ever appears in an event, a component, a snapshot, or the log. |
| **8** | **Vendor neutrality — zero domain types; enumerated runtime-meta types allowed** | Core ships **zero *domain* kinds, domain event types, domain actions, or severity/kind vocabulary**, and core code never branches on `payload`/`ext` internals or `khaos.*`/`loswf.*` types (lint-enforced). Core **does** define a small, **enumerated, domain-neutral set of runtime-meta event types** it reserves and may emit/handle in core reducers (see "Runtime-meta event allowlist" below). Vendor concepts (Khaos Machine — khaosd, KSPD, factory state; LOSWF/LOSWFX) live only in the examples/adapter layer. |
| **9** | **Cross-language seams** | The two IPC seams (the write envelope and the read observation/projection contract) are language-neutral framed protocols (CBOR/JSON over UDS/loopback). Renderers (Swift/Kotlin/TS/Go) and adapters (polyglot) interoperate without linking the Rust core. The core daemon is Rust (D2). |

#### Commit-point invariant (resolves the append/reduce ordering contradiction)

This ADR fixes the one point on which the envelope spec and the daemon spec previously diverged. The earlier envelope wording ("reduction is strictly *after* the durable commit"; "there is no 'reduction failed' error; a well-formed event is always appended") read as *temporal* sequencing, while the daemon spec ran reducers **in memory** and committed event+reduction **atomically** in one storage transaction, and described itself as "tightening the envelope spec's wording." Two specs cannot adjudicate this between themselves; the ADR adjudicates it once, here, as a binding part of invariants 1 and 4:

> **Append and reduce commit atomically.** For a well-formed event, the daemon runs the (pure, total) reducers **in memory** against the prior state, then commits — in **one storage transaction with a single `fsync`** — the fully-stamped event together with its reduction outputs (component upserts, provenance rows, checkpoint advance, dedupe entry, summary-index delta). Either the event-with-its-reduction lands, or nothing lands. The component view therefore **never lags the log for a committed event** under the normal path.

This preserves both producer-facing guarantees the envelope spec required:

- **`submit` never returns a reduction error.** Because reducers are pure and *total* (invariant 3), a total reducer cannot fail on a well-formed event; there is no "reduction failed" outcome a producer can observe. The only producer-visible failures are pre-append (`MalformedEnvelope`, unauthorized) and dedupe (idempotent `Deduplicated` no-op).
- **Ack ⇒ durable fact on the log.** Acknowledgement still means the fact is durable.

Exactly one narrow exception is defined, owned by the daemon spec and gated by this ADR: if a **registered bundle reducer panics** (a bundle bug, not a malformed event), the daemon commits the **event alone** to the log (the fact must not be lost), marks the affected component projection `degraded`, emits an internal `projection.degraded` diagnostic on the control channel, and leaves the event available for re-projection after the bundle is fixed (drop + replay). The log is never blocked by a bad reducer; the *view* degrades, never the *truth*. This is the **only** state in which a committed event may transiently lack its reduction, and it is observable and self-healing — not a producer-facing failure.

**Conformance consequence:** the envelope spec's submit-pipeline step that previously read "Reduce (downstream, not part of `submit`'s durability contract)" MUST be amended to state that reduction commits **atomically with the append** (still pure, still cannot fail for a well-formed event, producer never sees a reduction error). The practice of a downstream spec "tightening" an upstream one is retired: where two specs would disagree on a load-bearing invariant, the disagreement is lifted here and both specs cite the ADR.

#### Runtime-meta event allowlist (resolves the "zero event types" contradiction)

Invariant 8 was previously stated categorically as "core ships zero ... event types" and repeated verbatim in the reducer and envelope specs. That categorical wording contradicts the runtime itself: several **domain-neutral, core-owned** event types are required for the runtime's own meta-operations, are emitted/handled by **core** reducers (not bundle reducers), and carry no vendor semantics. To stop three or more downstream specs each quietly carving their own exception, the ADR enumerates the allowlist once, and each spec references it:

> **Core reserves the following enumerated, domain-neutral runtime-meta event-type namespaces.** They are part of core, are NOT domain types, and are the *only* event types core may define or emit:
>
> - `attention.*` — the attention/focus write-side verbs (`attention.snoozed`, `attention.deferred`, `attention.acknowledged`, `attention.resolved`, `focus.modeChanged`). Owned by the attention-routing spec; produced/consumed by the core attention reducer.
> - `approval.*` — the human-gate lifecycle (`approval.requested`, `approval.granted`, `approval.denied`, `approval.expired`). Owned by the action/capability spec.
> - `entity.*` — identity-graph node lifecycle (`entity.registered`, `entity.renamed`, `entity.rehomed`). Owned by the entity-identity spec.
> - `edge.*` — identity-graph edge lifecycle (`edge.added`, `edge.removed`). Owned by the entity-identity spec.
> - `ambisphere.egress.performed` — the core-reserved egress fact recording that a narration/egress action occurred. Owned by the privacy/credential-boundary spec; "core-reserved" means a bundle may not redefine it.
>
> This list is **closed**: adding a new runtime-meta event type is itself an ADR-gated change (a revision of this allowlist). Everything *not* on this list is a **domain** type and MUST live in a bundle (examples/adapter layer); core never defines, emits, or branches on a domain type. The vendor-neutrality lint targets *domain* leakage (`khaos.*`/`loswf.*`, branching on `payload`/`ext`), not these enumerated meta types.

Downstream specs cite this allowlist rather than each independently asserting "zero event types." Where a spec previously repeated the categorical wording, it is amended to read "zero *domain* event types; core-reserved runtime-meta types per ADR-0001 invariant 8 allowlist."

#### Local seam ("broker") definition (resolves the terminology collision)

The daemon, renderer, and adapter specs name the daemon's local IPC seam the **"broker"** (e.g. "daemon-as-broker"), while the ADR/daemon non-goals reject *message brokers* as machinery (no Kafka/Redis/NATS, no external pub/sub). To remove the internal-consistency hazard (a future contributor justifying topic/fan-out/external-broker features by appeal to the "broker" name), the ADR fixes a single shared normative definition all specs reference:

> **"broker"** in this suite denotes **only** the thin, local, single-process IPC seam exposed by the daemon over a Unix domain socket (with `127.0.0.1` loopback fallback). It has exactly **two data planes plus one control channel**: (1) a capability-gated, addressed **write** plane (`submit`, log-only), (2) a separately-gated, cursor-resumable, one-way **read** plane (a stream over the materialized view), and (3) a single reserved bidirectional **control** channel whose state changes all flow back through `submit` as facts. **Out of scope and ADR-gated:** topics, exchanges, fan-out/routing semantics, durable queues, and any external/network pub/sub or message-broker product. The "broker" is a local seam, never a message-broker.

Any feature that would add topics, exchanges, fan-out, or an external broker is a non-goal under this definition and would require an ADR revision.

### Supporting commitments (each detailed in a follow-on spec)

- **Determinism:** as in invariant 3. Replay-equality is a required property test (see acceptance criteria).
- **Ordering:** as in invariant 4. Per-entity total order only; daemon is the sole authority for `sequence`/`ingestTime`.
- **Authority:** as in invariant 5. Capability-shaped, write-only at the boundary, read separately gated; v1 RBAC-degenerate but ocap-compatible.
- **Fact/narration firewall:** as in invariant 6.
- **Human-gate vs prominence:** a confirm-required action emits durable `approval.requested` state (write side, async, on the runtime-meta allowlist); the attention bus may rank it as high as it likes (read side) without the runtime ever synchronously blocking. "blocking" is at most a renderer-honored prominence level, never a write-path block.
- **Local-first scoping:** adopt event sourcing, CQRS, ocap, snapshots; reject Kafka/external brokers/async cross-process projectors/consensus/sharding/scale-to-zero. Single-process daemon, synchronous in-process projection committed atomically with the append, embedded SQLite/WAL behind a `StorageDriver`. The local seam is a "broker" only in the narrow sense defined above.
- **Vendor neutrality:** as in invariant 8 — zero *domain* types; only the enumerated runtime-meta allowlist in core; lint-enforced.

### D2 — Per-tier implementation language

Adopt **best language per tier** (a single-language stack is rejected — no candidate is best across all tiers, and the IPC seams make polyglot clean):

- **Core daemon → Rust.** Ownership/borrow checking enforces the read-only-projection and capability invariants at compile time; no GC suits an always-on hibernating daemon; `rusqlite` + WAL is first-class; deepest systems ecosystem (serde for CBOR/JSON, mature crypto for macaroons); trivial single static cross-platform binary.
- **Renderers → best per platform.** Apple (macOS/iOS, tray, menubar, companion) → Swift/SwiftUI (the flagship surface); Android → Kotlin/Jetpack Compose; Web (dashboard cards, command palette, chat panel) → TypeScript (React/Svelte); Desktop (Linux/Windows) → reuse the web renderer in a Tauri shell (Rust shell + TS UI), matching the core language at the shell; TUI → Go/Bubbletea (existing skill leverage), with Rust/ratatui the single-core-language alternative.
- **Adapters → polyglot**, each in the language of the system it integrates, translating native events into the semantic envelope and never depending on the core. Ship a **Rust reference adapter SDK** plus a **language-neutral wire spec** so no adapter is forced to depend on it.

**Recorded close alternative for the core: Swift 6.3 (6.4 in development).** Core = Rust vs Swift was the one genuinely contestable pick; Swift is a co-leader and a fully defensible alternative. It is recorded as **decided in favor of Rust** with the team-fluency revision trigger spelled out in the acceptance criteria. (The source guidance writes "Swift 6.4"; as of June 2026 the current stable is Swift 6.3 — swift.org/blog/swift-6.3-released — with 6.4 in development. Either way the comparison stands.)

**Rust-vs-Swift deciding factors (recorded explicitly, the reason Rust won the core):**

| Factor | Rust | Swift 6.3/6.4 | Decisive because |
|---|---|---|---|
| Compile-time enforcement of *derived-never-authoritative* & capability types | ownership/borrow checking makes a read-only projection structurally enforceable | value semantics + `Sendable` (strong, but weaker than borrow checking for shared-state aliasing) | a headless system of record rewards the strongest static guarantee |
| Idle/runtime footprint for an always-on daemon with hibernating entities | no runtime/GC | ARC (no GC pauses, small runtime) — close, slight edge to Rust | always-on process; zero-runtime preferred |
| Embedded SQLite-as-log | `rusqlite` + WAL first-class | GRDB (mature) — parity | parity, no tiebreaker |
| Ecosystem for macaroons crypto / CBOR-JSON serde | deepest systems ecosystem | good, less deep for systems crypto | capability machinery depends on it |
| Maturity / "do not found on a moving target" | stable, broad | rapidly maturing off-Apple (Android/Static-Linux SDK 2026) but younger off-Apple | a system of record should not sit on the newest cross-platform surface |
| Native Apple renderer | weak (irrelevant to core) | best-in-class | Swift keeps the flagship Apple renderer regardless — so unifying on Swift for the core buys little |
| Team fluency | (ramp cost; no Rust skills currently installed) | (ramp cost; no Swift skills currently installed) | the one factor that could still flip D2 → see revision trigger in acceptance criteria |

Because language-unification is abandoned, a headless daemon rewards Rust's compile-time invariant enforcement, zero-runtime footprint, and ecosystem depth, while Swift keeps its home as the flagship Apple renderer either way. The decision is low-regret: a renderer or adapter can be rewritten in another language without touching the core, because both cross-language seams are language-neutral by design.

## Consequences

### Positive

- The read/write split lets each paradigm own the side it is strong on: capability/isolation on write, cross-entity query on read. The project's hardest novel problem (attention routing) and its hardest constraint (capability security) are each addressed where they are natural.
- One mechanism (the event log) delivers transactional reduction-with-rollback, full auditability, and the fact/narration firewall together — and, with the atomic commit-point invariant, the component view never lags the log for a committed event.
- All read-side artifacts (components, rollups, attention state, persona, renderer projections) are rebuildable materialized views — none is a source of truth.
- Rust enforces the core invariants at compile time; the polyglot edges keep best-per-platform UX and let adopters write adapters in their own languages.
- Vendor neutrality is structurally enforceable (lint), protecting the no-lock-in principle under adopter-driven convenience pressure; the runtime-meta allowlist makes the boundary between "core-reserved meta type" and "domain type" precise rather than aspirational.
- The nine numbered invariants give the downstream suite a single, stable conformance anchor.

### Negative

- **Hybrid-complexity tax** (issue #4's named risk): two representations to keep consistent and complexity inherited from both paradigms. *Mitigation:* the directionality invariant + the atomic append+reduce commit point + lint for direct component writes.
- **Schema/reducer evolution debt:** long-lived logs outlive reducer code; replaying old events through new reducers can break the rebuild guarantee. *Mitigation:* version the envelope and decide an upcasting/migration + snapshot strategy **before any log is written** (Semantic event envelope spec).
- **Snapshot drift / unbounded log growth.** *Mitigation:* snapshots must be a pure, verifiable function of a log-prefix; a compaction/retention policy preserving minimum lineage from day one.
- **Determinism leak:** a reducer/adapter reading wall-clock/RNG/IO destroys replayability. *Mitigation:* inject time/entropy as event fields; enforce with a replay-equality test.
- **Single-daemon SPOF and wedge risk.** *Mitigation:* external supervision (launchd/systemd), a liveness/health endpoint, bounded operations.
- **Polyglot operational surface** and a small core-language ramp cost (no Rust or Swift skills currently installed; Go tooling is). *Mitigation:* the language-neutral wire spec bounds the seam count to two; plan a ramp.

### Risks

- **The "ECS core" mislabel re-importing ambient authority** if contributors treat components as a freely-writable world. *Mitigation:* name it a projection, make components structurally read-only outside the reducer, lint for log-bypassing writes.
- **The "broker" name re-importing message-broker machinery.** *Mitigation:* the shared normative "broker" definition above scopes it to the local two-plane-plus-control seam; topics/exchanges/fan-out/external pub/sub are ADR-gated non-goals.
- **Fact/narration firewall erosion** (an AI summary written back "because it's convenient"). *Mitigation:* structural impossibility — only egress adapters write narration; narration template slots restricted to declared factual fields.
- **Vendor leakage into core** via the opaque payload being branched on. *Mitigation:* lint that core never reads `ext`/`payload` internals or `khaos.*`/`loswf.*` types; the runtime-meta allowlist makes "is this a legitimate core type?" answerable by enumeration.
- **Over-engineering for the single-user local case.** *Mitigation:* capability-shaped boundary with an RBAC-degenerate v1; conceptual PROV/bitemporal adopted only as needed; never the distributed CQRS infra.

## Acceptance criteria (met at acceptance)

The earlier draft listed Proposed→Accepted criteria that were not themselves testable or assignable. Each is now a checkable artifact with an owner and a concrete gate. These are the conditions under which this ADR moves (and has moved) to `Accepted`; they are also the standing conformance obligations for the suite.

- **Directionality / no-cross-actor-write lint exists.** Lint rule `no-direct-component-write` + `no-cross-entity-write-query` in `tools/lints/ambisphere_directionality.rs` (Rust core lint pass) and a CI job that fails on any `setComponent`/`setEdge`/direct-log-append call site or any cross-entity query on the write path. *Owner:* core daemon maintainer. *Gate:* CI green on the core crate.
- **Replay-equality property test exists.** Named test `replay_equality::byte_identical_on_replay` (proptest-based) asserting `replay(log) == replay(replay(log))` byte-for-byte and that snapshot⊕tail ≡ full replay. *Owner:* reducer/state-component spec implementer. *Gate:* test present and green **before any log is written**.
- **Vendor-neutrality lint exists.** Lint `no-vendor-symbols` asserting core contains no `khaos.*`/`loswf.*` literal and no branch on `data`/`payload`/`ext` internals, with the runtime-meta allowlist whitelisted by enumeration. *Owner:* core daemon maintainer. *Gate:* CI green; worked-example vendor symbols confined to `examples/adapters/`.
- **Attention-bus spec validates the read-side query contract.** The attention-routing spec (sequenced first, issue #4) §"read-side query contract" / §"the `attention` component is canonical" defines and validates the cross-entity query shape this ADR's read side assumes. *Owner:* attention-routing spec author. *Gate:* that section exists and is referenced (not contradicted) by the reducer and daemon specs.
- **Invariant conformance across the first three follow-on specs.** "Referenced (not contradicted)" is operationalized as: each spec's "Conforms to: ADR-0001" table cites the canonical invariant numbers above, and a cross-spec consistency check (`tools/lints/check_invariant_refs.sh`) verifies no spec redefines or renumbers ADR invariants 1–9 and that the commit-point and runtime-meta-allowlist wordings are cited, not re-derived. *Owner:* spec suite editor. *Gate:* the check passes for the attention, reducer, and envelope specs.
- **Core-language ratification with a dated revision trigger.** The Rust-vs-Swift pick is decided in favor of Rust as of acceptance. **Revision trigger:** a team-fluency ratification review is scheduled at the start of core implementation (daemon/runtime architecture milestone); if that review records a team decision to use Swift for the core, this ADR is **superseded by ADR-0001-rev2**, not edited in place, and dependent specs re-point their conformance anchor. Absent such a decision by that milestone, Rust stands. *Owner:* project lead. *Gate:* a recorded decision (this ADR for Rust; a revision ADR if it flips).

## Prior art (citations kept visible)

- **Actor lifecycle / hibernation / compound-key addressing / persistent alarms** — RivetKit / Rivet Actors, `github.com/rivet-dev/rivet`; adopt lifecycle, reject coordinator super-actor, serverless transport, RBAC-as-the-model (`specs/drafts/actor-model-prior-art.md`). Negative result: a production actor runtime has **no cross-entity query** — external evidence for spec-the-attention-bus-first.
- **Event sourcing / CQRS / stream-table duality / snapshots** — Kleppmann, *Designing Data-Intensive Applications* ch. 11–12; Azure Architecture Center CQRS & Event Sourcing. Adopt read/write split, log-as-truth, checkpoints, idempotent rebuildable read models; reject Kafka/external bus/async projectors. Informs the atomic append+reduce commit point (local single-process, no async projector).
- **Object-capability / no ambient authority** — Dennis & Van Horn 1966; Miller, *Robust Composition* (E); KeyKOS/EROS, seL4, Spritely Goblins. Adopt no-ambient-authority as the write-boundary design test; reject OCapN networking and full-runtime dependency.
- **Macaroons** — Birgisson et al., "Macaroons: Cookies with Contextual Caveats for Decentralized Authorization in the Cloud," ACM CCS 2014; `github.com/rescrv/libmacaroons`. Adopt caveat-based attenuation, offline verification, delegation-by-minting-weaker; reject third-party-caveat network round-trips except opt-in for genuinely remote actions. (Verified June 2026: HMAC verifiers hold the root secret — informs where the capability check sits.)
- **Event-driven ECS read side** — Bevy ECS with Observers (`bevyengine.org`, PR #10839); Flecs relationships. Adopt entities-as-IDs + reactive push-based observers as proof event-driven ECS is production-real; reject ECS-as-system-of-record and the tick scheduler.
- **Provenance** — W3C PROV-DM (entity/activity/agent triad) as lineage vocabulary; reject full RDF/OWL serialization.
- **Calm technology** — Weiser & Brown 1996; Amber Case 2015. Adopt center/periphery framing for read-side ranking; reject drift into a built-in persona system.
- **Languages** — Rust `rusqlite`/serde/ownership-ocap-fit (`github.com/rust-lang/rust`); Swift 6.3 Android SDK + Static Linux + server-side maturity (swift.org/blog/swift-6.3-released, March 2026; infoq.com/news/2026/04/swift-6-3-android-c-interop, April 2026); Kotlin Compose Multiplatform; Tauri (Rust + web desktop shell); Bubbletea/Charm (Go TUI); Zig pre-1.0 status (ruled out of core).

## Follow-on spec sequence

The attention-bus spec is sequenced **first** (issue #4): its cross-entity query shape dictates the component/facet model, which dictates reducer outputs, which dictates the event envelope (read-contract → component → reducer → envelope). This ADR gates all of them, and all cite the canonical invariants above.

1. **ADR-0001 (this record).** Unblocks all.
2. **Attention routing / interruption policy** (#5 spec 7) — specced first; defines the read-side query contract and the normalized `attention` component; owns the `attention.*` runtime-meta verbs.
3. **Reducer / state-component model** (#5 spec 3).
4. **Semantic event envelope** (#5 spec 2).
5. **Entity identity + hierarchy** (#5 spec 1) — owns `entity.*` / `edge.*` runtime-meta types.
6. **Daemon / runtime architecture** — owns the storage-transaction property (atomic append+reduce) and the "broker" local seam.
7. **Renderer observation/projection contract** (#5 spec 4).
8. **Action / capability manifest** (#5 spec 5) — owns `approval.*` runtime-meta types.
9. **Local-first privacy / credential boundary** (#5 spec 9/10) — owns `ambisphere.egress.performed`.
10. **Adapter / plugin API** (#5 spec 8/11).
11. **Persona projection** (#5 spec 6).
12. **Entity bundle / package format** (#5 spec 10) — specced last as an integration pressure-test.

## Open questions

Each points at the spec that resolves it. None is silently resolved here. (Resolved-since-prior-draft items — status contradiction, acceptance-criteria testability, append/reduce ordering, the zero-event-types vs runtime-meta contradiction, and the "broker" terminology collision — are settled in the Decision section above and are no longer open.)

- **Capability-model depth** — ocap macaroons from day one vs RBAC-degenerate single-principal v1. → Action/capability manifest spec (#5 spec 5).
- **Where non-authoritative AI narration lives, and who may write it** (leaning: a separate non-authoritative projection, written only by egress adapters, never to the log; the egress *fact* `ambisphere.egress.performed` is on the runtime-meta allowlist, the *narration* never is). → Reducer/state-component spec (#5 spec 3) + Adapter/plugin API spec (#5 spec 8/11).
- **One shared partitioned log vs per-entity logs; snapshot cadence; compaction/retention vs full audit.** → Daemon/runtime architecture spec (needs a DDIA spike at realistic Khaos/LOSWF event rates).
- **Envelope/reducer schema evolution** (type-version vs `dataschemaversion` vs upcast-at-replay) — must be decided before any log is written. → Semantic event envelope spec (#5 spec 2).
- **Whether read authority and write authority are separately gated** — decided **yes, separately** (invariant 5); remaining detail is the redaction/coarsening shape the attention bus sees. → Attention routing spec (#5 spec 7) + Local-first privacy/credential boundary spec (#5 spec 9/10).
- **Hierarchy rollup determinism and rule** (max-of-children vs weighted-sum vs adapter-defined; single- vs multi-parent). → Entity identity + hierarchy spec (#5 spec 1) with the Attention routing spec.
- **Whether the attention bus itself must be auditable, and whether "blocking" belongs in the attention core at all.** → Attention routing spec (#5 spec 7).
- **TUI language** (Go/Bubbletea vs Rust/ratatui), **desktop GUI shell** (Tauri vs Kotlin Compose MP vs Rust-native), **reference adapter SDK scope** (Rust-only vs additional TS/Go). → Renderer observation/projection contract spec (#5 spec 4); SDK scope tracked against the Adapter/plugin API spec.
- **Cross-compilation/packaging matrix** (macOS arm64/x86_64, Linux, Windows) and per-platform supervision (launchd/systemd). → Daemon/runtime architecture spec.
- **Contributor ramp** — no Rust or Swift skills currently installed (Go tooling is); plan the ramp for the chosen core language. → Daemon/runtime architecture spec + project onboarding. This is the one factor that could still flip D2 at the dated ratification review (see acceptance criteria); if it flips, this ADR is superseded by a revision.

## Related decisions

- Refs issues #4 (foundational paradigm), #5 (vendor adoption requirements), #6 (this ADR's intake), roadmap #1.
- Whether the language determination should later split into a companion ADR (paradigm + language as two records) is left to intake; this ADR records both, as issue #6 requests. If the core-language pick flips to Swift, the split happens naturally via the revision ADR.
