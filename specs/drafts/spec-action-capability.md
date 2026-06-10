# Action and capability manifest

**Status:** draft · **Scope:** the write-side **action** primitive and its two separated layers — (A) a declarative, MCP-tool-shaped `ActionManifest` (id, in/out schemas, behavioural flags, `requiredCapabilities`, `preconditions`, `resultEvents`) whose flags are **UX/attention hints only**, and (B) an **object-capability enforcement model** (unforgeable, attenuable, macaroon-caveated tokens; POLA; revocation) in which the capability check at the write boundary **is** the security boundary — plus the `invoke()` control-plane call, the async **`approval-requested`** durable-state mechanism for `confirmRequired`/`destructive` actions, precondition evaluation, and how an action's results re-enter the log as fact events. This revision additionally (a) pins the **canonical `locality` enum** and declares this spec its owner, (b) makes the **v1 capability token wire format, HMAC construction, and verify algorithm normative**, (c) defines **one canonical closed predicate language** for preconditions (and the shared declarative-predicate grammar bundle/persona must serialize), and (d) fixes the **approval-gate name and its attention-facet projection** · **Companion to:** `specs/VISION.md`, `specs/SRS.md`, `RFP.md` (§ "Launcher and action capabilities", "Human approval gates", "Control surface", "Local-first privacy and credential boundaries") · **Sequenced:** eighth among the follow-on specs (after the attention-bus, reducer/state-component, event-envelope, entity-identity, and daemon specs; before the privacy/credential, adapter, persona, and bundle specs) per ADR-0001 and issue #4 · **Conforms to:** ADR-0001 (foundational paradigm + directionality invariant; this revision **depends on the amended invariant 8**, see § conformance); the attention-routing spec (this spec **owns** the `approval-requested` gate the bus may rank, and **fixes its projection** onto the attention facet — attention inv. 6); the reducer/state-component spec (an action's results become `ReducibleEvent`s; preconditions read its component view; the **shared predicate grammar** resolves against its facet field types); the semantic-event-envelope spec (an action's results re-enter via `submit` carrying `correlation.causedBy`; commands never land on the log); the entity-identity spec (**owns** the canonical target/glob/kind/namespace matching grammar this spec consumes); the daemon-architecture spec (the control channel carries no ambient write authority; `invoke` is a control-plane primitive whose effects flow through `submit`) · **Sibling notes:** `specs/drafts/runtime-paradigm-and-specs-guidance.md`, `specs/drafts/actor-model-prior-art.md`, `specs/drafts/persona-prior-art.md`, `specs/drafts/implementation-language-guidance.md`

This spec defines how an ambient entity exposes **things a human (or an authorized adapter) can do**, and how the runtime decides whether a given doer is *allowed* to do them. It is the launcher/control-surface half of the vendor requirements (issue #5 §6): "open the PR", "rerun CI where safe", "approve the phase", "open the project", "retry the analysis". The hard requirement is that none of these may become an ambient-authority back door into the log.

The whole spec turns on one separation, repeated everywhere below:

> The **manifest** describes an action. The **capability** authorizes it. The manifest's flags are *hints* for UX and attention; the capability check at the write boundary is the *security boundary*. They are never conflated, and a flag never substitutes for a check.

This is the same stance the Model Context Protocol took with its tool annotations — `readOnlyHint`/`destructiveHint`/`idempotentHint` are "informational signals, not enforceable guarantees… a malicious or buggy server could mark a destructive tool as `readOnlyHint: true` to bypass confirmation dialogs" (MCP blog, *Tool Annotations as Risk Vocabulary*, 2026-03-16; modelcontextprotocol.io). We adopt the declarative shape and adopt the warning as a structural rule.

## Goals

- Define the **`ActionManifest`** (layer A): a declarative, bundle-owned description of an action — `actionId`, `inputSchema`/`outputSchema`, behavioural flags (`confirmRequired`/`destructive`/`idempotent`/`locality`), `requiredCapabilities`, `preconditions`, and `resultEvents`. Borrowed from MCP tool definitions.
- Define the **capability model** (layer B): authority as a possessed, unforgeable, attenuable token with macaroon-style caveats; POLA; lineage; revocation — **with a normative v1 wire format, HMAC construction, and verify algorithm** (no longer conceptual). Borrowed from the object-capability lineage and macaroons.
- Define **`invoke(cap, ActionRequest) -> ActionOutcome`**: the only way to run an action, a **control-plane** primitive (not a log write, not an event). The action's *results* re-enter as fact events via the envelope spec's `submit`.
- Define the **async human-approval gate**: `confirmRequired`/`destructive` actions emit durable **`approval-requested`** state (a fact event → reducer → component), never a synchronous daemon block. Approval/denial is itself a capability-gated action. **Fix the canonical name of this condition and its projection onto the attention facet.**
- Define **precondition evaluation** as a pure predicate over the read-side component view at an explicit `as_of`, authoritative at the daemon and advisory to renderers — **expressed in one canonical closed predicate language** shared across this spec, the bundle `where` clauses, and the persona state-matchers.
- Keep **core domain-empty**: core ships zero action manifests, zero verbs, zero capability grants, zero domain event types. All *domain* actions and event types live in the examples/adapter layer; the only core-owned event types are the enumerated **runtime-meta** set (see § conformance).

## Non-goals

- **Not** an identity provider, OAuth server, or login system. Authority is *possessed* (a held capability), not *claimed* (an authenticated identity that maps to a role). v1 MAY ship a single-principal keychain, but there is no account/role registry. (Reject: RBAC-with-accounts as the model — runtime guidance contradiction 2; `actor-model-prior-art.md` "RBAC permission hooks as the security model".)
- **Not** a remote-action transport/RPC protocol. `locality: remote-write` actions are *executed by an adapter*; this spec defines the authorization and the result-fact re-entry, not the wire to GitHub/CI. (Reject: folding adapter transport into core.)
- **Not** AI/LLM-driven actions by default. A chat surface is *one optional caller* that must hold a capability like any other; no model output auto-invokes. (Reject: LLM-as-primary-caller — MCP's assumption we explicitly drop.)
- **Not** the confirmation UI. This spec emits `approval-requested` durable state and a discharge mechanism; *how* a surface renders the prompt is the renderer's concern. (Reject: a built-in modal.)
- **Not** a synchronous block. `confirmRequired` never pauses the daemon, never blocks a reducer, never holds a `submit`. (Reject: synchronous approval — runtime guidance contradiction 3; attention spec § "blocking is a prominence, not a gate".)
- **Not** a place for vendor actions, verbs, capability grants, or domain event types. No `khaos.*`/`loswf.*` action, scope, or event type appears in core. (Reject: vendor leakage — ADR-0001 inv. 8.)
- **Not** a general expression/rules engine. Preconditions and every other declarative predicate in the suite use a **closed, total op set** over component fields — never a string expression to parse. (Reject: a Turing-complete `where` grammar — VISION "no personality/rules engine" non-goal.)
- **Not** distributed multi-node action consensus. Single local daemon. (Reject: cross-node action coordination.)

## Prior art (adopt / reject, citations kept visible)

- **MCP tool definitions + annotations** (modelcontextprotocol.io; *Tool Annotations as Risk Vocabulary*, MCP blog 2026-03-16). **Adopt:** the declarative tool shape — `id`, `title`, `description`, JSON-Schema input/output; the behavioural-hint vocabulary `readOnlyHint`/`destructiveHint`/`idempotentHint`/`openWorldHint` (mapped here to `destructive`/`idempotent`/`locality`); and **MCP's own stance that annotations are untrusted hints for UX, not the security boundary** ("keep your actual safety guarantees in deterministic controls"). **Reject:** the model-controlled JSON-RPC-over-HTTP transport, and the assumption the LLM is the primary caller.
- **Object-capability model** — Dennis & Van Horn 1966 ("Programming Semantics for Multiprogrammed Computations"); KeyKOS/EROS/seL4; the E language; Spritely Goblins (`actor-model-prior-art.md`). **Adopt:** authority is an **unforgeable, attenuable reference** that *is* the permission; **POLA** (renderers get zero action authority by default); confused-deputy immunity (the *holder* of the capability acts, the daemon never re-derives authority from ambient identity). **Reject:** full ocap-language lock-in, OCapN networking, and ocap-all-the-way-down inside reducers (reducers are pure and authority-free; the gate is at `invoke`/`submit`).
- **Macaroons** — Birgisson, Politz, Erlingsson, Taly, Vrable, Lentczner, "Macaroons: Cookies with Contextual Caveats for Decentralized Authorization in the Cloud", NDSS 2014 (theory.stanford.edu/~ataly/Papers/macaroons.pdf); `libmacaroons` (github.com/rescrv/libmacaroons). **Adopt:** **caveat-based attenuation** ("really easy to add a caveat, impossible to remove one" via an **HMAC chain** binding each caveat to all prior ones); offline/local verification; **delegation by minting a weaker token**; first-party caveats (predicates the daemon verifies at check time). This revision makes the **HMAC chain construction normative** (see § token format). **Reject:** third-party-caveat network round-trips as a *requirement* — they are specced as the conceptual shape for genuinely remote human-approval discharge but are **opt-in**, not v1; **v1 verifies first-party caveats only (normative).**
- **RivetKit actions + permission hooks** (`actor-model-prior-art.md`; rivet.dev/docs). **Adopt:** actions as **named, schema-typed, write-side operations** and the inspector/`list-actions` pattern (a surface can enumerate an entity's affordances). **Reject:** its RBAC `onBeforeConnect`/`canPublish` hooks as the capability *model* — RivetKit is RBAC-style, not ocap (the prior-art note's explicit refinement of issue #4).
- **Clean Architecture / hexagonal** (clean-architecture skill; DDD). **Adopt:** the `ActionManifest` is a **domain-layer value object/DTO** (pure data, no framework); the capability check is an **application-layer use case** (`Invoke` handler); the keychain/verifier and the adapter executor are **infrastructure adapters behind ports** (`CapabilityStore`, `ActionExecutor`); the dependency rule points inward so the core never depends on a vendor adapter. **Reject:** an anaemic model where authorization logic scatters across surfaces — it lives in exactly one use case, at one boundary.

## How this conforms to ADR-0001 and the prior contracts

| Invariant | How this spec honours it |
|---|---|
| (1) Log is source of truth; components derived | An action **never writes the log or a component directly**. Its *results* re-enter as fact events via `submit` (envelope spec). `invoke` mutates nothing of record. |
| (2) Directionality | The capability check lives on the **write boundary** (`invoke` → `submit`). Preconditions *read* the materialized view (read side) but the action's only write is through `submit`. The log is the single seam; `invoke` is upstream of it (envelope spec § "actions are a separate primitive"). |
| (3) Determinism | `invoke` and approval are **not** reducer inputs and not on the log; only their result *facts* are, and those carry all non-determinism stamped at ingestion. Preconditions are pure predicates over a snapshot view at `as_of` (no clock/RNG inside the predicate). The capability HMAC chain is deterministic given the root key. |
| (4) Per-entity order only | An action targets one entity; its result facts get per-entity `sequence` from the daemon like any submit. No cross-entity ordering is introduced. |
| (5) Capability-shaped authority | **This spec defines invariant 5.** Authority is possessed/attenuable/unforgeable, checked only at the write boundary; manifest flags are hints, never the boundary; renderers hold none by default (POLA); v1 may be RBAC-degenerate but ocap-shaped. The token construction and verify algorithm are normative below. |
| (6) Fact/narration firewall | A manifest and a capability carry **no narration**. An action result is a fact (or, for an AI-egress action, narration emitted *outward* by an egress adapter, never `submit`ted inward). The approval gate is a *fact* gate, not a narrated one. |
| (7) Credentials never in state/log | The capability is **not** a credential; the log/components/summary store only an opaque `capabilityRef` for provenance. A `remote-write` action's secret stays with the adapter; the capability names a `credentialRef`, never the secret (ADR inv. 7; privacy/credential spec). |
| (8) Vendor neutrality / event-type scoping (**amended reading**) | Core ships **zero DOMAIN** manifests, verbs, capability grants, precondition vocabularies, or domain event types, and never branches on `payload`/`khaos.*`/`loswf.*`. The categorical "zero event types" wording is read against the ADR's **enumerated runtime-meta allowlist** (see note below): this spec's `approval.requested`/`granted`/`denied`/`expired` are **runtime-meta** event types core reserves, emitted by a core domain-neutral reducer, carrying no domain payload. They are not domain types and do not violate inv. 8 under the amended wording. |
| (9) Cross-language seams | The `ActionManifest`, `ActionRequest`/`ActionOutcome`, the canonical predicate AST, and the serialized capability are language-neutral CBOR/JSON documents; `invoke` is a language-neutral control-plane RPC. Any adapter in any language can declare actions and present capabilities without linking core. |
| Attention spec inv. 6 | This spec **owns** `approval-requested` and now **fixes its projection**: `approvals.pending[].state == "awaiting"` projects the attention facet `state` to `awaiting-human` (§ approval gate). The bus may rank an awaiting-approval entity as high as `prominent`; it never performs a write-path block. "blocking" remains prominence-only. |

> **Amended invariant-8 reading (cross-spec, requires the ADR amendment).** ADR-0001 invariant 8 is stated categorically as "core ships zero … event types" and is repeated verbatim in the reducer and envelope specs, yet the system genuinely requires a small set of **core-owned runtime-meta event types** that are *not* domain types: `approval.requested`/`granted`/`denied`/`expired` (this spec), `ambisphere.egress.performed` (privacy spec, core-reserved), `entity.registered`/`renamed`/`rehomed` and `edge.added`/`removed` (identity spec), and the `attention.*`/`focus.*` verbs (attention spec). This spec **assumes ADR-0001 will be amended once** to distinguish **DOMAIN event types (zero in core)** from this **enumerated runtime-meta allowlist**, and to list that allowlist in the ADR so each dependent spec references it instead of independently carving an exception. Pending that amendment this is recorded as an open question; this spec carves no exception of its own beyond the named `approval.*` set, and the lint of acceptance #10 checks for that exact allowlist rather than an unconditional "zero".

## Layer A — the declarative action manifest

An `ActionManifest` is a **pure description**. It is registered by a bundle/adapter (examples layer); core ships none. It is the launcher/control vocabulary an entity kind exposes. It is MCP-tool-shaped.

```jsonc
// One action manifest. Bundle-owned. Core ships zero of these.
{
  "actionId":      "loswf.pr.rerunChecks",   // reverse-DNS, bundle-namespaced, stable
  "schemaVersion": 1,                          // this manifest schema's version (independent of payload/reducer versions)
  "title":         "Re-run checks",
  "description":   "Re-trigger CI checks for this pull request.",

  // --- schemas (JSON Schema; schema-on-read; core NEVER branches on these) ---
  "inputSchema":   { "type": "object", "properties": { "ref": {"type":"string"} }, "required": [] },
  "outputSchema":  { "type": "object", "properties": { "runId": {"type":"string"} } },

  // --- behavioural FLAGS (UX/attention HINTS ONLY — never the security boundary) ---
  "flags": {
    "confirmRequired": false,   // does a human approval gate apply? (UX/attention hint)
    "destructive":     false,   // additive vs destructive change? (UX hint; cf. MCP destructiveHint)
    "idempotent":      true,    // safe to re-invoke with same args? (retry hint; cf. MCP idempotentHint)
    "locality":        "remote-write"  // CANONICAL enum: local | remote-read | remote-write (cf. MCP openWorldHint, refined)
  },

  // --- AUTHORITY requirement: what capability SHAPE the caller must present.
  //     These are authority-token descriptors, NOT role names. (ocap, not RBAC.)
  "requiredCapabilities": [
    { "verb": "pr.rerunChecks", "target": "kind:loswf.pr" }   // matched against the presented capability's authority
  ],

  // --- PRECONDITIONS: canonical closed predicate AST over the read-side component view at as_of.
  //     Authoritative at the daemon; advisory to renderers. Total, side-effect-free. (See § preconditions.)
  "preconditions": [
    { "component": "loswf.ci", "path": "state", "op": "in", "value": ["failed", "errored"] }
  ],

  // --- RESULT EVENTS: the fact event types this action's results will re-enter as (via submit).
  //     Declares the lineage shape; does NOT itself write the log.
  "resultEvents": [ "loswf.ci.rerunRequested", "loswf.ci.passed", "loswf.ci.failed" ]
}
```

### Field semantics and rules

- **`actionId`** — reverse-DNS, bundle-owned, stable across versions (cf. envelope `type`). Core ships none and never branches on it.
- **`inputSchema`/`outputSchema`** — JSON Schema, validated **schema-on-read** at the boundary. Core validates the *envelope* of an `ActionRequest` and that the input *conforms to the declared schema*; it never interprets the domain meaning of the payload (ADR inv. 8; envelope spec schema-on-read).
- **`flags` are hints, structurally.** They drive UX (a surface shows a confirm dialog when `confirmRequired`), attention (the bus may rank an approval-gated action higher), and retry behaviour (`idempotent` ⇒ safe auto-retry). **They are never consulted by the capability check.** A bundle that sets `destructive: false` on a destructive action lowers only its *UX prominence*, never its *authority requirement* — exactly the MCP failure mode we refuse to let bypass anything (MCP blog 2026-03-16). The acceptance suite asserts that flipping any flag changes no authorization outcome.
- **`locality` — canonical enum (this spec is the owner).** The value set is exactly `local | remote-read | remote-write`:
  - `local` — in-process / filesystem; no external endpoint touched.
  - `remote-read` — an external read (e.g. fetch CI status); egress of a *request*, no external mutation.
  - `remote-write` — an external mutation (e.g. rerun CI, open PR).

  This refines MCP's `openWorldHint`/`readOnlyHint`/`destructiveHint` onto the adapter taxonomy. **The read/write distinction is load-bearing for the egress/privacy boundary** (the privacy/credential spec keys its egress evaluation on `locality`), so the two-valued `local|remote` form cannot express it and is **rejected**. **Downstream conformance (normative for the suite):** the entity-bundle-format spec's `[action]` serialization and validation, and the privacy/credential spec's egress evaluation, MUST use this three-valued enum; a bundle authored with `locality = "remote"` is invalid and the bundle validator MUST reject it. `locality` is still only an egress/privacy *hint* here — it is never a gate at `invoke`.
- **`requiredCapabilities`** are **authority shapes**, not role names. A caller satisfies them by *holding a capability whose authority subsumes the shape* (see layer B § matching). This is the ocap/RBAC fork: we require **possession**, not **membership**.
- **`preconditions`** — a list of canonical predicate-AST nodes (see § preconditions for the one shared grammar). The manifest declares them; the daemon evaluates them authoritatively at `invoke`.
- **`resultEvents`** — the reverse-DNS fact types the action's results will be `submit`ted as. This makes the lineage auditable from the manifest alone ("invoking `rerunChecks` will produce a `ci.rerunRequested` fact, then a `ci.passed`/`ci.failed`"). It is documentation + a validation hook (the daemon MAY warn if an adapter submits a result fact whose `causedBy` action declared a different `resultEvents` set); it is **not** itself a write.

### Where the manifest lives (clean-architecture)

The `ActionManifest` is a **domain-layer value object**: pure data, no IO, no framework. Bundles register manifests at attach time via an `ActionRegistry` port. The registry is queryable (the RivetKit `list-actions` pattern) so a surface can enumerate an entity's affordances — but enumeration returns **advisory** metadata only and grants no authority (POLA).

```rust
/// Read-only enumeration of an entity's declared actions. ADVISORY. Grants no authority.
/// Returned affordances are filtered by the caller's read capability (privacy spec) and
/// annotated with precondition status at as_of, so a renderer can grey-out unavailable actions.
fn list_actions(read_cap: &ReadCapabilityRef, entity: &EntityAddress, as_of: Timestamp)
    -> Vec<ActionAffordance>;

struct ActionAffordance {
    manifest: ActionManifest,         // the declarative description (hints included)
    preconditions_met: bool,          // evaluated at as_of, advisory (daemon re-checks at invoke)
    authorized_for_caller: bool,      // does the caller's read-side view of its own authority suggest yes?
                                      //   ADVISORY ONLY — the real check is at invoke (one source of truth)
}
```

> **One source of truth.** `authorized_for_caller` and `preconditions_met` here are *advisory* so a UI can render affordances without guessing. The authoritative decision is made once, at `invoke`, by the daemon. A renderer that skips the dialog because `confirmRequired` was false, or shows an action it shouldn't, can never cause an unauthorized effect — the gate is downstream and unconditional.

## Layer B — the object-capability enforcement model

A **capability** is the security boundary. It is a possessed, unforgeable, attenuable token that *is* the authority to perform a verb against a target, optionally narrowed by caveats. It is checked at exactly one place — the write boundary (`invoke`, which gates before any `submit`) — and nowhere else.

### Logical model

```jsonc
// A capability (LOGICAL view). Unforgeable (HMAC-rooted), attenuable (caveats only narrow), possessed.
// NEVER a credential. NEVER a role. The log/components store only an opaque capabilityRef to one of these.
{
  "capabilityId": "01J...ULID",      // opaque, stable id; what a capabilityRef points to (provenance)
  "authority": {
    "verb":   "pr.rerunChecks",       // the action verb (or a verb-glob, e.g. "pr.*")
    "target": "kind:loswf.pr",        // address | "kind:<kind>" | EntityAddress segment-glob (identity spec grammar)
    "constraints": {}                  // optional structured narrowing (bundle-defined, opaque to core matching)
  },
  "caveats": [                         // first-party predicates, macaroon-style, HMAC-chained; ONLY narrow
    { "type": "expiresAt", "value": "2026-06-11T00:00:00Z" },
    { "type": "entityGlob", "value": "loswf:pr/4217" },     // restrict to one PR (identity glob grammar)
    { "type": "maxInvocations", "value": 3 }
  ],
  "parent": "01J...PARENT | null",    // lineage: the capability this was attenuated from (root = null)
  "revocationEpoch": 7                 // checked at verify time against the live epoch (see § revocation)
}
```

### v1 token wire format (normative, first-party caveats only)

The **serialized** capability (the bearer token a holder presents) is a **CBOR map** carrying the logical fields plus an integrity `tag`. v1 uses **first-party caveats only**; third-party caveats are out of scope for v1 (open question).

```jsonc
// Serialized capability (CBOR). Field keys are CBOR text keys; values as shown.
{
  "v":              1,                 // token format version (this section)
  "capabilityId":   "01J...ULID",
  "authority":      { "verb": "...", "target": "...", "constraints": { } },
  "caveats":        [ /* ordered; order is part of the MAC, never reordered */ ],
  "parent":         "01J... | null",
  "revocationEpoch": 7,
  "tag":            h'…32 bytes…'       // the HMAC chain terminus (see construction)
}
```

**Canonical serialization.** Every value that enters the MAC is first encoded with **deterministic CBOR (RFC 8949 §4.2 core deterministic encoding)**: shortest-form integers, definite-length maps/arrays, map keys sorted bytewise. This makes `canonical(x)` a single well-defined byte string for any `authority`, `caveat`, or scalar, identical across languages and platforms (cross-language seam, ADR inv. 9).

**MAC algorithm.** `HMAC-SHA256` (RFC 2104; FIPS 198-1). The 256-bit root key lives only in the daemon keychain (§ keychain port).

**HMAC chain construction** (the macaroon chain — caveats can be appended by any holder, removed by none):

```
k0  = HMAC-SHA256( rootKey,
                   canonical(authority) || canonical(capabilityId) || canonical(revocationEpoch) )
k1  = HMAC-SHA256( k0,        canonical(caveats[0]) )
k2  = HMAC-SHA256( k1,        canonical(caveats[1]) )
...
kn  = HMAC-SHA256( k(n-1),    canonical(caveats[n-1]) )
tag = kn                                                   // the 32-byte value stored in the token
```

The root authority is bound under `rootKey`; each caveat re-keys the chain by the *prior* tag, so a holder can append a caveat (compute the next link from the current `tag`, without `rootKey`) but cannot remove or reorder one (that would require the intermediate key for a chain it cannot reconstruct), and cannot forge a fresh root link (it lacks `rootKey`). `parent` is recorded for lineage/audit but is **not** part of the MAC (a re-parenting forgery still fails because the chain's root link is keyed by `rootKey` over the immutable `authority`/`capabilityId`/`revocationEpoch`).

**`attenuate`** appends one caveat: `tag' = HMAC-SHA256(tag, canonical(newCaveat))`, push `newCaveat` onto `caveats`, leave `authority`/`capabilityId`/`revocationEpoch` untouched, set `parent = this.capabilityId` on the *derived* logical record for audit. Because caveats can only ever **narrow** (every first-party caveat is a *restriction* predicate; the verify step requires *all* of them to hold), `result.authority ⊆ parent.authority` holds by construction (acceptance #3).

**`verify(serialized, now, target)`** — the security boundary, step by step:

```
1. CBOR-decode the token; reject if v != 1, if any required field missing,
   or if re-encoding any MAC input is not canonical (non-deterministic CBOR) → VerifyError::Malformed
2. recompute the chain:
       k = HMAC-SHA256(rootKey, canonical(authority)||canonical(capabilityId)||canonical(revocationEpoch))
       for c in caveats:  k = HMAC-SHA256(k, canonical(c))
   compare k to token.tag in CONSTANT TIME            → unequal ⇒ VerifyError::Unforgeable
   (covers forgery, tamper, caveat removal/reorder, and re-rooting)
3. check token.revocationEpoch == live epoch for this root/caretaker
                                                       → stale ⇒ VerifyError::Revoked
4. evaluate every first-party caveat against (now, target):
       expiresAt:      now <= value                   → else VerifyError::CaveatFailed
       entityGlob:     identity-spec match(target, value)  → else CaveatFailed
       maxInvocations: live counter for capabilityId < value  → else CaveatFailed
       (caveat type set is closed and core-known; an unknown caveat type ⇒ CaveatFailed, fail-closed)
   → on success, return a `Capability` value object (the ONLY way to obtain one from bytes)
```

In a memory-safe core (Rust — implementation-language guidance: "a memory bug forges capabilities"), unforgeability is enforced both cryptographically and by the type system: a `Capability` is **never constructible from untrusted bytes except through `verify`**, and the `rootKey` type is non-`Clone`, non-`Debug`, zeroized on drop. The closed caveat-type set is **fail-closed**: an unrecognised caveat type fails verification rather than being ignored.

### Attenuation (POLA in action)

```rust
/// Mint a STRICTLY WEAKER capability by appending a narrowing caveat. Cannot widen authority.
/// This is delegation: a holder gives another holder a narrower slice (macaroon minting).
/// Implemented as the single-caveat HMAC append above; needs no root key.
fn attenuate(parent: &Capability, caveat: Caveat) -> Capability;   // result.authority ⊆ parent.authority
```

A bundle holding `pr.* over kind:loswf.pr` can hand a chat surface `attenuate(cap, {entityGlob: "loswf:pr/4217"})` and `attenuate(_, {verb: "pr.comment"})` — the surface can now comment on exactly one PR and nothing else. This is how the runtime guidance's motivating case (Khaos Machine granting LOSWFX narrow authority over one entity) is expressed **without a shared identity registry** — the thing RBAC cannot do (guidance contradiction 2).

### Matching a request to required capabilities

```rust
/// The ONLY authorization decision. Pure given (capability, manifest, target, now). No ambient authority.
fn authorize(cap: &Capability, manifest: &ActionManifest, target: &EntityHandle, now: Timestamp)
    -> Result<(), AuthzError>;
// Steps (all must pass):
//  1. verify(serialized, now, target): chain valid, revocationEpoch current, every caveat holds
//        → else Unforgeable | Revoked | CaveatFailed
//  2. cap.authority SUBSUMES at least one manifest.requiredCapabilities entry → else InsufficientAuthority
//     (verb match incl. globs; target match incl. kind/address/segment-glob — entity-identity spec grammar)
```

`authorize` reads **no role table** and **no caller identity** — only the presented capability. This is confused-deputy immunity: the daemon cannot be tricked into acting on ambient authority because it has none to draw on (Dennis & Van Horn; E; Goblins).

**Target/verb matching grammar is owned by the entity-identity spec.** Verb-globs (`pr.*`) and target matching (`address` | `kind:<kind>` | `EntityAddress` segment-glob | namespace) — and the `entityGlob` caveat — all match against the **canonical segment/glob/kind/namespace matching grammar the entity-identity spec owns** (exact match, single-segment wildcard, prefix/multi-segment wildcard, kind-via-`instance-of`, namespace match). This spec **consumes** that grammar and does not redefine it; it is a hard cross-spec dependency (see open questions) — the privacy/credential spec consumes the same grammar for read scopes and `namespace`-scoped caveats, so there is exactly one matcher.

### v1 degenerate case

v1 MAY ship a **single-principal keychain**: the daemon holds one root key at install; a local operator's surfaces are issued broad capabilities; cross-app delegation is not yet exercised. This is RBAC-degenerate (one principal) but **ocap-shaped** — the same `authorize` path, the same attenuation, the same verification. Nothing in the contract assumes one principal; turning on cross-app delegation is adding `attenuate` callers, not changing the model (guidance contradiction 2 resolution; ADR inv. 5).

### The keychain is an infrastructure adapter (clean-architecture)

The core depends on a `CapabilityStore` **port** (mint/attenuate/verify/revoke); the SQLite/OS-keychain-backed implementation is an infrastructure adapter. The root key never leaves the keychain; the core sees only the port. This keeps the security model testable against an in-memory keychain (daemon spec's in-memory-driver conformance requirement).

```rust
trait CapabilityStore {
    fn mint(&self, authority: Authority) -> Capability;          // root mint (keychain-held root key; builds k0..tag)
    fn verify(&self, serialized: &[u8], now: Timestamp, target: &EntityHandle)
        -> Result<Capability, VerifyError>;                      // the algorithm above
    fn revoke(&self, capability_id: &CapabilityId) -> RevocationEpoch;   // bumps the epoch (see § revocation)
    // attenuate() is pure and needs no store (any holder can narrow); verify checks the chain.
}
```

## The `invoke` call — a control-plane primitive, not a write

`invoke` is **not** a log write, **not** an event, **not** a reducer input. It is a control-plane request the daemon **may reject**. It sits *upstream* of the write boundary: it authorizes, evaluates preconditions, then either dispatches to an executor (which will `submit` result facts) or raises an approval gate. Commands never land on the log; only their result facts do (envelope spec § "actions are a separate primitive").

```rust
/// Invoke an action. Control-plane. Capability-gated. May be rejected. Effects (if any) re-enter
/// the log only as fact events via submit(), carrying correlation.causedBy = this action_instance_id.
fn invoke(cap: &Capability, req: ActionRequest) -> Result<ActionOutcome, InvokeError>;

struct ActionRequest {
    action_id: ActionId,            // must match a registered manifest for the target entity's kind
    target: EntityAddress,          // the entity the action acts on (resolved to a handle, like submit)
    input: serde_json::Value,       // validated against manifest.inputSchema (schema-on-read)
    action_instance_id: Ulid,       // client-minted; idempotency/correlation key for this invocation
                                    //   (distinct from the envelope dedupeKey of the result facts)
}

enum ActionOutcome {
    Dispatched   { action_instance_id: Ulid },          // executor accepted; result facts will follow via submit
    AwaitingApproval { approval_id: Ulid, entity: EntityHandle },  // gate raised; durable approval.requested emitted
    Completed    { output: serde_json::Value },          // synchronous local action finished (results already submitted)
}

enum InvokeError {
    Unauthorized,          // authorize() failed: Unforgeable | Revoked | CaveatFailed | InsufficientAuthority
    UnknownAction,         // no manifest for (action_id, kind)
    MalformedInput,        // input does not conform to inputSchema
    PreconditionFailed,    // a precondition predicate was false at invoke-time as_of (see § preconditions)
    UnknownEntity,         // target unresolvable and capability does not authorize creation
    ExecutorUnavailable,   // no adapter registered to execute this action_id
    Backpressure,          // control plane shedding load
    // NOTE: there is NO "action failed" outcome here. A remote action that FAILS does so by SUBMITTING
    //       a failure FACT (e.g. ci.failed). invoke() only reports whether the action was authorized,
    //       precondition-clear, and dispatched — not whether the external world later succeeded.
}
```

### Normative invoke order

```
1. resolve   action_id → ActionManifest (for target kind)              → else UnknownAction
2. validate  input against manifest.inputSchema (schema-on-read)        → else MalformedInput
3. authorize cap against manifest.requiredCapabilities + target         → else Unauthorized
              (verify HMAC chain, check caveats, check revocation epoch — the SECURITY BOUNDARY)
4. resolve   target EntityAddress → EntityHandle (identity spec)        → else UnknownEntity
5. precond   evaluate manifest.preconditions over the read view at as_of → else PreconditionFailed
6. gate?     if flags.confirmRequired OR policy requires approval:
                 submit(approval.requested fact) → reducer → approvals component
                 return AwaitingApproval                                 (NO synchronous block)
             else:
                 dispatch to ActionExecutor (adapter) with a discharge token
                 → executor performs the work, then submit()s result facts (causedBy = action_instance_id)
                 return Dispatched (or Completed for synchronous local actions)
```

Steps 1–5 are **pure-and-local** (no external IO); step 6 either raises a durable fact (approval) or hands off to an adapter. The authorization decision (step 3) and the precondition decision (step 5) are made **once, here, by the daemon** — the single source of truth.

### The executor is a port

```rust
/// Adapters register executors per action_id. The executor does the work (local or remote) and
/// re-enters results via submit(). It receives a DISCHARGE capability scoped to exactly the
/// result-fact submits this action declared (resultEvents) — POLA all the way down.
trait ActionExecutor {
    fn execute(&self, req: &ActionRequest, discharge: &Capability) -> ExecResult;
}
```

The executor is handed a **freshly attenuated discharge capability** authorizing only the `submit`s of the declared `resultEvents` for this target — not the caller's broad capability. So a `rerunChecks` executor can submit `ci.rerunRequested`/`ci.passed`/`ci.failed` to *this PR* and nothing else, even though the human who invoked it holds wider authority (confused-deputy immunity, end to end).

## The async human-approval gate

`confirmRequired`/`destructive` actions (or any action a local policy flags) **never block**. Per runtime-guidance contradiction 3 and attention spec inv. 6, the human gate is a **write-side durable fact**, distinct from how prominently it is surfaced.

### Canonical name and attention projection

The condition has **one canonical name in each domain**, with a fixed mapping between them:

- **Action domain:** the condition is **"approval-requested"**, materialized as an entry in the `approvals` component with `state == "awaiting"` (entry states: `awaiting | granted | denied | expired`).
- **Attention domain:** when an entity has at least one `approvals.pending[].state == "awaiting"`, its **attention facet `state` projects to `awaiting-human`** — the value already in the attention facet enum (`dormant | active | awaiting-human | acknowledged | resolved | expired`) that the bus ranks on. There is no `approval-requested` value in the attention enum; `awaiting-human` *is* its projection.

This projection is performed by the **core domain-neutral reducer** that produces the attention facet, reading the approval facts this spec owns: an `approval.requested` fact (no later `approval.granted`/`denied`/`expired` for the same `approval_id`) sets the entity's attention `state` to `awaiting-human`; a resolving fact clears it (back to `active`/`resolved` per the attention spec's rules). The attention spec's prose "the bus may rank an approval-requested entity" therefore refers to entities whose facet `state == awaiting-human`. Both specs use **"approval-requested" as the action-domain label and `awaiting-human` as the attention-domain value**, consistently.

```
invoke(cap, rerunProductionDeploy)         flags.confirmRequired = true
   │
   ├─ steps 1–5 pass
   ├─ step 6: submit  approval.requested  ──▶ [log] ──reduce──▶ approvals component (durable, state="awaiting")
   │                                                 │
   │                                                 └─▶ attention facet state ⇒ "awaiting-human"
   │                                                       (bus MAY rank entity up to `prominent`)
   └─ return AwaitingApproval{ approval_id }          (NEVER a synchronous daemon block)

   ... later, asynchronously, a human (holding an approval capability) ...

approve(approvalCap, approval_id)          a SEPARATE capability-gated action
   │
   ├─ authorize approvalCap (the right to approve THIS gate)
   ├─ mint  a ONE-SHOT discharge capability for the pending action (caveat approvedBy(approval_id))
   ├─ submit approval.granted fact ──▶ [log] ──reduce──▶ approvals component (state="granted")
   │                                                       attention facet clears awaiting-human
   └─ dispatch the pending action to its executor with the one-shot discharge
```

The `approvals` durable component (owned by this spec, produced by a core domain-neutral reducer over the `approval.*` runtime-meta facts) is the canonical gate state:

```jsonc
// The approvals component facet. Produced by a core domain-neutral reducer from approval.* facts.
// This is the durable "approval-requested" state the attention spec references (inv. 6),
// projected onto the attention facet as state="awaiting-human" while any entry is "awaiting".
{
  "schemaVersion": 1,
  "pending": [
    {
      "approvalId":      "01J...",
      "actionId":        "ops.deploy.rerunProduction",
      "actionInstanceId":"01J...",
      "requestedAt":     "2026-06-10T18:04:00Z",   // = the requesting fact's ingestTime (stamped, not clock-read)
      "requestedByRef":  "capabilityRef:01J...",    // opaque provenance, NEVER a credential
      "state":           "awaiting",                 // awaiting | granted | denied | expired
      "expiresAt":       "2026-06-10T19:04:00Z | null"
    }
  ],
  "provenance": { "lastEventId": "01J...", "lastEventTime": "...", "kind": "factual" }
}
```

- **Approval/denial are capability-gated actions**, not ambient operations. `approve`/`deny` each require an approval capability (which a bundle attenuates and hands to the human's control surface). This means *who may approve* is itself ocap-governed — a confused deputy cannot self-approve a destructive action it merely invoked.
- **Granting mints a one-shot discharge capability** (conceptually a macaroon discharge — Birgisson 2014): the pending destructive action proceeds only with a capability bearing the `approvedBy(approval_id)` first-party caveat, whose `maxInvocations: 1` consumes it once. This is the only place a *new* authority enters the flow, and it is minted by the approver, not the invoker.
- **Expiry/denial** emit facts (`approval.expired`/`approval.denied`); the pending action is dropped, never executed. No timer mutates state directly — expiry is realized by an alarm that *submits* an `approval.expired` fact (daemon spec lifecycle; alarms cause facts via submit, never direct mutation).
- **Prominence ≠ gate.** The attention bus may render the awaiting entity at `prominent` (even persistently), and a surface declaring `honorsBlocking` MAY show a modal — but the daemon is never blocked, no reducer pauses, and `invoke` returned immediately with `AwaitingApproval` (attention spec § "blocking is a prominence, not a gate").

## Preconditions — the one canonical predicate language

A precondition is a **pure, total predicate over the read-side component view** at an explicit `as_of`. It answers "is this action *currently sensible*?" (e.g. only offer `rerunChecks` when CI is `failed`). It is **not** authorization — an unauthorized caller is rejected at step 3 regardless of preconditions; an authorized caller whose preconditions are unmet is rejected at step 5 with `PreconditionFailed`.

This spec defines the **canonical closed predicate language**, and resolves the prior open question: **yes — this is one shared closed grammar**, used identically by (a) action `preconditions` here, (b) the entity-bundle-format spec's action `preconditions`/`where`, and (c) the persona-projection spec's `when` state-matchers. There is exactly one surface syntax; the free-text string form (`where = "phase == 'failed'"`) is **rejected** everywhere (see § rejected forms).

### Grammar (canonical)

A predicate is a node in a small AST. There is **no string expression to parse** and no user code.

```jsonc
// A single predicate node. Declarative, total, side-effect-free. Read-only over components at as_of.
{ "component": "loswf.ci", "path": "state", "op": "in", "value": ["failed", "errored"] }
```

- **`component`** — the reverse-DNS component (facet) name whose state is read. Resolved against the entity's materialized view at `as_of`.
- **`path`** — a **dotted field path** into that component's state object, e.g. `"state"`, `"ci.lastRun.conclusion"`, `"counts.failed"`. Path segments traverse JSON object keys only (no array indexing, no wildcards, no function calls in v1). A path that does not resolve yields the *absent* value (relevant to `exists`/`notExists`; for other ops an absent left-hand side makes the predicate `false`, never an error — totality).
- **`op`** — the **closed op set** (no others permitted): `eq | ne | in | notIn | lt | lte | gt | gte | exists | notExists`.
  - `eq`/`ne` — scalar equality / inequality.
  - `in`/`notIn` — membership in the `value` array.
  - `lt`/`lte`/`gt`/`gte` — ordered comparison (numbers; ISO-8601 timestamps compared lexically as their canonical string; strings compared bytewise). Cross-type comparison (e.g. number vs string) is `false`, never an error.
  - `exists`/`notExists` — the resolved path is present / absent. `value` is omitted/ignored.
- **`value`** — a JSON scalar or array of scalars. **Typing rule:** the predicate is evaluated against the field's *declared* type in the producing reducer's component schema (reducer/state-component spec). If the `value`'s JSON type is incompatible with the field's declared type, the predicate is **`false`** (no coercion, no error) — and the bundle validator SHOULD warn at load time. No implicit string↔number coercion ever occurs.

A `preconditions` array is a **conjunction** (all must hold). Disjunction/negation are intentionally **not** in v1 (keeps the grammar trivially total and analysable); if a bundle needs OR it declares two actions or a derived component field. This restriction is revisitable but the closed/total/pure property is non-negotiable (ADR inv. 3; VISION "no rules engine").

### Rejected forms (and required downstream change)

The free-text string form used today by the bundle and persona specs is the exact open-ended expression form this spec rejects:

```toml
# REJECTED — bundle spec today:
preconditions = [ { component = "loswf.workflow", where = "phase == 'failed'" } ]
# REJECTED — persona spec today:
when = { component = "loswf.workflow", where = "phase == 'blocked'" }
```

```toml
# REQUIRED — canonical structured form (TOML rendering of the same AST node):
preconditions = [ { component = "loswf.workflow", path = "phase", op = "eq", value = "failed" } ]
when = { component = "loswf.workflow", path = "phase", op = "eq", value = "blocked" }
```

**Normative downstream conformance (suite-level):** the entity-bundle-format spec's `preconditions`/`where` serialization and validation, and the persona-projection spec's `when` state-matcher serialization, MUST use this structured `{component, path, op, value}` form. A `where = "<string>"` value is invalid and the bundle validator (L4 firewall step) MUST reject it. The persona spec's text-slot **brace interpolation** (`"{loswf.workflow.blockedReason}"`) is a *separate* concern (field-reference / slot resolution, owned by persona) and is **not** governed by this predicate grammar; only the *predicate* (`when`) is. (See open questions on whether the slot-reference path syntax should share this `component`+`path` dotted form.)

### Evaluation discipline

- **Authoritative at the daemon, advisory to renderers.** The daemon re-evaluates at invoke (step 5) against the view at invoke-time `as_of`; renderers may evaluate the same predicate to grey-out an affordance (`list_actions` returns `preconditions_met`), but the renderer's view can be stale and is never trusted (one source of truth = daemon).
- **Reads the materialized view, never the write side.** Precondition evaluation is a read-side query at `as_of` (the attention spec's `as_of` discipline); it never queries across actors on the write path (ADR inv. 2).
- **Closed grammar, no Turing-completeness.** The op set, path syntax, and conjunction-only composition are fixed; predicates are a small AST over component fields. This keeps preconditions deterministic and side-effect-free (ADR inv. 3) and avoids drifting into the "personality/rules-engine" non-goal (VISION).

## Result events — how an action re-enters the log

An action's *effects* become facts the same way everything else does: through `submit`. The executor (adapter) submits one or more result facts, each carrying `correlation.causedBy = action_instance_id`, so the lineage from "human invoked X" to "these facts resulted" is reconstructable.

```
invoke(cap, rerunChecks @ loswf:pr/4217)         action_instance_id = 01J-ACT
        │
        └─ dispatch ──▶ [GitHub adapter executor]
                              │  (calls the GitHub API with its own held credential — secret never travels)
                              ├─ submit  ci.rerunRequested  { causedBy: 01J-ACT }  ──▶ [log] (fact)
                              │     ... time passes, CI runs ...
                              └─ submit  ci.passed          { causedBy: 01J-ACT }  ──▶ [log] (fact)

  the action itself (01J-ACT) NEVER appears on the log — only its result facts do (envelope inv. 6)
```

- **Invoker provenance** rides the result facts via the opaque `capabilityRef` (`source`/`capabilityRef` in the envelope) plus `causedBy`. Audit can answer "who caused `ci.passed`?" → the action instance, → the capability that invoked it (never a credential). (Guidance open question "do result events carry invoker provenance" → **yes**.)
- **Credentials never travel.** A `remote-write` action authorizes the *action*; the *adapter holds the secret*. The capability MAY name a `credentialRef` the adapter resolves locally, but no secret enters the capability, the request, or the log (ADR inv. 7; privacy/credential spec).
- **`declaredResultEvents` validation.** The daemon MAY warn (not reject) if an executor submits a result fact whose `causedBy` action's manifest did not declare that `type` in `resultEvents` — a soft consistency check, since the log's authority is the fact itself, not the manifest's prediction.

## Revocation

Capabilities are revoked by **caretaker/membrane indirection plus a revocation epoch**, not by mutating an issued token (you cannot, by design, reach into a holder's token).

- **Caretaker pattern (ocap):** a delegated capability is minted *through a caretaker* — an indirection the granter retains a handle to. Revoking is severing the caretaker, after which the delegated capability resolves to nothing. This is the membrane revocation of the E/Goblins lineage.
- **Revocation epoch:** each capability records the `revocationEpoch` it was minted under (bound into the chain's root link, so it cannot be tampered without failing `verify` step 2); the daemon holds the live epoch per root (and per caretaker). `verify` step 3 checks `cap.revocationEpoch` against the live epoch and fails `Revoked` if stale. Bumping the epoch (a keychain operation) instantly invalidates all capabilities minted before it under that root/caretaker — a coarse but always-correct kill switch for "revoke everything I granted to LOSWFX".
- **Expiry caveats** are the fine-grained complement: `attenuate(cap, {expiresAt})` bounds a delegation's lifetime without any central revocation. Macaroons make this free (first-party caveat, offline-verified — Birgisson 2014).

## Acceptance criteria

1. **Flags are not the boundary.** Flipping any manifest flag (`confirmRequired`/`destructive`/`idempotent`/`locality`) changes UX/attention/retry behaviour but **never** an authorization outcome — proven by a test that toggles each flag and asserts `authorize` is unchanged. (The MCP "mark destructive as readOnly to bypass" attack is structurally impossible.)
2. **Capability check is mandatory and sole.** Every `invoke` path runs `authorize`; there is no code path that dispatches an action or submits a result fact without a verified capability. A test asserts an unauthorized `invoke` returns `Unauthorized` and produces **zero** facts. POLA: a fresh renderer/observer connection holds no action capability and every `invoke` it attempts fails.
3. **Unforgeability + attenuation-only (against the normative format).** A tampered, forged, caveat-removed, or caveat-reordered serialized capability fails `verify` step 2 (HMAC chain mismatch, constant-time compare). A re-rooted (`parent`-swapped) token still fails because the root link is keyed by `rootKey` over the immutable `authority`/`capabilityId`/`revocationEpoch`. `attenuate` can only narrow: a property test asserts `attenuate(cap, c).authority ⊆ cap.authority` for all caveats and that no operation widens authority. An unknown caveat type fails closed. A cross-implementation test asserts two languages produce byte-identical canonical CBOR and the same `tag`.
4. **No ambient authority.** `authorize` consults only the presented capability — no role table, no caller identity. A test asserts identical inputs yield identical decisions regardless of "who" calls (confused-deputy immunity).
5. **Commands never hit the log.** No `invoke` writes the log or a component directly; only result facts (via `submit`) appear, each carrying `causedBy = action_instance_id`. A test asserts the action instance id never appears as a log `eventId`, and that result facts carry the correlation.
6. **Approval is async, durable, and projects correctly.** A `confirmRequired` `invoke` returns `AwaitingApproval` without blocking, emits a durable `approval.requested` fact, the `approvals` component shows `state == "awaiting"`, **and the entity's attention facet `state` projects to `awaiting-human`** (asserted jointly with the attention/reducer fixtures). The daemon never blocks; a concurrent `submit`/query to the same entity proceeds. Approval is itself capability-gated; granting mints a one-shot discharge consumed exactly once (`maxInvocations: 1`). Denial/expiry drop the pending action with the action never executed, and clear `awaiting-human`.
7. **Preconditions: one grammar, authoritative + advisory.** The daemon re-evaluates preconditions at invoke (`PreconditionFailed` when unmet) over the view at `as_of`; `list_actions` returns the same predicate's result advisorily; a stale-renderer test proves the daemon's decision overrides a renderer that thought the action was available. A grammar test asserts the closed op set, dotted-path resolution, totality (absent path / type-mismatch ⇒ `false`, never error), and that the bundle/persona structured form parses into the identical AST as the action manifest. A test asserts a `where = "<string>"` value is rejected by the bundle validator.
8. **Credentials never travel.** A `remote-write` action's secret never appears in the capability, the `ActionRequest`, the result facts, or the log — only an opaque `capabilityRef`/`credentialRef`. Static + property test.
9. **Revocation works two ways.** Bumping a revocation epoch invalidates prior capabilities (`verify` → `Revoked`); an `expiresAt` caveat invalidates after its time; severing a caretaker invalidates the delegated capability. Each proven by test.
10. **Vendor-empty core (against the runtime-meta allowlist).** Core ships zero **domain** manifests, verbs, capability grants, or precondition vocabularies, and zero **domain** event types; the only core-owned event types are the enumerated runtime-meta set, of which this spec contributes exactly `approval.requested`/`granted`/`denied`/`expired`. A lint asserts (a) no `khaos.*`/`loswf.*`/domain action id in core, (b) the daemon never branches on action `input`/`payload` internals, and (c) every core-emitted event type is on the ADR runtime-meta allowlist. All domain actions in the suite come from an examples-layer bundle.
11. **Canonical `locality` enum.** The action manifest, the bundle action serialization+validation, and the privacy egress evaluation all use exactly `local | remote-read | remote-write`; a cross-spec fixture asserts a `locality = "remote"` bundle is rejected by the validator, and that the egress evaluator distinguishes `remote-read` from `remote-write`.

## Open questions

- **ADR-0001 status and invariant anchor.** ADR-0001 is cited as binding ("decisions of record") by this and eight sibling specs yet is itself marked draft/Proposed. Before the suite is implementation-ready the ADR must (a) resolve to a single status, (b) publish the **canonical numbered invariant list** the nine conformance tables cite, and (c) adopt the **amended invariant-8 wording** (zero DOMAIN event types + an enumerated **runtime-meta allowlist**: `approval.*` (this spec), `entity.*`/`edge.*` (identity), `attention.*`/`focus.*` (attention), `ambisphere.egress.performed` (privacy)). This spec **assumes** that amendment and carves no exception of its own beyond the named `approval.*` set; if the ADR rejects the amendment, the runtime-meta `approval.*` events here must be re-justified.
- **Canonical predicate-language ownership.** This spec defines and owns the closed `{component, path, op, value}` grammar for preconditions and asserts it is the one shared declarative-predicate language for bundle `where` clauses and persona state-matchers. Whether the grammar's normative *home* should instead be the reducer/state-component spec (which owns the facet field types the paths resolve against) — with this spec referencing it — is a suite-level placement question. The grammar itself is non-negotiably closed/total/pure regardless of where it lives. Separately open: whether the persona text-slot field-reference syntax (brace interpolation `{component.field}`) should be unified onto the same dotted `component`+`path` form (recommended) or kept as persona's own slot grammar.
- **Capability target-matching grammar (cross-spec dependency).** Verb-globs and target matching (`address` | `kind:<kind>` | `EntityAddress` segment-glob | namespace), plus the `entityGlob`/`namespace` caveats, match against the **entity-identity spec's canonical matcher** (exact, single-segment wildcard, prefix/multi-segment wildcard, kind-via-`instance-of`, namespace). This spec is **blocked** on that grammar being pinned by the identity spec (the same matcher the privacy spec uses for read scopes), before caveat semantics are testable.
- **Macaroon depth for v1.** First-party-only caveats are now **normative** for v1 (the local daemon verifies locally). Third-party caveats with a discharge round-trip are specced only as the conceptual shape for genuinely remote human-approval discharge and are explicitly **not** required to ship; whether any v1 adapter needs them is deferred to the adapter/privacy specs.
- **Auditing failed/unauthorized attempts.** v1 rejects-before-effect with no fact emitted for `Unauthorized`/`PreconditionFailed` invokes; an opt-in attempt-audit channel is open and mirrors the envelope spec's open question on logging rejected `submit`s. Cross-ref: privacy/credential spec.
- **Credential-reference handshake.** The exact `credentialRef`-resolution protocol (how a capability names a credential an adapter resolves without the daemon ever seeing the secret) is co-owned with the privacy/credential and adapter specs.
- **Invoke idempotency key.** The client-minted `action_instance_id` is named as the idempotency key for re-sent invokes (distinct from the result facts' envelope `dedupeKey`); the exact at-least-once dedupe window/retention is co-owned with the envelope spec.
- **`actionability` source.** Whether the attention facet's `actionability` scalar should be computed from "are there capability-authorized actions whose preconditions hold at `as_of`?" (cleaner, self-consistent, but couples the read projection to the action manifest) remains a joint open question with the reducer and attention specs.
- **Capability-granting ceremony.** Daemon keychain vs per-bundle capability file vs grant-on-first-use. v1 leans on a single-principal keychain seeded at install; the cross-app delegation *ceremony* (Khaos Machine minting a narrow capability for LOSWFX over one entity) is specced ocap-shaped, but the minting UX, discovery, and trust-on-first-grant flow are deferred. Cross-ref: privacy/credential spec, adapter spec.

