# Persona projection

**Status:** draft · **Scope:** persona as a pure, optional, derived read-side projection — the function `project(entityState, attentionState, capabilityView, surface) -> PersonaProjection`; the three-layer separation (semantic states owned by reducers / expressive states owned by persona / renderer frames owned by renderers); the layered cascade resolution (product → kind → state·surface → instance); the declarative persona bundle that references the *declared* semantic-state vocabulary *through the one shared predicate + field-path mini-language*; the factual/narrated firewall as it crosses the persona boundary; and the rules that keep persona from ever gating a capability-critical signal · **Companion to:** `specs/VISION.md` (principle 2 "persona-agnostic", non-goals "a specific personality system" / "a virtual companion product"), `specs/SRS.md` (§3 "Persona projection"), `RFP.md` (§ "Persona abstraction"), issues #4 #5 #6 · **Sequenced:** eleventh among the follow-on specs (last among the read-side concerns, after the renderer observation contract and the action/capability and privacy specs; before only the entity-bundle/package-format spec) per ADR-0001 and issue #4 · **Conforms to:** ADR-0001 (foundational paradigm + directionality invariant — **currently `Proposed`; this spec conforms to it provisionally and re-pins on ADR acceptance**, see § "ADR status"); the attention-routing spec (persona *consumes* the `attention` facet and the ranked view, never feeds them; it receives a *query-time-computed* rung, never a cached one); the reducer/state-component spec (semantic states are facets produced there; persona reads them and is never a reducer-written component; the fact/narration firewall is structural there and re-asserted here; **and the shared declarative predicate + field-path mini-language is owned there — persona references it, it does not invent syntax**); the semantic-event-envelope spec (persona reads facts derived from the log; it never submits, never appears on the log); the entity-identity spec (the cascade walks `instance-of` for kind defaults and `child-of` for inheritance); the daemon-architecture spec (where the cascade resolves, how the persona channel is brokered, and the **three** observation channels `state | attention | persona`; `control` is a broker-only channel, not an observation channel) · **Sibling notes:** `specs/drafts/persona-prior-art.md`, `specs/drafts/runtime-paradigm-and-specs-guidance.md`, `specs/drafts/actor-model-prior-art.md`, `specs/drafts/implementation-language-guidance.md`

This spec defines the **persona projection**: the optional, replaceable read-side layer that maps an entity's *factual semantic state* into *expressive presentational metadata* a renderer can dress up. It is the read-side concern that attaches last, because it depends on everything below it (state, attention, capability affordances, surfaces) and nothing depends on it. An entity is fully functional with no persona at all; a CI watcher, an observability rollup, and an accessibility surface may never carry one. Persona is, in the words of VISION principle 2, "one optional projection over entity state, not a built-in concept."

It is a **pure derived projection**, in exactly the sense the reducer spec uses for components: `PersonaProjection = project(view, surface)` is a total function of read-only inputs, holds no authoritative state, is never written to the log, is never a reducer input, and is fully rebuildable and droppable. Per the ADR-0001 directionality invariant, persona lives entirely on the read side: it never submits an event, never checks a capability (it reads a *pre-resolved* affordance view), and never decides what is interruptive (attention has final authority). The recurring failure mode this spec exists to prevent is persona drifting into a personality/companion *engine* with its own state, its own authority, or its own facts — a VISION non-goal ("a specific personality system", "a virtual companion product", "a VTuber framework").

### ADR status

ADR-0001's own `Status` is currently **`Proposed`** (not yet `Accepted`), while this and the other follow-on specs cite its numbered invariants as binding. Until the ADR is ratified, **this spec conforms to ADR-0001 provisionally** and re-pins on acceptance. The invariant numbers used below (inv.1 directionality, inv.3 determinism, inv.5 ocap, inv.6 fact/narration firewall, inv.8 vendor neutrality) refer to the canonical numbered invariant list that ADR-0001 is expected to carry; if those numbers shift on ratification, this spec's conformance table is updated, not its substance. This note is mirrored across all nine follow-on specs so none of them claims implementation-readiness against an unaccepted foundation.

## Goals and non-goals

### Goals

- Define persona as a **pure, optional, derived** projection: `project(entityState, attentionState, capabilityView, surface) -> PersonaProjection` over read-only views, output carrying **no authoritative state**.
- Fix the **three-layer separation**: reducers own **semantic states** (factual facets), persona maps them to **expressive states** (presentational metadata), renderers map those to **frames** (sprites/vectors/widgets/text). Each layer is independently replaceable.
- Make persona **optional and additive**: zero-persona entities are first-class; a formal **null/factual projection** is the shared default everything degrades to.
- Define the **layered cascade**: `product default → entity-kind → state·surface → instance`, adopting the design-token three-tier override discipline, with a single deterministic precedence and one provenance audit point.
- Make the **factual/narrated firewall** structural across the persona boundary: persona may select and arrange *references to declared factual fields*, but narrated phrasing is a separately-tagged, non-authoritative projection produced only by an egress adapter; every surface MUST be able to render factual-only.
- Guarantee persona **never gates a capability-critical signal**: attention prominence, approval-requested state, and the factual projection are reachable on a surface even when persona is absent, errored, or stripped.
- Define the **declarative persona bundle**: persona rules ship as data that references the entity-kind's *declared* semantic-state vocabulary; no Turing-complete DSL, no imperative behavior.
- Define **where the cascade resolves** (daemon resolves semantic+attention into the projection; renderer resolves styling) and the **persona channel** of the renderer contract.

