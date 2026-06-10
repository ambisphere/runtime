# Entity identity and hierarchical graph

**Status:** draft · **Scope:** the two-part entity identity (an opaque, immutable `entityHandle` — ULID/UUIDv7 — that is the durable primary key and the value an address resolves to; plus a human-meaningful `EntityAddress`, an injection-safe ordered compound-segment list that is an alias onto the handle); the **canonical segment/glob/kind/namespace matching grammar** over `EntityAddress` segment lists (owned here; consumed by the action/capability and privacy specs for capability targets, caveats, and read scopes, and by this spec's own edge queries); entity **kind** as declarative bundle metadata and a core domain-neutral component, not a class hierarchy; the **typed directed-edge graph** with exactly two built-in relation types (`child-of`, `instance-of`) and bundle-defined types for everything else; address→handle **resolution** at the ingestion boundary; wildcard/predicate **edge queries** and ancestor/descendant traversals on the read side; **rollups** as derived read-model state over `child-of` (and the always-resident summary index the attention bus walks); **cascade/cleanup** as relation metadata · **Companion to:** `specs/VISION.md`, `specs/SRS.md`, `RFP.md` (§9 "Hierarchical and relational entity graph", §1 "Context-scoped entity identity") · **Sequenced:** fifth among the follow-on specs (after the attention-bus, reducer/state-component, and event-envelope specs; before the daemon spec) per ADR-0001 and issue #4 · **Conforms to:** ADR-0001 (foundational paradigm + directionality invariant; this spec cites ADR-0001's *enumerated* runtime-meta event-type allowlist and the ADR's *closed list of core-owned component types* rather than carving its own exceptions — see § conformance and § open questions); the attention-routing spec (rollup traverses `child-of`; the summary index this spec maintains is what the attention bus rolls up over; index contents are decay-invariant per the joint normative rule below); the reducer/state-component spec (identity and edge state are produced by core domain-neutral reducers as ordinary components from the closed core-component list; single-writer rule); the event-envelope spec (this spec owns the `resolve(address→handle)` step in the normative ingestion order, and the `entity` compound-segment-list address is the one defined here); the action/capability and privacy/credential specs (which reference the matching grammar defined here for capability targets and read scopes) · **Sibling notes:** `specs/drafts/runtime-paradigm-and-specs-guidance.md`, `specs/drafts/actor-model-prior-art.md`, `specs/drafts/persona-prior-art.md`, `specs/drafts/implementation-language-guidance.md`

This spec defines **who an entity is** and **how entities relate**. It fixes the addressing scheme producers use, the opaque handle the runtime tracks identity by, the **canonical grammar for matching addresses** (the shared dependency of capability scoping, read scoping, and edge queries), the rule that an entity's *kind* is data and not a type, and the typed directed graph over which the attention bus rolls up and renderers drill down. It is deliberately small and decisive: identity must be stable for the life of the log, the matching grammar must be one grammar everywhere, and the graph must stay vendor-neutral.

It sits at a precise seam in the already-ratified chain. The envelope spec's normative ingestion order is `validate → authorize → resolve(address→handle) → dedupe → assign RUNTIME → append+commit → ack → reduce`. **This spec owns the `resolve` step**: the producer proposes an `EntityAddress` (the envelope's `entity` compound-segment list); the daemon resolves it to the immutable `entityHandle` it stamps into `runtime.entityHandle`; and `sequence` is counted per *handle*, so it survives rename (envelope invariant 4). Everything graph-shaped — edges, rollups, the cross-entity summary index — is on the read side, produced from logged facts by core domain-neutral reducers, never written directly (ADR-0001 invariant 1).

## Goals and non-goals

### Goals

