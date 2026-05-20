# adws — AI Developer Workflows

Shell scripts that compose runtime adapters via `run_subagent`. Claude is still
the production default, but orchestration now resolves a runtime-specific
headless runner under `runtime/<name>/bin/headless-run.sh`. Each ADW is
single-purpose and emits structured events to `.loswf/state/events.jsonl`.

## Scripts

| Script | Purpose | Trigger |
| --- | --- | --- |
| `adw_feature.sh <issue>` | Full pipeline: intake → (architect)? → plan → review → build → review → ship | Per-issue, manual or webhook |
| `adw_chore.sh <issue>` | Abbreviated pipeline for XS chores (skips planning) | Per-issue; falls through to feature if S+ |
| `adw_review.sh <pr>` | Standalone review pass on a PR (factory or human-opened) | Per-PR |
| `adw_sweep.sh [--max-builds N]` | One full sweep cycle across all eligible issues | Cron / scheduled |
| `adw_harvest.sh [--cap N]` | Generate new issues from observed work | Scheduled (e.g. nightly) |
| `_lib.sh` | Shared helpers: `emit_event`, `run_subagent`, `get_phase`, `set_phase`, `require_phase`, `has_status`, `has_label`, `list_depends_on`, `depends_satisfied`, `all_children_done`, `log` | Sourced by all ADWs |

## Conventions

- POSIX-ish bash, `set -euo pipefail`
- Source `_lib.sh` from each ADW; never duplicate helpers
- Use `run_subagent <name> "<prompt>"` for headless invocation
- Select the runtime with `LOSWF_RUNTIME=<name>`; default is `claude`
- Event log: `.loswf/state/events.jsonl` — one JSON object per line
- Exit codes:
  - `0` — success or graceful skip
  - `64` — usage error
  - `65` — replan cap exceeded
  - `66` — unexpected phase after plan-review
  - `67` — builder failed to reach review phase
  - `68` — no PR linked after build
- Honor `factory:hold` and `factory:status:needs-attention` — skip those issues
- Worktrees (per-issue isolation for parallel sweeps) are left to the calling environment for v1; in-process bash sweep runs in the host checkout
- Sweep phase order lives in `.loswf/config.yaml` `sweep.sequence`, not in `adw_sweep.sh`. `adw_sweep.sh` is now a 37-line driver that calls `reset_work_counter`, `snapshot_phases`, then `run_sequence`. See design `docs/designs/curator-harvester-sequencing-remediation.md` §4.

### Work counter

`run_sequence` coordinates idle-tail phases against a per-sweep sentinel:

- **Path:** `$LOSWF_STATE_DIR/sweep.work_count` (truncated at sweep start by `reset_work_counter`).
- **Bump:** `bump_work_counter` is `printf '.' >> …` — a single-byte `O_APPEND` write, which POSIX guarantees atomic for writes strictly below `PIPE_BUF` (512 on macOS, 4096 on Linux). This makes the counter safe to bump from a `&`-forked builder subshell; the parent's `read_work_counter` (post-`wait`) sees every phase delta.
- **Read:** `read_work_counter` prints the current byte count (`0` if the sentinel is missing).
- **Idle gate:** phases with `idle_gated: true` in `sweep.sequence` (e.g. `harvest`, `curator-steward`) skip when `read_work_counter > 0`. By invariant, idle-gated phases also have `counts_as_work: false` — enforced by the `sweep-sequence-valid` validate gate.

### Error events

`run_sequence` normalizes error shape across the three phase `kind`s (`subagent`, `bash`, `command`). On non-zero dispatch exit, each dispatcher emits `emit_event <name> <issue> <agent-or-handler> error` and the sweep continues rather than halting — see the risks table in design `docs/designs/curator-harvester-sequencing-remediation.md` §4.

## Scheduling examples

```cron
# Sweep every 5 minutes during work hours
*/5 9-18 * * 1-5  cd /path/to/repo && ./adws/adw_sweep.sh >> .loswf/state/sweep.log 2>&1

# Harvest nightly at 02:00
0 2 * * *  cd /path/to/repo && ./adws/adw_harvest.sh --cap 10 >> .loswf/state/harvest.log 2>&1
```

## Webhook-driven (PITER) hookup

GitHub Issues `opened` or `labeled` event → tunnel (ngrok / Cloudflare) → small receiver invokes:

```bash
./adws/adw_feature.sh "$ISSUE_NUMBER"
```

The receiver should run in a worktree per invocation and de-dupe on issue number to prevent concurrent ADW runs on the same issue.
