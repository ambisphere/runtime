# Implementation language — guidance

**Status:** draft · **Scope:** language selection per architectural tier; depends on the paradigm in `specs/drafts/runtime-paradigm-and-specs-guidance.md` · **Companion to:** `specs/VISION.md`, `RFP.md`, issues #4 and #5 · **Sibling notes:** `specs/drafts/runtime-paradigm-and-specs-guidance.md`, `specs/drafts/actor-model-prior-art.md`

This note records the implementation-language determination for the runtime. It does not commit code; it records the recommended language per tier, the rubric that discriminated, the cross-tier comparison, and the open questions. The decision is **best language per job**, not one language for everything — a single-language approach was considered and abandoned because no candidate is best across all tiers, and the architecture's IPC boundaries make a polyglot stack clean.

## Decision summary

- **Core daemon → Rust.**
- **Renderers → best language per platform** (Swift/SwiftUI on Apple, Kotlin/Compose on Android, TypeScript on web, a Tauri shell for Linux/Windows desktop, Go/Bubbletea for TUI).
- **Adapters → polyglot**, in the language of the source system, emitting the semantic event envelope.
- **Reference adapter SDK + CLI + bundle tooling → Rust**, alongside a language-neutral wire spec so no adapter is forced to depend on it.

This is low-regret: the two seams that cross language boundaries — the renderer **observation contract** (one-way UDS + cursor-resumable stream) and the adapter **event envelope** (over the same socket) — are language-neutral by design (per the paradigm guidance). A renderer or adapter can be rewritten in another language without touching the core.

## Why a single language was abandoned

No candidate is best across all tiers. The single-language contenders each force a compromise:

- **Swift** is the only candidate strong at *both* the core daemon and a renderer tier (Apple), but off-Apple native UI depends on younger bridges (Skip, SwiftCrossUI), and a headless daemon does not reward its unification advantage.
- **Kotlin** (Compose Multiplatform + KMP) has the broadest *stable* renderer reach (iOS + Android + desktop stable, web beta) but the core daemon is its weak link (JVM/Kotlin-Native footprint for an always-on process).
- **Rust** is the strongest, safest core and excellent at non-GUI surfaces (TUI, web via WASM, adapters) but weak at native mobile/desktop GUI.

Because the architecture already decouples the edges via IPC, the polyglot option dominates: pick the best core, and the best renderer per surface, independently.

## Rubric (core daemon)

In priority order, derived from the paradigm guidance: ① memory safety → object-capability *unforgeability* (a memory bug forges capabilities); ② type system → compile-time enforcement of *derived-never-authoritative*, the *fact/narration firewall*, and capability types; ③ deterministic-reducer control (byte-identical replay); ④ embedded SQLite-as-log quality; ⑤ low idle footprint for an always-on daemon (GC pressure); ⑥ per-entity mailbox concurrency fit; ⑦ single-binary local-first distribution; ⑧ maturity/stability (do not found on a moving target); ⑨ ecosystem (crypto for macaroons, serialization); ⑩ contributor pool.

## Cross-tier comparison

Ratings: ●●● strong / first-party-stable · ●● good · ◐ partial / bridged / younger · ○ weak · — none.

| Language | Core daemon | Apple UI | Android UI | Desktop UI (Lin/Win) | Web UI | TUI | Adapters | Span verdict |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|---|
| **Rust** | ●●● | ◐ | ◐ | ●● | ●● | ●●● | ●●● | Best core + non-GUI surfaces; native mobile GUI weak |
| **Swift** | ●●● | ●●● | ◐ Skip | ◐ SwiftCrossUI | ◐ Wasm | ◐ | ●● | Best core+UI combo — superb on Apple, bridged off-Apple |
| **Kotlin** | ◐ JVM weight | ●● | ●●● | ●●● | ●● beta | ◐ | ●● | Broadest stable renderer reach; weak core |
| **C#/.NET** | ●● AOT | ◐ | ●● | ●●● Avalonia | ●● Blazor | ◐ | ●● | Genuinely broad dark horse |
| **TypeScript** | ○ | ●● | ●● | ●●● | ●●● | ●● | ●●● | Renderers + adapters only; cannot own the core |
| **BEAM** (Elixir/Gleam) | ●●● | — | — | — | ●●● LiveView | ○ | ●● | Core + web; no native GUI |
| **Go** | ●● | ○ | ○ | ◐ | ○ | ●●● Bubbletea | ●●● | Core + TUI + adapters; GUI weak |
| **C++** | ●● unsafe | ●● Qt | ◐ | ●●● Qt | ◐ | ◐ | ●● | Broad via Qt, but memory-unsafe core |

C, Zig omitted: no renderer story, and ruled out of the core (C/C++ memory-unsafety undermines capability unforgeability; Zig is pre-1.0 with unstable async/IO — fails "do not found on a moving target").

## Per-job determination

### Core daemon → Rust

**Adopt:** Rust for the headless system-of-record daemon. Ownership/borrow checking enforces the read-only-projection and capability invariants at compile time (stronger than value-semantics alone); no runtime/GC suits an always-on process with hibernating entities; `rusqlite` + WAL is first-class for the event log; the systems ecosystem is deepest for our specific needs (serde for CBOR/JSON, mature crypto for macaroons); single static cross-platform binary is trivial.

