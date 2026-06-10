# Attention routing and interruption policy

**Status:** draft · **Scope:** the read-side attention component schema, the cross-entity ranking system ("attention bus"), the explainable cost-benefit score (with a **normative v1 default policy object**), the escalation ladder, operator focus modes, the "show me what matters now" ranked query, and the surface affordance map · **Companion to:** `specs/VISION.md`, `specs/SRS.md`, `RFP.md` (§ "Attention systems", "Human interruption models"), issues #4 #5 #6 · **Sequenced:** first among the follow-on specs per ADR-0001 and issue #4 · **Conforms to:** ADR-0001 (foundational paradigm + directionality invariant — see § "Conformance to ADR-0001" and the note on its provisional status under Open questions) · **Sibling notes:** `specs/drafts/runtime-paradigm-and-specs-guidance.md`, `specs/drafts/actor-model-prior-art.md`, `specs/drafts/persona-prior-art.md`, `specs/drafts/implementation-language-guidance.md`

This spec defines how Ambisphere decides **which entities deserve human visibility right now, on which surfaces, at what prominence** — issue #4's named "novel unsolved problem" and the reason it is sequenced first. Its facet shape (the `attention` component) and its read query contract are load-bearing: the reducer/state-component spec, the renderer observation contract, the persona projection, and the event envelope all attach downstream. This spec deliberately fixes those shapes and records where it leaves room.

It is a **read-side** spec. Per the ADR-0001 directionality invariant, nothing here writes a component directly, queries across actors on the write side, or treats attention as authoritative. Attention is a derived, rebuildable projection over the per-entity event log. Where the user must *do* something to attention state (snooze, defer, acknowledge, change focus mode), that is a capability-gated command on the **write** side that emits a fact event; the reducer then projects it. The two are kept rigorously distinct throughout.

## Goals and non-goals

### Goals

- Define a single normalized `attention` component every entity-kind can carry, domain-agnostic, with no vendor severity vocabulary.
- Define the attention bus as a read-side **system** (in the ECS sense) that ranks entities carrying the component, producing a ranked, explainable view.
- Define an explainable cost-benefit score adapted from Horvitz's decision-theoretic alerting — *the math, not the sensing* — **with concrete, normative v1 default weights and thresholds so the ranker is buildable and testable**. No inferred or sensed user attention.
- Define an escalation ladder (`quiet → ambient → nudge → prominent → blocking`) with a structural **bias downward** and bounded deferral.
- Define operator-selected **focus modes** (`flow` / `operational` / `away`) as a first-class policy input that multiplies interruption cost.
- Define **"show me what matters now"** as a ranked read query over the projection, not a notification feed.
- Define the **surface affordance map**: each surface declares which rungs it honors; prominence is negotiated, never assumed.
- Keep human-approval gates (write side) strictly distinct from prominence (read side), and **define the canonical projection of the action spec's approval gate onto the attention facet**.

### Non-goals (adopt/reject framing — rejections carried from the guidance)