### Non-goals (adopt/reject framing — rejections carried from the guidance and VISION)

- **Not** a personality / character / mood engine or a companion product. (Reject: VISION non-goals "a specific personality system", "a virtual companion product", "a VTuber framework", "a chatbot platform".) Persona is metadata, not a being. Concretely: **core defines no schema for personality, traits, mood, or voice prompts.** Core's persona schema covers only expressive-state / tone / intensity / slots / narration-ref. Any personality/voice metadata an author wishes to ship is **opaque adapter-private data** core never parses (§ "Persona depth is adapter-private").
- **Not** a source of truth and **not** a reducer-written component. Persona is derived and droppable; it is never on the log and never authoritative. (Reject: persona as authoritative state — `persona-prior-art.md`.)
- **Not** required. Operational entities run with zero persona. (Reject: persona-as-mandatory.)
- **Not** the attention or capability authority. Persona reads attention and a pre-resolved affordance view; it never ranks, never interrupts, never authorizes. (Reject: persona deciding interruption or holding capability.)
- **Not** a renderer / animation-state vocabulary. No spritesheet, atlas geometry, frame counts, or nine hardcoded animation states in the persona contract. (Reject: spritesheet-as-truth and the fixed `idle`/`running-left`/`waving` atlas — `persona-prior-art.md`, codex-pets.)
- **Not** vendor identity. No hash-from-account-id determinism; no Khaos/LOSWF persona in core; identity belongs to the bundle, never the host account. (Reject: claude-buddy hash-from-account-id, `$CODEX_HOME` lock-in.)
- **Not** a mandatory AI feature. The factual projection requires no model. Narration is optional, egress-only, and bounded. (Reject: AI narration as required or as a fact.)
- **Not** a query/analytics surface or an action path. Persona consumes views; it does not extend the query contract or invoke actions.

## Prior art (citations kept visible)

- **codex-pets, hatch-pet, claude-buddy (`specs/drafts/persona-prior-art.md`).** Adopt: **state-vocabulary-as-contract** (the *named states* are the API between agents and entities — generalized here into the declared semantic-state vocabulary an entity-kind exposes); the **self-contained bundle** (persona ships as data the runtime consumes, authoring separable from runtime); the **hatch authoring → packaged-artifact-with-QA** shape (deferred to the bundle spec but assumed here). **Reject** (revised from the earlier "optional persona depth" adoption): persona **depth** (personality string / traits / voice prompt) as a *core-schema* concept — see § "Persona depth is adapter-private" and the resolution of the former open question. Personality/voice metadata is permitted only as **opaque, adapter-private** data that core never parses, validates, or reads; core ships no schema for it. This is the structural firewall against the VISION non-goal "a specific personality system". Reject also: **spritesheet-as-truth** and **nine hardcoded animation states** (`running-left`/`waving` are renderer concerns; `working`/`blocked`/`awaiting-human` are runtime concerns); **`$CODEX_HOME` path lock-in**; **hash-from-account-id** determinism; **single assumed render channel**. Sources: `github.com/codex-pets/codex-pets`, `github.com/openai/skills .../hatch-pet/SKILL.md`, `1270011/claude-buddy`.
- **Design tokens — Material Design 3 (reference → system → component) and Brad Frost.** Adopt: the **three-tier token cascade** — Material 3's *reference* (raw values), *system* (semantic roles, e.g. `md.sys.color.primary`), and *component* (per-component overrides, e.g. `md.comp.fab.container.color`) tiers map directly onto Ambisphere's *product default → kind/state-semantic → instance* cascade, and the white-label override pattern (theme without touching component logic) is exactly the layered persona override this spec needs. Reject: the **styling-only assumption** — design tokens carry no provenance and no factual/narrated discriminator; persona tokens MUST. Sources: `m3.material.io/foundations/design-tokens`, Material 3 reference/system/component token classes.
- **Calm Technology — Weiser & Brown (1996), Amber Case (2015).** Adopt: **tone matches purpose and context** — a calm presentation moves with the situation; persona's surface-aware tone is a discretization of center/periphery, *consuming* the attention spec's rung, never setting it. Reject: **device-specific tone** and physical-embodiment bias. Sources: `calmtech.com/papers/coming-age-calm-technology`, *Principles of Calm Technology*.
- **CQRS read-model projections / DDIA stream–table duality (Kleppmann ch. 11–12).** Adopt: persona as **one more independent projection** over the same log, recomputed and droppable, never on the write path. Reject: treating it as anything but derived; it must never gate a capability-critical signal.
- **LLM grounding / provenance research (arXiv 2411.01022).** Adopt: **structural factual-vs-generated separation** — untraceable narration is indistinguishable from hallucination, so narrated phrasing must cite the declared factual fields it grounds in. Reject: heavyweight RAG fact-checkers as a core dependency; the firewall here is structural (template slots bound to declared fields), not a runtime judge.
- **W3C PROV-DM (via the reducer spec).** Adopt: persona output carries provenance distinguishing `factual` (derived from a reducer-produced facet, with the source facet cited) from `narrated` (model-generated, with narration provenance) — the same `kind` discriminator the reducer spec fixes, re-asserted at this boundary.

## The three layers

Persona exists to keep one wall from collapsing: the wall between *what is true* and *how it looks*. The runtime enforces this as three layers, each owned by a different spec, each independently replaceable:

