# Entity bundle and package format

**Status:** draft · **Scope:** the declarative serialization that ties every other runtime contract together into one installable, versionable, verifiable artifact — entity-kind declarations, component/facet schemas, accepted event types, reducer bindings, persona/projection rules, action definitions, renderer hints, assets, capability metadata, and test fixtures. This spec owns **composition, reference, versioning, validation, identity, distribution, and load/activation** of bundles; it does **not** redefine the contracts it serializes (each is owned by its sibling spec) · **Companion to:** `specs/VISION.md`, `specs/SRS.md`, `RFP.md` (§ "Multi-application integration", "Context persistence", "Local daemon patterns") · **Sequenced:** last among the follow-on specs (it depends on eight of the other nine and is the integration pressure-test that all contracts serialize cleanly) per ADR-0001 and issue #4 · **Conforms to:** ADR-0001 (foundational paradigm + directionality invariant + Rust core — **currently `Proposed`; this spec conforms to it provisionally and re-pins on ADR acceptance**, see § "ADR status"); the attention-routing spec (the `attention` facet shape); the reducer/state-component spec (the `Component`/`Reducer`/provenance contracts, **the closed core-owned component list, and the single shared declarative predicate + field-path mini-language** — this spec references that grammar and invents none); the semantic-event-envelope spec (the `ProposedEvent`/`type`/`dataschema` contracts, **and the closed core-reserved `ambisphere.*` event-type allowlist**); the action/capability spec (the `inputSchema`/`requiredCapabilities`/`locality` action manifest and the **closed structured precondition predicate**); the entity-identity spec (the `EntityAddress`/`entityHandle`/relation-type contracts); the privacy/credential spec (the `egress`/`credentialRef`/`locality` egress boundary); the persona spec (the cascade and slot grammar); the daemon-architecture spec (load/activation, the `StorageDriver`, `reducerSetVersion`) · **Sibling notes:** `specs/drafts/runtime-paradigm-and-specs-guidance.md`, `specs/drafts/actor-model-prior-art.md`, `specs/drafts/persona-prior-art.md`, `specs/drafts/implementation-language-guidance.md`

This spec defines the **package**: the self-contained directory (and its on-disk archive) that an adopter authors, signs, distributes, and the daemon loads to teach the runtime about a domain. A bundle is the *only* mechanism by which domain knowledge enters the core — core ships zero domain kinds, event types, components, reducers, actions, personas, or severity vocabulary (ADR-0001 inv. 8), so every one of those things arrives as bundle content.

Crucially, this spec is **declarative glue, not new semantics**. It says how to *write down* and *wire together* the contracts the other eight specs already fixed; it adds exactly one thing of its own — the composition/reference/versioning/validation/identity rules that let those contracts coexist in one artifact without contradiction. Wherever a field's meaning is owned elsewhere, this spec references that owner and refuses to redefine it. The test of this spec is integration: if all the other contracts serialize into one bundle and load cleanly, the runtime's contracts compose; if they cannot, this spec has surfaced a real seam defect to send back upstream.

## Goals and non-goals

### Goals

1. Define the **bundle layout** (directory + archive) and a single **`bundle.toml` manifest** that declares identity, version, dependencies, and an index into every other artifact the bundle carries.
2. Define how each sibling contract is **serialized and referenced** — kinds, component schemas, event types, reducer bindings, persona rules, action defs, renderer hints, assets, capability metadata, fixtures — by *pointing at* the owning spec for meaning and fixing only the on-disk shape and the cross-references between them.
3. Define **identity and addressing of bundles** themselves (namespace ownership, package id, content digest) and how a bundle's declarations claim the `EntityAddress` namespaces it is authoritative for.
4. Define **versioning**: bundle SemVer, the independent per-artifact versions the runtime already tracks (`specversion`, `dataschema`, `reducerVersion` + component `schemaVersion`, persona/projection schema, action/manifest, renderer-projection schema), how a bundle pins/depends on others, and how `reducerSetVersion` is derived.
5. Define **validation**: a total, deterministic, offline `validate(bundle) -> Report` that statically proves a bundle's internal references resolve, its declarations conform to the sibling contracts, and it ships nothing forbidden (credentials, narration-on-the-log paths, vendor branches in core) — runnable in authoring tooling and re-run at load.
6. Define **load and activation** against the daemon: capability-gated install, deterministic ordering, the `reducerSetVersion` bump that discards stale snapshots (reducer spec), and conflict/precedence rules when multiple bundles touch the same namespace.
7. Carry **test fixtures** (golden event→state→provenance vectors) as first-class bundle content so the replay-equality and conformance tests (reducer/envelope specs) run against the bundle that ships them.

### Non-goals (adopt/reject framing — rejections carried from the guidance)

- **Reject** redefining any sibling contract. This spec serializes the `attention` facet, the `Component`/`Reducer` shapes, the envelope `type`/`dataschema`, the `EntityAddress`/relation types, the action manifest, the persona projection, and the renderer hints — it changes none of their fields. A bundle that disagrees with an owning spec is invalid, not an override.
- **Reject** any built-in domain kind/type/action/severity/persona in core (ADR-0001 inv. 8). The bundle format is domain-agnostic; `khaos.*`/`loswf.*` appear only in *example bundles* under `examples/`, never in core or in this spec's normative body.
- **Reject** a Turing-complete bundle DSL. Declarations are data (TOML/JSON-Schema/templates with bounded slots); behavior (reducers, action handlers, adapters) ships as registered code modules referenced by the manifest, not as logic embedded in the manifest. Persona phrasing is bounded template slots over *declared factual fields* (persona spec firewall), never arbitrary code.
- **Reject** credentials, secrets, or narration-as-fact anywhere in a bundle (ADR-0001 inv. 6, 7). A bundle may declare *capability requirements* and *credential references*; it never carries the secret, and it never ships a path by which narration becomes a log fact.
- **Reject** a network-resolvable registry / remote install as a core dependency. Bundles are local-first directories; content-addressable digests and a dependency graph are specced so a registry *could* exist later, but install is from a local path by default (VISION 4; daemon spec local-first stance).
- **Reject** spritesheet-as-truth and renderer-substrate lock-in (persona prior-art). Renderer *hints* are advisory projection metadata; assets are opaque content-addressed blobs the bundle never assumes a single renderer consumes.
- **Reject** a second event/state/identity model. The bundle is a thin serialization over the existing envelope/component/identity contracts; it introduces no parallel representation.

## Prior art (citations kept visible)

