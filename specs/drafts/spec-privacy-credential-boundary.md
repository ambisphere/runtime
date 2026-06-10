# Local-first privacy and credential boundary

**Status:** draft · **Scope:** the runtime's privacy and credential model — credentials never in entity state/components/log (only opaque references travel; adapters hold secrets via a daemon-mediated broker), the distinction between a *capability* (write authority), a *read-capability* (read authority), and a *credential* (which secret an adapter may resolve), the explicit adapter-owned **egress boundary** to remote models/providers with per-entity-kind redaction applied *before* egress and a content-free record of what was sent, **separately-gated read authority** (cross-entity and attention reads see a redacted/coarsened projection, not raw state), and the **namespace as the trust/privacy boundary** · **Companion to:** `specs/VISION.md`, `specs/SRS.md` (§5 "security model for cross-application event publishing"), `RFP.md` (§ "Privacy and local-first guarantees"), issue #5 §10 ("Local-first privacy and credential boundaries") · **Sequenced:** ninth among the follow-on specs (alongside the action/capability and adapter API specs, which all reference it) per ADR-0001 and issue #4 · **Conforms to:** ADR-0001 (invariants 5, 6, 7, and the amended invariant 8 — see § "Conformance to ADR-0001"), as a **provisional** decision of record (ADR-0001 is itself draft; see open questions); the semantic-event-envelope spec (the `redaction` envelope field, `capabilityRef`, `submit` as the only write path, **and the closed allowlist of core-reserved `ambisphere.*` types** that `ambisphere.egress.performed` is drawn from — this spec does *not* carve its own exception); the reducer/state-component spec (provenance `wasAttributedTo` carries `capabilityRef`, **never** a credential; the NarratedProjection store); the attention-routing spec (`read_capability` separately gates read; reads may return redacted/coarsened facets); the entity-identity spec (the `namespace` segment of `EntityAddress`, **and the canonical segment/glob/kind/namespace matching grammar** this spec's caveats and scopes reference); the action/capability spec (the canonical `locality` enum `local | remote-read | remote-write`; `CapabilityRef`); the daemon spec (the broker is the read/write enforcement point, the summary index holds no credentials) · **Sibling notes:** `specs/drafts/runtime-paradigm-and-specs-guidance.md` (§ "Local-first privacy / credential boundary"), `specs/drafts/actor-model-prior-art.md`, `specs/drafts/persona-prior-art.md`, `specs/drafts/implementation-language-guidance.md`

This spec defines the **trust seam** of a local-first runtime that nonetheless reaches out to remote models, providers, and APIs. It answers three questions the upstream specs deliberately deferred to it: *where do secrets live*, *what may leave the host and how is that recorded*, and *who is allowed to read what*. It owns no new write path (everything that lands is a fact via `submit`) and no new read path (everything observed flows through the daemon broker); it constrains both.

The core stance is structural, not advisory: a credential is **physically incapable** of appearing in entity state, and egress is **physically incapable** of bypassing redaction, because the only artifacts that can travel are opaque references and the only code that can resolve a secret or perform egress is an adapter holding the right reference. Privacy is enforced by what the types permit, in the spirit of the fact/narration firewall (ADR-0001 inv. 6) being structural rather than a guideline.

## Goals and non-goals

### Goals

- Define `CredentialRef` — an **opaque, secret-free** handle that names *which* secret, and **never** the secret — as the only credential-shaped value permitted anywhere in the envelope, state, components, log, snapshot, summary index, provenance, or narration.
- Define the **CredentialBroker**: a daemon-mediated facility that resolves a `CredentialRef` to a usable secret (or, preferably, to an *exchanged short-lived token*) **only inside an authorized adapter process**, never returning a raw secret to the core daemon's reducers/queries or to any renderer. Pin its v1 trust root (store-of-record + adapter authentication) so its interfaces are conformance-testable.
- Draw a crisp line between a **capability** (possessed write authority, ocap-shaped — owned by the action/capability spec) and a **credential** (the secret an adapter needs to reach an external system): distinct primitives, distinct lifecycles, distinct stores.
- Define the **egress boundary**: any flow of entity-derived data to a remote model/provider/API is an explicit, adapter-owned act, gated by an `EgressPolicy` declared per entity-kind in the bundle, **default-deny**, applied *before* the data leaves the host.
- Define the **egress record**: every egress emits an `ambisphere.egress.performed` **fact** event (via `submit`, on the full envelope contract) recording *what categories of data were sent, to where, under which policy, with which redactions* — **content-free** (hashes, not bodies), so the audit trail itself never becomes a leak.
- Make **read authority separately gated from write authority** (ADR-0001 inv. 5): a `ReadCapability` scopes both *which entities* and *which facets/fields* are visible; cross-entity and attention reads receive a daemon-computed **redacted/coarsened projection**, never raw state.
- Establish the **namespace** (first `EntityAddress` segment) as the trust/privacy boundary: capabilities and credentials are namespace-scoped; cross-namespace edges, reads, and egress are default-deny and require explicit authority.
- Give concrete schemas/interfaces (fenced) and **acceptance criteria** making each invariant testable.