```
            owns                       reads                          produces
─────────────────────────────────────────────────────────────────────────────────────
LAYER 1   reducer/state-component  →  the log (facts)            →  SEMANTIC STATES
  (facts)   spec                                                     (declared facets:
                                                                      lifecycle, attention,
                                                                      domain facets)

LAYER 2   THIS SPEC                →  semantic states +          →  EXPRESSIVE STATES
  (expression)                         attention + affordance        (PersonaProjection:
                                        view + surface                expressive-state tag,
                                                                      tone, intensity,
                                                                      slots, narration ref)

LAYER 3   renderer observation     →  expressive states          →  FRAMES
  (frames)  contract + renderer                                      (sprites / vectors /
                                                                      widgets / status text —
                                                                      renderer's private
                                                                      vocabulary)
```

- **Layer 1 — semantic states (facts).** Owned by the reducer/state-component spec. These are typed components produced by pure reducers from the log: the `ambisphere.identity` facet, the canonical `attention` facet, the entity's lifecycle, and whatever **declared domain facets** the entity-kind's bundle registers (e.g. a `workflow.phase` facet with values `planning | building | blocked | done`). The set of values a facet may take is the entity-kind's **declared semantic-state vocabulary**. Persona is forbidden from inventing facts; it may only read these.
- **Layer 2 — expressive states (expression).** Owned by **this spec**. A pure mapping from semantic states (plus attention, a pre-resolved affordance view, and the target surface) onto presentational metadata: an *expressive-state* tag, a tone, an intensity, a set of declarative-content slots, and an optional reference to a separately-stored narration. This is metadata only — it names *how to express*, never *how to draw*.
- **Layer 3 — frames (rendering).** Owned by the renderer observation contract and the renderer itself. The renderer takes an expressive state (e.g. `expressive: "concerned"`, `tone: "operational"`, `intensity: 0.7`) and chooses its own private frames: a sprite row, a Live2D motion, a vector pose, a tray-icon variant, a status-bar glyph, or a line of TUI text. **The persona contract names no frame.** Two renderers may dress the same expressive state completely differently; neither is canonical.

This is precisely the `persona-prior-art.md` adoption — "the named states are the contract; everything above and below is replaceable" — split into two contracts so that *operational* semantic states (`blocked`, `awaiting-human`) and *presentational* frames (`running-left`, `waving`) never live in the same vocabulary again.

### Replaceability is the test

Each layer must be swappable without touching the others:

- Replace **Layer 1** (a new reducer / new facet values) → persona's cascade re-resolves over the new vocabulary; a mapping for an unknown semantic value falls through to the default expressive state (never errors).
- Replace **Layer 2** (a different persona bundle, or none) → the same facts now express differently, or express as the null/factual projection; renderers see a different expressive state but the same channel shape.
- Replace **Layer 3** (a new renderer) → the same expressive state is dressed in new frames; no persona change.

A spec change that forces edits across two layers to stay correct is a layering violation and is rejected in review.

## The persona projection function

The single entry point is pure and total:

```
project(
    entity:        EntityHandle,          // identity only; resolved by the daemon
    semanticState: SemanticStateView,     // read-only snapshot of declared facets (Layer 1)
    attention:     AttentionView,         // read-only: score, rung, state (from attention spec)
    affordances:   AffordanceView,        // PRE-RESOLVED safe-action summary (NOT a capability)
    surface:       SurfaceDescriptor,     // which surface is asking (kind, capabilities)
    asOf:          Timestamp,             // query-time; persona computes no decay itself
    personaSet:    ResolvedPersonaBundle  // the cascade-resolved persona rules (see below)
) -> PersonaProjection
```