- **WASM Component Model / WIT packages** — a package is a directory of interface/world declarations with an optional full-SemVer version and a `namespace:name@version` id; imports deduplicate to the max semver-compatible version, and a "world" is the complete import/export contract of a component (`github.com/WebAssembly/component-model/blob/main/design/mvp/WIT.md`, `component-model.bytecodealliance.org/design/wit.html`). **Adopt:** the `namespace:name@semver` package id, the directory-of-declarations shape, and the "world = complete declared contract" framing (our `bundle.toml` declares the complete set of kinds/events/components/actions a bundle contributes). **Reject:** WIT's binary component encoding and its compile-to-Wasm assumption — our behavior modules are registered native code (Rust reference SDK) or out-of-process adapters, and the WASM Component Model is a *future* path for untrusted third-party bundles (adapter guidance), not adopted now.
- **OCI image spec** — content-addressable artifacts: a manifest references a config and a set of layers by `Descriptor{mediaType,digest,size}`; `digest = algorithm:encoded` is a collision-resistant hash that *is* the content id, and the on-disk layout stores blobs at `blobs/<alg>/<encoded>` whose bytes must match the digest (`github.com/opencontainers/image-spec/blob/main/manifest.md`, `.../image-layout.md`). **Adopt:** content-addressed assets (`assets/blobs/<alg>/<hex>`), `Descriptor{mediaType,digest,size}` references from the manifest, and a content digest that identifies the whole bundle. **Reject:** the registry/distribution protocol and the container runtime config — we borrow the addressing, not the daemon-pull machinery.
- **VS Code extension / npm package manifests** — a single declarative manifest (`package.json` / `package.json#contributes`) declares identity (`name`/`publisher`/`version`), SemVer dependencies, an `engines` host-compatibility range, and *contribution points* that register declarations (commands, languages) plus an `activationEvents`/lazy-activation model. **Adopt:** one manifest as the index, SemVer deps, an `engines`-style host-version range, contribution-point registration, and lazy activation. **Reject:** the npm dependency-tree/`node_modules` resolution model and the Marketplace — deps here are a flat pinned graph resolved locally.
- **OpenTelemetry semantic-convention schemas + schema-url versioning** — versioned, namespaced declarations with an explicit schema URL so consumers can upcast between versions. **Adopt:** per-artifact schema versions referenced by url-like ids (`bundle:loswf@2/ci.failed.v2`, already the envelope spec's `dataschema` shape) and the upcast-at-read contract. **Reject:** the OTel collector and wire protocol.
- **SemVer 2.0.0** — `MAJOR.MINOR.PATCH` with documented break/add/fix semantics. **Adopt** wholesale for bundle and per-artifact versions; **reject** nothing.
- **codex-pets / hatch-pet / claude-buddy** (`specs/drafts/persona-prior-art.md`) — self-contained entity bundle as a directory the runtime consumes, authoring-as-a-skill producing a packaged artifact with a `qa/` directory, "named states are the contract," optional persona-depth fields. **Adopt:** the self-contained directory, the `qa/`-style fixtures, state-vocabulary-as-contract, optional persona depth. **Reject:** `pet.json` spritesheet-as-truth, the nine hardcoded animation states, `$CODEX_HOME` path lock-in, hash-from-account-id identity (persona-prior-art rejection table) — bundles live under an Ambisphere-owned path the daemon brokers, identity belongs to the bundle, and renderer state vocabulary is never baked into core.

## Conformance to ADR-0001

| Invariant | How the bundle format conforms |
|---|---|
| 1 — log is source of truth; components derived | A bundle ships reducers (which *produce* components) and component *schemas*, never component values or a `setComponent` path. There is no "initial component state" key; an entity's state is always `fold(log)`. Seed data, if any, is shipped as **fixture events** replayed through `submit`, never as pre-baked components. |
| 2 — directionality (cap/actor write; ECS read; log is the seam) | Manifest sections are split into **write-side** declarations (event types, action defs, capability metadata) and **read-side** declarations (component schemas, persona/projection rules, renderer hints). The single seam — reducer bindings — maps write-side `type`s to read-side components. Validation rejects any read-side declaration that names a write capability or any write-side decl that references a component value. |
| 3 — determinism | Reducer/action *behavior* is registered code constrained by the reducer spec's purity rules; the manifest carries no clock/RNG. Fixtures are golden `(log) -> (state, provenance)` vectors that feed the replay-equality test. `reducerSetVersion` is derived deterministically from the bundle set (below). |
| 4 — per-entity total order; daemon assigns | A bundle declares *which `EntityAddress` namespaces/kinds it owns* and the relation types it uses; it never asserts sequence/ordering and never proposes an `entityHandle`. |
| 5 — capability-shaped authority | Action defs carry `requiredCapabilities` as authority-token *requirements* (action spec), `destructive`/`confirmRequired` as UX hints only, never the boundary. Bundle *install* is itself capability-gated (below). |
| 6 — fact/narration firewall (structural) | Persona/projection rules are **read-side, narrated-or-presentational** declarations that reference only declared factual component fields through the **shared slot/brace grammar owned by the reducer spec** (§ "declarative predicate + field-path mini-language"); the format provides **no** path from a persona rule to a reducer input or the log. Validation (L4) parses every slot with that one grammar and statically rejects a slot that names an undeclared field, a non-factual field, or a write event. |
| 7 — credentials never in state/log | A bundle declares `credentialRef`s (opaque names an adapter resolves) and `requiredCapabilities`; the format has no field that can hold a secret, and validation greps for secret-shaped literals and fails. |
| 8 — vendor neutrality | This spec's normative body names zero domain kinds; every concrete `khaos.*`/`loswf.*` token appears only in the worked example, explicitly labelled example-layer. The only `ambisphere.*` ids a bundle may *reference* (never redeclare) are the closed **core-reserved event-type allowlist** (envelope spec § core-reserved event types) and the closed **core-owned component list** (`attention`, `identity`, `lifecycle`, `approvals`; reducer spec). Validation L4's vendor-neutrality lint allowlists **exactly** that envelope set and nothing else; it does not re-derive "zero types". Core never branches on bundle `data`/`payload`; it treats all declarations as opaque-typed data validated against the fixed contracts. |
| 9 — language-neutral seams | The manifest is TOML; schemas are JSON-Schema; event/component/asset references are language-neutral ids. Behavior modules are referenced by a language-neutral `module` coordinate (§ behavior modules) behind a **defined v1 in-process ABI** so a bundle could ship a Rust, a future-WASM, or an out-of-process adapter implementation behind the same declaration. |

### ADR status

ADR-0001 is, at the time of writing, itself `draft`/`Proposed`, yet every follow-on spec — this one included — declares "Conforms to: ADR-0001" and cites numbered invariants as binding. The suite cannot be implementation-ready while its foundational ADR is unaccepted, and the conformance table above cites invariant numbers ADR-0001 must actually enumerate. This spec's position (shared verbatim with the reducer and envelope specs): **the conformance table above conforms to the *provisional* ADR-0001**; on ADR acceptance every dependent spec re-pins to the ratified numbered-invariant list. Resolving ADR-0001 to a single status and adding its canonical numbered-invariant list is an ADR-owned action, tracked in § Open questions; it is not resolvable inside this (downstream) spec.

## Bundle layout

A bundle is a directory with a fixed top-level shape. Its archive form is a deterministic tarball (sorted entries, normalized mtimes) so the same source produces the same content digest (OCI content-addressability, adapted).

```text
my-bundle/                          # source directory (and, zipped, my-bundle-<version>.absphere)
  bundle.toml                       # THE manifest — identity, version, deps, index into everything below
  kinds/                            # entity-kind declarations (identity spec)
    workflow.toml
    issue.toml
  components/                       # component/facet JSON-Schemas (reducer spec)
    workflow.schema.json
  events/                           # accepted event-type declarations + payload JSON-Schemas (envelope spec)
    ci.failed.v2.schema.json
    workflow.started.v1.schema.json
  reducers/                         # reducer BINDINGS (declarative) — code lives in modules/
    workflow.reducer.toml
  actions/                          # action definitions / manifest (action-capability spec)
    rerun-ci.action.toml
  personas/                         # persona / projection rules (persona spec) — read-side, bounded templates
    workflow.persona.toml
  renderers/                        # renderer HINTS (renderer spec) — advisory projection metadata
    hints.toml
  capabilities/                     # capability metadata: required caps, credential refs (action/privacy specs)
    capabilities.toml
  assets/                           # opaque content-addressed blobs (OCI-style)
    blobs/
      blake3/
        9f86d0818...                # bytes whose blake3 == 9f86d0818...
    index.toml                      # logical-name -> Descriptor{mediaType,digest,size}
  modules/                          # registered behavior code (reducers, action handlers) — referenced, not inlined
    workflow_reducer.so             # or a coordinate to an out-of-process adapter (see § behavior modules)
  fixtures/                         # golden test vectors: events -> expected state+provenance (reducer/envelope specs)
    workflow-happy-path.fixture.json
  qa/                               # optional authoring artifacts (hatch-pet pattern) — never loaded by the daemon
    contact-sheet.png
    review.json
  BUNDLE.lock                       # resolved, pinned dependency graph + content digests (generated)
```

Rules:

- Every subdirectory is **optional** except `bundle.toml`. A bundle that ships only `kinds/` + `events/` + `components/` + `reducers/` is valid (e.g. a pure operational bundle with no persona, no actions). The minimal viable bundle is just `bundle.toml` declaring identity and a namespace claim (a "namespace reservation" bundle).
- `qa/` is **authoring-only** and MUST be ignorable by the daemon; the content digest MAY exclude it (declared in `bundle.toml` via `digest.excludes`) so QA churn does not change the bundle's identity.
- All cross-file references are by **logical id** (e.g. a reducer binding names a component by its declared `component_type`, not by file path), so files may be reorganized without breaking references. File paths appear only in the manifest's index and in asset descriptors.

## The manifest — `bundle.toml`

One manifest is the index and the contract. It is TOML (matches the daemon spec's config idiom; deterministic, comment-friendly). Every section below is **declarative** and points at the owning spec for meaning.

```toml
# bundle.toml — the complete declared contract a bundle contributes (WIT "world", adapted)

[bundle]
id        = "loswf"                       # namespace segment this bundle is authoritative for (identity spec EntityAddress[0])
name      = "loswf-factory"               # human name
version   = "2.3.0"                        # bundle SemVer (SemVer 2.0.0)
abiVersion = "ambisphere.bundle/1"         # the BUNDLE-FORMAT version this manifest targets (this spec's version)
description = "LOSWF software-factory ambient entities"
license   = "Apache-2.0"
authors   = ["k@khaos.studio"]

[engines]                                  # host-compatibility range (npm `engines`, adapted)
ambisphere = ">=1.0.0 <2.0.0"             # daemon/core version range this bundle supports
specversion = "ambisphere.event/1"         # envelope spec version the event decls target (envelope spec)

[digest]                                    # OCI-style content identity of THIS bundle
algorithm = "blake3"
excludes  = ["qa/**", "BUNDLE.lock"]       # paths excluded from the canonical digest
# value is computed by tooling and written to BUNDLE.lock; not authored by hand

[[dependencies]]                            # flat, pinned, locally-resolved dependency graph (not a tree)
id      = "ambisphere.core"               # depend on a core-provided base bundle (e.g. ambisphere.identity/.attention reducers)
version = ">=1.0.0 <2.0.0"
[[dependencies]]
id      = "khaos"                          # cross-bundle dependency (e.g. shared "project" kind) — capability-gated edge (identity spec)
version = "^4.1.0"
optional = true                            # absent dep degrades gracefully (its kinds/edges simply unavailable)

# ---- INDEX into the artifacts. Each entry is a declaration the runtime registers. ----
# Entries reference files by path; everything else references by logical id.

[[kinds]]        path = "kinds/issue.toml"
[[kinds]]        path = "kinds/workflow.toml"
[[components]]    path = "components/workflow.schema.json"   # component_type + schemaVersion declared inside
[[events]]        path = "events/ci.failed.v2.schema.json"   # type + dataschema declared inside
[[events]]        path = "events/workflow.started.v1.schema.json"
[[reducers]]      path = "reducers/workflow.reducer.toml"
[[actions]]       path = "actions/rerun-ci.action.toml"
[[personas]]      path = "personas/workflow.persona.toml"
[[renderers]]     path = "renderers/hints.toml"
capabilities      = "capabilities/capabilities.toml"
assets            = "assets/index.toml"
[[fixtures]]      path = "fixtures/workflow-happy-path.fixture.json"
```

`[bundle].id` is the namespace this bundle **claims authority over** — the first segment of every `EntityAddress` the bundle's kinds produce (identity spec: `EntityAddress = [namespace, kind, local-id, ...]`). Two installed bundles MUST NOT claim the same `[bundle].id` unless one declares the other as a dependency and the precedence rules (§ load & activation) resolve it; otherwise install fails with a namespace conflict.

### Field ownership is the contract (what this spec does and does not own)

This spec owns the **container, the index, the references, the versions, and the validation**. It owns **none** of the meanings below; each is fixed by its sibling spec and merely *carried* here:

| Section | On-disk shape (owned here) | Meaning / fields (owned by) |
|---|---|---|
| `[[kinds]]` | a TOML kind decl referenced by path | entity-identity spec (`EntityAddress`, kind metadata, relation cleanup policy) |
| `[[components]]` | a JSON-Schema with `component_type`/`schemaVersion`/`kind` | reducer/state-component spec (`Component`) |
| `[[events]]` | a JSON-Schema with `type`/`dataschema` | semantic-event-envelope spec (`type`, `dataschema`, payload) |
| `[[reducers]]` | a binding: `{component_type, handles[type...], module}` | reducer spec (`Reducer`, single-writer, purity) |
| `[[actions]]` | an action manifest entry | action-capability spec (`inputSchema`, `requiredCapabilities`, flags, `locality` enum `local\|remote-read\|remote-write`, closed structured `preconditions`) |
| `[[personas]]` | bounded-template projection rules | persona spec (cascade, firewall) + reducer spec (the shared predicate `when` + slot grammar) |
| `[[renderers]]` | advisory projection hints | renderer spec (projection schema, surface kinds; per-surface `stateView` shape is daemon-owned) + reducer spec (field-path grammar for hint fields) |
| `capabilities` | required caps + credential refs + egress rules | action/privacy specs (capability tokens, `credentialRef`, egress keyed off the `locality` enum) |
| `assets` | `Descriptor{mediaType,digest,size}` index | this spec (OCI-style addressing) |
| `[[fixtures]]` | golden `(events)->(state,provenance)` vectors | reducer/envelope specs (replay-equality) |

## Serializing each contract

Each subsection fixes only the **on-disk shape** and the **cross-references**. Meanings stay with the owning spec.

### Kinds (entity-identity spec)

```toml
# kinds/workflow.toml — declares an entity KIND (identity spec: declarative metadata, NOT a class)
[kind]
name = "workflow"                          # EntityAddress[1]; the kind segment
summary = "A factory workflow run"
localIdScope = "namespace+kind"            # uniqueness scope for EntityAddress[2] (identity spec open Q, declared per-kind)

[identity]
# ambisphere.identity is one of the CLOSED core-owned components (attention, identity, lifecycle, approvals;
# reducer spec). It is produced by a CORE reducer; the bundle only REFERENCES it and never redefines it.
component = "ambisphere.identity"          # reference only — bundles cannot declare any ambisphere.* component

[[relations]]                              # relation types this kind participates in (identity spec)
type = "child-of"                          # one of the two built-ins, or a bundle-defined type
target = "loswf:factory"                   # EntityAddress kind this is a child of (for rollups)
onTargetDelete = "tombstone"               # cleanup policy is relation METADATA (identity spec), not behavior
single = true                              # single-parent child-of (clean rollups, identity spec v1 default)
[[relations]]
type = "blocks"                            # BUNDLE-DEFINED relation type (not built-in; declared here)
target = "loswf:issue"
onTargetDelete = "orphan"
```

A kind decl never proposes a handle (daemon assigns) and never claims a namespace other than `[bundle].id`. Bundle-defined relation types are registered here; the two built-ins (`child-of`, `instance-of`) are referenced, never redeclared.

### Component schemas (reducer/state-component spec)

A component file is a JSON-Schema annotated with the reducer spec's required envelope (`component_type`, `schemaVersion`, `kind`). The schema describes the `data` payload only; `kind` MUST be `"factual"` (reducer output is always factual; a narrated value is never a component — § firewall).

```jsonc
// components/workflow.schema.json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "x-ambisphere-component": {
    "componentType": "loswf.workflow",     // unique; one OWNING reducer (single-writer, reducer spec)
    "schemaVersion": 2,                    // per-component version (reducer spec evolution)
    "kind": "factual"                      // MUST be factual; validation rejects "narrated"
  },
  "type": "object",
  "required": ["phase"],
  "properties": {
    "phase": { "enum": ["pending","running","blocked","done","failed"] },
    "progress": { "type": "number", "minimum": 0, "maximum": 1 },
    "blockedReason": { "type": ["string","null"] }
  },
  "additionalProperties": false
}
```

The `attention` component is **never declared by a bundle** — its shape is fixed by the attention spec and it is produced by a core reducer (reducer spec). A bundle influences attention only by *mapping its domain events into the scoring scalars* via its reducer binding (below), never by redeclaring the facet.

### Event types (semantic-event-envelope spec)

An event file is a JSON-Schema for the `data` payload, annotated with the envelope spec's `type` and `dataschema`. `type` is reverse-DNS past-tense, bundle-owned; `dataschema` is the versioned id the envelope already uses (`bundle:<id>@<major>/<type>.v<n>`). The `ambisphere.*` `type` prefix is **reserved to core** (the envelope spec's closed core-reserved allowlist); a bundle MUST NOT declare a `type` under it, and L2/L4 validation rejects any bundle event whose `type` is in or shadows that allowlist. A bundle may *reference* a core-reserved `type` in a reducer `handles` list (to fold a runtime-meta fact), but it never *declares* its schema — that is a core artifact.

```jsonc
// events/ci.failed.v2.schema.json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "x-ambisphere-event": {
    "type": "ci.failed",                                  // envelope ENVELOPE.type, bundle-owned, past-tense
    "dataschema": "bundle:loswf@2/ci.failed.v2",          // envelope ENVELOPE.dataschema (versioned)
    "upcastsFrom": "bundle:loswf@2/ci.failed.v1"          // optional: declares this is the upcast target of v1
  },
  "type": "object",
  "required": ["checkName","conclusion"],
  "properties": {
    "checkName": { "type": "string" },
    "conclusion": { "enum": ["failure","timed_out","cancelled"] },
    "runUrl": { "type": "string", "format": "uri" }
  },
  "additionalProperties": false
}
```

Upcasters (envelope spec: pure, registered, run at read time) are declared by `upcastsFrom` and implemented in a behavior module (below). The log is never rewritten; a bundle ships the new payload schema + the upcaster, and validation checks that every `dataschema` referenced by a reducer is reachable (directly or via an upcast chain) from the schemas the bundle ships.

### Reducer bindings (reducer/state-component spec) — the seam

A reducer binding is the **single seam** (ADR-0001 inv. 2) between write-side `type`s and read-side components. It is declarative wiring; the fold *logic* lives in a behavior module. Single-writer is enforced here: exactly one binding may own a given `componentType` across the whole installed bundle set.

```toml
# reducers/workflow.reducer.toml
[reducer]
componentType = "loswf.workflow"           # the ONE component this reducer owns (single-writer, reducer spec)
reducerVersion = 3                          # reducer spec evolution; feeds reducerSetVersion (below)
module = "module:loswf_reducers#workflow"   # behavior coordinate (see § behavior modules)
handles = [                                 # event TYPES this reducer folds (envelope `type`s)
  "ci.failed", "ci.passed", "workflow.started", "workflow.completed"
]

# OPTIONAL declarative attention scalar mapping — how this bundle's domain events feed the
# attention scalars (reducer spec: bundle-layer translation; core NEVER branches on loswf.*).
# This is data, not code: a bounded mapping the core attention reducer reads. No clock/RNG.
[[attentionMap]]
onType = "ci.failed"
urgency = 0.9
importance = 0.8
actionability = 1.0
[[attentionMap]]
onType = "ci.passed"
urgency = 0.0
state = "resolved"
```

The `attentionMap` is the declarative, vendor-neutral way a bundle raises attention without core branching on its types: the core attention reducer (reducer spec) reads the mapping **as stamped reducer context (`ev.ctx`), not as an ambient input** (reducer spec § purity rule 7), and the merged `attentionMap` across the installed set is folded into `reducerSetVersion` via the `declarative-input-digest` term (§ `reducerSetVersion` derivation). This is what keeps the `attentionMap` from violating the `(prev, ev)`-only purity rule and what makes editing it a versioned, snapshot-invalidating, deterministically-re-projected change rather than a silent replay hazard. A reducer that needs richer-than-scalar logic ships it in the module instead, still constrained by the reducer spec's purity rules.

### Action definitions (action-capability spec)

```toml
# actions/rerun-ci.action.toml
[action]
id = "loswf.rerun-ci"
title = "Re-run CI"
description = "Re-trigger the failed CI check for this workflow"
module = "module:loswf_actions#rerun_ci"   # the handler (write-side; result re-enters via submit, envelope spec)
inputSchema  = "actions/rerun-ci.input.schema.json"   # JSON-Schema (action spec)
outputSchema = "actions/rerun-ci.output.schema.json"
destructive = false                         # UX HINT ONLY — never the security boundary (ADR-0001 inv. 5)
confirmRequired = false                      # UX HINT; a true value emits approval-requested state (action spec)
idempotent = true
locality = "remote-write"                     # local | remote-read | remote-write (action spec enum; egress boundary keys off this)
requiredCapabilities = ["loswf:ci:write"]    # AUTHORITY TOKEN requirements, not roles (action/ocap spec)
# preconditions are the CLOSED STRUCTURED predicate owned by the reducer spec's shared mini-language
# (§ "declarative predicate + field-path mini-language"). NOT a free-text expression grammar.
preconditions = [ { path = "loswf.workflow.phase", op = "eq", value = "failed" } ]
resultEvents = ["ci.requested"]              # the fact(s) the action's result will submit back (envelope spec)
```

Flags are advisory; the capability check at the write boundary is the boundary. `requiredCapabilities` are token requirements the installer/grantor satisfies (§ load & activation); the bundle never embeds a token.

### Persona / projection rules (persona spec) — read-side, firewall-safe

Persona rules are **read-side** and **bounded**: a cascade (product → kind → state/surface → instance, persona spec) of presentational/narrated metadata whose text slots may reference **only declared factual component fields**. The format provides no escape hatch to code or to a write path. Both the state-matcher (`when`) and the text slots use the **single shared declarative predicate + field-path mini-language owned by the reducer spec** (§ "declarative predicate + field-path mini-language"); this section invents no syntax of its own. `when` is therefore the same closed structured predicate an action precondition uses; a slot is a `{ref}`/`{text}` (with `"{field.path}"` brace sugar) over a field-path, identical to the persona spec's slot grammar.

```toml
# personas/workflow.persona.toml
[persona]
appliesTo = "loswf:workflow"               # kind this persona projects (read-side)
projectionSchemaVersion = 1                 # persona spec projection schema version
default = "null"                            # optional; "null" = factual-only projection (persona spec default)

[[states]]                                  # map a DECLARED factual state to expressive metadata
when = { path = "loswf.workflow.phase", op = "eq", value = "blocked" }   # SHARED structured predicate (reducer spec)
tone = "serious"
# slots use the SHARED slot/brace grammar (reducer spec); may reference ONLY declared factual fields (firewall).
# Validation parses each slot with that grammar and rejects a slot naming an undeclared/non-factual field or any event/capability.
summaryTemplate = "Workflow blocked: {loswf.workflow.blockedReason}"   # brace sugar = {ref} over a field-path
[[states]]
when = { path = "loswf.workflow.phase", op = "eq", value = "running" }
tone = "calm"
summaryTemplate = "Running ({loswf.workflow.progress})"
```

`summaryTemplate` output is a **narrated projection** (reducer spec: lives in its own store, never on the log, never a reducer input). The bundle declares the template; the daemon's persona projection produces the narrated value at read time, tagged `kind:"narrated"` with `grounds[]` pointing at the factual fields the slots referenced. The format makes a firewall violation a *validation error*, not a runtime accident.

### Renderer hints (renderer spec)

Advisory only. Renderer hints never carry authoritative state and never assume one substrate (persona prior-art: reject spritesheet-as-truth).

**Who owns the per-surface projection shape (cross-spec resolution).** The renderer spec requires the daemon to compute a per-surface view-model (the `tray` vs `card` `stateView` shape) as a *pure function*, while shipping zero `SurfaceKind` values and no presentation knowledge in core. The bundle's `renderers/hints.toml` is **not** that projection: it carries only advisory hints (which rungs a surface honors, a field to surface prominently, a logical asset name), never a projection template capable of shaping a full `stateView`. The resolved ownership is **daemon-driven, not bundle-driven**: the per-surface `stateView` is produced by the daemon's read plane as a pure projection over the *typed factual components*, the *persona projection*, and the *attention view* for the requested `surfaceKind` — a domain-neutral assembly that selects/orders already-declared factual fields and persona slots. Core ships **zero `SurfaceKind` values**; the surface taxonomy is semantic and negotiated at attach (renderer spec), and bundle `surfaceHints` only *bias* which declared fields the daemon's projection prefers for a given surface. There is therefore exactly one artifact that determines projection shape — the daemon's pure per-surface assembler — and the bundle contributes advisory bias, never a competing projection template. (Producing the full projection-template format, if hints ever prove too weak, is the renderer spec's open question; this spec deliberately does **not** introduce a projection-template DSL here, to avoid the Turing-complete-bundle trap and a second presentation system.)

Field references in hints use the **shared field-path grammar** (reducer spec § mini-language); L1 validation resolves every `field` to a declared factual field.

```toml
# renderers/hints.toml
[renderer]
projectionSchemaVersion = 1                 # renderer spec projection-schema version (negotiated at attach)

[[surfaceHints]]
surfaceKind = "tray"                        # semantic, not presentational (renderer spec keeps surface taxonomy semantic)
honoredRungs = ["ambient","nudge","prominent"]   # advisory; the surface's affordance map is authoritative (attention spec)
[[surfaceHints]]
surfaceKind = "dashboard-card"
field = "loswf.workflow.progress"           # ADVISORY bias: prefer this factual field on this surface (shared field-path grammar)
asset = "icon-workflow"                     # logical asset name -> resolved via assets/index.toml (content-addressed)
```

### Capability metadata (action / privacy specs)

```toml
# capabilities/capabilities.toml
[[requiredCapabilities]]                     # authority the bundle's actions/adapters need (granted at install)
id = "loswf:ci:write"
description = "Trigger CI re-runs"
locality = "remote-write"                     # local | remote-read | remote-write (action spec enum; privacy/egress keys off this)

[[credentialRefs]]                           # OPAQUE references — the adapter holds the secret; never in the bundle/log
id = "github-token"                          # an adapter resolves this to a secret out-of-band (ADR-0001 inv. 7)
description = "GitHub token for the CI adapter"
# NOTE: no `value`/`secret`/`token` field exists in this schema. Validation FAILS on any secret-shaped literal.

[egress]                                     # per-kind redaction/egress policy (privacy spec) applied before remote send
# The privacy/credential spec OWNS egress meaning and keys its gate off the action `locality` enum
# (local | remote-read | remote-write); `remote-read`/`remote-write` are the egress-relevant values.
[[egress.rules]]
appliesTo = "loswf:workflow"
redact = ["loswf.workflow.blockedReason"]    # fields stripped before any remote (remote-read/remote-write) egress (privacy spec)
```

### Assets (this spec — OCI-style content addressing)

```toml
# assets/index.toml — logical name -> content-addressed descriptor (OCI Descriptor, adapted)
[[asset]]
name = "icon-workflow"
mediaType = "image/svg+xml"
digest = "blake3:9f86d0818..."               # bytes at assets/blobs/blake3/9f86d0818... MUST hash to this
size = 2841
```

Assets are opaque blobs addressed by digest; the daemon never interprets them. A renderer resolves a logical name → descriptor → blob. Deduplication is automatic (identical bytes share one blob), as in OCI.

### Test fixtures (reducer / envelope specs)

Fixtures are first-class bundle content so the conformance tests run against the bundle that ships them. A fixture is a golden vector: a list of proposed events and the expected `(state, provenance)` after replay — directly feeding the reducer spec's replay-equality test and the envelope spec's dedupe/ordering tests.

```jsonc
// fixtures/workflow-happy-path.fixture.json
{
  "x-ambisphere-fixture": { "schemaVersion": 1, "appliesTo": "loswf:workflow" },
  "events": [                                  // ProposedEvents (envelope spec) — NO runtime region; the harness stamps it deterministically
    { "type": "workflow.started", "occurredAt": "2026-06-10T18:00:00Z", "dedupeKey": "wf:1:start",
      "data": { "name": "build" } },
    { "type": "ci.failed", "occurredAt": "2026-06-10T18:05:00Z", "dedupeKey": "wf:1:ci:99812",
      "data": { "checkName": "build", "conclusion": "failure" } }
  ],
  "deterministicStamps": { "baseSequence": 1, "ingestTimeBase": "2026-06-10T18:00:01Z", "seedBase": "00..00" },
  "expect": {
    "components": {
      "loswf.workflow": { "schemaVersion": 2, "kind": "factual",
        "data": { "phase": "blocked", "progress": 0, "blockedReason": "build failed" } },
      "ambisphere.attention": { "kind": "factual", "data": { "urgency": 0.9, "state": "active" } }  // via attentionMap
    },
    "provenanceValueHash": { "loswf.workflow": "blake3:..." }   // verifies snapshot-as-pure-function (reducer spec)
  }
}
```

The fixture harness stamps the runtime region deterministically (from `deterministicStamps`), runs the real reducers, and asserts byte-identical output — turning the bundle into a self-testing artifact and giving validation a way to prove the bundle's reducers actually produce the components its schemas declare.

## Behavior modules

Declarations are data; behavior is code referenced by a language-neutral **coordinate** so the same declaration can be backed by a Rust module (reference SDK), a future WASM component (adapter guidance: untrusted-third-party path, not v1), or an out-of-process adapter.

```text
module:<module-id>#<symbol>          # coordinate grammar
  module:loswf_reducers#workflow     # symbol `workflow` in registered module `loswf_reducers`
```

- A bundle ships modules under `modules/` (native dynamic libraries for the Rust reference SDK in v1) and/or declares **out-of-process adapter** coordinates (`adapter:<name>` resolved via the adapter API) for behavior that lives in another process/language.
- Modules are the *only* place imperative logic exists. They are bound by the contracts they implement: reducer modules MUST satisfy the reducer spec purity rules; action modules run on the write side; upcaster modules are pure functions. The manifest declares *which contract* a module symbol implements; the daemon loads it behind that contract's trait.
- v1 trust model: modules are **first-party / trusted** (loaded in-process). Sandboxing untrusted third-party bundles via the WASM Component Model is a declared future direction (adapter guidance), and the coordinate grammar is designed so a `module:` can become a `wasm:` without changing any declaration.

### v1 in-process module ABI (`module:` coordinate)

A `module:` coordinate is the **only** way reducers, action handlers, and upcasters enter the runtime, and `reducerSetVersion` hashes a module digest — so the ABI and the digest preimage must be defined, not deferred. The v1 ABI is the **C ABI over a single exported registration function**; the Rust reference SDK emits it behind a macro so authors never hand-write it.

```text
module:<module-id>#<symbol>          # coordinate grammar (re-stated)
  module-id  := identifier           # the registered module name; one dynamic library per module-id
  symbol     := identifier           # a contract implementation registered by that module
```

**Symbol resolution.** Each `modules/<module-id>.{so|dylib|dll}` MUST export exactly one C-ABI entry point:

```rust
// Exported by the dynamic library; emitted by the reference SDK's `#[ambisphere_module]` macro.
// `extern "C"` + repr-C handle types are the stable boundary; Rust types never cross it.
#[no_mangle]
pub extern "C" fn ambisphere_module_register_v1(reg: *mut AbiRegistrar) -> AbiStatus;
```

`ambisphere_module_register_v1` is the **single, versioned ABI surface**. The `_v1` suffix is the ABI version: the daemon resolves the highest `ambisphere_module_register_v<n>` symbol it supports; a library exporting only a higher, unknown version is rejected at load with `UnsupportedModuleAbi` (no partial load). The registrar receives, for each `#<symbol>` the manifest names, a `{contract, symbol-name, fn-pointer}` triple where `contract ∈ {Reducer, ActionHandler, Upcaster}`. The daemon binds each registered fn-pointer behind the matching contract's Rust trait object (`Reducer`, `ActionHandler`, `Upcaster`); a coordinate whose `#<symbol>` the library did not register, or registered under the wrong contract for its manifest binding, fails L1/L2 validation before any reduction runs.

**Version-compatibility rule.** The module ABI version (`ambisphere_module_register_vN`) is independent of `[bundle].abiVersion` (the *manifest* format) and of `[engines].ambisphere` (the *daemon* version). The compatibility contract is:

- The daemon publishes a set of supported module-ABI versions. A module loads iff it exports a registration symbol in that set. ABI versions are added (a new `_vN`) only when the C-ABI handle layout changes — a rare, daemon-`specversion`-level event, never a per-bundle freedom.
- Within one ABI version, the registrar interface is **append-only**: new contract kinds and new trait methods (with defaults) may be added; existing ones never change signature. This lets a newer daemon load an older first-party module unchanged (forward compatibility within `_v1`).
- A bundle does not declare a module-ABI version in `bundle.toml`; it is discovered from the exported symbol. `[engines].ambisphere` is the human-facing compatibility range; the symbol resolution is the machine-checked one.

**`module-digest` preimage (exact bytes).** `reducerSetVersion` (below) and the bundle content digest both consume a `module-digest`. It is defined to remove all ambiguity:

```text
module-digest(module-id) = blake3( canonical-module-bytes )
canonical-module-bytes  =  the exact on-disk bytes of modules/<module-id>.{so|dylib|dll}
                           for the platform target recorded in BUNDLE.lock, with NO normalization
```

- The digest is over the **shipped binary's raw bytes**, the same bytes the content digest hashes — so a recompiled module (different bytes) changes both digests deterministically, and an identical rebuild (reproducible build) does not.
- For an `adapter:` (out-of-process) coordinate there is no shipped binary; its `module-digest` term is `blake3(coordinate-string)` (the `adapter:<name>#<symbol>` text), and the out-of-process behavior's own versioning is carried by the adapter API's version negotiation, not by this hash. A reducer MUST NOT be backed by an `adapter:` coordinate in v1 (reducers are in-process for determinism and replay); only action handlers and egress may be out-of-process. Validation L2 rejects a reducer binding whose `module` is an `adapter:` coordinate.
- Multi-platform bundles ship one binary per target under `modules/<module-id>.<target>.{so|dylib|dll}`; `BUNDLE.lock` records the resolved target, and `module-digest` is taken over the binary for *that* target. `reducerSetVersion` is therefore per-target by construction — a snapshot built on one target is not reused on another (it is rebuilt from the log), which is correct since the reducer bytes differ.

## Bundle identity and versioning

Three orthogonal identities, none invented here beyond the bundle's own:

1. **Bundle package id** — `<namespace>:<name>@<semver>` (WIT package id, adapted): `loswf:loswf-factory@2.3.0`. `[bundle].id` (the namespace) is what `EntityAddress[0]` resolves authority to; `name` disambiguates multiple bundles under one namespace (rare; precedence rules below).
2. **Bundle content digest** — `blake3:<hex>` over the canonical (sorted, normalized) archive minus `digest.excludes` (OCI content-addressability). This is the immutable identity of *these exact bytes*; two builds of the same source yield the same digest (reproducible). The digest, not the SemVer, is what `BUNDLE.lock` pins.
3. **Per-artifact versions** (all owned by sibling specs; carried, not invented):
   - `abiVersion` / `specversion` — bundle-format & envelope versions (this spec / envelope spec).
   - `dataschema` per event — payload version (envelope spec).
   - `reducerVersion` + component `schemaVersion` — reduction & facet versions (reducer spec).
   - `projectionSchemaVersion` — persona & renderer projection versions (persona/renderer specs).
   - action manifest version, capability schema version.

### `reducerSetVersion` derivation

The daemon spec tags snapshots with `reducerSetVersion` and discards them when reducers change (reducer spec inv. 8). This spec defines how that version is **derived deterministically** from the installed bundle set:

```text
reducerSetVersion = blake3( sorted over all installed reducer bindings of
                            (componentType, reducerVersion, module-digest, declarative-input-digest) )

declarative-input-digest(binding) = blake3( canonical-CBOR of the binding's declarative reducer-input data )
  # for a domain reducer binding: the empty/absent set (no declarative input) -> blake3 of empty CBOR map
  # for the CORE attention reducer: the canonical CBOR of the MERGED attentionMap across all installed
  #   bundles (sorted by (bundleId, onType)), since that data is read by the core reducer via ev.ctx
```

**Why the `declarative-input-digest` term is required (cross-spec fix, folded in).** Some *core* reducers — notably the attention reducer — consult **declarative data a bundle ships**: the `attentionMap` (§ reducer bindings) that maps a domain event into the attention scalars. That data is neither `prev` nor the raw event, so a naive read would violate the reducer spec's "a reducer may read only `prev` and `ev`" purity rule *and* create a replay hazard: changing a bundle's `attentionMap` would change derived attention scalars with **no logged fact and no captured version**, so replaying an old log under the new map would not be byte-identical to the original. The reducer spec (§ purity rule 7) resolves this by (a) requiring the `attentionMap` (and any sibling declarative reducer-input) to be folded into `reducerSetVersion` — **this `declarative-input-digest` term is that requirement** — and (b) having the reducer read that data only as the *stamped* `ev.ctx` (the reducer context for the `reducerSetVersion` in force at the event's ingest), so from the reducer's point of view it *is* `(prev, ev)` and purity holds. Because the envelope stamps `reducerSetVersion` at ingest, a change to any `attentionMap` **bumps `reducerSetVersion`, invalidates the old-tagged snapshots, and forces a deterministic re-projection** — replay under the *same* `reducerSetVersion` stays byte-identical; replay under a *new* one is an intended, versioned re-projection, not accidental drift.

Any change to a reducer's version, its module bytes, *or its declarative input* (e.g. an `attentionMap` edit) changes `reducerSetVersion`, so stale snapshots are discarded and re-projected (reducer spec: snapshot⊕tail≡replay). Because it is a content hash over a sorted set, it is independent of install order (ADR-0001 inv. 3 determinism).

### SemVer semantics for bundles

- **MAJOR** — a breaking change to any declared contract: removing/renaming a `componentType` or event `type`, an incompatible component-schema change without an upcaster, removing an action, narrowing a capability. Consumers' pins must opt in.
- **MINOR** — additive: a new kind/event/component/action, a new optional component field, a new persona state, a new upcaster. Backward-compatible.
- **PATCH** — fixes that change no contract: corrected reducer logic that still produces the same component shape (bumps `reducerVersion`, hence `reducerSetVersion`, triggering re-projection — but not a schema break), copy fixes, asset swaps.

Dependencies use SemVer ranges (`^4.1.0`, `>=1.0.0 <2.0.0`); resolution is **flat and locally pinned** into `BUNDLE.lock` (not an npm tree). WIT's "max-compatible version wins" dedup is adopted for diamond deps: if two bundles depend on `khaos@^4`, the highest installed `4.x` satisfies both.

## Validation

`validate(bundle) -> Report` is **total, deterministic, and offline** (no network, no clock, no RNG). It runs in authoring tooling and is **re-run at load**; the daemon refuses to activate a bundle that fails. Validation is layered:

```text
validate(bundle):
  L0  structural:    bundle.toml parses; abiVersion supported; layout well-formed; archive digest matches BUNDLE.lock
  L1  reference:     every index path exists; every cross-ref (reducer->component, reducer->event type,
                     action->schema, persona/renderer field-path, renderer->asset) resolves to a declared id;
                     every action precondition / persona `when` / persona|renderer slot parses under the ONE
                     shared predicate + field-path mini-language (reducer spec) and resolves to declared fields;
                     every module: coordinate's #symbol is registered by its library under the matching contract
  L2  contract:      each artifact conforms to its OWNING spec's schema (component env, event annotation,
                     action manifest incl. structured `preconditions` + `locality` enum, persona slot grammar,
                     attention map bounds) — schema validation per § serializing; a reducer `module` that is an
                     `adapter:` coordinate is rejected (reducers are in-process); module ABI version is supported
  L3  composition:   single-writer (one reducer per componentType across the bundle SET); namespace ownership
                     unique or dependency-justified; upcast chains reach every referenced dataschema; relation
                     targets resolve to declared kinds; dependency ranges are satisfiable and acyclic
  L4  invariant:     FIREWALL — no persona/renderer slot (parsed via the shared grammar) names an undeclared /
                     non-factual field or any event/capability;
                     NO-SECRET — no secret-shaped literal anywhere (grep + schema: credentialRefs have no value field);
                     NO-NARRATION-ON-LOG — no path from persona/projection to a reducer input or submit;
                     VENDOR-NEUTRAL — a bundle declares zero `ambisphere.*` event `type`s and zero `ambisphere.*`
                     components (it may only REFERENCE the closed core-reserved event allowlist + closed core-owned
                     component list); the lint allowlists EXACTLY the envelope spec's set, never re-deriving it;
                     core-load additionally requires zero domain kinds
  L5  fixtures:      replay each fixture through the real reducers; assert byte-identical (state, provenance)
                     and that declared components match their schemas (proves reducers honor their declarations)
```

`Report` lists errors (block load) and warnings (advisory, e.g. a kind with no renderer hint). L4 is the load-bearing safety layer: it makes the ADR-0001 firewall and credential invariants **static, pre-load properties** of the artifact rather than runtime hopes. L5 makes a bundle self-proving: its reducers must actually produce what its schemas declare, or it is invalid.

## Load and activation

Install is capability-gated (daemon spec broker; ADR-0001 inv. 5 — even teaching the runtime new authority is itself an authority).

```text
install(installCap, bundlePath) -> InstallAck { bundleId, contentDigest, reducerSetVersion, outcome }
  outcome: Installed | AlreadyInstalled(sameDigest) | Upgraded(fromVersion) | Rejected(Report)
```

Normative load order:

```text
1. resolve + validate the dependency graph (deps before dependents; acyclic; ranges satisfiable) -> BUNDLE.lock
2. validate(bundle) at L0..L5 for each, in dependency order; ANY error => Rejected, nothing registered
3. grant: the installCap authorizes which requiredCapabilities the bundle may hold (POLA; default-deny extras)
4. register declarations in dependency order: kinds -> components -> events -> reducers -> actions -> personas -> renderers
5. compute reducerSetVersion over the new installed set
6. if reducerSetVersion changed: discard snapshots tagged with the old version; schedule re-projection (reducer spec)
7. ack. NO entity state is created at install — entities come into being only via submit (ADR-0001 inv. 1)
```

### Conflict and precedence

- **Namespace ownership.** Two bundles claiming the same `[bundle].id` conflict and install fails — *unless* one depends on the other, in which case the **dependent** may *extend* (add kinds/events/components under that namespace) but never *redefine* a `componentType`/`type` the dependency already owns (single-writer holds across the set). Redefinition is a `Rejected` composition error.
- **Component single-writer.** Exactly one reducer owns each `componentType` across all installed bundles. A second claimant is rejected (no last-write-wins; ADR-0001 inv. 1/2).
- **Upgrade.** Upgrading a bundle re-runs validation; if the new `reducerSetVersion` differs, affected projections re-build from the log (the log is untouched — ADR-0001 inv. 1). A MAJOR upgrade that drops a `componentType` leaves historical events on the log readable (schema-on-read) but stops producing that component; its snapshots are discarded.
- **Uninstall** stops producing a bundle's components and deregisters its handlers; it never deletes log events (the source of truth is immutable). Re-installing replays cleanly.

## Worked example (vendor concepts in the adapter/example layer only)

A LOSWF factory bundle (under `examples/`, **never** core) teaches the runtime about workflow entities. *Core ships none of these `loswf.*` kinds/types/components; this bundle is the only place they exist.*

```toml
# examples/loswf/bundle.toml (excerpt)
[bundle]
id = "loswf"
name = "loswf-factory"
version = "2.3.0"
abiVersion = "ambisphere.bundle/1"
[engines]
ambisphere = ">=1.0.0 <2.0.0"
specversion = "ambisphere.event/1"
[[dependencies]]
id = "ambisphere.core"; version = ">=1.0.0 <2.0.0"   # provides ambisphere.identity + ambisphere.attention reducers
[[kinds]]      path = "kinds/workflow.toml"
[[components]] path = "components/workflow.schema.json"
[[events]]     path = "events/ci.failed.v2.schema.json"
[[reducers]]   path = "reducers/workflow.reducer.toml"
[[actions]]    path = "actions/rerun-ci.action.toml"
[[fixtures]]   path = "fixtures/workflow-happy-path.fixture.json"
```

End-to-end: a GitHub adapter submits `ci.failed` for `["loswf","workflow","build-99812"]` (envelope worked example) → the daemon stamps the runtime region, appends, acks → the bundle's `loswf_reducers#workflow` reducer folds it to `loswf.workflow{phase:"blocked"}` and the declarative `attentionMap` raises `ambisphere.attention` to high urgency → the attention bus ranks it → a renderer (honoring the `surfaceHints`) shows it prominently → the persona rule renders the *narrated* summary "Workflow blocked: build failed" (tagged narrated, grounded in `blockedReason`) → an operator with `loswf:ci:write` invokes `loswf.rerun-ci`, whose result re-enters as `ci.requested` via `submit`. Every contract serialized in one bundle, composed cleanly, with core branching on nothing `loswf.*`.

## Acceptance criteria

A conforming implementation MUST satisfy, as automated tests:

1. **Manifest round-trip.** `bundle.toml` parses to a typed model and re-serializes byte-identically (canonical form); an unsupported `abiVersion` is rejected before any other processing.
2. **Reproducible digest.** Building the same source directory twice yields the identical `blake3` content digest; changing only `qa/**` (an excluded path) does not change the digest; changing any indexed artifact does.
3. **Reference integrity (L1).** A reducer naming an undeclared `componentType` or event `type`, an action naming a missing schema, a persona naming an undeclared field, or a renderer hint naming a missing asset each fails validation with a precise pointer.
4. **Contract conformance (L2).** Each artifact validates against its owning spec's schema; a component decl with `kind:"narrated"`, an event `type` that is not past-tense reverse-DNS, an out-of-bounds `attentionMap` scalar, an action `locality` outside `{local, remote-read, remote-write}`, an action `preconditions`/persona `when` not in the shared closed structured-predicate form, or a reducer `module` that is an `adapter:` coordinate is rejected.
5. **Single-writer across the set (L3).** Installing two bundles that both own one `componentType` is `Rejected`; the error names both claimants.
6. **Namespace ownership (L3).** Two bundles claiming the same `[bundle].id` without a dependency relationship fail install; a dependent extending (not redefining) its dependency's namespace succeeds.
7. **Firewall is static (L4).** A persona `summaryTemplate` slot referencing an undeclared field, a non-factual field, or any event/capability fails validation; there exists **no** schema field by which a persona rule can reach a reducer input or `submit` (structural).
8. **No secret can be packaged (L4).** The `credentialRefs` schema has no value/secret field; a secret-shaped literal anywhere in the bundle fails the no-secret grep; only opaque `credentialRef` ids and `requiredCapabilities` survive.
9. **Vendor neutrality (L4) and allowlist alignment.** Any bundle declaring an `ambisphere.*` event `type` or an `ambisphere.*` component is rejected (it may only *reference* the closed core-reserved event allowlist and closed core-owned component list); a bundle loaded as *core* additionally declaring any domain kind/type is rejected; the example LOSWF/Khaos bundles load only as example-layer bundles; core code contains zero `loswf.*`/`khaos.*` and never branches on bundle `data`. The vendor-neutrality lint allowlists **exactly** the envelope spec's core-reserved set — the same single allowlist the envelope (AC9) and adapter (AC4) lints reference — and does not re-derive "zero types".
10. **Fixtures are self-proving (L5).** Each shipped fixture, replayed through the bundle's real reducers with deterministically-stamped runtime regions, produces byte-identical `(state, provenance)`; the produced components validate against the bundle's component schemas; a deliberately-wrong fixture fails.
11. **`reducerSetVersion` is deterministic & order-independent.** Computed over the same installed reducer set in any install order, it is identical; bumping any `reducerVersion`, module digest, **or declarative reducer-input (e.g. an `attentionMap` edit)** changes it; the change discards old-tagged snapshots and triggers re-projection (no log rewrite). Replaying a log under an old `attentionMap` produces the old `reducerSetVersion`'s byte-identical result; replaying under a new `attentionMap` is a versioned re-projection, not a byte-identical match to the old result.
12. **Install creates no state.** After a successful install, no entity exists and the log is unchanged; entities appear only via subsequent `submit` (ADR-0001 inv. 1).
13. **Upgrade/uninstall preserve the log.** Upgrading or uninstalling a bundle never deletes or rewrites log events; a MAJOR upgrade that drops a component leaves prior events readable (schema-on-read) and stops producing the component.
14. **Capability-gated install.** `install` without an authorizing `installCap` is `Unauthorized`; a bundle is granted only the `requiredCapabilities` the `installCap` permits (POLA; extras default-denied).
15. **Dependency resolution.** Diamond deps resolve to the max semver-compatible version; an unsatisfiable range, a cycle, or a missing required (non-optional) dependency fails install; an absent *optional* dependency degrades gracefully (its kinds/edges unavailable, the rest loads).
16. **Module ABI is defined and load-checked.** A `module:` library exporting `ambisphere_module_register_v1` loads and registers each `#symbol` behind the correct contract trait; a library exporting only an unknown higher ABI version is rejected with `UnsupportedModuleAbi` and registers nothing; a manifest coordinate whose `#symbol` is unregistered, or registered under a contract mismatching its binding, fails validation. The `module-digest` is the blake3 of the shipped binary's raw bytes for the locked target; an identical reproducible rebuild yields the same digest (hence same `reducerSetVersion`), a recompiled-different binary yields a different one.

## Open questions

- **Behavior-module trust tiering (the ABI itself is now fixed).** The v1 in-process module ABI (single `ambisphere_module_register_v1` C-ABI entry point, contract-bound trait objects, version-by-symbol), the `module-digest` preimage, and the `adapter:`-coordinate restriction for reducers are **resolved above** (§ behavior modules). What remains open is purely the *trust boundary*: v1 loads first-party native modules in-process; the coordinate grammar anticipates a `wasm:` sandbox (adapter guidance) and `adapter:` out-of-process behavior, but the boundary between a "core" bundle, a "first-party example" bundle, and an "untrusted third-party" bundle — and whether an untrusted bundle's reducer may run in-process at all or only via WASM — needs a dedicated decision.
- **Egress-policy ownership (the locality enum is now aligned).** The `local | remote-read | remote-write` enum is **resolved above** and is used identically by the action manifest, capability metadata, and the privacy spec's egress gate. What remains open is the *home* of the egress policy *meaning*: this spec carries `egress` rules in `capabilities/`, but the privacy/credential spec owns the meaning; the split between bundle-declared egress rules, action-manifest locality, and a standalone egress spec is the privacy spec's call (it flags the policy spans all three).
- **ADR-0001 status (foundational, not resolvable here).** Every follow-on spec, this one included, declares "Conforms to: ADR-0001" yet ADR-0001 is itself `draft`/`Proposed`; the conformance table cites invariant numbers ADR-0001 must enumerate. This spec conforms to the *provisional* ADR-0001 (§ ADR status) and re-pins on acceptance; resolving the ADR to a single status and adding its canonical numbered-invariant list is an ADR-owned action shared across all nine dependent specs, not a bundle-spec change.
- **`local-id` uniqueness scope authority.** The kind decl carries `localIdScope`, but the identity spec lists uniqueness scope (namespace+kind vs within-parent vs global) as an open question. If the identity spec fixes it globally, the per-kind override here may be redundant or conflicting.
- **Cross-namespace edges and capability gating.** A bundle may declare a bundle-defined relation type whose `target` is another namespace's kind (e.g. `loswf:workflow blocks khaos:project`). Whether creating such an edge requires a capability granted by the *target* namespace's owner (identity spec open Q) determines whether this is a validate-time or a runtime authorization concern.
- **Bundle signing & provenance.** The content digest gives integrity; it does not give authenticity. A signature scheme (who signed this bundle, is the publisher trusted to claim this namespace) is out of scope here but needed before any non-local distribution — likely a thin layer over the digest plus the capability model.
- **Snapshot/upcaster co-versioning on upgrade.** When a MAJOR upgrade changes a component schema *with* an upcaster, the interaction between discarded snapshots (`reducerSetVersion` bump), re-projection cost, and upcast-at-read on a long log needs the DDIA-style spike the reducer/daemon specs already flagged — the bundle format must not make re-projection cost unbounded.
- **Fixture expressiveness vs determinism.** Fixtures stamp the runtime region from `deterministicStamps`. Whether that is rich enough to exercise dedupe, out-of-order arrival, and multi-entity rollup fixtures — or whether fixtures need a small scenario grammar — is open; over-growing it risks the Turing-complete-DSL trap this spec rejects.
- **Authoring skill output shape.** The persona prior-art `hatch` pattern (skill → packaged artifact with `qa/`) suggests an Ambisphere authoring skill that emits this bundle layout. Whether that skill also emits a default renderer bundle (so a bundle is immediately visible) is the persona spec's open question, inherited here as: does `validate` warn when a bundle ships kinds but no renderer hints at all?
