---
name: charm-tui
description: Build modern interactive terminal UIs in loswfx with the Charm v2 stack (charm.land/bubbletea/v2 + bubbles/v2 + lipgloss/v2 + huh/v2). Use when adding or refactoring an interactive TUI surface (a live dashboard, picker, wizard, monitor). It FORBIDS the legacy github.com/charmbracelet/* v1 modules and hand-rolled components (spinners, lists, help bars) — v1 components are wired to a different bubbletea and cannot feed the v2 Update loop. Covers the model contract, concurrent commands, the ready-made bubbles component set, lipgloss v2 styling against the shared internal/termui palette, the interactive-or-static fallback contract, and Bubble Tea unit-testing. Use a different skill (product) to design the UX first; this skill is the implementation methodology.
side: client
contract:
  kind: methodology
  inputs: []
  outputs: []
  verify:
    - skill-frontmatter
---

## Use the v2 stack. Never v1.

loswfx runs on the **`charm.land`** v2 line. Use these and only these:

| Concern | Module |
|---|---|
| Runtime / model loop | `charm.land/bubbletea/v2` |
| Ready-made components | `charm.land/bubbles/v2/...` (spinner, list, viewport, table, help, key, textinput, progress, …) |
| Styling | `charm.land/lipgloss/v2` |
| Forms / prompts | `charm.land/huh/v2` |

**Forbidden:** `github.com/charmbracelet/bubbletea`, `.../bubbles`,
`.../huh` (the v1 line), and any hand-rolled component you could get from
bubbles (spinners via `tea.Tick` frame counters, manual key-hint
strings, ad-hoc scrolling).

### Why — the field lesson

The v1 and v2 lines are **type-incompatible**. `charm.land/bubbletea/v2`
defines `type Msg = uv.Event` and `type Cmd func() Msg`. The v1 bubbles
(`github.com/charmbracelet/bubbles`) import the v1 bubbletea, whose
`Cmd` is `func() interface{}`. A v1 component's `Tick`/`Update` returns a
v1 `Cmd` that **cannot** be returned from a v2 `Init`/`Update` — different
types. That is why mixing them forces View-only hacks (rebuild the
component every frame, never drive its `Update`) and forces hand-rolled
spinners. Don't. Put the whole stack on v2 and the components work
natively in the loop.

If you find v1 imports, migrate: swap the import paths, run
`go mod tidy`, and fix the one common break — see Styling below.

## The Bubble Tea v2 model contract

```go
import tea "charm.land/bubbletea/v2"

type model struct{ /* state */ }

func (m model) Init() tea.Cmd { return tea.Batch(/* initial cmds */) }

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
    switch msg := msg.(type) {
    case tea.WindowSizeMsg:               // msg.Width, msg.Height
    case tea.KeyPressMsg:                 // msg.String() => "q","enter","ctrl+c","up"…
        switch msg.String() {
        case "q", "ctrl+c":
            return m, tea.Quit              // tea.Quit is a Cmd; it emits tea.QuitMsg
        }
    case myResultMsg:                      // your own async results
    }
    return m, nil
}

func (m model) View() tea.View { return tea.NewView(m.render()) }
```

- `View()` returns a `tea.View` — wrap your string with `tea.NewView(s)`;
  read it in tests as `m.View().Content`.
- Launch: `tea.NewProgram(m, tea.WithContext(ctx), tea.WithOutput(w)).Run()`.
  Add `tea.WithAltScreen()` for a full-screen app that restores the
  scrollback on exit; omit it for inline surfaces.

## Concurrency — stream work as commands

Run slow work (network probes, subprocess calls, file IO) as commands,
never inline in `Update`. Fan out with `tea.Batch`; deliver each result
as a custom message; let the model fill in as they arrive.

```go
func (m model) Init() tea.Cmd {
    cmds := []tea.Cmd{m.spin.Tick}
    for i, job := range m.jobs {
        i, job := i, job
        cmds = append(cmds, func() tea.Msg { return doneMsg{i, job.Run()} })
    }
    return tea.Batch(cmds...)
}
```

`tea.Tick(d, fn)` schedules a future message (animation, polling). Keep
ticking only while work is in flight, then let it stop.

## Use the components — don't reinvent them

`charm.land/bubbles/v2` ships, at minimum: **spinner, list, viewport,
table, progress, paginator, textinput, textarea, filepicker, timer,
stopwatch, help, key**. Each is a sub-model with `Update`/`View`; embed
it, forward messages to it in `Update`, render it in `View`.

Spinner (the canonical "I reached for v1" trap — use this instead):

```go
import "charm.land/bubbles/v2/spinner"

sp := spinner.New()
sp.Spinner = spinner.Line                 // ASCII-safe; or .Dot, .MiniDot
sp.Style = lipgloss.NewStyle().Foreground(termui.Accent)
// Init: return sp.Tick
// Update: case spinner.TickMsg: m.sp, cmd = m.sp.Update(msg); return m, cmd
// View:   m.sp.View()
```

Keybindings + help bar — use `key.Binding` + `help.Model`, not a
hand-written hint string:

```go
import ("charm.land/bubbles/v2/key"; "charm.land/bubbles/v2/help")

type keymap struct{ Up, Down, Enter, Quit key.Binding }
func (k keymap) ShortHelp() []key.Binding { return []key.Binding{k.Up, k.Down, k.Enter, k.Quit} }
func (k keymap) FullHelp() [][]key.Binding { return [][]key.Binding{{k.Up, k.Down}, {k.Enter, k.Quit}} }