### Non-goals (adopt/reject framing — rejections carried from the guidance)

- **Not** a centralized credential store or cloud secret manager. Secrets live local, in an OS keystore or a daemon-encrypted store, never synced. (Reject: cloud secret vaults, centralized credential stores — issue #5 §10.)
- **Not** an identity provider, OAuth server, or login system. The broker resolves *already-provisioned* secrets; provisioning a credential into the keystore is an out-of-band operator/installer act. (Reject: an IdP in core — carried from the action/capability guidance.)
- **Not** a general DLP/PII-detection engine, and **not** a redaction *vocabulary*, and **not a secret-pattern classifier**. Core ships zero field classifiers, zero PII regexes, zero category names, and **no heuristic "this looks like an API key" detector**. Classification is bundle-declared per entity-kind; any runtime detector is an adapter concern. The one credential check core *does* perform at the write boundary is a **precise byte-equality** check against known keystore secrets — not a fuzzy pattern (see § "Non-goals restated as guardrails"). (Reject: built-in PII taxonomy / secret-pattern heuristics — vendor-neutrality, ADR-0001 inv. 8.)
- **Not** sensor-based or inferred privacy/attention state. What is private is *declared*, not sensed. (Reject: ML/Bayesian sensitivity inference — carried from the attention guidance.)
- **Not** the AI provider / prompt / summarization stack. A remote model is *just another capability-gated, credential-holding egress adapter*; this spec governs the boundary, not the provider. (Reject: defining the AI stack — carried from the adapter guidance.)
- **Not** information-flow control with full taint propagation through reducers. v1 enforces redaction *at the boundaries* (egress and read), not as a lattice over every derived value. (Reject: a non-interference IFC type system in v1 — see open questions and prior art.)
- **Not** a transport-level encryption or network-security spec. The default endpoint is loopback/UDS (daemon spec); over-the-wire concerns for any future remote endpoint are out of scope here.
- **Not** the owner of the core-reserved event-type allowlist. The envelope spec owns that closed allowlist; this spec is a *consumer* of one entry (`ambisphere.egress.performed`). (Reject: a lone privacy-spec exception to "zero core types" — superseded; see § "Conformance to ADR-0001".)

## Prior art (citations kept visible)

- **Object-capability model + POLA (Dennis & Van Horn 1966; Miller, *Robust Composition*; Spritely Goblins).** Adopt: the *confused-deputy* lens — a credential is exactly the ambient authority a confused deputy leaks, so it must be a possessed, non-ambient reference resolved only by the holder, never readable by intermediaries. Adopt: the principle that authorizing an action and *holding the secret to perform it* are separable (the deputy is authorized; the secret stays with the resource). Reject: a full ocap object graph or OCapN networking in v1.
- **Macaroons (Birgisson et al., *Cookies with Contextual Caveats*, ACM CCS 2014; `libmacaroons`).** Adopt: caveat-based **attenuation** as the model for read-capability scoping — a coarse read capability can be minted into a strictly weaker one (namespace + entity + projection-profile + field-set caveats) **offline, without contacting an issuer**, via the chained-HMAC construction. Reject: third-party-caveat network round-trips except opt-in for genuinely remote discharge. theory.stanford.edu/~ataly/Papers/macaroons.pdf.
- **Credential broker / token-exchange patterns (SPIFFE/SPIRE workload identity; CI/CD credential brokers, arXiv 2504.14761; OS keychain MCP discussions, `anthropics/claude-code#15961`).** Adopt: the broker as a runtime decision point that *issues a short-lived, scoped credential* rather than handing back the long-lived secret — "the token never entered the caller's context." Adopt: OS keystore (macOS Keychain / Windows Credential Manager / Linux Secret Service) as the protected store of record, and **UDS peer-credential checks** to authenticate the calling adapter process (the SPIFFE workload-identity idea reduced to a single-host primitive). Reject: SPIFFE's distributed PKI/attestation machinery for a single-host daemon.
- **Data minimization for LLM prompting (arXiv 2510.03662 "Operationalizing Data Minimization for Privacy-Preserving LLM Prompting"; AI-gateway redaction patterns).** Adopt: *redact-by-default, send only the minimum the model needs, and prove it* — combined with a **content-free, hash-chained audit log** that records *that* redaction fired and *which categories* were redacted without storing the raw prompt. This is the exact shape of our `ambisphere.egress.performed` record. Reject: a probabilistic risk-scoring engine and an inline reversible-tokenization gateway as core dependencies (they may be adapter-side).
- **Information-flow control / data-flow control (Myers & Liskov decentralized label model; LUCON, arXiv 1805.05887).** Adopt: the *conceptual* frame that data carries a confidentiality classification and the system enforces where it may flow (here: at the egress and read boundaries). Reject (for v1): runtime taint-propagation through every derived value / a non-interference guarantee — too heavy for the single-user local case (see open questions).
- **CloudEvents `redaction`-style envelope hints + our envelope spec.** Adopt: the envelope's producer-proposed `redaction` field is a *hint* the egress policy may consult, **never** the security boundary (mirrors the action spec's "manifest flags are UX hints, not the boundary"). The boundary is the daemon/adapter policy check.