- **Not** a notification system or "notification OS." We rank a queryable projection; we do not own a delivery feed, retry, or guaranteed-delivery alerting. (Reject: guaranteed-delivery alerting.)
- **Not** sensed/inferred attention. Context is **explicitly operator-selected** for privacy and determinism. No ML focus detection, no Bayesian attentional-state inference, no calendar/webcam/keyboard-idle sensing. (Reject: Horvitz's sensor-based attentional-state inference; adopt only his cost-benefit + bounded-deferral math.)
- **Not** authoritative. The attention component is a materialized view; it is never a source of truth and never written outside a reducer.
- **Not** per-renderer attention engines. One daemon-side ranker; surfaces observe. (Reject: per-renderer attention logic.)
- **Not** persona/tone in the ranking. Persona consumes attention; it never feeds it. (Reject: narrative/tone in ranking.)
- **Not** a write-path block. `blocking` is a renderer-honored prominence level, never a synchronous block of the daemon (see § "blocking is a prominence, not a gate"). (Reject: treating "blocking" as a write-path block.)
- **Not** domain severity vocabulary. `release-critical`, `analysis-failed`, etc. live in adapters and map *into* the normalized scalars. (Reject: domain-specific severity vocabulary in core.)
- **Not** the human-approval mechanism itself. The durable approval-gate state and the `approvals` component are owned by the action/capability spec; here it is only an input the bus may rank highly, projected onto the facet's `awaiting-human` state value (see § "The approval-gate projection").

## Prior art (citations kept visible)

- **Horvitz, Jacobs & Hovel, *Attention-Sensitive Alerting* (UAI 1999), and Horvitz et al. *bounded-deferral policies* (2001/2005).** Adopt: the decision-theoretic framing where the decision to alert minimizes **expected cost** = `cost-of-interruption` weighed against `cost-of-deferral / loss-of-value-with-delay`, and **bounded deferral** (hold a low-utility signal for a bounded time while the user is busy, release at a deadline). Reject: their probabilistic *sensing* of attentional state (the PRIORITIES-style inference of busyness from sensors). We replace the sensed attentional-state variable with an **operator-selected focus mode**. arxiv.org/abs/1301.6707; Microsoft Research, "Attention-Sensitive Alerting"; "Principles of Bounded Deferral for Balancing Information Awareness with Interruption."
- **Weiser & Brown, *The Coming Age of Calm Technology* (Xerox PARC, 1996).** Adopt: center/periphery framing — a calm system "moves easily from the periphery of our attention, to the center, and back"; periphery-default; recentering is a *pull*. The escalation ladder is a discretization of center↔periphery. Reject: physical-embodiment bias (Dangling String). calmtech.com/papers/coming-age-calm-technology.
- **Amber Case, *Principles of Calm Technology* (2015).** Adopt as heuristics (not normative): "technology should require the smallest possible amount of attention"; "fail gracefully" to a glanceable state. Treated as design intent behind the downward bias, not as schema.
- **Kleppmann, *DDIA* ch. 11–12 (stream–table duality, materialized views, derived data).** Adopt: attention is a **materialized view** over the event log; rankings are recomputed/derived, never authored; the always-resident attention summary index is a secondary derived index maintained alongside the primary projection (DDIA "derived data / secondary indexes"), letting the bus rank without waking cold entities. Reject: distributed/streaming-broker machinery.
- **RivetKit (`actor-model-prior-art.md`).** Negative result, kept visible: a production actor runtime has **no "query all actors" primitive**; cross-entity ranking *must not* be an actor or a coordinator super-actor. Adopt: persistent **alarms** as prior art for time-based escalation. Confirms attention is a read-side view, not an entity.

## Conformance to ADR-0001

The conformance table below cites ADR-0001's numbered invariants. ADR-0001's own ratification status is currently unresolved (see Open questions); this spec conforms to it **provisionally** and must be re-confirmed when ADR-0001 is accepted with its canonical numbered invariant list.

| Invariant | How this spec honors it |
|---|---|
| (1) Log is source of truth; components derived, read-only | `attention` is projected by reducers from log events; never written directly; rebuildable by replay. |
| (2) Directionality | Ranking is read-only ECS-shaped query; snooze/defer/ack/focus-mode are write-side capability-gated commands → fact events → reducer → component. The log is the seam. |
| (3) Determinism | Recency/decay are computed at **query time** from `as-of` minus event-stamped times; reducers never read the clock. **rung and score are NEVER cached anywhere; they are always computed at query time** (see § "The resident-index / rollup-cache invariant"). Tie-breaks use a total order over opaque handles, never map iteration order. Declarative reducer-input data (`attentionMap`) is folded into `reducerSetVersion` and delivered as stamped event context so reductions remain pure over `(prev, ev)` and replay byte-identically (see § "Reducer purity and the declarative attentionMap"). |
| (4) Per-entity total order only | The bus ranks the **materialized view**, not the raw log; it needs no cross-entity log order. |
| (5) Capability-shaped authority | Changing attention state requires a capability; the **read** of the ranked view is separately gated and may be a redacted/projected facet (see § privacy). |
| (6) Fact/narration firewall | Score inputs are factual scalars only. Persona/narration may *read* the ranked view; they are never inputs to the score and never written to the log. |
| (8) Vendor neutrality | Core ships zero severity/kind vocabulary; adapters map domain severity into the normalized scalars. |

## The `attention` component (the facet shape — load-bearing)

Every entity that wishes to participate in routing carries exactly one `attention` component. It is intentionally **minimal and normalized**: domain meaning is compressed into a small set of unit-scalars and enums so the bus is domain-agnostic. Adapters/reducers are responsible for the mapping (a LOSWF `ci.failed` becomes high `urgency`+`importance`+`actionability`; a Khaos speculative-analysis failure becomes low ones — same schema).

```jsonc
// attention component v1 — a derived, read-only projection facet.
// Produced ONLY by a deterministic reducer. Never authored, never authoritative.
{
  "schemaVersion": 1,

  // --- normalized scoring inputs (unit interval [0,1], domain-mapped) ---
  "urgency":      0.0,   // how time-sensitive: value decays if ignored (the "loss with delay")
  "importance":   0.0,   // stakes if missed, independent of time
  "actionability":0.0,   // is there a human action available now? (0 = purely informational)

  // --- temporal dynamics (declarative; evaluated at QUERY time, not in the reducer) ---
  "decay": {
    "model": "none | linear | exponential | step",
    "halfLifeMs": 0,          // EXPONENTIAL ONLY: ms for urgency to halve. Ignored by other models.
    "rampMs": 0,              // LINEAR ONLY: ms over which urgency ramps from raw to floor. Ignored by other models.
    "stepAfterMs": 0,         // STEP ONLY: ms after anchor at which urgency drops to `stepTo`.
    "stepTo": 0.0,            // STEP ONLY: the post-step urgency value (clamped to >= floor).
    "anchorTime": "RFC3339",  // event-stamped; the t0 the decay is measured from
    "floor": 0.0              // urgency never decays below this (e.g. an SLA breach stays urgent)
  },

  // --- lifecycle state machine (semantic, set by reducer from facts) ---
  // `awaiting-human` is the CANONICAL attention value for a pending human-approval gate
  // (the action spec's approvals.pending[].state == "awaiting"; see § "The approval-gate projection").
  "state":  "dormant | active | awaiting-human | acknowledged | resolved | expired",

  // --- deferral surface (PROJECTED from write-side commands; see firewall note) ---
  "deferUntil":  "RFC3339 | null",   // operator/system bounded-deferral deadline
  "snoozeUntil": "RFC3339 | null",   // operator-chosen suppression deadline
  "ackBy":       "capabilityRef | null", // who acknowledged (provenance ref, never a credential)

  // --- ladder & escalation policy (declarative inputs to the bus) ---
  "ceiling":     "quiet | ambient | nudge | prominent | blocking", // max rung this entity may ever reach
  "escalation": {
    "enabled": false,
    "afterMs": 0,             // age in `awaiting-human`/`active` after which the bus raises one rung
    "maxRung": "ambient",     // never escalate above this even with time
    "stepRungs": 1            // rungs raised per escalation tick (default 1 — bias is +1, not jump-to-top)
  },

  // --- provenance (W3C PROV-shaped; required, factual) ---
  "provenance": {
    "lastEventId": "ulid",      // the event that last moved this facet
    "lastEventTime": "RFC3339", // event-time (occurred-at), stamped at ingestion
    "kind": "factual"           // ALWAYS factual here; narration may never write this component
  }
}
```

Design notes:

- **Why unit-scalars, not a single "severity".** A single severity number cannot express "important but not urgent" (a quietly accruing backlog) vs "urgent but low-stakes" (a transient that self-heals). Splitting `urgency`/`importance`/`actionability` is what lets the score be both explainable and domain-neutral. This is the direct read-side analogue of Horvitz separating loss-with-delay from cost-of-interruption.
- **`decay` is declarative, evaluated at query time.** The reducer stamps `anchorTime` from the event; it does **not** compute current urgency (that would require a clock, violating invariant 3). The bus computes effective urgency at `as-of`. This keeps reducers pure and makes recency a query concern (resolving the guidance open question "escalation-over-time via alarm vs age-at-query" toward **age-at-query**, with alarms reserved only for waking cold entities — see § daemon co-design). The per-model parameters (`halfLifeMs`, `rampMs`, `stepAfterMs`/`stepTo`) are decay-invariant inputs and may be cached in the resident index; the resulting urgency may not.
- **`ceiling` vs the surface affordance map.** `ceiling` is per-entity ("this entity may never block"); the affordance map is per-surface ("this tray never renders modal"). Effective prominence is `min(score-derived rung, entity ceiling, surface max, focus-mode cap)`. Every cap biases **down**.
- **`deferUntil`/`snoozeUntil`/`ackBy` are projections of write-side facts.** The reducer writes them only in response to logged `attention.deferred` / `attention.snoozed` / `attention.acknowledged` events (see § write-side commands). They appear in the read component for query convenience; they are not a back-channel.

## The approval-gate projection (firewall between write and read, made concrete)

The action/capability spec owns the durable human-approval mechanism: an action declared `confirmRequired`/`destructive` emits an `approval.requested` fact that the action reducer projects into an **`approvals` component**, whose entries carry `state ∈ { awaiting | granted | denied | expired }`. That spec's prose calls the open condition "approval-requested" state.

This spec fixes the canonical mapping so a reducer authoring the attention facet has an unambiguous target value:

- The **canonical attention value for a pending approval gate is `awaiting-human`.** When an entity has any `approvals.pending[].state == awaiting`, the core/bundle attention reducer sets the `attention.state` to `awaiting-human`.
- **One term per side, cross-referenced both ways.** "approval-requested" is the **action-domain label** for exactly this condition; `awaiting-human` is its **attention-facet projection**. The two names denote the same condition; there is no separate `approval-requested` value in the attention `state` enum, and there must not be one (a second name for the same state would re-introduce the ambiguity this finding flagged). The action spec, the persona spec, and the daemon summary index all refer to the ranked condition as `awaiting-human`.
- **The bus ranks on `awaiting-human`, not on the `approvals` component.** The bus never reads `approvals` directly; it ranks the projected attention facet. This keeps the directionality clean: approval authority flows on the write side; prominence flows on the read side; the projection is the seam.
- The action spec's statement "the bus may rank an approval-requested entity as high as `prominent`" is therefore precise: such an entity carries `attention.state == awaiting-human` and is ranked exactly like any other facet — high `importance`/`actionability`, typically — capped by `ceiling`/surface/mode like everything else. It is **not** auto-promoted to `blocking` (see § "blocking is a prominence, not a gate").

Cross-spec note (normative for the action and persona specs): both refer to this condition as `awaiting-human` on the attention facet and as `approval-requested` only in action-domain prose; persona's `attention.state=awaiting-human` key (persona spec § state map) is the correct, canonical key.

## The escalation ladder

Five ordinal rungs, a discretization of Weiser & Brown's periphery↔center continuum, with the strict order `quiet < ambient < nudge < prominent < blocking`:

```
quiet      — suppressed; excluded from default ranked view; counts only in explicit "everything" queries
ambient    — peripheral; a glanceable posture/badge change; never moves to center on its own
nudge      — a gentle one-shot recentering cue; no modality, no blocking; dismissible
prominent  — persistent center-of-attention presence (e.g. a sticky card / tray emphasis)
blocking   — renderer MAY render a modal; honored ONLY by surfaces that declare it; never a daemon block
```

**Structural downward bias (normative):**

1. The **default rung is `ambient`**, not `nudge`. A new active entity surfaces peripherally.
2. The bus computes a rung from the score, then applies `min(...)` against every cap (`ceiling`, surface max, focus cap). Caps can only lower.
3. Escalation up the ladder is **time-gated and bounded** (`escalation.afterMs`, `maxRung`, `stepRungs` default 1). A signal climbs one rung at a time as it ages unacknowledged; it never jumps to `blocking` on arrival.
4. **De-escalation is automatic and free**: passing `snoozeUntil`/`deferUntil`, decay below thresholds, or transition to `acknowledged`/`resolved` drops the rung at query time with no event required.
5. `blocking` requires **both** entity `ceiling: blocking` **and** a surface that declares `honorsBlocking`. Absent either, it degrades to `prominent`. (Reject: blocking-by-default.)

### `blocking` is a prominence, not a gate

Per guidance contradiction (3): a human-approval requirement is a **write-side** concern. A `confirmRequired`/`destructive` action emits durable approval-gate state (the action spec's `approvals` component, projected to attention `awaiting-human` per § above). The attention bus MAY rank that entity as high as `prominent` — even persistently — but the runtime never synchronously blocks. `blocking` here means only "a surface is permitted to render a modal"; it grants **zero** authority and does not pause any reducer or write. Approval authority flows exclusively through capability-gated actions on the write side. This is the firewall between *human-approval gates* (write) and *prominence* (read) the focus mandates.

## Cost-benefit score (explainable, no sensing)

The bus assigns each participating entity a scalar **attention score** and a derived rung. The score is an **expected-utility-of-interruption** adapted from Horvitz, with the sensed attentional-state term replaced by the operator's focus mode.

```
effUrgency(e, asOf)   = applyDecay(e.urgency, e.decay, asOf)          // query-time decay
benefit(e, asOf)      = w_u·effUrgency + w_i·importance + w_a·actionability
interruptCost(e, mode, rung) = modeCost[mode] · rungCost[rung]        // mode multiplies cost
score(e, asOf, mode)  = benefit(e, asOf) − λ · interruptCost(e, mode, targetRung)
```

### `applyDecay` — exact closed forms (all clamped to `floor`)

`applyDecay(u, decay, asOf)` is pure and deterministic given `asOf`. Let `Δ = max(0, asOf − decay.anchorTime)` in milliseconds (an `asOf` before the anchor clamps `Δ` to 0, yielding raw `u`). Let `f = decay.floor`. Every model returns `max(f, raw_model_value)`, additionally clamped to `[0, 1]`.

- **`none`** — `applyDecay = u`. (No time dependence; `floor` still applies but is a no-op when `f ≤ u`.)
- **`exponential`** — half-life `h = decay.halfLifeMs` (`h > 0` required; `h ≤ 0` is a validation error). `applyDecay = max(f, u · 0.5^(Δ / h))`. Asymptotes toward `f`.
- **`linear`** — ramp `r = decay.rampMs` (`r > 0` required). Urgency ramps linearly from `u` at `Δ=0` to `f` at `Δ=r`, then holds at `f`: `applyDecay = max(f, u − (u − f) · min(1, Δ / r))`. Equals `u` at `Δ=0` and exactly `f` for `Δ ≥ r`.
- **`step`** — `applyDecay = u` while `Δ < decay.stepAfterMs`; `applyDecay = max(f, decay.stepTo)` once `Δ ≥ decay.stepAfterMs`. (A single discrete drop; for multi-step behavior, ship richer logic in a reducer module per the bundle/reducer specs — the facet stays single-step.)

`halfLifeMs` is meaningful **only** for `exponential`; `rampMs` **only** for `linear`; `stepAfterMs`/`stepTo` **only** for `step`. The bundle validator (bundle spec L2) rejects a facet whose `decay.model` does not carry its required parameter (`halfLifeMs > 0` / `rampMs > 0` / `stepAfterMs ≥ 0`). All four forms are reproducible byte-for-byte given the same `(u, decay, asOf)`, satisfying acceptance criterion #3.

### Normative v1 default policy object

Weights and thresholds are **policy, not code**, but v1 ships **concrete normative defaults** so the ranker is buildable and the acceptance criteria (deterministic, reproducible rankings + explanations) are satisfiable. The default policy object is:

```jsonc
// attention-policy v1 — NORMATIVE DEFAULTS. Tunable; precedence is layered (see § policy precedence).
{
  "policyVersion": 1,
  "weights":   { "w_u": 0.45, "w_i": 0.35, "w_a": 0.20 },   // sum to 1.0; benefit ∈ [0,1]
  "lambda":    1.0,                                          // interruption-cost weight
  "modeCost":  { "flow": 1.0, "operational": 0.5, "away": 0.15 }, // flow > operational > away
  "rungCost":  { "quiet": 0.0, "ambient": 0.15, "nudge": 0.40, "prominent": 0.70, "blocking": 1.00 },
  "rungThreshold": {            // highest rung whose threshold the score clears
    "quiet":     null,          // floor; an entity below `ambient` is `quiet`/excluded
    "ambient":   0.20,
    "nudge":     0.45,
    "prominent": 0.65,
    "blocking":  0.85
  }
}
```

Rung selection: compute `benefit(e, asOf)`; then for candidate rungs from highest to lowest, compute `score(e, asOf, mode)` against that rung's `rungCost` and accept the highest rung whose `score ≥ rungThreshold[rung]` (`quiet`/`null` is the catch-all floor). Then cap: `rung = min(rawRung, ceiling, surfaceMax, focusCap)`. Because `interruptCost` depends on the target rung, evaluation is top-down: a high `modeCost` (e.g. `flow`) raises the cost of high rungs and naturally pushes the accepted rung down — this **is** the bounded-deferral knob.

- `applyDecay` is pure (above). Deterministic given `asOf`.
- `modeCost[flow] > modeCost[operational] > modeCost[away]` — in `flow`, interruption is expensive, so only very high-benefit signals clear the bar; in `away`, interruption is cheap (the user is not in a protected task), so more reaches center. This is the **bounded-deferral knob expressed as a cost multiplier**, the spec's single substitution for Horvitz's sensed busyness.
- **Explainability is required (for audit, per guidance "whether the attention bus must be auditable").** Every ranked result MUST carry an `explanation` enumerating the contributing terms and the binding cap, so "why is this prominent / why was this suppressed?" is always answerable.

### Worked example (sample entity → explanation block)

Apply the v1 defaults to a concrete entity. Inputs: `urgency=0.9`, `importance=0.8`, `actionability=0.4`; `decay={model:"exponential", halfLifeMs:3_600_000, anchorTime:T0, floor:0.10}`; `asOf = T0 + 1_800_000` (30 min, i.e. half of one half-life); `mode = operational`; `ceiling = blocking`; surface honors up to `prominent`; focus cap (operational) = none.

1. **Decay:** `Δ/h = 1_800_000 / 3_600_000 = 0.5`; `0.9 · 0.5^0.5 = 0.9 · 0.7071 = 0.6364`; above `floor 0.10` ⇒ `effUrgency ≈ 0.62` (rounded for display; `0.6364` used in arithmetic).
2. **Benefit:** `0.45·0.6364 + 0.35·0.8 + 0.20·0.4 = 0.2864 + 0.28 + 0.08 = 0.6464`.
3. **Rung selection (top-down, operational ⇒ modeCost 0.5):**
   - `prominent`: `score = 0.6464 − 1.0·(0.5·0.70) = 0.6464 − 0.35 = 0.296`; threshold `0.65` ⇒ **fails**.
   - `nudge`: `score = 0.6464 − 1.0·(0.5·0.40) = 0.6464 − 0.20 = 0.446`; threshold `0.45` ⇒ **fails by 0.004**.
   - `ambient`: `score = 0.6464 − 1.0·(0.5·0.15) = 0.6464 − 0.075 = 0.571`; threshold `0.20` ⇒ **passes**. Raw rung = `ambient`.
4. **Caps:** `min(ambient, ceiling=blocking, surfaceMax=prominent, focusCap=none) = ambient`. Binding cap is the score itself (`boundBy: "score"`).

The same entity in `away` mode (`modeCost 0.15`): `prominent` score `= 0.6464 − 0.15·0.70 = 0.541` (< 0.65, fails); `nudge` score `= 0.6464 − 0.15·0.40 = 0.586` (≥ 0.45, passes) ⇒ raw rung `nudge`. This is the focus-mode knob doing its job: the identical facet recenters more readily when the operator is `away`.

```jsonc
// explanation for the operational-mode evaluation above
"explanation": {
  "benefit": 0.6464,
  "terms": { "urgency": {"raw":0.90,"decayed":0.6364,"weighted":0.2864},
             "importance": {"raw":0.80,"weighted":0.280},
             "actionability": {"raw":0.40,"weighted":0.080} },
  "interruptCost": 0.075,          // modeCost[operational]·rungCost[ambient] = 0.5·0.15
  "mode": "operational",
  "score": 0.571,                  // benefit − λ·interruptCost at the ACCEPTED rung
  "rawRung": "ambient",
  "boundRung": "ambient",
  "boundBy": "score",              // one of: score | entity-ceiling | surface-max | focus-mode-cap | snoozed | deferred | decayed
  "policyVersion": 1,
  "asOf": "RFC3339"
}
```

Weights (`w_u`, `w_i`, `w_a`, `λ`, `modeCost`, `rungCost`, `rungThreshold`) are **policy**, not code. v1 ships the fixed defaults above with the weight vector itself a replaceable policy object; precedence is layered (see § policy precedence). This answers the open question "pluggable vs fixed ranker" as **fixed algorithm, tunable weights** for v1.

## Focus modes (operator-selected context)

Exactly three modes ship in core; adapters/bundles MAY define additional modes by supplying a `modeCost` multiplier (kept domain-neutral — no `release-mode`).

```jsonc
{
  "mode": "flow | operational | away",
  "scope": "global | entityGroup",   // see open questions on per-group modes
  "groupSelector": null,             // when scope=entityGroup: an edge/kind predicate
  "since": "RFC3339",
  "setBy": "capabilityRef"           // changing mode is a capability-gated write-side command
}
```

- **flow** — protect deep work. Highest interruption cost (`modeCost 1.0`); in practice only signals with `benefit` well above the relevant `rungThreshold + rungCost` recenter.
- **operational** — actively watching systems. Moderate cost (`0.5`); `prominent` reachable; the default for an operator at a console.
- **away** — not present / async catch-up. Low cost (`0.15`); signals accumulate and may reach `prominent`/`blocking` (subject to caps) because there is no protected task to interrupt; effectively "show me everything that piled up."

Mode is set by the operator (or by an adapter the operator authorized) via a logged command — it is a **fact**, replayable, never sensed. The guidance open question "minimum mode set / global vs per-group" is answered as: **three modes minimum; global by default, per-entity-group permitted** via `scope`, so a desktop running a Khaos creative `flow` group and a LOSWF operational group simultaneously is expressible (see open questions for precedence subtleties).

## "Show me what matters now" — the ranked read query

The flagship affordance is a **query over the projection**, not a feed. It is the canonical read-side contract this spec hands downstream.

```rust
// Read-side query contract (language-neutral; Rust sketch per ADR-0001 core = Rust).
// Pure over the materialized view + secondary attention index. No write authority.
pub struct AttentionQuery {
    pub as_of: Timestamp,                 // explicit; decay/recency computed against this
    pub mode: FocusMode,                  // current operator focus mode (or per-group resolved)
    pub surface: SurfaceId,               // caller surface; binds the affordance map
    pub min_rung: Rung,                   // default `ambient`; `quiet` only on explicit request
    pub scope: Option<EntityPredicate>,   // kind/edge/parent filter (read-side ECS query)
    pub limit: Option<u32>,
    pub include_explanation: bool,        // default true
    pub read_capability: CapabilityRef,   // gates WHICH entities/facets are visible (redaction)
    pub policy: Option<PolicyRef>,        // resolved layered policy; defaults to the v1 default object
}

pub struct RankedEntity {
    pub entity: EntityHandle,             // opaque internal handle (not the address)
    pub score: f64,                       // computed at query time; NEVER read from a cache
    pub rung: Rung,                       // computed at query time, then capped by ceiling/surface/mode
    pub state: AttentionState,
    pub explanation: Option<Explanation>,
    pub roll_up: Option<RollUp>,          // present for parent entities (see hierarchy)
}

pub trait AttentionRead {
    /// Ranked, capped, explainable. Pure given (view, index, as_of, policy). rung and score are
    /// ALWAYS computed here from decay-invariant inputs + as_of — never served from a cache
    /// (see § the resident-index / rollup-cache invariant). Determinism: ties broken by a total
    /// order over opaque handles, never map iteration order (ADR-0001 invariant 3).
    fn what_matters_now(&self, q: &AttentionQuery) -> Vec<RankedEntity>;
}
```

Properties:

- **Pull, not push (calm-tech recentering-as-pull).** Surfaces *ask*; the bus does not deliver. A subscription variant (below) is sugar over re-running the query on view change, not a guaranteed-delivery channel.
- **Deterministic given `(as_of, policy)`.** Two calls with the same `as_of`, `policy`, and view return identical rankings — required for testability and for the explanation to be reproducible.
- **`read_capability` separately gates read** (ADR-0001 invariant 5 + guidance privacy boundary): the bus may see a **redacted/projected** attention facet, not raw entity state. A caller without authority over an entity gets it omitted or coarsened, never raw. This answers the guidance open question "whether read authority and write authority are separately gated" → **yes, separately**.
- **Subscription sugar:** a renderer MAY subscribe to "the ranked view for (surface, mode, scope)"; the daemon re-evaluates on relevant view deltas **and on `as_of` advance** (so a decaying or escalating entity re-ranks even with no new event) and pushes the new ranked slice with a monotonic cursor. This is latest-wins ambient state (no backpressure queue), consistent with the renderer-contract guidance.

## The resident-index / rollup-cache invariant (cross-spec, normative)

The always-resident attention summary index (owned physically by the daemon spec) and any materialized `child-of` rollup cache exist so the bus can rank without waking cold entities. To preserve "identical rankings for identical `(view, as_of, policy)`", they MUST cache **only decay-invariant values**:

```
ALLOWED in the resident index / rollup cache (decay-invariant):
  raw scalars (urgency, importance, actionability), decay params (model + halfLifeMs/rampMs/stepAfterMs/stepTo + floor),
  anchorTime, lastEventTime, state, ceiling, parent, childCount, contributing-set (handles of children at/above min_rung),
  escalation policy fields.

FORBIDDEN anywhere (must be computed at query time from the above + as_of + policy):
  effUrgency, benefit, score, rung, rawRung, boundRung, rollUp.rung.
```

A cached `rung` or `score` is `as_of`-and-decay-dependent; serving it would return stale results and break this spec's determinism guarantee. This rule is normative for all four read-side specs:

- **This spec:** `RankedEntity.rung`/`.score` and `RollUp.rung` are query-time computed; the schemas above carry no cached rung.
- **Entity-identity spec:** its summary-index example must NOT cache `lastAttentionSummary.rung`/`score`; it caches the decay-invariant scalars + state + ceiling + edges only.
- **Daemon-architecture spec:** `EntitySummary.attn` already caches only scalars/state/ceiling/anchor/lastEventTime (correct, keep as-is); its `RollupSummary` must drop any cached `rung`/`score` and store only `childCount` + `contributing` (count and/or handle set) + the decay-invariant child scalars needed to compute the parent rung at query time. The materialized rollup is a cache of decay-invariant aggregates, not of a rung.
- **Persona-projection spec:** `presence` must be derived from an **`as_of`-computed** rung supplied by the attention channel for the persona's evaluation `as_of`, not from a cached rung; the rung still wins on any disagreement.

## Surface affordance map

Each surface declares, at attach (LSP-style capability handshake, per renderer-contract guidance), which rungs it honors and its presentation budget. The bus uses this to cap prominence per surface — the same entity is `prominent` on a dashboard card and `ambient` on a tray.

```jsonc
{
  "surfaceId": "tray.macos.menubar",
  "kind": "tray",                  // semantic, not presentational (tray|card|widget|tui|chat|palette|companion|...)
  "honoredRungs": ["quiet","ambient","nudge"],  // this surface caps at `nudge`
  "honorsBlocking": false,
  "maxConcurrent": 3,              // how many ranked entities it can show at once
  "supportsExplanation": true,    // can it surface "why?"
  "projectionSchemaVersion": 1,
  "ignoresUnknownRungs": true     // forward-compat degradation
}
```

- `surfaceMax = max(honoredRungs)`; the bus never asks a surface to render a rung it did not declare.
- Unknown future rungs degrade to the highest known honored rung (forward-compat).
- The map is **advisory to the renderer and authoritative to the bus** only for capping — it grants no action authority (renderers have zero action capability by default, POLA).

## Hierarchy rollup

The read side traverses the `child-of` edge (per entity-identity guidance, exactly two built-in relations). A parent entity's attention is a **derived rollup** of its participating children, never authored, and **its rung is computed at query time** (per the resident-index invariant above).

```jsonc
"rollUp": {
  "rule": "max | weighted-sum | adapter-defined",   // v1 default: max
  "childCount": 12,
  "contributing": 3,                  // children at/above min_rung (decay-invariant set, cacheable)
  "topChild": "entityHandle",         // the child driving the parent's rung (drill-down target)
  "rung": "prominent"                 // COMPUTED at query time from child scalars + as_of; never cached
}
```

- **v1 default rule is `max`** (parent is as loud as its loudest child) — the calm-tech "ambient signal that can drill down to actionable detail" from RFP scenario C. `weighted-sum` and `adapter-defined` are permitted via per-kind policy.
- Rollup is computed from the **always-resident attention summary index**, so a factory-level entity can summarize children without waking cold child entities (the DDIA secondary-index move that resolves the attention-vs-isolation tension; co-designed with the daemon spec). The index supplies the children's **decay-invariant** scalars; the parent's rung/score is derived at query time.
- This answers the guidance open question "rollup rule" → **max default, policy-overridable**; "rollup determinism" → computed at query time over the index, deterministic given `as_of` (because nothing rung-shaped is cached).

## Write-side commands (kept distinct — the seam)

Operating on attention is a **write-side, capability-gated command** that emits a fact event; the reducer then projects it into the component. These are the *only* ways attention state changes. The bus never mutates anything.

```jsonc
// Commands (write side). Each requires a capability and emits a fact event.
// Core ships these as domain-neutral attention verbs; adapters do not invent severity.
"attention.snooze"      // { until }            -> emits attention.snoozed
"attention.defer"       // { until, boundedMax } -> emits attention.deferred (bounded-deferral deadline)
"attention.acknowledge" // {}                    -> emits attention.acknowledged
"attention.resolve"     // {}                    -> emits attention.resolved
"attention.setFocusMode"// { mode, scope, groupSelector } -> emits focus.modeChanged
```

- **Bounded deferral (Horvitz):** `defer` carries a `boundedMax`; the reducer stamps `deferUntil`; at `as_of ≥ deferUntil` the bus stops suppressing and (if `escalation.enabled`) resumes climbing. A deferred signal cannot be deferred indefinitely — the deadline is the contract.
- Snooze/defer/ack/mode-change all become **fact events on the log**, so the audit trail answers "who silenced this and when" — satisfying the operational-auditability requirement (issue #5 §4) and making attention itself auditable.
- These verbs are core and **domain-neutral**; an adapter mapping `release.approved` to an `attention.resolve` is adapter-layer translation, not core branching on `loswf.*`. Likewise the action spec's approval grant/deny resolves the `awaiting-human` state by the same path.

## Reducer purity and the declarative `attentionMap`

A bundle raises attention without core branching on its event types by shipping a declarative `attentionMap` (bundle spec): the core attention reducer reads the mapping as **data** to turn a domain event into normalized scalars. This is data, not a module, so the naive reading — "the reducer consults `attentionMap`, which is neither `prev` nor `ev`" — would violate the reducer-purity rule "a reducer may read only `prev` and `ev`" (reducer spec) and create a replay hazard (editing a bundle's `attentionMap` would change derived scalars with no logged fact and no captured version, so replaying an old log under the new map would not be byte-identical).

This spec fixes the rule (normative for the reducer, bundle, and event-envelope specs):

1. **`attentionMap` is part of `reducerSetVersion`.** Any declarative data the core reducer consults to produce a component (the `attentionMap`, and any analogous declarative reducer-input table) is included in the `reducerSetVersion` content hash (bundle spec § derivation). Changing the map changes `reducerSetVersion`.
2. **The envelope stamps `reducerSetVersion` at ingest** (envelope spec RUNTIME region). The version in force when the event was ingested is therefore a stamped fact on the event.
3. **The map is read as part of the stamped event context, preserving `(prev, ev)`-purity.** The reducer receives the `attentionMap` *for the stamped `reducerSetVersion`* as part of `ev`'s resolved context (the daemon resolves it from the installed bundle set keyed by the stamped version). The reducer still reads only `prev` and `ev`; the map is not ambient state, it is event-context data pinned by the stamped version.
4. **A `reducerSetVersion` bump forces deterministic re-projection.** Because a changed map yields a new `reducerSetVersion`, snapshots tagged with the old version are discarded and the projection is rebuilt from the log (reducer spec inv. 8) — so the derived scalars always match the map version that was in force, and replay-equality holds: replaying under the *same stamped version* is byte-identical; replaying after a deliberate map change is a deliberate, versioned re-projection, not a silent drift.

The reducer spec's purity section should state this explicitly so the "`(prev, ev)`-only" rule and the `attentionMap` mechanism no longer contradict each other: declarative reducer-input data is admissible **iff** it is captured in `reducerSetVersion` and delivered as part of the stamped event context.

## Acceptance criteria

1. **Schema fixed.** The `attention` component v1 (above) is the canonical facet; the reducer spec defines reducers that produce it; no other spec redefines its fields. `awaiting-human` is the sole attention value for a pending approval gate.
2. **Read-only.** A property test demonstrates the component is producible *only* via reducer-over-log and is byte-identical on replay under a fixed `reducerSetVersion` (ADR-0001 invariants 1, 3).
3. **Determinism.** `what_matters_now` returns identical rankings for identical `(view, as_of, mode, surface, scope, policy)`; tie-breaks are by total order over handles. A replay-equality test covers decay-at-query for all four decay models (`none`/`linear`/`exponential`/`step`). No cached rung/score exists to test against — the test asserts the index holds only decay-invariant fields.
4. **Downward bias.** Default rung is `ambient`; `blocking` is reachable only with both entity `ceiling: blocking` and a `honorsBlocking` surface; absent either it degrades to `prominent`. Covered by tests.
5. **Explainability.** Every ranked result carries an `explanation` with the binding cap (`boundBy`) and `policyVersion`; the worked example above is reproduced by the reference ranker bit-for-bit (modulo display rounding).
6. **Firewall.** `provenance.kind` is always `factual`; no narration field exists in the component; a test asserts narration cannot write it. Human-approval gates remain write-side and project to `awaiting-human`; `blocking` performs no daemon block.
7. **Vendor neutrality.** Core contains zero severity/kind/`khaos.*`/`loswf.*` vocabulary; an example adapter (in `examples/`) demonstrates mapping a domain severity into the scalars via `attentionMap`.
8. **Separate read gating.** A caller lacking read capability over an entity receives it omitted/coarsened, never raw (privacy boundary).
9. **Surface capping.** The same entity renders at different rungs on two surfaces with different affordance maps, driven solely by `surfaceMax`.
10. **Bounded deferral.** A deferred signal re-enters ranking at its `deferUntil` deadline and cannot be deferred past `boundedMax`.
11. **Policy & defaults present.** The v1 default policy object (concrete weights/thresholds above) is the shipped default; the ranker is buildable from this spec alone, and a tuned policy object replaces it without code change.
12. **attentionMap replay safety.** Changing a bundle's `attentionMap` changes `reducerSetVersion`, discards old-tagged snapshots, and re-projects; replay under a fixed `reducerSetVersion` is byte-identical (joint test with the bundle/reducer/envelope specs).

## Open questions

- **ADR-0001 status.** No `ADR-0001` file exists in `specs/drafts/`, yet all nine follow-on specs declare "Conforms to: ADR-0001" and cite numbered invariants (1–8) as binding, while the guidance note treats the paradigm as draft. The suite cannot be implementation-ready while its foundational ADR is unwritten/unaccepted. **Resolution direction:** author `ADR-0001` carrying the canonical numbered invariant list these conformance tables already cite (1 log-is-truth, 2 directionality, 3 determinism, 4 per-entity-total-order, 5 capability authority, 6 fact/narration firewall, 7 credentials-never-in-state, 8 vendor neutrality) and set a single status. Until ADR-0001 is Accepted, this spec (and its siblings) conform to it **provisionally** and must be re-confirmed on acceptance. Recorded here rather than silently fixed because the ADR is out of this spec's ownership.
- **Ordinal vs continuous urgency.** v1 uses continuous `[0,1]` scalars + an ordinal rung. Whether adopters need a coarser ordinal urgency (3–5 buckets) for hand-authored entities is open; the scalar is the contract, buckets could be sugar.
- **Policy precedence under per-group modes.** When `scope=entityGroup` modes overlap (an entity in two groups with conflicting modes), which wins — most-protective (max interruption cost), most-specific selector, or operator-pinned? Leaning most-protective; must be specced before per-group ships.
- **Who owns the weight vectors and mode/cost defaults beyond v1.** The v1 defaults are normative here, but the layered override path (product default → bundle → operator override) and whether an operator override is itself a logged fact (probably yes) needs the reducer/identity specs to land.
- **Escalation mechanism at the storage layer.** Age-at-query is the default; but for an entity that must *wake a cold child* to escalate (e.g. ring louder after 30 min with the child hibernated), a persistent alarm is needed. The boundary between age-at-query (cheap, default) and alarm-driven wake (for cold entities) is co-designed with the daemon spec and not fully fixed here.
- **Rollup beyond single-parent.** `max` over `child-of` assumes single-parent containment (clean). If multi-parent edges land (entity-identity open question), the rollup dedup/aggregation rule must be defined.
- **Graceful degradation when the ranked stream is unavailable.** Calm-tech says "fail to glanceable." The fallback view when the bus/index is rebuilding after a crash is unspecified; likely "serve last-good index snapshot, flagged stale" — and, per the resident-index invariant, even that snapshot carries only decay-invariant inputs, so a stale-flagged ranking is still recomputed from them at the fallback `as_of`.
- **Index contents.** Exactly which fields live in the always-resident attention summary index is co-owned with the daemon spec; minimally `(handle, kind, parent, scalars, decay params, anchorTime, state, ceiling, lastEventTime)` — all decay-invariant; never a rung/score.
- **Should `quiet` entities be fully excluded or returned flagged.** v1 excludes from default queries; some surfaces (an "everything" audit view) want them returned with a `suppressed` flag rather than omitted.
- **Whether `actionability` should be derived from the action manifest rather than reducer-set.** It currently is a reducer-set scalar; once the action/capability spec lands, `actionability` could be *computed* from "are there capability-authorized actions whose preconditions hold?" — cleaner, but couples the read side to the manifest. Open.
