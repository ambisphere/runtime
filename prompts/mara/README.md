# Mara Warmups

This directory holds the **canonical LOSWF interaction-layer assets** for the
Claude-first Mara plugin.

The intended use is not "another developer helper." Mara is the **primary
human interface to the factory** for the client or engagement side: she helps
people steer project work, delegate tasks into the factory, resolve issues, and
route LOSWFX bugs or feature requests back to the platform team.

## What lives here

- `base.md` — the shared Mara persona contract.
- `warmups.yaml` — the warmup manifest. This is the source of truth for the
  supported modes and their behavior.
- `.claude/tools/mara_widget.go` — read-only helper that packages LOSWFX
  readmodel state into compact Markdown cards.

The files under `.claude/commands/` are the Claude Code surface generated from
these assets. They should not drift from the manifest.

Claude companion commands such as `/factory`, `/queue`, and `/health` can run
the widget helper to surface compact factory-state cards for the human-facing
Mara interface.

## What a warmup is

A warmup is a **persistent session stance setter**:

- it activates Mara explicitly
- it defines audience, posture, and response structure
- it remains active until another warmup replaces it
- it keeps the interaction human-facing even when the underlying work is being
  delegated into the factory

Warmups are intentionally narrow. They shape responses; they do **not**
automatically trigger tools, workflows, or file mutations.

## How this differs from skills and workflows

- **Warmups** set the conversation mode and voice.
- **Skills** capture a reusable methodology for producing work.
- **Workflows** orchestrate multi-step execution engines.
- **State cards** surface live factory status in a compact human-facing form.

If the goal is "change how the assistant responds in this session," use a
warmup. If the goal is "teach the system how to perform a repeatable operation,"
use a skill. If the goal is "run a multi-step engine," use a workflow.

## Adding a new warmup

1. Add the mode to `warmups.yaml`.
2. Keep the fields complete and behavior-focused.
3. Add or update the Claude command file under `.claude/commands/`.
4. Run the warmup tests so manifest, command files, and prompt contract stay in
   sync.
