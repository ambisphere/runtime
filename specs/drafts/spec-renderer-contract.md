# Renderer observation and projection contract

**Status:** draft · **Scope:** the one-way, read-only contract by which any renderer/surface observes entity state — *not* a UI API. Defines the three observation channels (`state` / `attention` / `persona`); LSP-style capability negotiation at attach; per-surface view-model **projections** (daemon-computed from a **bundle-shipped projection template**, never raw components, never core-hardcoded shapes); the snapshot + delta + monotonic-version + resync transport; the rule that **all action invocation flows through the write side**, never the renderer port; the `RendererPort` as a *driven* port in the outermost ring with a headless core; and best-per-platform renderers (Swift/Kotlin/TS/Tauri/Go-TUI) over a language-neutral framed transport · **Companion to:** `specs/VISION.md`, `specs/SRS.md`, `RFP.md` (§ "Renderer Independence", "Multi-surface rendering contract" via issue #5 §5, "Glanceable over interruptive") · **Sequenced:** seventh among the follow-on specs (after the attention-bus, reducer/state-component, event-envelope, entity-identity, and daemon specs; before the action/capability, privacy, adapter, persona, and bundle specs) per ADR-0001 and issue #4 · **Conforms to:** ADR-0001 **(provisional — see "Conformance to ADR-0001" below; ADR-0001 is itself draft and not yet Accepted, so every conformance reference here is provisional pending its ratification)** — the foundational paradigm + directionality invariant + Rust core; the attention-routing spec (this spec *consumes* its `AffordanceMap`, `what_matters_now`/`AttentionQuery`/`RankedEntity`, rung caps, and the `attention` facet — it redefines none of them); the reducer/state-component spec (this spec projects its `Component`/`EntityState` into view-models and carries its `NarratedProjection` on the persona channel, honoring the fact/narration firewall); the semantic-event-envelope spec (action invocation re-enters the system *only* via `submit`, carrying `correlation.causedBy`); the daemon spec (this spec *specializes* the broker read plane `subscribe(readCap, SubscribeRequest) -> FrameStream`, the `Frame` shape, cursor resumability on `logPosition`, and the UDS/loopback framed transport); the entity-identity spec (`EntityHandle`/`EntityAddress`); the entity-bundle-format spec (this spec defines the **projection-template** format the bundle's `renderers/` section serializes and the daemon evaluates) · **Sibling notes:** `specs/drafts/runtime-paradigm-and-specs-guidance.md`, `specs/drafts/actor-model-prior-art.md`, `specs/drafts/persona-prior-art.md`, `specs/drafts/implementation-language-guidance.md`

This spec defines how a surface **sees**. It is deliberately not an interface a renderer *calls to do things* — it is a contract a renderer *subscribes to in order to observe*. The asymmetry is the whole point and is the third assertion of issue #4: events flow inward (active, addressed, capability-gated, through `submit`); rendering flows outward (passive, subscription-based, filtered by attention). A renderer is a read-only consumer of a materialized view, never an authority over it.

It owns no rendering technology, no layout, no animation, no persona content, no attention math, no action semantics, and no domain vocabulary. It owns the *seam* a surface attaches to: the channel set, the capability handshake, the shape of the per-surface view-model **and the bundle-driven rule that produces it**, the snapshot/delta/resync transport, and the hard rule that a renderer cannot write.

## Terminology: what "broker" means here

This spec, the daemon-architecture spec, and the adapter spec all use the word **broker** for the daemon's local IPC seam. To prevent the terminology from being read as message-broker machinery, the term is scoped normatively and identically across all of them:

> **"Broker" denotes only the thin, local, in-process seam exposed over a Unix domain socket (with `127.0.0.1` loopback fallback): exactly two data planes — a capability-gated addressed **write** ingest (`submit`) and a cursor-resumable one-way **read** subscription — plus one reserved bidirectional **control** channel.** Topics, exchanges, fan-out routing, subscriptions-as-subjects, durable queues, and any external/networked pub-sub system (Kafka/Redis/NATS and the like) are **explicitly out of scope** and ADR-gated: introducing any of them is a paradigm change requiring a new ADR, not an extension justified by the name. The daemon spec's non-goals already reject "a general-purpose message queue or broker product"; this spec adds nothing to that surface.

The renderer contract uses only the **read** plane (plus the attach handshake). It never uses the control channel for observation (see "The three channels" and "What the control channel is not", below).

## Goals and non-goals

### Goals

- Define a **one-way observation contract** — renderers are passive subscribers (LSP `textDocument/publishDiagnostics` model: the server owns truth and pushes; the client never owns state), not callers of a UI API.
- Define the **three observation channels** — `state` (factual view-model), `attention` (ranked, surface-capped), `persona` (expressive/narrated, firewall-gated) — *exactly three*, fixed here, not redefinable downstream and not extended by the broker's control channel — so a tray subscribes to `state`+`attention` and a companion to all three.
- Define **capability negotiation at attach** (LSP `initialize`-shaped): a surface declares what it is and what it honors; unknown fields are ignored (forward-compatible degradation); the surface's declaration *is* the attention spec's `AffordanceMap`.
- Define the **per-surface projection** and, crucially, **its production rule**: a daemon-computed **view-model**, keyed by `(surfaceKind, projectionSchemaVersion, readCapability)`, whose shape is determined by a **bundle-shipped, bounded, declarative projection template** — never raw components, never a shape hardcoded in core.
- Define the **transport contract**: initial snapshot + incremental deltas + a **monotonic version** for gap detection + a cheap **full resync** — specialized from the daemon broker's `Frame` stream and its `logPosition` cursor.
- Make explicit that **action invocation flows through the write side** (`submit`), not this port; action affordances ride in the projection as **advisory metadata only** (POLA: a renderer holds zero action authority by default).
- Model `RendererPort` as a **driven (outbound) port** in the outermost ring; the core runs **headless** with zero renderers; the wire is **language-neutral** so any renderer tier is reimplementable without touching the Rust core.
- Give concrete schemas/interfaces (fenced) and **acceptance criteria** that make the read-only, capability-degradation, projection-production, resumability, and no-write-path invariants testable.

### Non-goals (adopt/reject framing — rejections carried from the guidance)

- **Not** a rendering / layout / animation engine or UI toolkit. The contract describes *what a surface sees*, never *how it draws*. No sprite/atlas/frame/spritesheet vocabulary (reject persona-prior-art's spritesheet-as-truth). (Reject: a rendering standard — VISION non-goal.)
- **Not** a UI API or a request/response protocol. There is no `getState()` on the hot path, no method a renderer calls to mutate. The only pull is snapshot/resync. (Reject: request/response orientation — adopt LSP's push model instead.)
- **Not** the action execution path. A renderer never invokes an action through this port; affordances are advisory and invocation is the action/capability spec's `submit`-backed path. (Reject: renderer-as-write-authority.)
- **Not** the attention-ranking algorithm. This spec *consumes* `what_matters_now`/`RankedEntity` and the surface caps; it computes no score and redefines no rung. (Reject: per-renderer attention engines — guidance.)
- **Not** persona content or authoring. The `persona` channel *carries* a `NarratedProjection` + expressive tokens the persona spec defines; it authors none. (Reject: a built-in personality system — VISION non-goal.)
- **Not** the owner of presentation *logic*. The view-model **shape** is bundle-supplied data (a bounded projection template), evaluated by core as a pure function. Core ships no surface shapes and no `if surfaceKind == "tray"` branch. (Reject: presentation knowledge in core — guidance; vendor leakage.)
- **Not** a general query / analytics API, nor chat-history / artifact retrieval. Those are a separate query surface (see Open questions). (Reject: a general-purpose query engine exposed to renderers — guidance.)
- **Not** a fourth observation channel via the control plane. The daemon's reserved bidirectional **control** channel (daemon spec) is *not* one of this contract's observation channels; observation is `state`/`attention`/`persona` only. (Reject: blurring control into the read plane.)
- **Not** a mandated wire protocol. The spec fixes the *shapes* and a single reference binding for conformance; it does not force JSON-RPC or any one framing on every tier. (Reject: a single transport standard — VISION non-goal.)
- **Not** a place for vendor concepts. Core ships zero surface-taxonomy values beyond a semantic open string, zero renderer/persona vocabulary, and never branches on `payload`/`khaos.*`/`loswf.*`. (Reject: vendor leakage.)

## Prior art (citations kept visible)

- **Language Server Protocol 3.17 (`textDocument/publishDiagnostics`; `initialize` capability handshake; `PublishDiagnosticsClientCapabilities`).** Adopt: the **authoritative-server / decoupled-multi-client push** model — the server owns truth and *publishes* to passive clients that never hold authoritative state; the `initialize`-time **capability exchange** where each side declares what it supports; **forward-compatible degradation** (a client declares the diagnostic features it can handle; a server honoring fewer is still correct). We map `publishDiagnostics` → the `state`/`attention`/`persona` push channels, and the `initialize` client-capabilities → the `RendererManifest` handshake. Reject: LSP's request/response orientation and its document model; we do **not** mandate JSON-RPC in core (the daemon's framed CBOR/JSON is the reference binding). (microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification.)
- **Server-Sent Events / `EventSource` `Last-Event-ID` (HTML Living Standard §9.2).** Adopt: a **one-way, cursor-resumable** stream — the server stamps each event with a monotonic `id`; a reconnecting client presents its last `id` and resumes gap-free. We inherit the daemon spec's mapping of the SSE `id` to the storage `logPosition` and specialize it into the renderer's `version` for gap detection + resync. Reject: WebSockets on the read path (bidirectional, no built-in resume). (html.spec.whatwg.org/multipage/server-sent-events.html; http.dev/last-event-id.)
- **CQRS read models / per-surface view-models (DDIA ch. 6 stream–table duality; Azure Architecture Center CQRS).** Adopt: **multiple projections from one log** — each surface gets a view-model shaped for it, all derived from the same materialized view; the read side never writes back. We extend this with the explicit observation that *the projection definition is itself versioned data* (the bundle's projection template), not code baked into the query side. Reject: distributed projection infrastructure (single local daemon — guidance).
- **Clean Architecture / ports-and-adapters (Martin; Cockburn).** Adopt: `RendererPort` as a **driven (outbound) port** in the outermost ring; the application core depends on nothing in the renderer; renderers are interface adapters that conform to the port. The Dependency Rule points inward: a renderer knows the contract; the core knows no renderer. Because the projection template is bundle data, the surface-shape knowledge lives *outside* the core too, preserving the rule. Reject: full onion/DDD ceremony — the port is a thin observation seam, not an aggregate. (clean-architecture skill.)
- **Calm Technology (Weiser & Brown 1996; Amber Case 2015).** Adopt: prominence is a **daemon decision** (attention spec), surfaced *per surface* via the affordance map; the renderer honors it, never invents it; "glanceable over interruptive" (VISION 7) is realized by the surface declaring a low `surfaceMax`. Treat as the *why*, not a wire format.
- **RivetKit connection model (`onConnect`/`onDisconnect`; `actor-model-prior-art.md`).** Counter-example: RivetKit assumes *active* clients with bidirectional connections. Ambisphere renderers are **passive observers**. Adopt the negative result — do **not** model renderers as connected actors; adopt snapshot+delta+resync over the cursor stream instead. Reject: connection-as-authority.
- **codex-pets state-vocabulary-as-contract (`persona-prior-art.md`).** Adopt: the *named states* are the contract between producers and surfaces — generalized here as: reducers project facts into a factual `EntityState`, a **bounded projection template** shapes them into a surface-specific `stateView`, the `persona` channel maps them to expressive tokens, renderers map those to frames; each layer is replaceable data. This is the *same bounded-template discipline* the persona spec uses for narration, applied to the factual view-model. Reject: spritesheet-as-truth, nine hardcoded animation states, renderer assumed by the host.

## Conformance to ADR-0001

**Provisional-conformance note.** ADR-0001 is itself a **draft** and not yet Accepted, and the suite has flagged that its own Status section is self-contradictory. Until ADR-0001 is resolved to a single status and publishes a **canonical numbered-invariant list**, this table cites that list *provisionally*: the invariant numbers below are the anchor ADR-0001 must ratify, and this spec is "conforming to a provisional ADR-0001." When ADR-0001 is Accepted with its acceptance criteria checked off, this note is removed and the citations become binding. (This is a suite-wide blocker shared by all nine follow-on specs, not local to this one.)

| Invariant | How this spec honors it |
|---|---|
| (1) Log is source of truth; components derived, read-only | A renderer observes a **projection** of the materialized view; it never writes a component and never holds authoritative state. The projection (template + computed view-model) is droppable/rebuildable from the log; the renderer is downstream of it. |
| (2) Directionality | This is purely the **read** side. ECS-shaped queries (the `scope` predicate, `what_matters_now`) live here; **no** capability/actor write semantics appear. Action invocation is explicitly routed **out of this contract** to `submit`. The log remains the single seam. The broker's control channel is *not* an observation channel and carries no observation authority here. |
| (3) Determinism | The projection is a **pure function** of `(materialized view, projection template, surfaceKind, projectionSchemaVersion, readCapability, as_of)`. The template is versioned bundle data; given the same inputs the daemon computes the same view-model. Renderers receive stamped, already-derived values; they introduce no clock/RNG into facts. (A renderer may animate on its own clock — that is presentation, never a fact.) |
| (4) Per-entity total order only | The stream `version` is the storage `logPosition` — a **stream** order for gap detection and resume, **never** a cross-entity logical order. Two entities' deltas interleave in storage order only. |
| (5) Capability-shaped authority | A subscription presents a **read** capability, separately gated from write; it grants **zero** write/action authority (POLA). Action affordances in the projection are advisory UX hints, never the boundary. The read capability bounds *which factual fields the template may emit* and may coarsen/redact the projection (privacy spec). |
| (6) Fact/narration firewall | The `state` and `attention` channels are **factual-only** (`kind: "factual"`). The projection template's slots reference **only declared factual component fields** (same firewall discipline as persona templates; a slot naming a non-factual field is a bundle-validation error). The `persona` channel is the *only* place a `NarratedProjection` (`kind: "narrated"`) appears, delivered **only** when `include_narration` is set; a surface can always subscribe factual-only and render correctly. Narration is never an input to any view-model fact. |
| (7) Credentials never in state/log | The projection carries opaque `capabilityRef`s/`modelRef`s only (e.g. an action's `requiredCapabilityRef`, a narration's `modelRef`) — never a credential. |
| (8) Vendor neutrality | Core ships zero surface-taxonomy values beyond an open semantic `SurfaceKind` string, zero renderer/persona/animation vocabulary, **and zero per-surface view-model shapes** — every `stateView` shape comes from a bundle projection template. Projection computation never branches on `payload` internals or `khaos.*`/`loswf.*`; it evaluates the template generically. |
| (9) Cross-language seams | The contract is **language-neutral by design** — framed CBOR/JSON over the daemon's UDS/loopback. Swift/Kotlin/TS/Tauri/Go renderers interoperate without linking the Rust core. The projection template is declarative data, equally consumable across languages. |

## Position in the architecture

The renderer is the outermost ring. The Dependency Rule (clean-architecture) points inward: the renderer depends on the observation contract; the core depends on no renderer. The *projection-shape* knowledge lives in bundle data, outside core, so neither the renderer nor a surface taxonomy leaks inward.

```
        ┌──────────────────────────────────────────────────────────────┐
        │  WRITE side (capability-gated)        READ side (this spec)    │
        │                                                                │
 adapter│  submit(cap, ProposedEvent) ──▶ LOG ──▶ reducers ──▶ view ──┐  │
        │        ▲                                                    │  │
        │        │ (action results re-enter as facts)                ▼  │
        │        │                              ┌──────────────────────┐│
        │        │   bundle projection template │  PROJECT(view,tmpl)  ││
        │        │   (renderers/ section) ─────▶ │  -> ProjectedEntity  ││
 render │        │                              └──────────┬───────────┘│
 -er    │        │                              ┌──────────▼───────────┐│
 action │   invoke ── (action/capability spec)  │ RendererPort (driven)││
        │   ─────────────────────────────────▶  │  subscribe(readCap,…)││
        │   NEVER through the renderer port       │  3 channels, frames ││
        │                                         └──────────┬──────────┘│
        └─────────────────────────────────────────────────── ┼──────────┘
                                                              ▼
                            ┌───────────────┬─────────────┬───────────────┐
                            │ Swift/SwiftUI │ Kotlin/Compose│ TS/Tauri/Go-TUI │  (passive observers)
                            └───────────────┴─────────────┴───────────────┘
```

The dashed loop is load-bearing: a renderer that wants to *do* something does **not** call this port. It invokes an action (action/capability spec), whose result re-enters as a fact via `submit` (envelope spec, `correlation.causedBy`), is reduced, re-projected (template re-evaluated), and pushed back out as a new frame on this contract. The renderer sees the *effect* of its action as a normal state update — it never mutates the view directly. This is the LSP `publishDiagnostics` loop: the client requests a code action, the server applies an edit, and the client learns of it via a fresh `publishDiagnostics`.

## The three channels

A surface subscribes to any subset of **exactly three** channels. They are fixed here and **not redefinable, extendable, or supplementable** downstream — neither by a bundle nor by the broker's control channel.

| Channel | Carries | Source | Firewall |
|---|---|---|---|
| `state` | A factual `ProjectedEntity` view-model (lifecycle, domain `stateView`, advisory `actions[]`) | reducer/state-component spec `EntityState`, shaped per surface by the **bundle projection template** | **factual only** (`kind: "factual"`) |
| `attention` | Ranked, surface-capped `RankedEntity` slices ("what matters now" for this surface) | attention spec `what_matters_now` under the surface's `AffordanceMap` | factual scalars only; persona is never an input |
| `persona` | A `NarratedProjection` (optional narration) + declarative expressive tokens | persona spec / egress adapters | **narrated** (`kind: "narrated"`), delivered only if `include_narration` |

Rules:

- A surface MUST be able to function with `state` alone (an operational TUI). `attention` and `persona` are additive.
- The `persona` channel is the **only** channel that may carry `kind: "narrated"`. The other two are structurally factual (reducer spec firewall). A surface that omits `persona` (or sets `include_narration: false`) renders the factual world and is always correct.
- The `attention` channel does **not** re-rank; it relays the attention spec's `RankedEntity` already capped by `min(score-rung, entity.ceiling, surfaceMax, focusModeCap)`. `surfaceMax` comes from this surface's affordance map (below).

### What the control channel is *not* (cross-spec correction)

The daemon-architecture spec exposes a **reserved bidirectional control channel** alongside the two data planes (for health, focus-mode change, drain requests, and `projection.degraded` diagnostics). That control channel is **not** an observation channel of this contract, and a renderer does **not** observe entity state through it. The fixed observation set is `state | attention | persona` — three, not four.

This resolves a known cross-spec inconsistency, and the two owning specs need a matching one-line correction:

- The **daemon spec**'s `SubscribeRequest.channels` comment (`state | attention | persona | control (renderer contract's 3 channels)`) is self-contradictory and MUST be corrected: `control` is a broker construct distinct from the read-plane observation channels, and the renderer contract's fixed set is the three named here. The `ChannelSet` a `subscribe` carries is the observation set (`state|attention|persona`); the control channel is a separate, reserved bidirectional channel, not a member of a `subscribe` channel set.
- The **persona spec**'s phrasing "the renderer contract's channel set (`state | attention | persona | control`)" MUST be corrected to cite the renderer contract's **three** observation channels; the control channel is the daemon's, not an observation channel.

A surface that wishes to participate in interactive control/chat uses the daemon's control channel per the daemon spec; any state change it triggers still flows through `submit` as a capability-gated fact and is observed back on `state`/`attention` like any other. The directionality invariant is thereby preserved on both the observation and control surfaces.

## Attach: the capability handshake

A surface attaches by presenting a **read capability** and a `RendererManifest`. This is the LSP `initialize` exchange specialized for observation. Crucially, the manifest **is** the attention spec's `AffordanceMap` (extended with renderer-specific fields) — there is one declaration, consumed by both the broker and the bus, so prominence capping and projection shaping agree.

```jsonc
// RendererManifest — declared at attach. Superset of the attention spec's AffordanceMap.
// Unknown fields MUST be ignored by the daemon (forward-compatible degradation, LSP-style).
{
  "surfaceId": "tray-main",            // stable id for THIS surface instance (resume/coalesce key)
  "surfaceKind": "tray",               // OPEN semantic string (not presentational): tray|card|tui|
                                       //   companion|palette|notifier|panel|… — core ships none as values.
                                       //   Binds to the bundle projection template for this kind (below).
  "channels": ["state", "attention"],  // subset of state|attention|persona this surface will consume (3 only)
  "projectionSchemaVersion": 1,        // the view-model/template schema this surface understands
  "supportsResync": true,              // can it accept a full snapshot reissue on gap? (MUST be true v1)
  "includeNarration": false,           // persona channel only; default false (factual-only firewall)

  // --- attention spec AffordanceMap (canonical there; relayed verbatim) ---
  "honoredRungs": ["quiet", "ambient", "nudge"], // surfaceMax = max(honoredRungs)
  "honorsBlocking": false,
  "maxConcurrent": 3,                  // how many ranked entities it can show at once
  "supportsExplanation": true,         // can it surface "why?" (RankedEntity.explanation)

  // --- renderer-advisory (hints; never the security boundary) ---
  "supportsActionAffordances": true,   // will it render advisory action descriptors? (still cannot invoke here)
  "preferredDeltaMode": "entity"       // "entity" (whole ProjectedEntity replace) | "component" (opt-in diffs)
}
```

The daemon replies with `ServerCapabilities` advertising what it will actually honor — never more than the surface declared, possibly less (degradation is always safe):

```jsonc
// ServerCapabilities — daemon's reply. A surface MUST function if the daemon honors a SUBSET.
{
  "channelsHonored": ["state", "attention"],   // ⊆ requested (always within state|attention|persona)
  "projectionSchemaVersion": 1,                 // the version the daemon will emit (may be < requested)
  "deltaMode": "entity",                        // what the daemon will actually send
  "resyncSupported": true,
  "narrationAvailable": false,                  // false ⇒ persona channel will carry no narrated frames
  "projectionTemplateResolved": true,           // true ⇒ a bundle template matched (surfaceKind,version);
                                                //   false ⇒ no template; daemon emits the passthrough stateView
  "heartbeatIntervalMs": 15000
}
```

Negotiation rules:

- **Forward-compatible degradation (LSP).** Unknown manifest fields are ignored; a surface declaring features the daemon lacks still attaches and works on the intersection. A daemon emitting a *lower* `projectionSchemaVersion` than requested is correct; the surface must handle older view-models (or refuse to attach — its choice, not the daemon's).
- **No write authority is ever negotiated.** There is no manifest flag that grants a renderer the ability to write or invoke. POLA is structural, not a setting.
- **`surfaceMax` is derived, not asserted.** The daemon takes `surfaceMax = max(honoredRungs)` and feeds it to the bus's `min(...)` cap. A surface cannot raise its own ceiling.
- **The read capability gates visibility.** Which entities and which facets appear in this surface's projection is bounded by the read capability (privacy spec). Two surfaces with different read capabilities legitimately see different — possibly coarsened — projections of the same entity.
- **Template resolution is advertised, never required.** If no bundle projection template matches `(surfaceKind, projectionSchemaVersion)`, the daemon advertises `projectionTemplateResolved: false` and emits the **passthrough `stateView`** (defined below). A surface always gets a correct, factual view-model; an unmatched kind degrades to passthrough, never to an error or to raw components.

## The per-surface projection (view-model) and how it is produced

A renderer never receives raw `Component`s. It receives a **`ProjectedEntity`**: a view-model the daemon computes as a **pure function** of `(EntityState, projection template, surfaceKind, projectionSchemaVersion, readCapability, as_of)`. This is the CQRS "multiple read models from one log" move — a `tray` projection and a `card` projection of the same entity are different shapes, both derived, neither authoritative — with the projection **shape supplied as bundle data**, not hardcoded.

```jsonc
// ProjectedEntity — the unit of the `state` channel. A daemon-computed view-model, NOT raw components.
{
  "handle": "entityHandle(ULID)",       // identity spec: durable PK
  "address": ["khaos", "project", "atlas"], // identity spec: compound segment LIST (never a joined string)
  "kind": "khaos.project",              // declarative bundle metadata (core ships none)
  "projectionSchemaVersion": 1,
  "version": 41207,                     // == the logPosition at which this projection is valid (gap/resume)

  "lifecycle": { "phase": "active", "since": "RFC3339" },  // from ambisphere.lifecycle component

  // --- factual domain view: SHAPED BY THE BUNDLE PROJECTION TEMPLATE for (surfaceKind, version) ---
  // firewall: kind=factual; every field traces to a declared factual component field via a template slot.
  "stateView": {
    // shape is template-defined and surface-shaped; opaque to core, schema-on-read.
    // e.g. a `card` template yields: { "headline": "...", "progress": 0.62, "blockedReason": null, "recency": "2m" }
    // e.g. a `tray`  template yields: { "glyphState": "running", "badgeCount": 0 }
    // core never branches on this; it evaluates the template generically and copies only readCapability-permitted fields.
  },

  // --- attention view: the capped rung for THIS surface (relayed from the bus, not recomputed) ---
  "attentionView": {
    "rung": "ambient",                  // already min(score-rung, ceiling, surfaceMax, focusModeCap)
    "state": "active",                  // attention facet lifecycle
    "score": 0.41,                      // present iff supportsExplanation
    "explanation": "high importance, decayed urgency", // present iff supportsExplanation
    "boundBy": "surface-max"            // why this rung (attention spec: score|entity-ceiling|surface-max|…)
  },

  // --- ADVISORY action affordances (UX hints; NOT authority; invocation is via submit) ---
  "actions": [
    {
      "actionId": "example.workflow.retry",   // action/capability spec owns the manifest
      "title": "Retry analysis",
      "destructive": false,                    // UX hint, NOT the security boundary (ADR-0001 inv.5)
      "confirmRequired": false,                // UX hint
      "preconditionsSatisfied": true,          // daemon-evaluated advisory bit (authoritative check is at invoke)
      "requiredCapabilityRef": "capref:opaque" // a REFERENCE, never a credential; may be null if surface lacks it
    }
  ]
}
```

### The projection template (the production rule)

The previously-open question — *how the daemon shapes a `tray` vs `card` `stateView` without leaking presentation into core* — is resolved as follows: **the projection shape is bundle-driven, declared as a bounded projection template, and evaluated daemon-side as a pure function.** Core ships no shapes and never branches on `surfaceKind`.

This is the same discipline the bundle/persona specs already use for narration (bounded template slots over declared factual fields), applied to the factual view-model. It lives in the bundle's existing `renderers/` section (entity-bundle-format spec, `[[renderers]]`), which previously carried only advisory hints; this spec defines the **projection-template** artifact that section serializes.

```toml
# renderers/projections.toml  (entity-bundle-format spec serializes this under [[renderers]];
#   this renderer spec OWNS its meaning. Companion to the advisory renderers/hints.toml.)
projectionSchemaVersion = 1        # MUST match a version a surface negotiates at attach

# A template is keyed by surfaceKind. Selecting fields + bounded, declared derivations only.
# Slots reference ONLY declared FACTUAL component fields (firewall — same rule as persona templates).
# NO code, NO arbitrary expressions, NO narration. A slot naming a non-factual / undeclared field
# is a BUNDLE-VALIDATION ERROR (entity-bundle-format spec L4 firewall check), not a runtime accident.

[[projection]]
surfaceKind = "tray"
[projection.stateView]
glyphState = { field = "loswf.workflow.phase" }                 # direct factual field copy
badgeCount = { field = "loswf.workflow.openCount", default = 0 }

[[projection]]
surfaceKind = "card"
[projection.stateView]
headline      = { field = "loswf.workflow.title" }
progress      = { field = "loswf.workflow.progress" }           # 0..1 factual scalar
blockedReason = { field = "loswf.workflow.blockedReason", default = null }
recency       = { field = "loswf.workflow.lastEventAt", derive = "recency-bucket" }  # bounded derivation
```

Template evaluation rules (normative):

- **Bounded, declarative, no code.** A template is field-selection + rename + a *closed, daemon-provided set* of bounded derivations (e.g. `recency-bucket`, `ratio`, `truncate`, `count`). It is **not** a DSL, has no control flow, and cannot reference a write event, a capability, or a narration slot (bundle-format spec L4 rejects all of these statically). The closed derivation set is owned by this spec; bundles may not add derivations.
- **Daemon-evaluated, pure.** `stateView = evaluate(template, EntityState, readCapability)` is a pure, total function. Core walks the template generically; it never pattern-matches on `surfaceKind` or on the field names — those are data. This keeps vendor-neutrality (inv. 8): the only thing core "knows" is how to evaluate a template, never any specific surface's shape.
- **Read-capability gating.** A slot whose source factual field the read capability does not permit is **omitted** (or coarsened per the privacy spec), not denied — the surface still gets a valid `stateView` with the permitted subset. The capability bounds what the template may emit.
- **Firewall.** Every slot's source MUST be a declared factual component field. The bundle validator statically rejects a slot naming a non-factual field, an undeclared field, an event `type`, or a capability — making the firewall a pre-load property (bundle-format spec).
- **Passthrough fallback.** If no `[[projection]]` matches `(surfaceKind, projectionSchemaVersion)`, the daemon emits a **passthrough `stateView`**: a flat, read-capability-filtered map of the entity's declared factual fields under their declared names (no renames, no derivations). This guarantees a correct factual view-model for any surface kind — including a kind no bundle anticipated — without core inventing a shape.
- **Versioned.** `projectionSchemaVersion` versions the template/view-model schema independently (bundle-format spec tracks it among the per-artifact versions). A surface negotiates a version at attach; a daemon may emit a lower one.

Other projection rules:

- **Daemon-computed, renderer-dumb.** The view-model is shaped server-side from the template so renderers stay thin (the LSP locus: the server does the analysis, the client renders). The `stateView` shape is template-defined and **opaque to core** (schema-on-read); core evaluates the template and copies only permitted fields and never interprets their meaning.
- **Keyed projection.** The cache/computation key is `(surfaceKind, projectionSchemaVersion, readCapability)` — which selects the template and bounds the fields. The same entity yields as many view-models as there are distinct keys.
- **`version` == `logPosition`.** Every `ProjectedEntity` is stamped with the `logPosition` at which it is valid — the monotonic handle for gap detection and resume.
- **Actions are advisory only.** The presence of an action descriptor with `preconditionsSatisfied: true` is a *hint* the surface MAY render an affordance. It is **not** authorization. The authoritative precondition + capability check happens at invoke time on the **write** side. `destructive`/`confirmRequired` are UX hints (ADR-0001 inv. 5), never the boundary.

### Relationship to `renderers/hints.toml`

The bundle's `renderers/hints.toml` (advisory: `honoredRungs`, a `field` to surface prominently, an `asset` name) and `renderers/projections.toml` (the projection-template defined here) are **complementary, both read-side, with distinct roles**:

- `hints.toml` — *advisory metadata*: prominence preferences and asset associations. Never authoritative (the affordance map at attach wins for capping). Unchanged by this spec.
- `projections.toml` — *the shaping rule*: determines the `stateView` shape per surface kind. This is the artifact the finding asked for; it did not previously exist, and `hints.toml` alone could not shape a full `stateView`. Both specs now agree the shaping artifact is `projections.toml`, bundle-shipped, daemon-evaluated.

## The transport: snapshot + delta + version + resync

This specializes the daemon broker's `subscribe(readCap, SubscribeRequest) -> FrameStream` and its `Frame` enum. The renderer view of those frames (all over the **read** plane — never the control channel):

```jsonc
// Frames the renderer observes (specialization of daemon Frame; one-way, cursor-resumable).
// SNAPSHOT — initial correctness for the matched scope (also the resync payload).
{ "kind": "snapshot", "atVersion": 41207, "entities": [ /* ProjectedEntity[] for this surface */ ] }

// DELTA — an incremental change, id'd by monotonic version (== logPosition) for gap detection.
{ "kind": "delta", "version": 41208, "handle": "entityHandle",
  "change": { /* whole ProjectedEntity (deltaMode=entity) OR a component-level patch (deltaMode=component) */ } }

// NARRATED — persona channel only; delivered iff includeNarration; carries kind:"narrated".
{ "kind": "narrated", "version": 41209, "handle": "entityHandle",
  "projection": { /* NarratedProjection from reducer/persona spec: text, grounds[], narrationProvenance */ } }

// RESYNC_REQUIRED — daemon tells a lagging/gapped observer to re-snapshot (cheap full recovery).
{ "kind": "resyncRequired", "fromVersion": 41100, "reason": "coalesced | gap | schema-bump" }

// HEARTBEAT — liveness without data, so a slow link can detect a dead stream.
{ "kind": "heartbeat", "version": 41209 }
```

The matching subscribe request (daemon spec `SubscribeRequest`, viewed from the renderer):

```jsonc
{
  "resumeFrom": 41100,        // last version the surface saw (SSE Last-Event-ID); null ⇒ fresh snapshot+tail
  "scope": { /* by entity / by kind / predicate over the materialized view (READ side only) */ },
  "channels": ["state", "attention"],   // subset of the THREE observation channels (never "control")
  "includeNarration": false
}
```

Transport rules:

- **Snapshot establishes correctness; deltas maintain it.** A fresh subscription (`resumeFrom: null`) receives a `snapshot` of the matched scope, then `delta`s. A new observer is immediately correct (no warm-up window where it shows stale or empty state).
- **Monotonic version is the gap detector.** Deltas carry strictly increasing `version`. If a surface sees `version` jump (missed a frame) it requests a resync. Because `version == logPosition` is gap-free monotonic in storage order, gap detection is exact.
- **Resync is cheap and idempotent.** On gap, schema bump, or coalescing, the surface re-snapshots its scope. A snapshot is self-sufficient — applying it discards prior local state. This is the LSP "republish full diagnostics for a document" pattern, not an incremental patch reconciliation.
- **Latest-wins coalescing for ambient state.** For high-frequency ambient changes, the daemon MAY coalesce deltas — a slow surface receives the latest projection or a `resyncRequired`, never an unbounded backlog. (Renderer guidance: latest-wins is correct for ambient state.)
- **The read plane never backpressures the write plane.** A slow or stuck renderer cannot stall `submit`/ingestion (directionality: read and write are separate planes; daemon spec). Worst case the renderer is told to resync.
- **Cross-stream consistency is eventual per-stream.** Each subscription converges to the latest `version` for its scope; the contract does **not** guarantee two surfaces are at the same `version` at the same instant (see Open questions).

## Action invocation does not happen here

The single most important boundary in this spec: **a renderer cannot invoke an action through the renderer port.** There is no method on `RendererPort` that mutates anything, and the broker's control channel grants no ambient write authority (daemon spec).

- Action **affordances** ride in the `ProjectedEntity.actions[]` as advisory metadata (title, flags, a `preconditionsSatisfied` bit, an opaque `requiredCapabilityRef`).
- When a human engages an affordance, the surface calls the **action/capability spec's** invocation path with a held capability. That path performs the authoritative capability + precondition check on the **write** boundary, executes, and the **result re-enters as a fact via `submit`** carrying `correlation.causedBy` (envelope spec).
- The renderer then observes the effect as a normal `delta` on the `state`/`attention` channels. It never sees its action "succeed" by mutating local state; it sees the projected consequence.

This keeps directionality intact (capability semantics only on the write boundary), keeps renderers POLA-zero by default, and makes the "optimistic UI" question a renderer-local presentation choice that is reconciled by the next authoritative frame — never a write to the view.

## The `RendererPort` (driven port)

`RendererPort` is the outbound port the daemon drives to push frames at a surface; the surface implements the consuming half. It is the headless core's only outward dependency for observation, and it is satisfied by an adapter (a UDS/loopback connection) — the core links no renderer.

```rust
/// Driven (outbound) port: the application core PUSHES frames; it never pulls from a renderer.
/// Implemented by a transport adapter (UDS/loopback). The core depends on this trait, never on a
/// concrete renderer (clean-architecture Dependency Rule: dependencies point inward).
pub trait RendererPort: Send + Sync {
    /// Negotiate at attach. Returns the capabilities the daemon will honor (a subset of the manifest),
    /// including whether a bundle projection template matched (else passthrough stateView is emitted).
    fn attach(&self, read_cap: &ReadCapabilityRef, manifest: RendererManifest)
        -> Result<ServerCapabilities, AttachError>;

    /// Open a one-way frame stream for a subscription over the READ plane. Frames are pushed; the
    /// renderer never calls back to mutate. `channels` is a subset of the THREE observation channels
    /// (state|attention|persona) — never the broker control channel. resume_from carries the last
    /// seen version (SSE Last-Event-ID).
    fn subscribe(&self, read_cap: &ReadCapabilityRef, req: SubscribeRequest)
        -> Result<FrameStream, SubscribeError>;
    // NOTE: there is deliberately NO `invoke`, NO `set_state`, NO `mutate` method here.
    // Action invocation is a DIFFERENT port (action/capability spec) on the WRITE side.
    // The broker's reserved control channel is a DIFFERENT seam (daemon spec), not part of this port.
}

pub enum AttachError { Unauthorized, UnsupportedProjectionSchema, MalformedManifest }
pub enum SubscribeError { Unauthorized, UnknownScope, UnsupportedChannel }
```

- **Driven, not driving.** The core never asks a renderer for anything; it pushes. A renderer that disappears is just a closed stream — no `onDisconnect` authority semantics (counter to RivetKit's connection model).
- **Language-neutral wire.** The reference binding is framed CBOR/JSON over the daemon's UDS (loopback fallback), per the daemon spec. A Swift/Kotlin/TS/Go renderer implements the consuming half over the same framing without linking the Rust core (implementation-language guidance: the observation contract is a language-neutral seam). The projection template is declarative data, equally consumable everywhere.
- **Headless core.** The daemon runs and is fully correct with zero renderers attached. Renderers are optional observers; their absence changes nothing about the log, reducers, the view, or template evaluation (templates evaluate lazily per subscription).

## Worked surfaces (illustrative — vendor concepts live in the adapter/example layer)

These are illustrations of *how surfaces differ in projection and affordance*, not core types. The kinds and `stateView` shapes are bundle-template-defined.

- **Tray item.** `surfaceKind: "tray"`, `channels: ["state","attention"]`, `honoredRungs: ["quiet","ambient","nudge"]`, `maxConcurrent: 1`. Its `tray` projection template yields a tiny `stateView` (`glyphState`, `badgeCount`) and it sees a capped `attentionView`. A `loswf.factory.<repo>` entity that the bus ranks `prominent` is shown at `nudge` here (capped by `surfaceMax`) — the calm-technology "glanceable" default.
- **Dashboard card.** `surfaceKind: "card"`, `channels: ["state","attention"]`, `honoredRungs` up to `prominent`, `supportsExplanation: true`, `supportsActionAffordances: true`. Its `card` template yields a richer `stateView` (headline, progress, blocked reason, recency), plus the `score`/`explanation`, and advisory `actions[]`. Engaging "Retry" invokes via the write side.
- **Companion.** `surfaceKind: "companion"`, `channels: ["state","attention","persona"]`, `includeNarration: true`. Additionally receives `narrated` frames on the persona channel and expressive tokens — but still renders correctly if `narrationAvailable: false`.
- **TUI.** `surfaceKind: "tui"`, `channels: ["state"]`, factual-only. A pure operational view with no persona. If the bundle ships no `tui` template, it receives the **passthrough `stateView`** — proving a surface functions on `state` alone even for a kind no bundle anticipated.

## Acceptance criteria

1. **One-way / no write path.** There exists no method on `RendererPort` (or its wire binding) that mutates the log, a component, or the view. A conformance test asserts the port surface contains attach/subscribe only; an attempt to "write back" has nowhere to land. The broker control channel grants no write authority.
2. **POLA by default.** A renderer attaches with a read capability and can invoke **no** action through this contract; affordances are advisory. A test confirms a renderer holding only a read capability cannot cause any log append via the renderer port.
3. **Action round-trip via write side.** Engaging an advisory affordance results in an `invoke` (action/capability spec) → `submit` (envelope spec, `correlation.causedBy`) → reduction → a fresh `delta` on the renderer's `state` channel. A test asserts the renderer observes the effect only as a pushed frame, never via local mutation.
4. **Capability degradation.** A surface declaring `channels`/`projectionSchemaVersion`/affordances the daemon does not fully support still attaches and works on the intersection; unknown manifest fields are ignored. A test attaches a "future" manifest and asserts correct degraded operation.
5. **Exactly three observation channels.** The fixed observation set is `state | attention | persona`. A test asserts a `subscribe` cannot name `control` (it is rejected/unrepresentable as an observation channel) and that no fourth channel exists; a cross-spec lint asserts the daemon and persona specs cite this three-channel set.
6. **Three-channel firewall.** `state` and `attention` frames carry only `kind: "factual"`; `narrated` frames appear **only** on `persona` and **only** when `includeNarration: true`. A surface subscribed factual-only never receives a `narrated` frame and renders correctly. A test asserts narration cannot leak onto `state`/`attention`.
7. **Projection production rule.** The `stateView` shape is produced by evaluating a bundle-shipped projection template for `(surfaceKind, projectionSchemaVersion)`; core contains no per-surface shape and no `surfaceKind` branch. A test (a) shows two kinds (`tray`, `card`) yield different `stateView`s from one `EntityState` purely from their templates, (b) asserts a grep of core finds no `SurfaceKind` literal and no branch on `stateView` contents, and (c) asserts evaluation is a pure function of `(view, template, readCapability)`.
8. **Template firewall is static.** A projection-template slot naming a non-factual field, an undeclared field, an event type, or a capability fails **bundle validation** (entity-bundle-format L4), not at runtime. A test feeds such a bundle and asserts load is rejected with a precise pointer.
9. **Passthrough fallback.** A surface whose `surfaceKind` matches no template attaches with `projectionTemplateResolved: false` and receives a flat, read-capability-filtered factual `stateView` (declared field names), never an error and never raw components. A test attaches an unanticipated kind and asserts a correct passthrough view-model.
10. **Per-surface projection from one view.** Two surfaces (`tray`, `card`) subscribed to the same entity receive **different** `ProjectedEntity` shapes from one `EntityState`, each a pure function of its key; neither receives raw components. A test diffs the two projections and asserts both derive from the same view version.
11. **Snapshot correctness.** A fresh subscription receives a `snapshot` before any `delta`; the observer is immediately correct (no empty/stale window). A test attaches mid-stream and asserts the first frame is a snapshot at the current version.
12. **Monotonic version + gap detection + resync.** Deltas carry strictly increasing `version == logPosition`; a forced gap (dropped frame) is detected by the observer and triggers a `resyncRequired`/re-snapshot that restores correctness. A test injects a gap and asserts recovery without missing state.
13. **Resumability.** A surface that disconnects and reconnects with `resumeFrom = lastVersion` receives exactly the frames it missed, gap-free (SSE Last-Event-ID semantics). A test asserts no duplicates and no gaps across a reconnect.
14. **Surface capping.** The same entity the bus ranks `prominent` is delivered at the surface's `surfaceMax` rung in `attentionView`, with `boundBy: "surface-max"`. A test attaches two surfaces with different `honoredRungs` and asserts different capped rungs for the same entity.
15. **Backpressure isolation.** A deliberately stalled renderer never delays `submit`/ingestion; it is coalesced or told to resync. A test stalls an observer and asserts write throughput is unaffected.
16. **Headless core.** The daemon runs, ingests, reduces, and projects correctly with zero renderers attached; attaching one later yields an immediately-correct snapshot. A test runs a full ingest cycle with no observers, then attaches and asserts a correct snapshot.
17. **Language-neutral wire.** A non-Rust reference observer (e.g. a TS or Go test client) attaches over the framed transport and receives correct snapshot/delta/resync frames without linking the core. A cross-language conformance test asserts byte-compatible frames.
18. **Vendor neutrality.** Core/projection code ships zero `SurfaceKind` values and zero per-surface view-model shapes and never branches on `payload`/`khaos.*`/`loswf.*`; the `stateView` is produced solely by generic template evaluation. A lint/test asserts no vendor identifiers, no surface-shape literals, and no `payload`-internal branching in core.
19. **Broker scoping.** A cross-spec lint asserts that the shared "broker" definition (thin local seam; two data planes + one control channel; topics/fan-out/external pub-sub out of scope and ADR-gated) is referenced identically by the renderer, daemon, and adapter specs, and that this spec introduces no topic/fan-out construct.

## Open questions

- **Projection-template expressiveness.** The template grammar is deliberately small (field-selection + rename + a closed daemon-provided derivation set) to keep presentation logic out of core. Whether realistic Khaos/LOSWF surfaces need richer derived fields — and if so whether they extend the closed derivation set or move to a registered read-side projection *module* referenced by a language-neutral coordinate (bundle-format spec module pattern) rather than a declarative template — is open and pending a spike. The constraint is firm: no Turing-complete bundle DSL (bundle-format spec reject).
- **Surface-taxonomy ownership.** `SurfaceKind` is an **open free-form semantic string** here (not presentational, not a fixed enum). With the template mechanism, an unregistered kind falls back to passthrough; whether the daemon should instead validate kinds against the bundle-registered template set (failing closed, or warning) for deterministic routing, or keep them fully open, is unresolved. (Guidance: keep it semantic, not presentational — settled; registry-vs-open — open.)
- **ADR-0001 status (suite-wide).** This spec conforms to a **provisional** ADR-0001 and cites a canonical numbered-invariant anchor ADR-0001 must publish. Until ADR-0001 is resolved to a single status (Accepted, acceptance criteria checked off, canonical invariant list added), every conformance reference here is provisional. This is a shared blocker across all nine follow-on specs, recorded here rather than silently treated as ratified.
- **Delta granularity/encoding.** Default is whole-`ProjectedEntity` replacement (`deltaMode: entity`) for small entities, with opt-in component-level patches (`deltaMode: component`) for high-frequency surfaces — pending a DDIA spike at realistic Khaos/LOSWF view-change rates.
- **Cross-surface consistency.** The contract guarantees **eventual per-stream** convergence only, not cross-stream simultaneity. Is a stronger cross-surface consistency guarantee ever required (e.g. two surfaces in one window must never disagree)?
- **Action metadata split.** Advisory descriptors (id, title, flags, `preconditionsSatisfied`, `requiredCapabilityRef`) ride in the projection; full `inputSchema` is deferred to an on-engage fetch from the action/capability spec. The split point is provisional and depends on that spec landing.
- **Chat / artifact / event-history retrieval.** Issue #5 §7 (chat scoped to entity context) and history/artifact queries are scoped **out** of this contract as a **separate query surface**. The boundary needs the action/capability and adapter specs to confirm whether they extend this observation contract or stand apart.
- **Persona channel resolution locus.** Whether the **daemon** resolves the persona cascade (semantic + attention) and the renderer resolves only styling, or the renderer receives raw expressive tokens — deferred to the persona projection spec. This spec fixes only the channel and the `kind: "narrated"` firewall tag.

