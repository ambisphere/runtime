# Actor model — prior art

**Status:** draft · **Scope:** runtime computational model, not persona authoring · **Companion to:** `specs/VISION.md`, `RFP.md`, issue #4 · **Sibling note:** `specs/drafts/persona-prior-art.md`

This note surveys a production actor-model runtime — **RivetKit** (Rivet) — to test the actor-side claims raised in issue #4 (*"RFP response: Foundational runtime paradigm — actor model vs ECS vs hybrid"*). It exists so the paradigm decision can stand on evidence from a mature implementation rather than on actor-model theory alone. It does not pick a paradigm; it records what a real actor runtime does and does not solve for an ambient entity runtime.

Issue #4 already cites Erlang/OTP and Spritely Goblins. RivetKit fills a gap: a contemporary, locally-runnable, actor-per-entity runtime with durable state and hibernation — the closest existing analogue to "a long-running local daemon that owns persistent entity state."

## Surveyed project

### RivetKit / Rivet Actors

**What it is.** An open-source TypeScript actor runtime. An entity is an actor; actors are "long-lived processes with durable state, realtime, and hibernate when not in use." The runtime can run as a single-node local environment (filesystem or memory driver), self-hosted (Rust binary / Docker, persisting to Postgres or RocksDB), or on Rivet cloud. Drivers are pluggable behind an `ActorDriver` / `ManagerDriver` interface.

**Source.** `github.com/rivet-dev/rivet` · docs `rivet.dev/docs` · mined via the `rivetkit` agent skill (`rivet-dev/skills@rivetkit`, ~6.3K installs).

## Claim-by-claim findings against issue #4

### Confirmed — the actor side is solved-problem space

- **Sleepy actors / hibernation.** RivetKit implements this as a default lifecycle, not a bespoke feature: `Loading → Ready → Started → SleepGrace → SleepFinalize`, with `onSleep` / `onWake` hooks, a configurable `sleepTimeout`, and `c.keepAwake(promise)` to hold off sleep. Wake triggers are network requests, websocket messages, or persistent **alarms**. This maps directly to ambient entities that may go hours between semantic events and must restore transparently. #4's "sleepy actors" claim is production-proven.

- **Addressed messages by entity ID.** RivetKit **actor keys** are a string or compound array key (`getOrCreate(["room", "general"])`), supporting hierarchical, multi-dimensional addressing and singleton actors. It explicitly warns against building keys via string interpolation of user data (key-injection risk). This is a ready-made entity-identity and addressing scheme, including the footgun to avoid, for #4's "events are messages, entities are actors."

- **Per-entity isolation.** "actor-per-entity… isolated state that combines compute and storage." Canonical examples: actor-per-user, -session, -document, -tenant. Confirms #4's claim that a buggy operational entity cannot corrupt another entity's state.

- **Durable state across crashes and upgrades.** State is in-memory yet auto-persisted, surviving crashes and upgrades; persistent scheduling (`c.schedule.after` / `c.schedule.at`) survives restarts; **live actor migration** (hibernatable websockets) preserves connections across upgrades and hot reloads.

### Confirmed as the hard problem — the attention bus

This is the most useful finding. #4's central worry is that actors are isolated, so the attention bus — which must look across **all** entities to decide visibility — either becomes a privileged super-actor that breaks isolation, or duplicates state in a parallel index. RivetKit's design confirms this is a real, unsolved gap even in a mature actor runtime:

- Cross-actor communication is strictly **point-to-point**: `c.client().<actor>.getOrCreate(key)`. You address each actor individually.
- There is **no native "query all actors matching a predicate"** primitive. Nothing scans across the actor population.
- RivetKit's own answer to multi-entity workflows is an **"Actor Orchestration" coordinator actor** — precisely the "privileged super-actor" #4 warned against.
- Composing a multi-entity view means holding separate event subscriptions per actor and reassembling — matching #4's "more complexity for no clear benefit over a flat data store."

→ External evidence for #4's recommendation: **spec the attention bus before the entity state model.** A production actor framework still has no answer for cross-entity visibility routing; ECS makes it trivial. This asymmetry is the binding constraint on the paradigm choice.

### Refinement — "capability security slots into the actor model" is too strong