## Conformance to ADR-0001 and upstream specs

| Upstream invariant | How this spec honors it |
|---|---|
| ADR-0001 inv. 7 — credentials never in state/components/log | Made structural here: only `CredentialRef` (a secret-free name) is a permitted value type anywhere durable; `SecretLease`/`ExchangedToken` are non-serializable by construction (no `Serialize`, no leaking `Debug`), so they *cannot* land on the log or in a component even by mistake; the `submit` validator additionally runs a **precise byte-equality** check rejecting any envelope value byte-equal to a known keystore secret (a backstop, not a heuristic). The secret resolves only inside an adapter via the broker. |
| ADR-0001 inv. 5 — authority capability-shaped, write-only-gated; read separately gated | `CapabilityRef` (write) and `ReadCapability` (read) are distinct; redaction is applied at the read boundary; `CredentialRef` is a *third* primitive, neither a write nor a read authority — it authorizes an *adapter* to resolve a secret, gated by the adapter's own capability. |
| ADR-0001 inv. 6 — fact/narration firewall | Model *input* is firewalled and redacted like any egress; model *output* (narration) may return only into the `NarratedProjection` store (reducer spec), never the log, never a reducer input. Only egress adapters write narration (carried invariant). |
| ADR-0001 inv. 8 — vendor neutrality / **domain** types are zero in core | **Reconciled, not excepted.** Invariant 8 is read in its amended form: core ships **zero *domain* event types** (`khaos.*`/`loswf.*`), and core MAY reserve a small **closed, enumerated** set of *runtime-meta* `ambisphere.*` types that the runtime's own facts (egress audit, attention/focus/edge/entity/approval verbs) travel on. That allowlist is **owned by the envelope spec** (§ "Core-reserved event types"), not minted here. `ambisphere.egress.performed` is one entry on it. This spec does **not** carve a lone exception; it points at the single source of truth, and its vendor-neutrality lint references the same allowlist. The amendment must be ratified in ADR-0001 itself (open questions). |
| Envelope spec — `submit` is the only write path; `redaction` is producer-proposed; the core-reserved allowlist | The `ambisphere.egress.performed` record re-enters via `submit` as an ordinary semantic event on the **full envelope contract** (`specversion = "ambisphere.event/1"`, three-region ENVELOPE/PAYLOAD/RUNTIME split, daemon-assigned RUNTIME, `dataschema` resolving to a core artifact). The envelope `redaction` field is consumed as a *hint*, never trusted as the boundary. |
| Reducer spec — provenance `wasAttributedTo(adapter + capabilityRef, NEVER a credential)` | This spec is the authority for *why* provenance carries `capabilityRef` not a credential; it adds nothing to provenance, it constrains it. |
| Attention spec — `read_capability` gates which entities/facets are visible; reads may be redacted/coarsened | This spec defines *how* that redaction/coarsening is computed and what a read capability scopes. |
| Daemon spec — broker is the read/write enforcement point; summary index holds no credentials | This spec defines the broker's credential-resolution duty (with a pinned v1 auth model) and the read-redaction duty the daemon performs before frames leave. |
| Identity spec — `namespace` is the first `EntityAddress` segment; **owns the matching grammar** | This spec elevates `namespace` to the trust/privacy boundary that capabilities, credentials, edges, reads, and egress are scoped to, and **references the identity spec's canonical segment/glob/kind/namespace matching grammar** for caveats and read scopes rather than redefining it. |
| Action/capability spec — `locality` enum; `CapabilityRef` | This spec consumes the canonical `locality` enum `local | remote-read | remote-write` (action spec owns; bundle serialization aligns) when reasoning about which actions cross the egress boundary; `remote-write`/`remote-read` actions are exactly those that touch the broker + egress path. |

## The three primitives — capability, credential, read-capability

The single most important clarification this spec makes: **three distinct primitives**, never conflated.