- Define a **two-part identity**: an opaque, immutable, never-reused `entityHandle` (the ECS id and durable PK) and a human-meaningful `EntityAddress` alias that maps onto it.
- Make the address an **ordered compound-segment list**, not a delimited string, so untrusted data can never inject a delimiter (RivetKit's documented key-injection footgun).
- **Own the canonical matching grammar** over segment lists — exact-segment, single-segment wildcard, multi-segment/prefix wildcard, plus `kind:<k>` (via `instance-of`) and `namespace:<ns>` match — so capability targets, read scopes, and edge-query predicates all evaluate identically. This grammar is the single normative definition the action and privacy specs reference.
- Specify **address→handle resolution** as the ingestion-time `resolve` step, including create-on-first-reference, rename (re-alias), and re-home (re-parent) — with `sequence` always per handle.
- Make entity **kind** declarative bundle metadata surfaced as a core, domain-neutral `ambisphere.identity` component (one of the closed core-component set in ADR-0001 / the reducer spec) — **not** a class hierarchy, and **not** something core branches on.
- Define a **typed directed-edge graph** `(relationType, source, target, metadata)` and ship **exactly two** built-in relation types: `child-of` and `instance-of`. Everything else is bundle-defined.
- Make edge mutation a **write-side, capability-gated fact** (an event through `submit`); make the edge *set* a **derived read-model projection** with no direct-write API.
- Specify **wildcard/predicate edge queries** and ancestor/descendant **traversals** on the read side, pure and deterministic given `(view, as_of)`, separately capability-gated for read, and predicated using the canonical matching grammar.
- Specify **rollups** as derived read-model state over `child-of`, backed by an **always-resident summary index** that caches only **decay-invariant** values (raw scalars, decay params, `anchorTime`, `lastEventTime`, `state`, `ceiling`, `parent`, `childCount`, contributing-set) — never a cached `rung` or `score` — so cross-entity rollups (the attention bus, dashboards) need not wake cold entities yet remain correct under `as_of`.
- Make **cascade/cleanup** a property of **relation metadata** (`cascade | orphan | restrict | tombstone`), not built-in runtime behavior.
- Give concrete schemas/interfaces (fenced) and **acceptance criteria** that make the invariants testable (handle immutability, resolution determinism, injection safety, matching-grammar determinism, edge-as-derived, rollup ≡ recompute, decay-invariant index).

### Non-goals (adopt/reject framing — rejections carried from the guidance)

- **Not** a built-in domain kind. Core ships **no** `Issue`/`PR`/`Project`/`Character`/`Workflow`/`Agent` kind, and core code never branches on a kind value. (Reject: any domain kind in core — ADR-0001 inv. 8.)
- **Not** new event types beyond the ones ADR-0001 enumerates. The identity/edge events this spec emits (`entity.registered`, `entity.renamed`, `entity.rehomed`, `entity.deleted`, `edge.added`, `edge.removed`) are **runtime-meta** event types drawn from ADR-0001's enumerated allowlist — they are *not* domain event types, and ADR-0001 inv. 8 forbids only *domain* event types in core. This spec does not invent the exception; it references the ADR's list. (Reject: any *domain* event type in core; reject: each spec quietly carving its own exception to a "zero event types" reading.)
- **Not** a general-purpose graph query language. No Cypher/Gremlin/Datalog surface in v1; we ship a narrow typed predicate-and-traversal API over the canonical matching grammar. (Reject: a graph DSL in core.)
- **Not** more than two built-in relation types. We resist the convenient `blocks`/`depends-on`/`member-of`; those are bundle-defined. (Reject: a growing built-in relation vocabulary.)
- **Not** a class/inheritance hierarchy for entities. `instance-of` records *which kind* an entity is; it is membership, not subtyping, and confers no behavior in core. (Reject: OOP-style kind inheritance.)
- **Not** a distributed/sharded identity authority. The daemon is the sole resolver and PK minter for its local store. (Reject: a global/networked identity registry — ADR-0001 local-first.)
- **Not** identity derived from persona, vendor account, or rendering substrate. No hash-from-account-id (claude-buddy lesson). Identity belongs to the entity, not the host. (Reject: vendor-identity-derived handles.)
- **Not** network-resolvable URLs or IANA-registered URNs. The address is a local logical name, not a dereferenceable locator. (Reject: `urn:`/URL identity.)
- **Not** the attention ranking or persona projection. This spec owns the *relation* (`child-of`) and the *decay-invariant summary index* the attention bus rolls up over; it does not rank, score, or style, and it never caches a `rung`. (Reject: ranking/persona/cached-rung here.)
- **Not** a new core-owned component beyond the closed list. This spec defines `ambisphere.identity` and `ambisphere.edges`, both of which are members of ADR-0001's / the reducer spec's **closed enumeration of core-owned component types** (`ambisphere.attention`, `ambisphere.identity`, `ambisphere.edges`, `ambisphere.lifecycle`, `ambisphere.approvals`). It does not introduce core components ad hoc. (Reject: core-component creep.)
- **Not** edge-as-full-entity in v1. Edges get a ULID (so they are addressable and can carry metadata) but do not carry component state or attention. (Reject: promoting every edge to an entity now — see open questions.)

## Prior art (citations kept visible)

- **Flecs entity relationships (Sander Mertens).** Adopt: the `(relation, target)` **pair** model generalized to a property graph; the distinct, built-in **`ChildOf`** (hierarchy; deleting a parent deletes children) vs **`IsA`** (one entity "is a" kind/prefab) relationships as the *only* two we bake in; **wildcard** pair queries ("find all instances of a relationship for an entity") — the wildcard semantics here are generalized to the canonical matching grammar below; and **cleanup policies as per-relationship metadata** — Flecs's own example is that the cleanup for `Likes` and `ChildOf` may differ, so cleanup is specified per relation, not globally. Reject: Flecs's 64-bit-packed pair encoding and archetype-table internals (an engine-internal optimization, not a contract). flecs.dev — `docs/Relationships.md`, `docs/Queries.md`.
- **ULID spec (`github.com/ulid/spec`) and UUIDv7 (RFC 9562).** Adopt: a 128-bit, **lexicographically sortable, time-prefixed** opaque id as the `entityHandle` — both put a 48-bit ms timestamp in the high bits so inserts are near-sequential (B-tree-friendly, the storage-engine concern the `ddia-systems` lens flags), and both are 128-bit so they are cheap PKs and cursors. ULID's 26-char Crockford-Base32 form is the canonical wire rendering (URL/log-safe, human-glanceable); UUIDv7 is the recorded close alternative where a native `uuid` column is wanted. Adopt the **monotonic** variant so two handles minted in the same millisecond still sort by creation. Reject: UUIDv4 as the handle (random high bits fragment the index) and exposing the timestamp as semantically meaningful (it is opaque). singhajit.com/ulid-guide, authgear.com/post/time-sortable-identifiers-uuidv7-ulid-snowflake.
- **OpenTelemetry resource semantic conventions (`service.namespace` / `service.name` / `service.instance.id`).** Adopt: the **three-part decomposition** of a logical identity — a namespace that groups, a name unique within the namespace, and an instance id unique within `(namespace, name)`, with the triplet globally unique. We map this onto `namespace / kind / local-id` segments and make uniqueness an **enforced unique index**, not OTel's "best-effort label." Reject: OTel's mutable/best-effort framing (identity here is enforced) and the assumption that the instance id should be a random UUID the *producer* mints (the daemon mints the handle; the producer proposes the address). opentelemetry.io/docs/specs/semconv/resource/service.
- **RFC 8141 URNs + DataHub immutable URNs.** Adopt: a **persistent, location-independent, immutable identifier** as the lineage anchor — once an entity exists, its handle never changes or is reused, so provenance and edges stay valid across rename/re-home. Reject: the literal `urn:` scheme, IANA namespace registration, and any global resolution authority. datatracker.ietf.org/doc/html/rfc8141.
- **RivetKit compound-key addressing (`actor-model-prior-art.md`).** Adopt: hierarchical **array/segment-list addressing** (`["room","general"]`) and its explicit **key-injection warning** — never build a key by interpolating untrusted data into a delimited string. The matching grammar below preserves this: a wildcard is a *typed list element*, never a character inside a segment. Reject: point-to-point-only addressing (we add a queryable read-side graph) and the assumption that referential integrity comes free.
- **glob / `gitignore` / RFC 1035 label matching.** Adopt: the familiar `*` (single segment) vs `**` (zero-or-more segments, prefix/multi-segment) distinction, lifted from the file-path/glob world but applied **per list element**, never across a flattened string — so the grammar inherits glob's intuitiveness without glob's path-injection hazards. Reject: in-segment character globbing in v1 (a segment matches a pattern element whole; intra-segment `foo*` is an open question), and full regex (DoS surface, non-determinism risk).
- **ClickHouse materialized-view rollups / DDIA stream-table duality (Kleppmann, *DDIA* ch. 11).** Adopt: **incremental, bottom-up aggregation** — rollups are a materialized view maintained as child facts change, declared per kind, and always **rebuildable** by recomputing over the log; the rollup is a *derived table*, never authored; the always-resident summary index is a **secondary derived index** holding only decay-invariant inputs. Reject: the OLAP engine itself, any second source of truth for rollup state, and any cache of a query-time-computed value (`rung`/`score`) in the index.

## Conformance to ADR-0001

This table references two ADR-0001 anchors that resolve cross-spec findings rather than restating exceptions locally:

- **Runtime-meta event-type allowlist (ADR-0001 inv. 8, amended).** ADR-0001 distinguishes **domain** event types (zero in core) from a small **enumerated set of runtime-meta event types** core reserves: `egress.performed`, `approval.*`, `entity.registered|renamed|rehomed|deleted`, `edge.added|removed`, and the `attention.*` verbs. This spec emits only `entity.*` and `edge.*` from that list and cites the ADR rather than independently carving an exception.
- **Closed core-component list (ADR-0001 / reducer spec).** The core-owned component types are a closed enumeration: `ambisphere.attention`, `ambisphere.identity`, `ambisphere.edges`, `ambisphere.lifecycle`, `ambisphere.approvals`. This spec owns the *shapes* of `ambisphere.identity` and `ambisphere.edges` within that closed list; it adds no others.

| Invariant | How this spec honors it |
|---|---|
| (1) Log is source of truth; components derived, read-only | Identity facts (`entity.registered`, `entity.renamed`, `entity.rehomed`, `entity.deleted`) and edge facts (`edge.added`, `edge.removed`) are events on the per-entity log. The `ambisphere.identity` and `ambisphere.edges` components, the edge set, and the summary index are **derived projections** folded by core domain-neutral reducers; there is no `createEntity`/`addEdge` direct-write API. |
| (2) Directionality | `resolve(address→handle)` and capability checks for edge creation live on the **write boundary**. Edge queries, traversals, and rollups live on the **read side** and are read-only. The matching grammar is evaluated on both sides (capability check on write, predicate on read) from one definition. The log is the single seam. |
| (3) Determinism | The `entityHandle` (ULID) and any edge id are minted at ingestion and **stamped into the event**, so identity/edge reducers read them as data, never an RNG/clock. Edge-set reducers iterate ordered maps (`BTreeMap`), never `HashMap`. Matching is a pure total function of `(pattern, segments)`. The summary index caches **only decay-invariant** values; any `rung`/`score` is computed at query time from those plus `as_of`, so two identical `(view, as_of)` reads rank identically (attention spec guarantee). Replay is byte-identical. |
| (4) Per-entity total order only | `sequence` is per `entityHandle`; it **survives rename** because rename changes the address, not the handle. No global cross-entity order exists. Graph queries read the materialized view (edge projection + summary index), never a global log. |
| (5) Capability-shaped authority | Creating/removing an edge, registering, renaming, re-homing, or deleting an entity each require a capability authorizing that write to the target entity/subgraph, checked only at the boundary, with the target expressed in the canonical matching grammar. Read of the graph is **separately** gated and may return a redacted/coarsened view, scoped by the same grammar. v1 may use an RBAC-degenerate single-principal token; the contract stays ocap-compatible. |
| (6) Fact/narration firewall | Identity and edge facts are factual; their reducers emit `kind: "factual"`. No narration field exists on any identity/edge event; narration never participates in resolution, matching, edges, or rollups. |
| (7) Credentials never in state | Addresses, handles, edges, the identity/edges components, and the summary index carry no secret — only an opaque `capabilityRef` for provenance, per the reducer spec. |
| (8) Vendor neutrality | Core fixes the address *shape*, the handle *shape*, the matching *grammar*, the two built-in relation types, and the `ambisphere.identity`/`ambisphere.edges` *schemas* (members of the closed core-component list); it ships **zero** domain kinds and **zero** domain event types, and never branches on a kind value, a namespace value, or an edge's bundle-defined `relationType`. Bundles declare kinds, custom relation types, and rollup rules in the examples/adapter layer. |
| (9) Cross-language seams | The address (segment list), handle (ULID string), matching pattern, edge, and components are language-neutral JSON/CBOR. Resolution, matching, and edge queries are language-neutral local RPCs (bindings owned by the daemon spec). Any adapter in any language can address/match an entity without linking core. |

## Two-part identity

Every entity has **two** names, and the distinction is load-bearing:

1. **`entityHandle`** — an opaque, immutable, globally-unique-within-this-store, never-reused 128-bit id (ULID canonical, UUIDv7 the recorded alternative). This is the real ECS id, the durable primary key, the foreign key every edge and every provenance record points at, and the unit `sequence` is counted per. **A producer never assigns it; the daemon mints it.** It carries no meaning a reader may parse (the embedded timestamp is an index optimization, not data).

2. **`EntityAddress`** — a human-meaningful, adopter-defined **ordered list of opaque string segments** that is an *alias* onto exactly one handle at any moment in time. It is what producers put in the envelope's `entity` field, what a renderer shows, and what a human types. It can change (rename/re-home); the handle it points to does not.

```rust
// Core = Rust per ADR-0001. Language-neutral by intent; this is the normative shape.

/// The opaque, immutable identity. ULID canonical (UUIDv7 the recorded alternative).
/// Minted by the daemon at first reference; NEVER reused; the durable PK and FK target.
pub struct EntityHandle(pub Ulid);   // 128-bit; wire form = 26-char Crockford-Base32

/// The human-meaningful alias. An ORDERED LIST of opaque segments — NEVER a joined string.
/// This is exactly the envelope's `entity` field (the seam to the event-envelope spec).
pub struct EntityAddress {
    pub segments: Vec<EntitySegment>,   // non-empty; >= 2 (namespace, kind) by the rules below
}

/// One address segment. Opaque to core. Validated structurally, never by meaning.
pub struct EntitySegment(pub String);  // see § address rules for the constraints
```

### Why two parts, not one

A single human-readable id (the URN temptation) couples identity to a name that *will* change — projects get renamed, runs get re-parented, kinds get re-namespaced. If edges and provenance pointed at the *address*, every rename would orphan history. So the handle is the anchor (RFC 8141 / DataHub immutable-URN lesson) and the address is a mutable view onto it (OTel three-part decomposition, but enforced). This also keeps the write path honest: the producer proposes a name; the runtime owns the identity.

## Address rules (the injection-safe compound key)

The address is the project's most exposed attack surface for key-injection, so its rules are normative.

- The address is a **non-empty ordered list** of segments. Core requires **at least two** segments: `segment[0]` is the **namespace**, `segment[1]` is the **kind**. Segments `[2..]` are the local id / sub-ids (`local-id`, then optional `sub-id`s for finer scoping).
- A segment is an **opaque string**; core never parses *inside* a segment. Each segment MUST be non-empty, MUST NOT exceed a fixed byte cap (default 256 bytes), MUST be valid UTF-8, and MUST NOT contain a NUL byte. Core imposes **no delimiter** because there is no delimiter — the list *is* the structure.
- **Injection safety is structural.** Because the address is a list, an adapter that does `["loswf", "issue", untrustedId]` cannot let `untrustedId = "../factory/secret"` escape the segment — `"../factory/secret"` is one opaque segment, not three. Adapters MUST construct the list element-wise and MUST NOT build a segment by interpolating untrusted data into a delimited string. (This is the RivetKit footgun, made unrepresentable by the type.)
- **The matching wildcards (`*`, `**`) are pattern-element values, not segment contents.** A literal segment whose *string value* is `"*"` is a normal opaque segment and never a wildcard; wildcards exist only in `AddressPattern` (below), which is a distinct type from `EntityAddress`. This keeps untrusted data from ever being interpreted as a wildcard.
- **Uniqueness** is an enforced unique index. v1 fixes the uniqueness scope at the **full segment path** within a store: the tuple `(segments...)` resolves to at most one live handle. (Whether a shorter `(namespace, kind, local-id)` scope should also be enforced for flat kinds is an open question; bundles may declare a stricter scope, validated at registration.)
- **Namespace is the trust/privacy boundary** (carried from the privacy/credential guidance). Edges and resolution that cross namespaces are subject to the capability/privacy rules (see § cross-namespace, the matching grammar's `namespace:` form, and the privacy spec).

```jsonc
// Examples — addresses are LISTS. The vendor strings live ONLY in the adapter layer.
["khaos",  "project",  "kspd-7f3a"]                 // a Khaos story project
["khaos",  "workflow", "run-2291"]                  // a composition/analysis run
["khaos",  "character","ari", "arc-3"]              // a character, sub-scoped to an arc
["loswf",  "factory",  "ambisphere/runtime"]        // factory health for a repo
["loswf",  "issue",    "4217"]                      // factory lifecycle for an issue
["loswf",  "agent",    "reviewer", "run-88"]        // an agent run (role + run-id)
```

A canonical *display* rendering (e.g. `khaos:project/kspd-7f3a`) MAY be derived by renderers for humans, but the **list is the identity** and the display string is never parsed back into segments by core or any adapter.

## The canonical matching grammar (owned here)

Capability targets (action spec), credential/read scopes (privacy spec), and this spec's own edge-query predicates all need to test "does this address match this scope?" The action spec records that "the canonical glob/segment-match semantics over `EntityAddress` segment lists must be pinned jointly with the entity-identity spec." **This spec is the owner.** This is the one normative definition; the action and privacy specs reference it and add no matching semantics of their own.

### The pattern type

```rust
/// A pattern matched against an EntityAddress's segment list. DISTINCT from EntityAddress:
/// wildcards are typed list elements, NEVER characters inside a segment, so untrusted data
/// in an EntityAddress can never be interpreted as a wildcard.
pub struct AddressPattern {
    pub elements: Vec<PatternElement>,
}

pub enum PatternElement {
    Exact(String),   // matches exactly one segment whose value equals this string
    AnyOne,          // "*"  — matches exactly one segment, any value
    AnyRun,          // "**" — matches zero or more consecutive segments (prefix/multi-segment)
}

/// Higher-level scope forms that DESUGAR to AddressPattern (or to an instance-of lookup).
/// These are what capability/read scopes are authored in; core lowers them to the matcher.
pub enum AddressScope {
    Pattern(AddressPattern),     // the general form
    Kind { namespace: Option<String>, kind: String },  // "kind:<k>" (optionally ns-qualified)
    Namespace(String),           // "namespace:<ns>"  == Pattern([Exact(ns), AnyRun])
}
```

### Matching semantics (normative)

`matches(pattern, address.segments) -> bool` is a **pure total function**. Wire/textual syntax (for human-authored scopes) is `segment / segment / …` with the two reserved tokens `*` and `**`; tooling parses this textual form into `AddressPattern`, but core only ever evaluates the structured type.

1. **`Exact(s)`** matches exactly one segment equal to `s` (byte-for-byte after UTF-8 NFC normalization is applied identically to both sides — see note 7).
2. **`AnyOne` (`*`)** matches exactly one segment, any value.
3. **`AnyRun` (`**`)** matches zero or more consecutive segments. To keep matching unambiguous and linear-time, **at most one `AnyRun` is allowed per pattern**, and it is greedy with a single fixed backtrack point; patterns with more than one `AnyRun` are rejected at scope-registration time (`MalformedPattern`). This makes matching `O(n)` and total — no regex-style catastrophic backtracking (a deliberate DoS-avoidance choice; ddia-systems lens).
4. A pattern with **no `AnyRun`** matches **iff** it has the same length as the address and every element matches positionally.
5. A pattern **with one `AnyRun`** matches **iff** the fixed prefix elements (before the `AnyRun`) match the leading segments positionally and the fixed suffix elements (after the `AnyRun`) match the trailing segments positionally, with `AnyRun` absorbing the (possibly empty) middle.
6. **`AddressScope::Kind { namespace, kind }`** desugars to a check, not a positional pattern: the address matches iff `address.segments[1] == kind` and (if `namespace` is `Some(ns)`) `address.segments[0] == ns`. **`kind:<k>` is resolved structurally via `segment[1]`** — the same fact the `instance-of` edge records — so `kind:loswf.pr` matches every address whose kind segment is `pr` in namespace `loswf`. On the *read side*, `EndpointMatch::Kind(k)` (edge queries) is defined identically and additionally resolvable by walking `instance-of` edges to the kind-entity (the two definitions are required to agree; acceptance criterion 4). Core never enumerates known kinds — it tests the segment/edge, never a registry.
7. **Normalization.** Both the pattern's `Exact` segments and the address segments are compared after Unicode **NFC** normalization (and nothing else — no case-folding, no trimming), so visually-identical-but-differently-encoded segments match consistently and matching stays deterministic across platforms. NFC is applied at *ingestion* to addresses (so the stored form is canonical) and at *scope parse* to patterns.
8. **No in-segment globbing in v1.** `Exact("foo")` does not match `"foobar"`; there is no `foo*` element. Intra-segment prefix matching is deferred (open question) to avoid the injection/ambiguity surface.

```jsonc
// Worked matches (textual pattern on the left, address on the right).
"loswf / issue / 4217"        matches  ["loswf","issue","4217"]            // exact
"loswf / issue / *"           matches  ["loswf","issue","4217"]            // single wildcard
"loswf / issue / *"           NO-match ["loswf","issue","4217","comment"]  // length differs
"loswf / **"                  matches  ["loswf","issue","4217","comment"]  // run absorbs middle
"loswf / **"                  matches  ["loswf","factory","x"]             // ns-scoped, any depth
"** / agent / **"             matches  ["khaos","agent","reviewer","r-1"]  // prefix+suffix run
"kind:loswf.pr"               matches  ["loswf","pr","991"]                // kind via segment[1]
"namespace:loswf"             matches  ["loswf", ...anything ]             // == "loswf / **"
"*"                           NO-match ["loswf","issue"]                   // length differs (2≠1)
```

### Who consumes it

- **Action/capability spec.** A capability's `target` and any `entityGlob` caveat are an `AddressScope`; the boundary check is `scope_matches(cap.target_scope, resolved_address)`. The action spec references this grammar and defines no matching of its own.
- **Privacy/credential spec.** Namespace-scoped grants and `entityGlob` read caveats are `AddressScope::Namespace` / `AddressScope::Pattern`; a read view is filtered by `matches`. The privacy spec references this grammar.
- **This spec (read side).** `EdgeQuery`'s `EndpointMatch` and `RelationMatch` use `AddressScope`/`AddressPattern` for endpoint predicates and `kind:<k>` resolution.

## Resolution — the ingestion-time `resolve` step

The envelope spec's normative ingestion order names a `resolve(address→handle)` step between `authorize` and `dedupe`. This spec defines it. (Addresses are NFC-normalized at this boundary before lookup/mint, per matching note 7.)

```rust
/// Owned by this spec; called by the daemon at ingestion (write side), capability already checked.
/// Pure given the current resolution view, EXCEPT the create branch, which mints a handle
/// (stamped into RUNTIME at the boundary, so downstream replay is deterministic).
pub fn resolve(view: &IdentityView, addr: &EntityAddress, policy: ResolvePolicy)
    -> Result<Resolved, ResolveError>;

pub struct Resolved {
    pub handle: EntityHandle,
    pub created: bool,          // true iff this call minted a new handle (emits entity.registered)
    pub followed_redirect: bool,// true iff addr was a stale alias resolved via the alias history
}

pub enum ResolvePolicy {
    CreateOnMissing,   // default for submit: an event to an unknown address registers it
    RequireExisting,   // for edges/queries: a missing address is an error
}

pub enum ResolveError { UnknownEntity, AmbiguousAddress, MalformedAddress }
```

- **Known address →** pure lookup returning the live handle.
- **Unknown address under `CreateOnMissing` →** the daemon **mints a new `entityHandle`**, records an `entity.registered` fact (carrying the proposed `kind` from `segment[1]`), and returns `{created: true}`. This is the *create-on-first-reference* path that makes "an event to a new entity just works" true while keeping creation a logged fact. (`UnknownEntity` from the envelope spec corresponds to `RequireExisting` failing.)
- **Stale address (after rename) →** the alias history maps the old address to the still-live handle; resolution follows the redirect and returns `{followed_redirect: true}`. (Whether stale resolution should transparently succeed or hard-fail with a "moved to" hint is an open question; v1 leans transparent-with-audit.)
- `sequence` is **always** counted per resolved `handle`, never per address — this is the mechanism by which `sequence` survives rename (envelope invariant 4).

### Rename and re-home

`entity.renamed`, `entity.rehomed`, `entity.deleted`, `edge.added`, and `edge.removed` are all **runtime-meta event types from ADR-0001's enumerated allowlist** — core-reserved, not domain types.

```jsonc
// entity.renamed — re-alias: the handle is unchanged; the address moves.
// Emitted to the SAME handle, so it is just another fact in that entity's stream.
{ "type": "entity.renamed",
  "from": ["loswf","issue","4217"],
  "to":   ["loswf","issue","4217-archived"] }

// entity.rehomed — re-parent within the graph (a child-of edge change is the usual cause);
// recorded for audit. The handle and sequence are unchanged.
{ "type": "entity.rehomed",
  "address": ["khaos","workflow","run-2291"],
  "note":    "moved under project kspd-9 (see edge facts)" }
```

Rename appends to an **append-only alias history** keyed by handle, so old addresses can redirect and provenance referencing the old name stays resolvable. The handle never changes; nothing is rewritten (envelope: the log is never rewritten).

## Kind as declarative metadata, not a class

An entity's **kind** answers "what sort of thing is this" — but it is **data**, not a type the runtime branches on or inherits from.

- Kind is declared in the bundle (the kind schema names accepted event types, reducer bindings, rollup rules, default relation cascade policies, renderer hints — the bundle spec owns the full schema). It is the `service.name`-within-`service.namespace` of the OTel mapping.
- At runtime, kind is surfaced two ways, both derived:
  1. As `segment[1]` of the address (the producer-facing name), and
  2. As a field on the core, domain-neutral **`ambisphere.identity`** component (the read-facing fact), produced by a **core reducer** (single-writer, per the reducer spec) from the `entity.registered` fact. `ambisphere.identity` is a member of the closed core-component list.
- An entity's membership in a kind is *also* expressible as an **`instance-of`** edge from the entity to a **kind-entity** (a registered entity whose kind is the meta-kind `ambisphere.kind`). This is the Flecs `IsA` analogue and lets the graph answer "all entities of kind X" as an ordinary wildcard edge query, and is the second, edge-based resolution path for `kind:<k>` (matching note 6). Core never branches on the kind string in either path.

```jsonc
// ambisphere.identity — a CORE, domain-neutral component (member of the closed core-component
// list: attention, identity, edges, lifecycle, approvals). Fields fixed here.
// Produced by a core reducer from entity.registered / entity.renamed facts. kind == "factual".
{
  "component_type": "ambisphere.identity",
  "schemaVersion": 1,
  "kind": "factual",
  "data": {
    "handle":     "01J8...ULID",                 // the immutable id
    "address":    ["loswf","issue","4217"],      // the CURRENT alias (segment list, NFC-normalized)
    "entityKind": "issue",                        // == address[1]; opaque to core, declared by bundle
    "namespace":  "loswf",                        // == address[0]; the trust boundary
    "registeredAt":"2026-06-10T18:22:05.913Z",   // ingestTime of entity.registered (stamped)
    "aliasHistory":[                              // append-only; for redirects + provenance
      { "address": ["loswf","issue","4217"], "since": "2026-06-10T18:22:05.913Z" }
    ],
    "provenance": { "lastEventId": "01J8...", "lastEventTime": "2026-06-10T18:22:05.913Z", "kind": "factual" }
  }
}
```

Core never switches on `entityKind` or `namespace`. They are opaque strings for adapters and renderers, tested only by the matching grammar (which itself never enumerates kinds). (ADR-0001 inv. 8; lint-enforced per the guidance: no `khaos.*`/`loswf.*` in core.)

## The graph — typed directed edges

The graph is a set of **typed, directed edges** between handles. An edge is `(relationType, source, target)` plus metadata, generalizing Flecs's `(relation, target)` pair to a property graph (DDIA's "graph model excels at highly interconnected data with recursive traversals").

```rust
/// A directed, typed edge. Identified by its own ULID so it is addressable and carries metadata.
/// Source and target are HANDLES (immutable) — edges survive rename/re-home of either endpoint.
pub struct Edge {
    pub edge_id: Ulid,            // minted at ingestion; lets an edge be referenced/removed precisely
    pub relation_type: RelationType,  // built-in (ChildOf|InstanceOf) or bundle-defined
    pub source: EntityHandle,
    pub target: EntityHandle,
    pub metadata: EdgeMetadata,   // cascade policy + bundle-opaque attributes
    pub provenance: Provenance,   // PROV-shaped, per the reducer spec; kind == factual
}

pub enum RelationType {
    ChildOf,            // BUILT-IN. Containment/hierarchy. Feeds rollups + the summary index.
    InstanceOf,         // BUILT-IN. Kind membership (Flecs IsA analogue). source is-a target(kind).
    Defined(String),    // bundle-defined (e.g. "loswf:blocks"). Core never branches on the string.
}

pub struct EdgeMetadata {
    pub on_source_delete: CleanupAction,  // what happens to THIS edge / its target when source dies
    pub on_target_delete: CleanupAction,
    pub attributes: CanonicalValue,       // bundle-opaque; core never inspects internals
}

pub enum CleanupAction { Cascade, Orphan, Restrict, Tombstone }
```

### Exactly two built-in relation types

- **`ChildOf`** — directed `source ChildOf target` means "source is contained by / a child of target." This is the relation rollups aggregate over and the relation the attention bus's `child-of` rollup (attention spec) traverses. v1 enforces **single-parent** `ChildOf` per entity (at most one live `ChildOf` edge out of any source) so rollups are an unambiguous tree. (Multi-parent is an open question.)
- **`InstanceOf`** — directed `source InstanceOf target` means "source is an instance of the kind-entity target." This is membership, **not** subtyping: it confers no behavior, no field inheritance, nothing core acts on. It exists so "all entities of kind X" is a wildcard edge query and so `kind:<k>` has an edge-based resolution path.

**Everything else is bundle-defined** (`loswf:blocks`, `loswf:depends-on`, `khaos:appears-in`, `khaos:derived-from`, …). Core stores and queries them uniformly and never branches on the `relation_type` string (ADR-0001 inv. 8).

### Edges are facts, the edge set is derived

There is **no `addEdge`/`removeEdge` direct-write API**. An edge changes only by a capability-gated fact event (a runtime-meta event type, ADR-0001 allowlist) submitted through the envelope's `submit`:

```jsonc
// edge.added — a fact. The edgeId is minted at ingestion (stamped, deterministic on replay).
// Addressed to the SOURCE entity (so it lands in that entity's per-entity stream).
{
  "type":   "edge.added",
  "entity": ["loswf","issue","4217"],            // source address (resolved to source handle)
  "data": {
    "relationType": "child-of",
    "target":       ["loswf","factory","ambisphere/runtime"],  // resolved to target handle
    "metadata": { "onSourceDelete":"orphan", "onTargetDelete":"cascade", "attributes": {} }
  }
}

// edge.removed — a fact referencing the precise edgeId (or the relation+target tuple).
{ "type": "edge.removed", "entity": ["loswf","issue","4217"],
  "data": { "edgeId": "01J8...EDGE" } }
```

A **core domain-neutral reducer** (single-writer, per the reducer spec) folds `edge.added`/`edge.removed` into a core `ambisphere.edges` component on the source entity — the adjacency list, a member of the closed core-component list — and the daemon mirrors edges into the always-resident summary index (below). The edge set is therefore a **derived, rebuildable projection**: drop it and replay the log to reconstruct it exactly (DDIA stream-table duality; ClickHouse rollup rebuildability). Edges point at **handles**, so they are unaffected by rename/re-home of either endpoint.

### Edge identity and addressing decision

An edge is **addressed to its source** (so it is part of that entity's per-entity stream and ordered by that entity's `sequence`). It gets its own `edgeId` ULID so it can be removed precisely and so its metadata/provenance are addressable. In v1 an edge does **not** carry its own component state or attention (it is not a full entity); promoting an edge to a first-class entity is deferred (open question).

## Read side — edge queries, traversals, rollups

All graph reads are on the read side of the seam, pure and deterministic given `(view, as_of)`, and **separately capability-gated** for read (a read capability may yield a redacted/coarsened view, scoped by the canonical matching grammar — ADR-0001 inv. 5, privacy spec).

### Wildcard / predicate edge queries

```rust
/// Read-only. Pure/deterministic given (view, as_of). Separately read-gated.
pub fn query_edges(view: &GraphView, q: EdgeQuery) -> Vec<Edge>;

pub struct EdgeQuery {
    pub as_of: Timestamp,                 // as-of-transaction-time (envelope/reducer v1: txn time only)
    pub relation_type: Option<RelationMatch>, // None == WILDCARD over all relation types
    pub source: Option<EndpointMatch>,    // None == wildcard
    pub target: Option<EndpointMatch>,    // None == wildcard
    pub limit: usize,
    pub read_capability: ReadCapRef,
}

pub enum RelationMatch { Exact(RelationType), Any }   // "Any" is the Flecs Wildcard analogue

/// Endpoint predicates reuse the canonical matching grammar (§ matching grammar).
pub enum EndpointMatch {
    Handle(EntityHandle),     // a specific entity
    Scope(AddressScope),      // Pattern / Kind / Namespace — evaluated by `matches`
    Any,                      // wildcard
}
```

`EndpointMatch::Scope(AddressScope::Kind{..})` is the read-side `kind:<k>` predicate; it MUST resolve identically to the write-side capability check (matching note 6, acceptance criterion 4). This is the narrow, typed analogue of Flecs's wildcard pair queries — enough to answer "all children of X" (`source=Any, target=Handle(X), relation=ChildOf`), "X's parent" (`source=Handle(X), relation=ChildOf`), "all entities of kind K" (`relation=InstanceOf, target=Scope(Kind{kind:K})`), and "everything that `loswf:blocks` issue 4217" — **without** a general graph DSL.

### Traversals

```rust
pub fn neighbors(view: &GraphView, of: EntityHandle, rel: RelationMatch, dir: Direction) -> Vec<EntityHandle>;
pub fn ancestors(view: &GraphView, of: EntityHandle, rel: RelationType, max_depth: u32) -> Vec<EntityHandle>;
pub fn descendants(view: &GraphView, of: EntityHandle, rel: RelationType, max_depth: u32) -> Vec<EntityHandle>;
pub enum Direction { Outgoing, Incoming }
```

`ancestors`/`descendants` over `ChildOf` are how a renderer drills down from a factory entity to its issues/PRs/agents (RFP §9). Traversal is bounded by `max_depth` (cycle-safe; `ChildOf` single-parent makes it a tree, but the guard is mandatory for bundle-defined relations that may cycle).

### Rollups — derived read-model state over `child-of`

A **rollup** is a summary an ancestor carries about its `ChildOf` descendants (e.g. a factory entity's "3 children blocked, 1 awaiting human, 12 healthy"). Per the carried guidance and the attention spec, rollups are **derived read-model state, never authored**:

- Rollup rules are **declared per kind** by the bundle (which child facets aggregate, and how — count, max, weighted-sum). Core ships the *mechanism*, zero rules.
- Rollups are maintained **incrementally, bottom-up** as child component values change (ClickHouse-style chained materialized view), and are **fully rebuildable** by recomputing over the log.
- **Materialized rollup caches and the resident index hold only decay-invariant values.** A rollup over an attention facet caches the contributing raw scalars, decay params, `anchorTime`, and `state` — **never a computed `rung` or `score`**. The rung/score is computed at query time from those inputs plus `as_of`, so a rollup queried at two different `as_of` values yields two correct results (the bug a cached `rung` would introduce). This is normative and mirrors the attention spec's index rule and the daemon spec's rollup-cache rule.
- The **attention rollup specifically** traverses `ChildOf` with the `max` reducer over the always-resident summary index (attention spec contract item 8); this spec owns that index and the `ChildOf` relation it walks. Attention computes *its* rung/score at query time; this spec guarantees the index supplies the decay-invariant inputs and the traversal it needs.

```rust
/// The mechanism, not a rule. A bundle registers a RollupRule per (kind, source_facet).
/// Pure/deterministic; recomputing over the log yields the identical rollup (rebuildability).
/// op may aggregate raw scalars but MUST NOT cache an as_of-dependent value (rung/score).
pub struct RollupRule {
    pub over_relation: RelationType,   // v1 default + attention case: ChildOf
    pub source_facet: ComponentType,   // which child component to aggregate
    pub op: RollupOp,                  // Count | Max | Min | Sum | WeightedSum | BundleDefined(String)
    pub into_facet: ComponentType,     // the derived rollup component on the ancestor
}
pub enum RollupOp { Count, Max, Min, Sum, WeightedSum, BundleDefined(String) }
```

### The always-resident summary index (decay-invariant only)

To do cross-entity rollups and graph queries **without waking cold entities** (the key move from the daemon guidance and the tension the attention bus must resolve), the daemon maintains a small, always-resident index, fed by identity and edge facts as they commit. **It caches only decay-invariant values; it MUST NOT cache a `rung` or `score`** — those are always computed at query time from the cached inputs plus `as_of`. This is co-normative with the attention spec (whose index minimally holds `(handle, kind, parent, scalars, decay, state, ceiling, lastEventTime)`), the daemon spec (materialized rollup cache), and the persona spec (which receives an `as_of`-computed rung, never a mirrored cached one).

```jsonc
// Always-resident per entity (handle-keyed). Bounded, cheap, rebuildable from the log.
// Lets the attention bus + dashboards roll up and query the graph without warming entities.
// DECAY-INVARIANT ONLY — no cached rung/score; the bus computes those at query time.
{
  "handle":        "01J8...ULID",
  "address":       ["loswf","issue","4217"],   // current alias (for display/redirect/matching)
  "entityKind":    "issue",
  "namespace":     "loswf",
  "parent":        "01J8...FACTORY",           // the single ChildOf target (null if root)
  "childCount":    0,
  // Attention INPUTS the bus needs to compute rung/score at query time (shapes owned by attention):
  "attentionInputs": {
    "scalars":     { "urgency": 0.0, "importance": 0.0, "actionability": 0.0 },
    "decay":       { "halfLifeMs": 0, "anchorTime": "2026-06-10T18:22:05.913Z" },
    "state":       "active",      // active | awaiting-human | acknowledged | resolved | ...
    "ceiling":     "nudge",       // max rung this entity may ever reach (decay-invariant)
    "lastEventTime":"2026-06-10T18:22:05.913Z"
  }
}
```

The exact contents and size bound of this index are co-designed with the daemon spec (storage), the attention spec (consumer/shape owner of `attentionInputs`), and the persona spec; the *invariant* — decay-invariant inputs only, no cached `rung`/`score` — is fixed here and recorded as resolved across all four specs. Remaining sizing is an open question.

## Cascade / cleanup as relation metadata

What happens to the graph when an entity is removed is **per-relation metadata**, not built-in behavior (the explicit Flecs lesson: cleanup for `ChildOf` and `Likes` differ, so it is specified per relation).

| `CleanupAction` | Meaning when the referenced endpoint is deleted |
|---|---|
| `Cascade` | Delete the dependent endpoint too (the classic `ChildOf` default: deleting a parent deletes children — *if the bundle declares it*). Emits `entity.deleted` facts (runtime-meta, ADR allowlist) for the cascade set. |
| `Orphan` | Remove the edge only; leave the other endpoint alive but unparented. |
| `Restrict` | **Refuse** the deletion while the edge exists; the delete fact is rejected at the write boundary (capability/precondition failure), never mid-reduction. |
| `Tombstone` | Remove the edge and leave a redirect/he-was-here marker on the endpoint (retention governed by the daemon's compaction policy — open question). |

- **Defaults are bundle-declared per kind**, not hardcoded in core. Core's *only* opinion is that `ChildOf` is the relation rollups traverse; it does **not** force `Cascade` on `ChildOf`. (A factory deleting itself should arguably orphan its issues, not delete them — that is the bundle's call.)
- **Referential integrity is enforced on the handle**: an edge may not point at a handle that was never registered; `Restrict` blocks a delete that would dangle a referenced edge; deletion is itself a logged fact (`entity.deleted`), so the cleanup set is auditable and replayable.

## Worked example (adapter layer only — vendor concepts live here, never in core)

```jsonc
// A LOSWFX factory and one of its issues. ALL vendor strings are adapter-supplied.
// 1. First reference to the factory registers it (create-on-first-reference).
{ "type":"factory.observed", "entity":["loswf","factory","ambisphere/runtime"], "data":{...} }
//    -> daemon mints handle 01J8...FACTORY, emits entity.registered(kind="factory")

// 2. An issue event registers the issue.
{ "type":"issue.planned", "entity":["loswf","issue","4217"], "data":{...} }
//    -> daemon mints 01J8...ISSUE, emits entity.registered(kind="issue")

// 3. Make the issue a child of the factory (a capability-gated fact).
{ "type":"edge.added", "entity":["loswf","issue","4217"],
  "data":{ "relationType":"child-of",
           "target":["loswf","factory","ambisphere/runtime"],
           "metadata":{ "onTargetDelete":"orphan", "onSourceDelete":"orphan" } } }

// 4. A bundle-defined relation: this issue blocks another. Core stores it uniformly.
{ "type":"edge.added", "entity":["loswf","issue","4217"],
  "data":{ "relationType":"loswf:blocks", "target":["loswf","issue","4300"] } }

// CAPABILITY (action spec, using THIS spec's grammar): a token scoped to
//   target: "namespace:loswf"   (== AddressScope::Namespace("loswf") == "loswf / **")
// authorizes the edge writes above (both endpoints in loswf). A token scoped to
//   target: "kind:loswf.issue"  authorizes writes only to issue-kind entities.

// READ SIDE — the attention bus rolls up the factory over child-of using the summary index,
// computing rung/score at query time from the cached decay-invariant inputs;
// a dashboard runs query_edges{ source:Any, target:Handle(FACTORY), relation:ChildOf } to drill down,
// or query_edges{ relation:InstanceOf, target:Scope(Kind{kind:"issue"}) } for "all issues".
```

Core sees `child-of`, `loswf:blocks`, `factory`, `issue` as opaque strings. It branches on none of them, and tests them only through the matching grammar (which never enumerates kinds).

## Acceptance criteria

1. **Handle immutability & non-reuse.** Across rename, re-home, and entity deletion+re-registration of the *same address*, the original handle is never reassigned to a different entity; a freshly registered address gets a fresh handle. (Property test over random rename/delete/register sequences.)
2. **Resolution determinism.** `resolve` over a fixed identity view is a pure function except the create branch; replaying the log yields byte-identical handle assignments because handles are stamped at ingestion. (Replay-equality test.)
3. **Injection safety.** No constructed address can cause a segment's contents to be reinterpreted as multiple segments, to escape its namespace, or to be interpreted as a wildcard; a segment whose value is `"*"`, `"**"`, contains delimiters, `..`, or NULs is either rejected (NUL) or treated as one opaque literal segment. (Fuzz test over adversarial segment values, including literal wildcard tokens.)
4. **Matching grammar determinism & cross-side agreement.** `matches(pattern, address)` is a pure total function with at most one `AnyRun` (multi-`AnyRun` patterns rejected); the read-side `EndpointMatch::Scope(Kind{..})` and the write-side capability `AddressScope::Kind{..}` resolve the *same* set of addresses for any `kind:<k>`. Matching is `O(n)` (no catastrophic backtracking). (Property + fuzz test, and an action/privacy/identity cross-spec conformance vector.)
5. **`sequence` survives rename.** After `entity.renamed`, subsequent events to the new address continue the same per-handle `sequence` with no gap or reset. (Conformance test against the envelope contract.)
6. **Edge-as-derived.** There is no API that mutates the edge set except `submit`; dropping the `ambisphere.edges` projection and the summary index and replaying the log reconstructs both exactly. (Rebuild-equality test.)
7. **Exactly two built-in relations; vendor neutrality; closed lists.** Core source contains no relation type beyond `ChildOf`/`InstanceOf`, no domain kind, no domain event type, no core component outside the closed list (`attention`, `identity`, `edges`, `lifecycle`, `approvals`), and no branch on a kind/namespace/bundle-relation string. (Lint + grep gate: no `khaos.*`/`loswf.*`, no kind switch in core, no component_type outside the closed list.)
8. **Decay-invariant index.** Neither the always-resident summary index nor any materialized rollup cache stores a `rung` or `score`; both store only decay-invariant inputs, and ranking/rollup computed at two different `as_of` values yields two correct results from the same cached inputs. (Index-shape lint + a two-`as_of` equivalence test mirroring the attention spec's "identical rankings for identical (view, as_of)".)
9. **Rollup ≡ recompute.** An incrementally-maintained rollup equals the rollup recomputed from scratch over the same log prefix. (Equivalence test, mirroring the snapshot ≡ replay test of the reducer spec.)
10. **Cleanup is metadata-driven.** Deleting an entity applies exactly the per-relation `CleanupAction`s declared in metadata; `Restrict` rejects the delete at the write boundary (never mid-reduction); the cascade set is a set of logged `entity.deleted` facts. (Behavioral test per `CleanupAction`.)
11. **Read/write separation.** Edge creation requires a write capability (target an `AddressScope`); `query_edges`/traversals require a separate read capability and never mutate state; a read-only principal cannot create or remove an edge. (Capability conformance test.)

## Open questions

- **Cross-spec amendments this spec depends on.** This spec *references* (a) ADR-0001's amended invariant 8 distinguishing domain from runtime-meta event types with an enumerated allowlist, and (b) ADR-0001's / the reducer spec's closed core-component enumeration. Those amendments must land in ADR-0001 and the reducer spec for the references to resolve; if either is not adopted, this spec falls back to declaring its own runtime-meta exception inline. (Tracked jointly; this spec is a consumer, not the owner, of those two edits.)
- **ADR-0001 status.** Every follow-on spec, this one included, cites ADR-0001 as ratified with numbered invariants. ADR-0001's own status must be resolved to a single value (Accepted, with a canonical numbered invariant list, or Provisional with all dependents marked "conforms to provisional ADR"). This blocks implementation-readiness suite-wide; recorded here because this spec's conformance table cites the numbered list.
- **Intra-segment globbing.** v1 matches segments whole (`Exact("foo")` ≠ `"foobar"`; no `foo*` element). Whether bundles/operators need intra-segment prefix or character globbing (and the injection/ambiguity cost it reintroduces) is deferred.
- **Multiple `AnyRun` / richer pattern algebra.** v1 caps patterns at one `AnyRun` for linear-time, total matching. Whether richer patterns (alternation, multiple runs) are ever needed for capability/read scopes is open; the cost is matching complexity and DoS surface.
- **`kind:<k>` resolution path precedence.** `kind:<k>` resolves both via `segment[1]` and via `instance-of` edges, required to agree. If an adapter sets `segment[1]` inconsistently with the `instance-of` edge (a bug), which wins, and should the daemon flag the divergence? Leaning: `segment[1]` is authoritative for matching, `instance-of` for graph queries, with a lint that warns on divergence.
- **Identity rebinding on rename/re-home.** v1 retains an append-only alias history with redirects, but should a stale address resolve transparently (follow the redirect) or hard-fail with a "moved to" hint? Leaning transparent-with-audit; the daemon spec must confirm the resolution-cache invalidation cost.
- **Multi-parent containment.** v1 enforces single-parent `ChildOf` for deterministic rollups. When multi-parent is genuinely needed (an asset shared by two projects), is the answer a *bundle-defined* relation (e.g. `member-of`) that does **not** feed the rollup index, or a defined dedup/aggregation rule for multi-parent rollups? Leaning the former.
- **Cross-namespace edge authority.** Must creating an edge whose source and target live in different namespaces be gated by a capability over **both** subgraphs (each expressed as an `AddressScope`), or only the source? This is the trust boundary the privacy/credential spec owns; precedence must be specced jointly, but both specs now use this spec's grammar to express the scopes.
- **Summary-index sizing.** The *invariant* (decay-invariant inputs only, no cached rung/score) is fixed and resolved across the attention/daemon/persona specs. The exact field set and size cap remain co-design with the daemon (storage) and attention (consumer); needs a `ddia-systems` spike at realistic Khaos/LOSWF edge fan-out.
- **Edge-as-entity.** Edges get a ULID (so they are addressable/removable) but in v1 carry no component state or attention. Promoting an edge to a first-class entity (so an edge can itself be the subject of events) is deferred.
- **local-id uniqueness scope.** v1 fixes uniqueness at `(namespace, kind, full-segment-path)`. Whether a shorter `(namespace, kind, local-id)` scope should also be enforceable for flat kinds, or whether parent-scoped uniqueness is ever wanted, is left to bundle declaration with a validated default.
- **Tombstone & alias-history retention.** `Tombstone` and `aliasHistory` rows accumulate; their retention interacts with the log-compaction/retention policy owned by the daemon spec.