#4 states capability-based security "slots in naturally" to the actor model. RivetKit's access control is **deny-by-default permission hooks (RBAC-style)** — `onBeforeConnect`, per-action authorization, and `canPublish` / `canSubscribe` gates — **not** object-capability (no unforgeable references-as-permissions). Capability security is a property of *specific* ocap actor systems (Spritely Goblins), not of the actor model in general; most production actor runtimes, RivetKit included, are RBAC-style. The survey and any spec should distinguish **"actor model"** from **"capability-secured actor model"** — different lineages with different security guarantees. This narrows #4's claim without refuting it.

### Nuance — "transactional state / rollback" is not free

#4 borrows "transactional state, rollback on failed reduction" from actor-model literature. RivetKit provides *durable, auto-persisted* state — not transactional rollback or event-sourcing by default. The transactional guarantee #4 wants is real in some systems (Goblins) but is not an automatic property of adopting the actor model. If reduction-with-rollback is a requirement, it must be specced explicitly (e.g. an event-sourced log under the entity), not assumed to come with the paradigm.

## What Ambisphere can adopt

1. **Lifecycle hook vocabulary.** `createState` / `onCreate` / `onWake` / `onSleep` / `onDestroy` plus `sleepTimeout` and `keepAwake` is a clean, proven lifecycle for entities that idle for long periods. Worth importing as the shape of the entity lifecycle spec (roadmap item 1).

2. **Compound-key addressing.** Hierarchical array keys with injection safety give entity identity and addressing without string-delimiter hazards. A strong default for the entity identity model.

3. **Driver abstraction as a decoupling precedent.** "Write actors once, plug in any backend" (filesystem / memory / engine / Cloudflare Durable Objects) is a working precedent for Ambisphere's renderer-agnostic, no-lock-in philosophy applied at the persistence layer.

4. **Persistent scheduling.** Alarms that survive restart are prior art for ambient entities with temporal behavior (a deploy watcher that escalates after N minutes; a companion that acts on a timer).

## What Ambisphere should not inherit

| Pattern | Why |
|---|---|
| Coordinator-actor as the cross-entity answer | This is exactly the attention-bus anti-pattern #4 flags. Ambisphere's attention routing must not be modeled as a privileged super-actor that reaches into every entity. The attention bus needs its own design, likely closer to a materialized view over an event stream. |
| Serverless / HTTP-request execution model | RivetKit's default mode is HTTP-driven and scale-to-zero for cloud. Ambisphere is local-first and daemon-oriented; the daemon owns entity state continuously. Adopt the lifecycle, not the serverless transport. |
| RBAC permission hooks as "the" security model | Fine for authorizing connections, but #4's multi-application trust model (roadmap items 9–10) likely wants object-capability semantics. Don't conflate RivetKit's RBAC with the capability model the vision implies. |
| Vendor / cloud coupling (Rivet engine, dashboard.rivet.dev) | Cite the runtime patterns; do not introduce a dependency on Rivet cloud. Local-first must stay vendor-neutral. |

## Open questions

- If the attention bus cannot be an actor without breaking isolation, what is it? A system over a flat store (ECS), a materialized view over an event log, or a separate index the daemon maintains? This is the paradigm-deciding question — open, and the reason #4 recommends speccing the attention bus first.
- Does Ambisphere require transactional reduction-with-rollback? If yes, an event-sourced entity log is implied regardless of actor-vs-ECS framing — which may dissolve part of the dichotomy at the persistence layer. Needs a `ddia`-lens spike.
- Which security model does the multi-application sharing vision actually need — RBAC hooks (sufficient for single-user local) or object-capability (needed for cross-app/cross-trust sharing)? Drives whether a capability-secured actor lineage (Goblins) is in scope.
- Does the lifecycle hook set above survive contact with renderers as passive observers? RivetKit's connection model (`onConnect` / `onDisconnect`) assumes active clients; Ambisphere renderers are subscription-based observers (#4 assertion #3). The mismatch needs a spec.

## Citations to keep visible

When the runtime architecture spec or ADR-0001 lands, RivetKit must be cited inline alongside Erlang/OTP, Spritely Goblins, and Bevy ECS, with this note's mappings — so contributors can see which actor-model properties are production-proven, which are lineage-specific (capability security, transactional state), and which the actor model demonstrably does *not* solve (cross-entity attention routing). The runtime is better when its lineage is legible.