```rust
/// WRITE authority. Possessed, unforgeable, attenuable (ocap-shaped).
/// Owned by the action/capability spec; checked ONLY at the write boundary.
/// Carries NO secret. Possessing it never reveals a credential.
struct CapabilityRef(/* opaque token bytes */);

/// READ authority. Scopes WHICH entities and WHICH facets/fields are visible.
/// Attenuable (macaroon-style caveats: namespace, entity, profile, field-set),
/// where entity/namespace match uses the identity spec's canonical grammar.
/// Checked at the read boundary (broker). Carries NO secret.
struct ReadCapability(/* opaque token bytes */);

/// A NAME for a secret. NEVER the secret. The ONLY credential-shaped value
/// permitted in any durable artifact (state, components, log, snapshot,
/// summary index, provenance, narration, envelope).
struct CredentialRef {
    /// Stable opaque id the broker resolves against the keystore.
    ref: String,            // e.g. "cred:01J..." — a handle, not a value
    /// What KIND of secret this names (for the adapter to know how to use it).
    scheme: CredentialScheme, // ApiKey | BearerToken | OAuthRefresh | BasicAuth | Custom(String)
    /// Which provider/system it is for (for routing + egress records).
    provider: String,       // bundle-defined, e.g. "github", "anthropic" — a label, not a vendor branch in core
    /// The namespace this credential is scoped to (trust boundary).
    namespace: String,
}
```

Worked distinction, in the words of the action/capability guidance: *"the capability authorizes the action; the adapter holds the secret; secrets never travel in the token."* A renderer may hold a `ReadCapability` and see that an entity *has* a configured credential (`provider: "github"`); it can never obtain the token. An action's `CapabilityRef` (a `remote-write` action, in the canonical `locality` enum) authorizes "rerun CI on this entity"; the *adapter* that performs the rerun resolves a `CredentialRef` through the broker to actually call GitHub. The two are minted, attenuated, and revoked independently.

**Why three and not two.** Folding the credential into the capability (a bearer-token-with-embedded-secret) would put a secret on the write path and, transitively, into provenance and audit records — exactly what inv. 7 forbids. Folding read into write breaks POLA (renderers would gain write authority to observe). Three primitives keep each concern minimal and independently revocable.

## The credential broker

Secrets are held by the daemon's broker (resolving against an OS keystore or daemon-encrypted store) and released **only into an authorized adapter process**, **never** to core reducers/queries, **never** to a renderer.

### v1 trust root (decided — no longer an open question)