**The decision that was made:** core = Rust vs Swift was the one genuinely contestable pick. Swift 6.4 is a co-leader (memory-safe, ADTs, ARC = no GC pauses, actors/`Sendable` for the write side, GRDB for SQLite) and remains a fully defensible alternative decided by team fluency. It was set aside for the *core* because, with language-unification abandoned, a headless daemon rewards Rust's compile-time invariant enforcement, zero-runtime footprint, and ecosystem depth — and Swift keeps its home as the flagship Apple renderer regardless.

**Reject (for the core):** C / C++ (memory-unsafety undermines the ocap security model); Zig (pre-1.0, unstable async/IO); JVM-Kotlin / Node-TypeScript (footprint/weak invariant enforcement for an always-on system of record).

**Determinism caveat (applies to whatever core is chosen):** reducers must never iterate a randomized-order map. In Rust, use `BTreeMap`/`IndexMap`, never raw `HashMap` iteration, inside reducers; pair with the replay-equality property test the paradigm guidance already mandates.

### Renderers → best per platform

**Adopt:**
- **Apple (macOS/iOS, tray, menubar, companion) → Swift / SwiftUI.** Best-in-class native UX; the flagship surface.
- **Android → Kotlin / Jetpack Compose.** The platform's native language.
- **Web (dashboard cards, command palette, chat panel) → TypeScript** (React/Svelte).
- **Desktop (Linux/Windows rich widget) → reuse the web renderer in a Tauri shell** (Rust shell + TS UI), avoiding a fourth UI toolkit and matching the core language at the shell.
- **TUI → Go / Bubbletea** (existing `tui-component-design` + `go-testing` skill leverage); Rust/ratatui is the alternative if keeping it in the core language is preferred.

**Reject:** forcing one UI toolkit across all surfaces (fights renderer-agnosticism and yields a worst-of-all-platforms UX); any renderer holding authoritative state (it subscribes only).

### Adapters → polyglot

**Adopt:** each adapter in the language of the system it integrates (khaosd/khaos-wfl in whatever Khaos uses; GitHub/CI in TypeScript or Go). Adapters only translate native events into the envelope and never depend on the core. Ship a Rust reference adapter SDK plus a language-neutral wire spec.

**Reject:** a vendor SDK requirement; any adapter linking the core daemon as a library dependency.

## Prior art / citations to keep visible

- **Rust** — `rusqlite` (SQLite/WAL), serde, the object-capability fit of ownership; see `specs/drafts/actor-model-prior-art.md` for RivetKit lessons. github.com/rust-lang/rust.
- **Swift 6.3/6.4** — official Android SDK, static Linux SDK, Windows Workgroup, server-side production maturity, Swift 6.4 reduced-annotation concurrency. swift.org/blog/whats-new-in-swift-may-2026, infoq.com/news/2026/04/swift-6-3-android-c-interop.
- **Kotlin** — Compose Multiplatform 1.8 made iOS stable; desktop stable, web beta. blog.jetbrains.com/kotlin (Compose MP 1.8.0).
- **Swift cross-platform UI** — Skip (SwiftUI→Compose, open-sourced Jan 2026) and SwiftCrossUI (GTK/WinUI backends, nascent). infoq.com/news/2026/01/swift-skip-open-sourced, github.com/moreSwift/swift-cross-ui.
- **TUI** — Bubbletea / Charm (Go). **Desktop shell** — Tauri (Rust + web). **Zig** — pre-1.0 status, blog.jetbrains.com (Why Zig Isn't 1.0 Yet, June 2026).

## Open questions

- Final core pick ratification: Rust is recommended; confirm via ADR (the Rust-vs-Swift trade-off should be recorded explicitly with the deciding factors).
- TUI language: Go/Bubbletea (skill leverage) vs Rust/ratatui (single-core-language discipline) — pick when the renderer contract is specced.
- Desktop GUI: Tauri (web-in-shell) vs Kotlin Compose MP desktop vs a Rust-native toolkit (Slint/Dioxus) — depends on how rich the desktop widget must be beyond what the web renderer covers.
- Reference adapter SDK scope: Rust-only first, or a second SDK in TypeScript/Go to lower the adapter-authoring barrier for common integrations.
- Contributor readiness: no Rust or Swift skills are currently installed in the working environment (Go tooling is); a small ramp cost for the chosen core language should be planned.
- Cross-compilation / packaging targets: which OS/arch matrix the single-binary daemon must ship (macOS arm64/x86_64, Linux, Windows) and the supervision integration per platform (launchd/systemd).

## Relationship to the paradigm guidance

This determination assumes the paradigm in `runtime-paradigm-and-specs-guidance.md`: a capability-gated actor-bounded write side over a per-entity append-only event log, with an ECS-shaped read-side materialized view. Rust serves the write-side capability boundary (compile-time-enforced unforgeable capabilities), the event log + deterministic reducers (no-runtime determinism), and the read-side projection (typed components). The language choice and the paradigm should be ratified together — likely as ADR-0001 (paradigm) with the language determination recorded alongside or as a companion ADR.