km := keymap{Up: key.NewBinding(key.WithKeys("k","up"), key.WithHelp("k/↑","up")), /* … */}
// match with key.Matches(msg, km.Up); render with help.New().View(km)
```

Forms / prompts (a confirm, a multi-field wizard): use `huh` rather than
building input handling by hand.

## Styling — lipgloss v2 + the shared palette

Import the brand palette from **`internal/termui`** (theme.go) — it is the
single source of truth for the DESIGN.md §2 colors and reusable styles.
Do not redefine hex literals in a new surface.

```go
import "charm.land/lipgloss/v2"
import "github.com/loswf/loswfx/internal/termui"

style := lipgloss.NewStyle().Foreground(termui.Accent).Bold(true)
out := style.Render("text")
w := lipgloss.Width(out)                  // display width, ANSI-aware
```

**The one v2 break to know:** `lipgloss.Color` is now a *function*
(`func(string) color.Color`), not a type. Call-sites like
`lipgloss.Color("#3D85C6")` still work. For a *type annotation* (a struct
field, a return type), use `color.Color` from `image/color`:

```go
func statusColor(s string) color.Color { … }   // NOT lipgloss.Color
```

### Color & non-TTY output (the v2 gotcha that breaks tests)

lipgloss v1's default renderer auto-detected the terminal and stripped
color for non-TTY output. **lipgloss v2 does not** — `Style.Render`
emits truecolor ANSI unconditionally. Render styled text straight to a
pipe / file / test buffer and you get raw escape codes, and any test
asserting a string that spans two styled tokens (e.g. `"LOSWF Console
provider probe"`) fails because escapes sit between them.

The fix in this repo is a global gate in `internal/termui`:

- `termui.SetColorEnabled(bool)` — the CLI entrypoint turns color ON
  only for a real terminal (`isCharDevice(os.Stdout) && NO_COLOR unset`);
  it defaults OFF, so tests and pipes are plain.
- `termui.Sanitize(s)` — strips ANSI when color is off, passthrough
  otherwise. `termui.Header`/`RenderPanel` already route through it.

Rules:
- Any code that builds styled output with **raw lipgloss** (a TUI
  `View()`, a custom help screen) must wrap its final string in
  `termui.Sanitize(...)` so the gate applies. Every TUI model here does:
  `return tea.NewView(termui.Sanitize(b.String()))`.
- Do NOT reach for `colorprofile.NewWriter(w, os.Environ())` to fix
  this — it honors `COLORTERM`/`CLICOLOR_FORCE` and will keep coloring a
  non-TTY buffer. Gate on the destination being a real terminal instead.

### Brand rules (DESIGN.md §1–§3, non-negotiable)

- Palette only: accent-blue `#3D85C6` marks LOSWFX surfaces; state colors
  `#7ec07e`/`#e8c040`/`#c06060`; surface `#161616`; muted `#888888`. No
  gradients, no other colors.
- **No emoji-as-UI** and **no color-only signaling** — every status reads
  via a glyph/letter AND its color, so monochrome terminals still parse it.
- Prefer ASCII-safe glyphs and `spinner.Line` so it renders anywhere.
- New interactive surfaces author/extend **DESIGN.md §3 component
  stylings** for any new primitive.

## Interactive-or-static: the fallback contract

A TUI must degrade cleanly. Run the interactive program ONLY on a real
terminal; otherwise emit static text or JSON (never ANSI into a pipe/log).

```go
if jsonRequested { return writeJSON(w, report) }
if forcedPlain || !isTTY(stdout) || os.Getenv("TERM") == "dumb" {
    return renderStatic(w, report)        // shares the same data layer
}
return runInteractive(w)                   // bubbletea program
```

Detect a TTY with the char-device check on both stdout and stdin
(`fileInfo.Mode()&os.ModeCharDevice != 0`). Share the data/check layer
between the interactive and static paths so they can't drift.

## Testability

Bubble Tea models are pure functions — test them without a terminal:

- Drive `Update` with constructed messages:
  `m.Update(tea.KeyPressMsg{Code: 'r', Text: "r"})`,
  `m.Update(tea.KeyPressMsg{Code: tea.KeyEnter})`, your own result msgs.
- Assert rendered output via `m.View().Content` (contains check).
- Assert a quit: the returned `cmd()` is a `tea.QuitMsg`.
- Keep ranking/verdict/selection logic in pure helper methods and unit
  test those directly; the view is a thin projection.

## Workflow for a new surface

1. **Design first.** Run the product-design workflow (`product` skill /
   `cycle dispatch --role designer`) to produce a spec — states, layout,
   keyboard model, accessibility — before coding. Land it in the shadow
   repo.
2. Build the model to the spec on the v2 stack, composing bubbles
   components and the `termui` palette.
3. Add the TTY guard + static/JSON fallback.
4. Unit-test the model (Update transitions, View content).
5. Register any new flags (args + flag registry); run `./scripts/check.sh`.

## Canonical example

`internal/cli/cli_doctor_tui.go` — the `loswfx doctor` model: streaming
checks (spinner), ranked rows, focus/expand, re-run, TTY-guarded
fallback, brand-themed via `internal/termui`. Read it before building a
new surface. The operator console (`internal/tui/operator.go`) is the
multi-panel reference.

## Pitfalls

- **Reaching for `github.com/charmbracelet/*` v1.** It will compile in
  isolation but cannot join the v2 loop. Always `charm.land/.../v2`.
- **Hand-rolling a spinner / list / help bar.** Use bubbles.
- **`lipgloss.Color` as a type.** It's a func in v2; annotate with
  `color.Color`.
- **Redefining the palette per surface.** Import `internal/termui`.
- **Leaking ANSI into pipes/CI.** Gate the interactive program on a TTY.
- **Logic in the view.** Keep it in testable helpers.