The interfaces below cannot be conformance-tested (acceptance #2) against an undecided auth model, so v1 pins both ends of the trust root. These are normative for v1; a future security spike may harden specifics, but the *shape* is fixed:

- **Store-of-record: the OS keystore.** macOS Keychain / Windows Credential Manager / Linux Secret Service, with the **daemon as the sole reader**. The daemon's keystore item ACL names the daemon binary; no other local process may read the items.
- **Fallback store (no OS keystore present): a daemon-encrypted store.** Secrets are sealed (libsodium sealed-box / `age`) under a master key that is itself held in an OS-protected location (e.g. a file with `0600` perms under a keystore-derived key); decryption happens only in daemon memory.
- **Adapter authentication: UDS peer credentials + capability.** The broker is reachable only over the daemon's Unix-domain socket. The broker reads the **peer's OS credentials** (`SO_PEERCRED` / `LOCAL_PEERCRED`) to identify the calling adapter process, then requires the adapter to present its own `CapabilityRef` authorizing the requested credential's `provider`/`namespace`. Identity (peer creds) and authority (capability) are *both* required; neither alone suffices.
- **Namespace scope check.** The `CredentialRef.namespace` must match the namespace the adapter's capability authorizes, or an explicit cross-namespace grant must be present. Otherwise `CrossNamespaceDenied`.
- **Provisioning is out of band.** Putting a secret *into* the keystore is an operator/installer act (CLI `cred set`, OS keystore UI), never a runtime event. The runtime only ever *names* and *resolves*, never *ingests*, a secret.

```rust
/// Lives in the daemon. The ONLY code path that can turn a CredentialRef
/// into anything usable. Authenticates the calling adapter (UDS peer
/// credentials) AND checks the adapter's capability + namespace scope, then
/// either performs token-exchange or leases a short-lived secret.
trait CredentialBroker {
    /// Preferred path: the broker performs the outbound auth itself OR mints a
    /// short-lived exchanged token; the raw long-lived secret never leaves the daemon.
    fn exchange(
        &self,
        adapter: AdapterIdentity,     // authenticated caller (UDS peer creds: pid/uid/gid)
        cap: CapabilityRef,           // the adapter's own authority (checked against provider+namespace)
        cref: CredentialRef,
        scope: ExchangeScope,         // operation + audience + TTL request
    ) -> Result<ExchangedToken, BrokerError>; // short-lived, scoped, revocable

    /// Fallback (explicitly weaker): lease the raw secret for providers that
    /// cannot do token-exchange. Returns a guarded handle with a hard TTL;
    /// the lease is recorded. Marked DANGEROUS in the API surface.
    fn lease_secret(
        &self,
        adapter: AdapterIdentity,
        cap: CapabilityRef,
        cref: CredentialRef,
        ttl: Duration,
    ) -> Result<SecretLease, BrokerError>;
}

enum BrokerError {
    UnknownCredential,      // ref not in keystore
    Unauthorized,           // adapter capability does not cover this credential (or peer-cred check failed)
    CrossNamespaceDenied,   // cref.namespace != adapter's authorized namespace, no grant
    KeystoreUnavailable,    // OS keystore locked / absent and no fallback store configured
    SchemeUnsupported,      // exchange requested for a scheme that cannot exchange
}

/// A SecretLease zeroizes its buffer on drop and refuses to be serialized,
/// logged, or placed in any event/component (compile-time: no Serialize impl,
/// no Debug that prints the secret). ExchangedToken has the same property.
struct SecretLease { /* zeroizing, non-Serialize, non-Debug-leaking */ }
```

Rules:

- **No secret ever crosses into core.** Reducers and queries are pure and credential-free; the broker is reachable only from the adapter plane (over UDS), not from the reduce/query path. A `SecretLease`/`ExchangedToken` is structurally non-serializable, so it *cannot* be put on the log or into a component even by mistake — this is the load-bearing structural guarantee.
- **Token-exchange preferred over raw-secret lease.** Where the provider supports it, the broker performs the outbound authentication or mints a short-lived audience-scoped token, so the long-lived secret never leaves the daemon's memory. Raw-secret leasing is the explicitly-marked weaker fallback (and is recorded — see below).
- **Every resolution is authenticated, authorized, and namespace-checked**, per the v1 trust root above.
- **Resolution is recorded, content-free.** Each `exchange`/`lease_secret` contributes to the `ambisphere.egress.performed` audit when followed by egress; a bare resolution with no egress MAY be recorded as `ambisphere.credential.resolved` for audit **only if** that type is added to the envelope spec's allowlist (it is **not** in the v1 allowlist, so v1 records resolution implicitly via the lease/egress correlation in § guardrails, not as a distinct fact). v1 therefore relies on broker-internal lease accounting for the "lease with no matching egress" detector.

## The egress boundary

Any flow of entity-derived data to a remote model, provider, or API is an explicit adapter act, governed by an `EgressPolicy` declared **per entity-kind in the bundle**, **default-deny**. Egress is precisely the set of actions whose canonical `locality` is `remote-read` or `remote-write` (action spec); a `local` action never crosses this boundary.

### EgressPolicy (bundle-declared, per entity-kind)

```jsonc
{
  "policyId": "khaos.project.egress",        // bundle-defined; core never branches on it
  "policyVersion": 3,                         // bumped on any change; recorded in the audit
  "appliesToKind": "khaos.project",           // entity-kind (identity spec); EXAMPLE-LAYER value
  "defaultDecision": "deny",                  // fields not listed are NEVER sent (default-deny)
  "destinations": [
    {
      "destinationId": "model.summary",       // a logical remote sink (a model/provider/API)
      "credentialRef": "cred:01J...",         // which secret the adapter resolves to reach it
      "allow": [                              // ONLY these fields/facets may leave, transformed as stated
        { "field": "title",            "transform": "passthrough" },
        { "field": "phase",            "transform": "passthrough" },
        { "field": "blockedReason",    "transform": "passthrough" },
        { "field": "recentSummary",    "transform": "truncate", "maxChars": 2000 },
        { "field": "authorEmail",      "transform": "mask",      "keep": "domain" },
        { "field": "filePaths",        "transform": "tokenize" } // reversible placeholder, adapter-rehydrated
      ],
      "denyNarrationEcho": true               // model output may not re-quote denied fields verbatim
    }
  ]
}
```

- **`transform` vocabulary is small and bundle-referenced, not core-vendor.** v1 names `passthrough | truncate | mask | drop | tokenize | hash`. Core provides the *mechanism*; the *which-field-gets-what* is the bundle's declaration. There is **no built-in classifier**: a field is sensitive because the bundle says so by omitting it (default-deny) or transforming it, not because core recognized a pattern.
- **Applied before egress, in the adapter, deterministically.** Given the same component values + policy version, the redacted payload is identical (a replay/property test target). Non-deterministic detectors, if an adapter chooses to run them, run adapter-side and their decisions are recorded — they never become a core dependency.
- **Default-deny is the safety property.** A new component field added by a reducer is *not* egressed until the bundle author explicitly lists it. Forgetting to update the policy fails closed.

### The egress record (`ambisphere.egress.performed`) — content-free, full envelope contract

After (or atomically with) an egress, the adapter emits a fact via `submit`. This is *the record of what was sent* required by issue #5 §10. `ambisphere.egress.performed` is a **core-reserved event type drawn from the envelope spec's closed allowlist** — *not* a privacy-spec-local exception — and it travels the **identical envelope contract** as every other semantic event: `specversion = "ambisphere.event/1"`, the three-region ENVELOPE / PAYLOAD / RUNTIME split, producer-proposed `occurredAt`/`dedupeKey`/`dataschema`, and daemon-assigned RUNTIME. There is **no** CloudEvents-bare (`"1.0"`) shortcut and **no** flat document.

```jsonc
{
  // ============================================================
  // ENVELOPE — producer-proposed, domain-agnostic. The `type` here is a
  //            CORE-RESERVED value from the envelope spec's allowlist.
  // ============================================================
  "specversion": "ambisphere.event/1",                 // envelope contract version (NOT a CloudEvents 1.0 bare value)
  "type":        "ambisphere.egress.performed",        // CORE-RESERVED (envelope spec allowlist); not a domain type
  "source":      "adapter:khaos.summary",              // the producing adapter context (PROV agent basis)
  "entity":      ["khaos","project","atlas"],          // ADDRESS: compound segment LIST (the entity whose data left)
  "occurredAt":  "2026-06-10T18:22:05Z",               // proposed valid time (the adapter's clock; NOT trusted for order)
  "dedupeKey":   "egress:01J...:model.summary",         // producer-stable idempotency key
  "datacontenttype": "application/json",
  "dataschema":  "bundle:ambisphere.core@1/ambisphere.egress.performed.v1", // CORE ARTIFACT (shipped by ambisphere.core base bundle)
  "redaction":   "local-only",                          // hint only; the record itself never leaves the host

  // ============================================================
  // PAYLOAD — bundle/adapter-defined values core never branches on. CONTENT-FREE.
  // ============================================================
  "data": {
    "policyId": "khaos.project.egress",
    "policyVersion": 3,
    "destinationId": "model.summary",
    "destinationDescriptor": "anthropic:claude-…",  // a label, not a secret
    "credentialRef": "cred:01J...",                 // the NAME used; never the secret
    "capabilityRef": "cap:01J...",                  // the authority under which egress occurred
    "fieldsSent": ["title","phase","blockedReason","recentSummary","authorEmail","filePaths"],
    "redactionsApplied": [
      {"field":"recentSummary","transform":"truncate"},
      {"field":"authorEmail","transform":"mask"},
      {"field":"filePaths","transform":"tokenize"}
    ],
    "requestPayloadHash": "sha256:…",   // hash of the REDACTED payload that left — never the body
    "responseHash": "sha256:…",         // hash of what came back — never the body
    "outcome": "ok"                     // ok | denied | error
  }

  // ============================================================
  // RUNTIME — assigned by the daemon at ingestion (eventId, sequence, ingestTime,
  //           seed, logPosition, reducerSetVersion). NOT proposed by the adapter;
  //           omitted from the submit() input entirely (envelope spec § ingestion).
  // ============================================================
}
```

- **Bodies are never logged.** The prompt and the response are content-free in the record — only hashes, field names, and transform names. This mirrors the data-minimization audit pattern (hash-chained, content-free) and ensures the audit trail itself can never re-leak the content it audits.
- **The reserved type and its `dataschema` are core artifacts.** `ambisphere.egress.performed.v1` is shipped by the `ambisphere.core` base bundle so adapters and reducers can validate against it; it is registered on the envelope spec's allowlist. Privacy auditing is a *runtime-meta* concern (not domain content): the `entity`, `policyId`, and `destinationDescriptor` are bundle/adapter values core never branches on.
- **A denied egress is still recorded.** If the policy denies a field the adapter tried to send, `outcome: "denied"` is recorded; the egress does not occur. Fail-closed is auditable.

### Egress sequence (normative)

1. Adapter assembles candidate payload from a **read** of the entity's components (itself read-gated, see below).
2. Adapter loads the entity-kind `EgressPolicy`; applies `defaultDecision` + per-field `transform`. Any field not in `allow` is dropped.
3. Adapter resolves `credentialRef` via the **broker** (`exchange` preferred), obtaining a short-lived token/lease (authenticated by UDS peer creds + capability + namespace).
4. Adapter performs the remote call with the **redacted** payload and the exchanged token.
5. Adapter emits `ambisphere.egress.performed` (content-free, full envelope contract) via `submit`.
6. If the response is narration, the adapter writes it to the **NarratedProjection** store (never the log), tagged `kind:"narrated"`, grounded in the factual fields it was allowed to see.

## Read authority and read-side redaction

Read is gated separately from write (ADR-0001 inv. 5; attention spec inv. 4). A `ReadCapability` scopes both *which entities* and *which facets/fields* are visible, and the daemon computes the redacted projection **before frames leave the broker**. Entity/namespace targeting in `ReadScope` uses the **identity spec's canonical matching grammar** (exact segment, single-segment wildcard, prefix/multi-segment wildcard, `kind:`-via-`instance-of`, namespace match), referenced — not redefined — here.

```rust
/// Resolved at the read boundary (daemon broker) for every subscribe/query.
struct ReadScope {
    /// Namespaces/entities this capability can observe at all.
    /// EntityPredicate is the identity spec's address/kind/namespace matcher.
    visible: EntityPredicate,        // identity spec grammar (exact | wildcard | kind | namespace)
    /// Per entity-kind, which projection profile applies (named, bundle-declared).
    profile: ProfileSelector,        // e.g. "full" | "summary" | "redacted"
    /// Optional further attenuation: explicit allow/deny field set (caveat).
    fieldCaveats: Option<FieldSet>,
}

/// A named, bundle-declared read projection profile per entity-kind.
/// Mirrors EgressPolicy in shape but governs LOCAL reads, not remote egress.
struct ReadProfile {
    profileId: String,               // bundle-defined
    appliesToKind: String,
    defaultDecision: Decision,       // deny by default for unlisted facets
    allow: Vec<FacetRule>,           // facet/field -> passthrough|coarsen|mask|drop
}
```

- **Cross-entity and attention reads see a projection, never raw state.** `what_matters_now` (attention spec) and any cross-entity edge query return facets filtered through the caller's `ReadScope`. A caller without authority over an entity gets it **omitted or coarsened**, never raw — this is the attention spec's "redacted/coarsened facet" made concrete.
- **The always-resident summary index is already credential-free** (daemon spec), but read-redaction still applies to its facets: a low-authority caller may see only attention scalars and lifecycle, not identity details.
- **Redaction is computed in the daemon, before the frame leaves the broker.** Renderers/adapters never receive raw-then-filter; they receive already-redacted frames. The broker is the single enforcement point.
- **Read capabilities attenuate offline (macaroon-style).** A `ReadCapability` for `profile:"full"` over namespace A can be minted into a strictly weaker one (`profile:"summary"`, single entity, field-set caveat) without contacting the daemon, then handed to a less-trusted renderer.

## The namespace as the trust/privacy boundary

The first `EntityAddress` segment — `namespace` (identity spec) — is the unit of trust. Khaos data and LOSWF data live in different namespaces; that boundary is where default-deny bites. Namespace match uses the identity spec's grammar.

- **Capabilities and credentials are namespace-scoped.** A `CapabilityRef`/`ReadCapability`/`CredentialRef` names its namespace; authority does not leak across namespaces implicitly.
- **Cross-namespace edges are default-deny.** Creating a `child-of`/bundle-defined edge whose `source` and `target` straddle namespaces requires a capability authorizing *both* namespaces (resolves the identity spec's open question "must the privacy boundary gate edge creation into another adopter's subgraph?" → **yes**).
- **Cross-namespace reads require an explicit grant.** A renderer authorized for namespace A sees nothing in namespace B unless granted an attenuated read capability scoped into B.
- **Cross-namespace egress is doubly evaluated.** If data from namespace A is egressed via an adapter operating under namespace B's authority, *both* namespaces' egress policies apply (the more restrictive wins). (See open questions — deferred until cross-app delegation is real.)
- **Example, vendor-neutral framing.** "Khaos Machine granting LOSWFX narrow authority over one entity" (the cross-application sharing scenario from issue #5 / the guidance) is expressed as Khaos minting an attenuated `ReadCapability` caveated to one entity + a `summary` profile, scoped from the `khaos` namespace into a grant LOSWFX holds — never by sharing a credential, never by widening write authority.

## Non-goals restated as guardrails (surfacing the failure modes)

- **Credential-in-payload.** The single most likely leak is an adapter author stuffing an API key into `data` "for convenience." Guardrail (two layers, no fuzzy claim): (1) the **structural** guarantee — `CredentialRef` is the *only* credential-shaped type with a `Serialize` impl, and `SecretLease`/`ExchangedToken` are non-serializable by construction, so a resolved secret cannot be placed on the write path even deliberately; (2) the **backstop** — at `submit`, the daemon runs a **precise byte-equality** scan of envelope/payload values against the set of known keystore secret *byte strings* and rejects any exact match. This is deterministic and testable; it is **not** a regex/heuristic "looks like a key" classifier (core ships none). The byte-equality scan catches the literal copy-paste leak; the type system catches the programmatic one. Neither over-claims to detect a secret core has never seen.
- **Egress without a record.** An adapter calling a remote model and not emitting `ambisphere.egress.performed`. Guardrail: the reference adapter SDK's egress helper *requires* a policy and *emits* the record; bypassing it is a conformance failure, and the destination's credential lease is recorded by the broker (lease accounting) regardless, so an unrecorded egress is detectable (a broker lease with no matching `ambisphere.egress.performed` within its TTL window).
- **Raw read then client-side filter.** A renderer receiving raw state and "promising" to redact. Guardrail: redaction is daemon-side, pre-frame; the renderer never holds the raw value.
- **Narration laundering a denied field.** A model echoing a denied field back into narration that then becomes visible. Guardrail: `denyNarrationEcho` + narration template slots restricted to *allowed* factual fields (reducer spec firewall + persona-spec template validation).

## Acceptance criteria

1. **No credential in any durable artifact.** A property test scans the log, component tables, snapshots, summary index, provenance, and NarratedProjection store; with a known set of keystore secrets seeded, a **byte-equality** scan finds none present. The only credential-shaped values present are `CredentialRef`s. (This criterion is precise because the check is byte-equality, not pattern-matching.)
2. **Broker never returns a secret to core/renderer, and the trust root is real.** A test asserts: (a) the reduce/query path has no reachable `CredentialBroker` handle; (b) `SecretLease`/`ExchangedToken` have no `Serialize`/leaking-`Debug` impl (compile-time + reflection test); (c) a broker call from a process whose UDS peer credentials do not match an authorized adapter, or lacking a covering `CapabilityRef`, returns `Unauthorized`; (d) resolving a `CredentialRef` whose namespace the adapter is not authorized for returns `CrossNamespaceDenied`.
3. **Default-deny egress.** Given a component field not listed in the `EgressPolicy.allow`, egress of that field is impossible; adding the field to a reducer without updating the policy results in the field being dropped, not sent.
4. **Egress is recorded, content-free, on the envelope contract.** Every successful egress has exactly one `ambisphere.egress.performed` fact with matching `requestPayloadHash`; the fact validates against the envelope spec (`specversion = "ambisphere.event/1"`, three-region split, `dataschema` resolving to the `ambisphere.egress.performed.v1` core artifact); no prompt/response body appears anywhere durable. A broker lease with no matching record within its TTL window is flagged.
5. **Deterministic redaction.** Same components + same `policyVersion` ⇒ byte-identical redacted payload and identical `fieldsSent`/`redactionsApplied` (replay-equality target).
6. **Separate read gating + redaction.** A caller with a `summary`-profile read capability receives coarsened facets; a caller lacking authority over an entity receives it omitted; neither ever receives raw state. Redaction is observed to occur daemon-side (frames leave already-redacted).
7. **Namespace boundary enforced.** Cross-namespace edge creation, read, and credential resolution all fail closed without an explicit cross-namespace grant; the cross-app sharing scenario succeeds only via an attenuated read capability, never via credential sharing.
8. **Capability ≠ credential.** Possessing a `CapabilityRef` for an action never yields the secret needed to perform it; the secret is resolvable only by the adapter via the broker.
9. **No lone core-type exception.** A vendor-neutrality lint confirms the only `ambisphere.*` `type` literal this spec/its reference code introduces is `ambisphere.egress.performed`, and that it appears on the envelope spec's closed allowlist; no other core-defined `type` is introduced here.

## Open questions

- **Reversible vs one-way redaction.** Reversible tokenization lets a model operate on placeholders the adapter rehydrates, but reintroduces a secret-mapping table that must never be logged; v1 leans one-way drop/mask with reversible `tokenize` an opt-in adapter capability whose mapping table is held **in adapter memory only** (never via `submit`, never in a component).
- **Static classification vs runtime detectors.** v1 fixes static per-field bundle declaration (deterministic, replay-checkable). Whether adapter-side NER/regex detectors are permitted for free-text payloads — and how their non-deterministic decisions are recorded in `ambisphere.egress.performed` without becoming a core dependency — is open.
- **Where does `ambisphere.egress.performed` live** — the source entity's stream, a per-namespace audit-rollup entity, or both? Leaning the source entity's stream plus a derived per-namespace egress rollup; the rollup's entity-kind and reducer are unspecified pending the daemon/identity specs. (Whether a separate `ambisphere.credential.resolved` type should be *added* to the envelope allowlist for bare resolutions is also open; v1 does not add it.)
- **Cross-namespace sharing ceremony and double egress evaluation** — minted attenuated read capability vs explicit edge-with-grant; whether cross-namespace egress requires a second policy evaluation at the destination namespace (more-restrictive-wins). Leaning attenuated capability + double evaluation, deferred until cross-app delegation is real.
- **How far toward information-flow control?** v1 enforces at boundaries only. Whether a future version adds lightweight taint labels on components (so a "secret-derived" component cannot be egressed even if the policy author forgot) is open; the boundary-only model is the deliberate v1 scope cap.
- **ADR-0001 ratification.** This spec conforms to ADR-0001 as a **provisional** decision of record. The invariant-8 amendment it relies on — *domain* event types are zero in core, but a **closed, enumerated** set of runtime-meta `ambisphere.*` types (owned and listed by the envelope spec) is reserved — must be ratified in ADR-0001 itself, and ADR-0001's numbered invariant list completed, before the suite is implementation-ready. Until then, every "conforms to ADR-0001" claim (this spec included) is against a draft.