Properties (inherited from the reducer spec's projection discipline and the ADR-0001 invariants):

- **Pure / total / deterministic.** No IO, clock, RNG, or randomized-map iteration. Given identical inputs it returns byte-identical output. `asOf` is passed in (persona never reads the wall clock); any recency/attention input is already computed by the attention query against the same `asOf`.
- **Read-only inputs.** All four state inputs are *views* — redacted/coarsened projections the read plane already produces (daemon spec inv.7; privacy spec). Persona cannot reach raw entity state, the log, or a credential.
- **No authority.** `affordances` is a `AffordanceView` — a pre-resolved list of *which safe actions are currently available and their UX hints* — **not** a capability and **not** the capability policy. Persona never evaluates a capability; the action/capability spec resolves authority on the write side and the daemon hands persona only the resulting safe-action summary. (Open question resolved in favor of the pre-resolved view, per `persona-prior-art.md`.)
- **Surface-aware, attention-subordinate.** `surface` and `attention` shape tone and intensity, but persona **never changes the rung**. If persona wants to look calm and attention says `prominent`, the surface still renders at `prominent`; persona only chooses how the `prominent` thing is dressed.
- **Total over unknown vocabulary.** An unmapped semantic value, a missing facet, or an empty `personaSet` resolves to the **null/factual projection** (below), never an error.

### `PersonaProjection` schema

```jsonc
{
  "schemaVersion": "1",
  "entity": "<entityHandle>",            // identity echo; no entity state inlined
  "surface": "<surfaceId>",              // the surface this projection was computed for
  "asOf": "2026-06-10T12:00:00Z",

  // ── expressive state (Layer 2 output; the renderer's input) ──
  "expressive": "concerned",             // an expressive-state TAG from the persona bundle's
                                         //   declared expressive vocabulary; NOT a frame name
  "tone": "operational",                 // a declared tone token (e.g. operational|playful|quiet|formal)
  "intensity": 0.7,                      // [0,1]; how strongly to express; renderer may quantize
  "presence": "ambient",                 // glanceability hint, an ADVISORY mirror of the rung the
                                         //   attention query COMPUTED for this same `asOf`. The rung
                                         //   is never read from a cache; it is always computed at
                                         //   query time from decay-invariant index inputs + `asOf`
                                         //   (attention spec). `presence` is never the rung itself.

  // ── declarative content slots (factual-only) ──
  // Slots use the SHARED slot/brace grammar owned by the reducer/state-component spec
  // (§ "declarative predicate + field-path mini-language → slot / brace resolution").
  // A {ref} is a field-path into EntityState; a {text} is a static authoring literal.
  // Persona invents no slot syntax of its own.
  "slots": {
    "label":   { "ref": "example.workflow.phase" },   // field-path; resolves to a declared facet value
    "summary": { "text": "Blocked on review" },        // static bundle literal (no facts)
    "badge":   { "ref": "ambisphere.attention.rung" }  // attention rung resolved AT QUERY TIME (never cached)
  },

  // ── narration reference (OPTIONAL, never inlined here) ──
  "narration": {
    "available": true,                   // whether an egress adapter has produced narration
    "ref": "narr:01J...",                // opaque handle into the SEPARATE narrated store
    "kind": "narrated"                   // ALWAYS narrated when present; never factual
  },

  // ── provenance (the firewall, re-asserted at this boundary) ──
  "provenance": {
    "kind": "factual",                   // the PROJECTION ITSELF is factual: a pure function
                                         //   of facts; "narrated" content lives only behind
                                         //   narration.ref, never in this document's slots
    "personaSetVersion": "khaos.story@2.3.0+resolved.7c1f",  // which resolved cascade produced this
    "groundedFacets": ["example.workflow", "ambisphere.attention"],  // declared facets (component-types) this drew from
    "cascade": ["product:khaos", "kind:khaos.project", "state:blocked@tray", "instance:proj-42"]
  },

  // ── degradation flag ──
  "fallback": false                      // true when this is the null/factual projection
}
```

Notes that are load-bearing:

- **The projection document itself is `kind: "factual"`.** It is a pure function of facts. Anything generated by a model is *not* inlined; it is reachable only through `narration.ref`, which points into the separate narrated store the reducer spec defines (`NarratedProjection`, never on the log, never in `EntityState`). A surface that renders factual-only simply ignores `narration`.
- **Slots are references or literals, never free narration.** A `{ref}` resolves to a *declared* factual field (a facet value, an attention scalar). A `{text}` is a static authoring-time literal from the bundle. There is no slot type that carries model output; that path is exclusively `narration.ref`.
- **`presence` is an advisory mirror, not the authority.** It is derived from the `attention.rung` *that the attention query computed for this projection's `asOf`* so a renderer that subscribes only to the persona channel still has a glanceability hint, but the attention channel's rung is the truth; if the two ever disagree, the rung wins. **No rung or score is ever cached and re-served.** The always-resident attention summary index and any materialized rollup hold only decay-invariant inputs (raw scalars, decay params, `anchorTime`, `lastEventTime`, state, ceiling, parent, child-count, contributing-set); rung and score are *always* recomputed from those plus `asOf` (attention spec inv. determinism; daemon spec). A persona projection therefore never mirrors a stale rung — `presence` for a given `asOf` is whatever the rung is for that same `asOf`, which is the property that keeps "identical rankings for identical (view, as_of)" intact across the persona boundary.
- **No frame anywhere.** No sprite path, no atlas coordinate, no animation name. The closest persona gets to rendering is the abstract `expressive`/`tone`/`intensity` triple; turning that into pixels is Layer 3's private business.

### The null / factual projection

The shared default — the value `project(...)` returns when there is no persona bundle, the cascade is empty, an input facet is missing, or persona errors — is a first-class, formally-specified value:

```jsonc
{
  "schemaVersion": "1",
  "entity": "<entityHandle>",
  "surface": "<surfaceId>",
  "expressive": "neutral",
  "tone": "neutral",
  "intensity": 0.0,
  "presence": "<mirror of the query-time-computed attention.rung>",
  "slots": { "label": { "ref": "ambisphere.identity.displayName" },
             "badge": { "ref": "ambisphere.attention.rung" } },
  "narration": { "available": false },
  "provenance": { "kind": "factual", "personaSetVersion": "null", "groundedFacets": ["attention"] },
  "fallback": true
}
```

Every renderer MUST be able to render this. It guarantees that even with zero persona authored, a surface can still show identity + attention prominence — which means **persona absence never hides a capability-critical or attention-critical signal**. This is the structural form of "persona must never gate a capability-critical signal."

## The layered cascade

Persona rules resolve through an ordered cascade, adopting the design-token three-tier override discipline (Material 3 reference → system → component; Brad Frost primitive → semantic → component) generalized to four layers because Ambisphere has both a *product* and a *kind* axis:

```
product default            (broadest; the bundle/product persona, e.g. "khaos")
   ↓ overridden by
entity-kind                (per declared kind, e.g. "khaos.project" vs "khaos.character")
   ↓ overridden by
state · surface            (per semantic-state value AND per surface, e.g. "blocked@tray")
   ↓ overridden by
instance                   (narrowest; a single entity override, e.g. instance proj-42)
```

### Resolution semantics

- **Two distinct mechanisms, not two predicate grammars.** Cascade *layer selection* (`product → kind → state·surface → instance`) is a fixed, closed key match (a bundle layer declares `layer` + `appliesTo`, e.g. `kind: "khaos.project"` or `state·surface: blocked@tray`) — it is **not** the predicate mini-language and never grows an expression grammar. *Within* a selected layer, a rule's `when` is the shared predicate mini-language (reducer spec). The `state·surface` cascade key is a coarse selector over a single declared semantic-state *value* plus a `SurfaceDescriptor.kind`; the `when` predicate is the fine matcher over arbitrary declared fields. Keeping these separate is deliberate: the cascade key must be totally ordered for deterministic precedence, while `when` is an arbitrary (still closed) predicate.
- **Precedence is fixed and deterministic:** narrower always wins. Within a layer, a more specific match (state·surface) beats a less specific one (state·any-surface beats any-state·any-surface). Ties are impossible by construction (each match key is unique); a reducer-style `BTreeMap`/sorted iteration is used so resolution is byte-identical (ADR-0001 inv.3).
- **Merge is per-field override, not whole-record replace.** Each cascade layer contributes a partial persona record; resolution deep-merges field by field, narrower overriding. This is the white-label pattern: an instance can override only `tone` while inheriting everything else from its kind. (Mirrors Material 3 system-token remap without rewriting component logic.)
- **Kind inheritance walks `instance-of` then `child-of`.** The entity's kind is found via the `instance-of` edge (entity-identity spec); a kind with no persona inherits its parent kind's persona by walking `child-of` on the kind graph. This is the only place persona touches the graph, and it is read-only.
- **Unmatched → fall through, never error.** A semantic-state value with no mapping at any layer falls through to the layer default, ultimately to the null/factual projection. New facet values (Layer 1 evolution) therefore never break persona.
- **The resolved set is cached and versioned.** Resolution produces a `ResolvedPersonaBundle` stamped with a `personaSetVersion` (a content hash of the merged cascade). It is recomputed only when a bundle changes; it is reused across `project()` calls for that (kind, surface) pair. The version is echoed into every `PersonaProjection.provenance` so any rendered expression is traceable to the exact resolved rules — the single provenance audit point.

### Where the cascade resolves

Per `persona-prior-art.md`'s open question and the daemon spec: **the daemon resolves the semantic + attention layers (Layers 1→2); the renderer resolves styling (Layer 3).** Concretely:

- The **daemon** owns cascade resolution and runs `project()`, emitting `PersonaProjection` on the persona channel. This keeps one consistent resolution and one provenance audit point across all surfaces, and keeps renderers dumb (they receive an expressive state, not a pile of rules).
- The **renderer** owns the expressive-state → frame mapping (Layer 3) and any styling tokens, because the appropriate frame for `concerned@operational@0.7` is inherently surface-specific.

This split is the same authoritative-server / dumb-client shape the renderer contract adopts from LSP: the daemon computes the view-model; the surface dresses it.

## The persona bundle (declarative content)

Persona rules ship as **declarative data** in the entity bundle (full bundle format is the next spec; this section fixes the persona-relevant shape). The hard constraint, to avoid re-creating the "personality system" non-goal: **no Turing-complete DSL, no imperative behavior, no callbacks.** A persona bundle is a static rule table (predicate → expressive metadata, in the shared predicate grammar) plus declared vocabularies.

```jsonc
{
  "personaSchemaVersion": "1",
  "id": "khaos.story",                   // bundle-owned id; NEVER derived from a host account
  "version": "2.3.0",
  "layer": "product",                    // product | kind | state-surface | instance
  "appliesTo": { "kind": "khaos.project" },   // match key for this layer (omitted for product)

  // ── declared expressive vocabulary (Layer 2's output alphabet) ──
  "expressiveStates": ["neutral", "working", "concerned", "celebrating", "waiting"],
  "tones": ["operational", "playful", "quiet", "formal"],

  // ── the mapping: a WHEN predicate over factual state → expressive metadata ──
  // Each rule's `when` is a predicate in the SHARED predicate grammar owned by the
  // reducer/state-component spec (§ "declarative predicate + field-path mini-language").
  // Both the canonical structured form `{ path, op, value }` and its string sugar are
  // accepted and parse to the same AST. Persona invents NO predicate syntax of its own;
  // there is exactly ONE predicate grammar across action preconditions, bundle `where`,
  // and persona `when`. Rules are evaluated in array order; the first matching rule wins
  // (resolution is deterministic — sorted, no map-iteration dependence, ADR-0001 inv.3).
  "rules": [
    {
      "when": { "path": "example.workflow.phase", "op": "eq", "value": "blocked" },
      "expressive": "concerned",
      "tone": "operational",
      "intensity": 0.7,
      "slots": { "summary": { "text": "Blocked — needs a look" } }
    },
    {
      "when": "example.workflow.phase == 'done'",   // string sugar; parses to the same AST
      "expressive": "celebrating",
      "tone": "playful",
      "intensity": 0.4
    },
    {
      "when": { "path": "ambisphere.attention.state", "op": "eq", "value": "awaiting-human" },
      "expressive": "waiting",
      "tone": "formal",
      "intensity": 0.6
    }
  ],

  // ── narration TEMPLATES (factual/narrated firewall; authoring-time bound) ──
  // Template slots use the SHARED slot/brace grammar (reducer spec § slot resolution):
  // `{component-type.path}` is brace sugar for a {ref} over a declared FACTUAL field-path.
  "narrationTemplates": {
    "blocked-explainer": {
      "template": "This {ambisphere.identity.kind} is blocked on {example.workflow.blockedReason}.",
      "allowedFields": ["ambisphere.identity.kind", "example.workflow.blockedReason"],  // declared fields ONLY
      "egressOnly": true                           // only an egress adapter may realize this
    }
  }

  // NOTE: there is NO `depth` block in the core persona schema. Personality / traits /
  // voice prompts are NOT a core concept. An author who wants such metadata ships it in
  // a separate adapter-private region the core loader treats as opaque pass-through and
  // NEVER parses or validates — see § "Persona depth is adapter-private".
}
```

Rules the validator MUST enforce at authoring/bundle-load time:

- **Every `when` predicate parses under the shared mini-language and references a declared field path.** The `when` is parsed by the *one* predicate parser owned by the reducer/state-component spec; its `path` must resolve to a declared facet field (a declared domain facet field or a canonical `ambisphere.attention` field), its `op` must be in the closed op set, and its `value` must type-check against the field. An unknown field path, an out-of-set `op`, or a value that cannot be parsed to a `CanonicalValue` is a bundle error (caught at load, not at render). This is the same closed, total, replay-safe predicate the action spec uses for preconditions and the bundle spec uses for `where` — there is no second grammar.
- **Every rule's `expressive`/`tone` are members of the declared vocabularies.** No ad-hoc strings reach the renderer.
- **Every slot is a `{ref}` (field-path) or `{text}` (literal) in the shared slot grammar.** No slot type carries model output; the only path to narrated text is `narration.ref` into the separate store.
- **Every narration template `{slot}` is listed in its `allowedFields`, and every `allowedField` is a *declared factual field* addressable by the shared field-path grammar.** A template that references a non-declared field, or that has a free-text slot not bound to a declared field, is rejected. This is the structural enforcement of "narrated phrasing is bounded to reference only declared factual fields" — the firewall is a compile-time/load-time property, not a runtime hope.
- **No field names any frame, sprite, atlas, or animation.** Renderer concerns are not expressible in the bundle.
- **No `depth` / personality / traits / voice-prompt key is parsed by core.** The core persona schema has no such field. Any personality metadata lives in an adapter-private region the core loader does not read (§ "Persona depth is adapter-private"); the validator's only obligation there is to confirm core never dereferences it.
- **No host-account / vendor-identity derivation.** `id` is bundle-owned; there is no hash-from-account-id path. (Reject: claude-buddy determinism.)

## Persona depth is adapter-private

The earlier draft carried an optional `depth` block (`displayName`, `personality` string, `traits` map, `voicePromptRef`) directly inside the core persona bundle schema. Review found this to be a structural foothold for exactly the VISION non-goal "a specific personality system" — even inert, a core-defined schema *for personality traits and voice prompts* is core carrying a personality model. This spec resolves its own former open question against the non-goal:

- **Core's persona schema defines only expressive-state, tone, intensity, slots, and narration-ref.** There is no `personality`, no `traits`, no `mood`, no `voicePromptRef`, and no `displayName`-as-personality field in any core-parsed structure. (`displayName` as a plain *identity* field already belongs to the `ambisphere.identity` facet — Layer 1, a fact — and is reached through the normal `{ref}` slot grammar; it is not persona depth.)
- **Personality / voice metadata, if an author wants it, is opaque adapter-private data.** It is carried in a region the core loader treats as **opaque pass-through**: core does not parse it, does not validate it, does not type it, and never reads it during `project()`. It is delivered, untouched, only to the egress adapter that opted to consume it. Concretely, an egress-adapter's own config (or an `x-adapter`-namespaced blob the bundle format reserves for adapter-private data — owned by the bundle spec) holds it; core's persona schema has no key for it.
- **Acceptance criterion (firewall against the non-goal):** there is no code path by which `project()` or the cascade resolver reads personality/traits/voice data; a test loads a bundle carrying an adapter-private personality blob and asserts (a) the bundle loads, (b) the resolved `PersonaProjection` is byte-identical to the same bundle with the blob removed, and (c) no core symbol dereferences the blob. If core can observe depth, the test fails.
- **Why this is sufficient, not over-strict.** Narration templates already give an egress adapter everything it needs to *express* character — bounded to declared factual fields. A voice/personality prompt is just more egress-adapter input; it does not need to be a core concept to work, and making it one is precisely the rejected coupling. Voice/character is an *egress adapter* capability, not a *runtime* capability.

## The factual / narrated firewall across the persona boundary

The reducer spec makes the firewall structural at the source: `ReducibleEvent` has no narration field, reducers cannot emit `kind: "narrated"`, and `NarratedProjection` lives in its own store, never on the log, never in `EntityState`, never a reducer input. Persona is the place where a narrated *styling* of facts is most tempting, so the wall is re-asserted here with three structural guarantees:

1. **The persona projection is itself factual.** `project()` is pure over facts; its output `provenance.kind` is always `factual`. No model runs inside `project()`.
2. **Narration is reachable only by reference, only from egress.** A `PersonaProjection` carries at most a `narration.ref` (opaque handle) and `narration.kind: "narrated"`. The narrated text lives in the separate narrated store and is produced **only** by an egress adapter (reducer spec inv.5; daemon spec — only egress adapters emit narration). Persona neither produces nor stores narration; it only *indicates a handle exists*.
3. **Factual-only is always renderable.** Every surface MUST be able to render a `PersonaProjection` ignoring `narration` entirely — slots resolve to declared factual fields, identity and attention are present, the result is true. This is the renderer-contract requirement ("surfaces must render factual-only") expressed at the persona layer.

```
   facts (log → reducers → facets)        ← single source of truth
        │  (read-only view)
        ▼
   project()  ──────────────────────────  PersonaProjection { kind: factual, slots:{ref|text}, narration:{ref?} }
        │                                          │
        │ factual-only render path                 │ optional, opt-in
        ▼                                          ▼
   renderer dresses facts                  egress adapter realizes narrationTemplate
   (always available)                      against declared fields → NarratedProjection
                                           (separate store, kind: narrated, grounded[])
```

The arrow from narration **never** points back left: a `NarratedProjection` is never an input to `project()`, never a facet, never on the log.

## Persona never gates a capability-critical signal

This is the single most important safety property and is enforced structurally, not by convention:

- **Attention is computed independently of persona.** The attention bus ranks entities and answers `what_matters_now` over the always-resident summary index (attention + daemon specs) with no persona input. A surface can subscribe to the **attention channel alone** and receive every rung, including `prominent`/`blocking`, with persona entirely absent.
- **Approval-requested is owned upstream.** The `approval-requested` state is action/capability-spec state surfaced by attention; persona may *style* it (`expressive: "waiting"`) but cannot suppress, downgrade, or hide it. Persona has no write path and no rung authority.
- **Persona absence/error degrades to the null/factual projection**, which still mirrors `attention.rung` in `presence` and exposes identity + badge slots. There is no persona state in which a critical signal becomes invisible because persona failed or was stripped.
- **The persona channel is independent and droppable.** The renderer contract fixes **exactly three** observation channels — `state | attention | persona` — and declares them not redefinable downstream; `persona` is one of these three. (`control` is **not** an observation channel: it is a separate broker-only bidirectional channel established by its own handshake, per the daemon spec § channel taxonomy; the earlier draft's four-element `state | attention | persona | control` listing is corrected here.) A surface chooses which of the three observation channels to subscribe to. Dropping the persona channel loses expression, never facts or prominence. The daemon never makes a capability-critical signal depend on the persona channel being subscribed.

Stated as an invariant for review: *no value of any persona input or any persona failure mode may reduce the set of attention/approval/factual signals reachable on a surface that subscribes to the state and attention channels.*

## Conformance to upstream contracts

- **ADR-0001 directionality.** Persona is read-side only: no `submit`, no capability check, no component write, no cross-actor write-side query. It reads views; the log is the seam it sits far downstream of. (inv.1, inv.2)
- **Determinism (ADR-0001 inv.3).** `project()` and cascade resolution are pure/total/deterministic, sorted-iteration, clock-free (`asOf` injected). Replaying the same views yields byte-identical projections — a required test.
- **Attention spec.** Persona consumes `AttentionView` (score/rung/state) and never feeds the ranking; `presence` is an advisory mirror of the **query-time-computed** rung; the rung always wins on disagreement. Persona relies on the attention spec's normative rule that the resident summary index and any materialized rollup cache only decay-invariant inputs, and that rung/score are always recomputed from those plus `asOf` — so persona can never serve a stale rung.
- **Reducer/state-component spec.** Semantic states are facets produced there; persona is never a reducer-written component; the `kind` discriminator and the `NarratedProjection`-in-a-separate-store firewall are honored. **The shared declarative predicate + field-path mini-language is owned there**; persona's rule `when` predicates and `{ref}`/`{text}`/brace slots parse under that one grammar — persona defines no predicate or slot syntax of its own. This resolves the cross-spec "three incompatible predicate grammars" finding: action preconditions, bundle `where`, and persona `when` are one closed grammar.
- **Renderer contract / daemon spec.** Persona is one of the **three** observation channels `state | attention | persona`; `control` is a broker-only channel, not an observation channel; persona cites the three-channel set.
- **Event-envelope spec.** Persona reads facts derived from the log and never appears on the log; it submits nothing.
- **Entity-identity spec.** The cascade resolves kind via `instance-of` and inherits via `child-of`, read-only; persona creates no edges.
- **Daemon spec.** The daemon resolves the cascade and brokers the persona channel; persona resolution is part of the read plane, never the write plane, and never backpressures it.
- **Vendor neutrality (ADR-0001 inv.8).** Core ships zero persona content: no default personality, no expressive vocabulary, no tones, no Khaos/LOSWF persona. Core ships only the *projection function*, the *schema*, the *cascade engine*, the *null/factual projection*, and the *validator*. All persona content lives in bundles (examples/adapter layer). `khaos.story` above is an **example**, not core.

## Acceptance criteria

A persona implementation conforms when:

1. **Pure projection.** `project()` has no IO/clock/RNG; given identical views + surface + resolved set it returns byte-identical output; a replay-equality test passes.
2. **Optional & null-default.** An entity with no persona bundle yields the null/factual projection on every surface; that projection renders and exposes identity + `attention.rung`.
3. **Three-layer separation holds.** No persona schema field names a frame/sprite/atlas/animation; no renderer needs persona rules to choose frames; swapping a renderer requires zero persona change; swapping a persona bundle requires zero reducer/renderer change.
4. **Cascade determinism.** `product → kind → state·surface → instance` resolves with fixed precedence, per-field merge, and a stable `personaSetVersion`; identical bundles produce identical resolved sets; unmatched semantic values fall through without error.
5. **Firewall structural.** The projection document is `kind: factual`; no slot carries model output; narration is reachable only via `narration.ref` into the separate store and is produced only by an egress adapter; a factual-only render is always possible; a narration template referencing a non-declared field is rejected at load.
6. **Capability-critical safety.** A surface subscribed to state + attention channels receives every rung and every `approval-requested` signal with persona absent, errored, or stripped; no persona input or failure shrinks that set.
7. **Declarative-only bundles.** A persona bundle is static data (rules + vocabularies + narration templates); the loader rejects any imperative/Turing-complete construct; every rule `when` parses under the shared predicate mini-language and references a declared field path; every expressive/tone value is in the declared vocabulary.
8. **One shared predicate/slot grammar.** Persona rule `when` predicates and `{ref}`/`{text}`/brace slots parse with the *same* parser as action preconditions and bundle `where`; a conformance test feeds one predicate (structured and string-sugar forms) through the action, bundle, and persona consumers and asserts identical resolution against a fixed `EntityState`. Persona contributes no second grammar.
9. **Depth is adapter-private and unread by core.** Core's persona schema has no personality/traits/voice key; a bundle carrying an adapter-private personality blob loads, and the resolved `PersonaProjection` is byte-identical with the blob present or absent; no core symbol dereferences it. (Firewall against the "personality system" non-goal.)
10. **No stale rung.** `presence` for a given `asOf` equals the rung the attention query computes for that same `asOf`; a replay test at two `asOf` values shows `presence` tracking the recomputed rung, with no cached rung/score anywhere on the persona path.
11. **Three-channel citation.** Persona is delivered on the `persona` observation channel, one of exactly three (`state | attention | persona`); `control` is not an observation channel; a surface dropping the persona channel still receives every rung and `approval-requested` signal.
12. **Vendor-neutral core.** The core ships zero persona content; removing all bundles leaves a runtime where every entity uses the null/factual projection.

## Open questions

- **Expressive-vocabulary governance.** Is the expressive-state alphabet wholly bundle-defined (max flexibility, but two bundles may name the same mood differently and confuse a shared renderer), or does core publish a small *recommended* expressive vocabulary that bundles extend? Leaning bundle-defined with an optional published baseline, but a shared renderer needs a fallback mapping for unknown expressive tags — its rule is unspecified here (likely: unknown expressive → `neutral`).
- **Surface taxonomy for state·surface keys.** The cascade keys on `surface`, but the surface taxonomy (fixed enum vs open capability strings) is owned by the renderer contract. This spec assumes a `SurfaceDescriptor.kind`; if that taxonomy is free-form, persona match keys need a defined matching rule (exact vs capability-predicate). Defer to the renderer spec; flag the dependency.
- **Narration trigger and lifecycle.** This spec fixes *where narration may come from* (egress adapter, bounded to declared fields) and *how persona references it* (`narration.ref`), but not *when* narration is generated, who pays for it, how stale a `narration.ref` may be, or how it is invalidated when facts change. Likely a narration/egress sub-concern of the adapter + privacy specs; recorded here as the persona-side contract only.
- ~~**Persona depth vs the personality-engine non-goal.**~~ **Resolved** (this revision): `depth` is removed from the core persona schema entirely. Personality / traits / voice-prompt metadata is opaque adapter-private data core never parses, validates, or reads (§ "Persona depth is adapter-private"); core's persona schema covers only expressive-state / tone / intensity / slots / narration-ref. The remaining sub-question is purely a bundle-format detail: *which* reserved region (egress-adapter config vs an `x-adapter` namespace in `bundle.toml`) holds adapter-private blobs — deferred to and owned by the entity-bundle/package-format spec.
- ~~**Predicate / slot grammar.**~~ **Resolved** (this revision, jointly with the reducer and action specs): there is one shared declarative predicate + field-path mini-language, owned by the reducer/state-component spec. Persona rule `when`, bundle `where`, and action preconditions all parse to that one closed grammar; `{ref}`/`{text}`/brace slots use its slot grammar. Persona invents no syntax. The action spec's open question "is the predicate AST shared with attention/persona grammars" is answered **yes, one shared closed grammar**.
- **Intensity semantics.** `intensity` is a `[0,1]` expressive scalar distinct from `attention` scalars. Is it derived from attention (a function of urgency/rung) or independently authored, or both (authored baseline scaled by rung)? Leaning authored baseline optionally scaled by rung, but the scaling function would need to be declarative and clock-free; unspecified pending a worked example.
- **Resolution caching invalidation.** `ResolvedPersonaBundle` is cached per (kind, surface). The invalidation triggers (bundle change, kind-graph `child-of` change) are clear; whether a new facet *value* (Layer 1 vocabulary growth) needs cache invalidation is not — it should not (unmatched falls through), but a worked migration test should confirm.
- **Cross-bundle persona for shared/child entities.** When a `child-of` rollup entity summarizes children from *different* bundles (Scenario C in issue #5: a Khaos project and a LOSWFX review under one rollup), whose persona expresses the rollup? Likely the rollup entity's own kind persona, with children expressing independently — but the composition rule for a mixed-bundle rollup surface is unspecified.
