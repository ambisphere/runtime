#!/usr/bin/env python3
"""Render a Remotion composition via `npx remotion render`.

Thin wrapper that:
  - Validates the requested composition ID exists (npx remotion compositions --quiet).
  - Materializes --props as a temp JSON file (Windows shells don't accept inline JSON).
  - Resolves a tier preset (preview / default / max / prores-4444-xq) into
    codec + concurrency + jpeg-quality flags. Tier presets are documented
    in the remotion-render skill.
  - Shells out to `npx remotion render`.
  - Writes a structured receipt JSON beside the rendered file.
  - Captures wall-clock duration, output file size, exit code, stderr tail.

Modeled on generate_image.py's pattern: take the inputs, shell out, write
a receipt, exit 0/1/2 cleanly. No SDK dependency — just `npx` on PATH.

CLI:
  render_remotion.py --project <dir> --composition <id> --out <path.mp4>
                     [--props-file <path.json>]
                     [--tier preview|default|max|prores-4444-xq]
                     [--codec h264|h265|vp9|prores|png]
                     [--concurrency N]
                     [--frames START-END]
                     [--entry src/index.ts]
                     [--no-validate-comp-id]

Exit codes:
  0 — render succeeded, receipt written.
  1 — render failed (npx exited non-zero); receipt written with error.
  2 — operator error (bad args, missing project, comp id not found, missing npx).

Receipt schema: loswf-remotion-render-receipt-v1.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

RECEIPT_SCHEMA = "loswf-remotion-render-receipt-v1"

# Tier presets translate human intent into concrete flags. Modeled on the
# rendering-guide in RinDig/Content-Agent-Routing-Promptbase, simplified.
# Each tier carries codec + extra flags; concurrency defaults to 4 unless
# the caller overrides.
TIER_PRESETS = {
    "preview": {
        "codec": "h264",
        "extra": ["--jpeg-quality=70"],
        "doc": "Fast draft. Lower quality, fast turnaround.",
    },
    "default": {
        "codec": "h264",
        "extra": ["--jpeg-quality=85"],
        "doc": "Balanced. Suitable for review + most ship paths.",
    },
    "max": {
        "codec": "h264",
        "extra": ["--jpeg-quality=100", "--pixel-format=yuv420p"],
        "doc": "Highest h264 quality. Larger files; slower.",
    },
    "prores-4444-xq": {
        "codec": "prores",
        "extra": ["--prores-profile=4444-xq"],
        "doc": "Mastering tier. ProRes 4444 XQ for downstream editing.",
    },
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _which_npx() -> str | None:
    return shutil.which("npx")


def _read_props_file(path: str) -> tuple[dict | None, str | None]:
    """Load JSON props from a file. Returns (data, error) where exactly
    one is non-None."""
    p = Path(path)
    if not p.exists():
        return None, f"props file not found: {p}"
    try:
        text = p.read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, dict):
            return None, f"props file must contain a JSON object, got {type(data).__name__}"
        return data, None
    except json.JSONDecodeError as e:
        return None, f"props file is not valid JSON: {e}"
    except OSError as e:
        return None, f"props file unreadable: {e}"


def _list_compositions(project_dir: Path, entry: str) -> tuple[list[str], str | None]:
    """Run `npx remotion compositions <entry> --quiet` and split the output
    on whitespace. Returns (ids, error)."""
    entry_path = project_dir / entry
    cmd = ["npx", "--yes", "remotion", "compositions", str(entry_path), "--quiet"]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return [], "compositions listing timed out after 120s"
    except FileNotFoundError:
        return [], "npx not on PATH"
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip()[-400:]
        return [], f"npx remotion compositions failed (exit {result.returncode}):\n{tail}"
    ids = [t for t in result.stdout.split() if t]
    return ids, None


def _build_render_cmd(
    project_dir: Path,
    entry: str,
    composition: str,
    out: Path,
    props_file: str | None,
    tier_cfg: dict,
    codec_override: str | None,
    concurrency: int | None,
    frames: str | None,
) -> list[str]:
    codec = codec_override or tier_cfg["codec"]
    cmd = [
        "npx",
        "--yes",
        "remotion",
        "render",
        str(project_dir / entry),
        composition,
        str(out),
        f"--codec={codec}",
        "--log=error",
    ]
    cmd.extend(tier_cfg.get("extra", []))
    if codec_override:
        # When the caller overrode codec, the tier's extras may carry
        # codec-bound flags (e.g. --pixel-format on h264). Keep them;
        # they're benign on most codec switches.
        pass
    if concurrency is not None:
        cmd.append(f"--concurrency={concurrency}")
    if frames:
        cmd.append(f"--frames={frames}")
    if props_file:
        cmd.append(f"--props={props_file}")
    return cmd


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="render_remotion.py",
        description="Render a Remotion composition with tier presets and a receipt.",
    )
    p.add_argument("--project", required=True, help="Remotion project root (contains package.json + src/).")
    p.add_argument("--composition", required=True, help="Composition ID to render.")
    p.add_argument("--out", required=True, help="Output file path. Codec must match extension.")
    p.add_argument("--props-file", help="Path to JSON file with props injected into the composition.")
    p.add_argument(
        "--tier",
        default="default",
        choices=sorted(TIER_PRESETS.keys()),
        help="Quality/speed preset. Default: default.",
    )
    p.add_argument("--codec", help="Override codec from the tier preset (h264, h265, vp9, prores, png).")
    p.add_argument("--concurrency", type=int, help="Parallel workers. Lower if OOM.")
    p.add_argument("--frames", help="Frame range, e.g. 0-100. Default: full duration.")
    p.add_argument("--entry", default="src/index.ts", help="Composition entry path inside --project. Default: src/index.ts.")
    p.add_argument(
        "--no-validate-comp-id",
        action="store_true",
        help="Skip the `npx remotion compositions` pre-check. Faster but errors are less helpful.",
    )
    p.add_argument(
        "--retries",
        type=int,
        default=0,
        help="Retry the render up to N additional times on transient "
             "failures (subprocess.TimeoutExpired, recognizable npm/"
             "puppeteer/network errors in stderr). Default 0 — no "
             "retry. Bundler errors and OOM never retry; the operator "
             "needs to fix those.",
    )
    p.add_argument(
        "--render-timeout-sec",
        type=int,
        default=3600,
        help="Per-attempt subprocess timeout. Default 3600 (1 hour). "
             "First-run renders can need extra time for Chromium download.",
    )
    return p.parse_args(argv)


# Recognizable transient-failure markers in stderr. Match against the
# tail so a deeply-nested error message still triggers. Mirrors the
# retry classification in generate_image.py (timeouts + network +
# registry hiccups retry; content errors don't).
_TRANSIENT_STDERR_MARKERS = (
    "ECONNRESET",
    "ETIMEDOUT",
    "EAI_AGAIN",
    "ENOTFOUND registry.npmjs.org",
    "Could not download Chromium",
    "puppeteer/.local-chromium",
    "socket hang up",
    "network timeout",
    "Cannot find module",  # rare; sometimes npx race; safe to retry once
)


def _is_transient_stderr(stderr_tail: str) -> bool:
    if not stderr_tail:
        return False
    for marker in _TRANSIENT_STDERR_MARKERS:
        if marker in stderr_tail:
            return True
    return False


def main(argv: list[str]) -> int:
    args = _parse_args(argv)

    if _which_npx() is None:
        print("render_remotion: npx is not on PATH. Install Node 16+ first.", file=sys.stderr)
        return 2

    project_dir = Path(args.project).resolve()
    if not project_dir.is_dir():
        print(f"render_remotion: --project not a directory: {project_dir}", file=sys.stderr)
        return 2
    if not (project_dir / "package.json").exists():
        print(f"render_remotion: --project missing package.json: {project_dir}", file=sys.stderr)
        return 2

    entry_path = project_dir / args.entry
    if not entry_path.exists():
        print(f"render_remotion: entry not found: {entry_path}", file=sys.stderr)
        return 2

    props_data = None
    props_file_abs: str | None = None
    if args.props_file:
        props_data, err = _read_props_file(args.props_file)
        if err:
            print(f"render_remotion: {err}", file=sys.stderr)
            return 2
        props_file_abs = str(Path(args.props_file).resolve())

    if not args.no_validate_comp_id:
        ids, err = _list_compositions(project_dir, args.entry)
        if err:
            print(f"render_remotion: comp-id pre-check failed: {err}", file=sys.stderr)
            return 2
        if args.composition not in ids:
            print(
                f"render_remotion: composition {args.composition!r} not found. "
                f"Available: {', '.join(ids) or '(none)'}",
                file=sys.stderr,
            )
            return 2

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    tier_cfg = TIER_PRESETS[args.tier]
    cmd = _build_render_cmd(
        project_dir=project_dir,
        entry=args.entry,
        composition=args.composition,
        out=out_path,
        props_file=props_file_abs,
        tier_cfg=tier_cfg,
        codec_override=args.codec,
        concurrency=args.concurrency,
        frames=args.frames,
    )

    started = time.monotonic()
    started_iso = _now_iso()
    timeout_sec = args.render_timeout_sec
    backoff_schedule = [10, 30]
    attempt = 0
    transient_retries = 0
    retry_log: list[dict] = []
    result = None
    stderr_tail = ""
    timeout_message = None
    while True:
        attempt += 1
        attempt_started = time.monotonic()
        try:
            result = subprocess.run(
                cmd,
                cwd=str(project_dir),
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            stderr_tail = (result.stderr or "").strip()[-1200:]
            exit_code = result.returncode
            if exit_code == 0:
                break
            # Non-zero exit. Retry only if stderr matches a known
            # transient pattern AND we have budget. Bundler errors,
            # OOM, etc. fall through to a clean failure.
            if transient_retries < args.retries and _is_transient_stderr(stderr_tail):
                delay = backoff_schedule[min(transient_retries, len(backoff_schedule) - 1)]
                retry_log.append({
                    "attempt": attempt,
                    "duration_sec": round(time.monotonic() - attempt_started, 2),
                    "exit_code": exit_code,
                    "reason": "transient_stderr",
                    "backoff_sec": delay,
                })
                print(
                    f"render_remotion: transient failure (attempt {attempt}); "
                    f"retrying in {delay}s",
                    file=sys.stderr,
                )
                transient_retries += 1
                time.sleep(delay)
                continue
            break
        except subprocess.TimeoutExpired:
            if transient_retries < args.retries:
                delay = backoff_schedule[min(transient_retries, len(backoff_schedule) - 1)]
                retry_log.append({
                    "attempt": attempt,
                    "duration_sec": round(time.monotonic() - attempt_started, 2),
                    "exit_code": 124,
                    "reason": "timeout",
                    "backoff_sec": delay,
                })
                print(
                    f"render_remotion: timed out after {timeout_sec}s (attempt {attempt}); "
                    f"retrying in {delay}s",
                    file=sys.stderr,
                )
                transient_retries += 1
                time.sleep(delay)
                continue
            duration = time.monotonic() - started
            timeout_message = f"render timed out after {timeout_sec}s (attempt {attempt})"
            _write_receipt(
                out_path=out_path,
                schema_args=args,
                tier_cfg=tier_cfg,
                cmd=cmd,
                started_iso=started_iso,
                finished_iso=_now_iso(),
                duration_sec=duration,
                exit_code=124,
                stderr_tail=f"timed out after {timeout_sec}s",
                output_size=None,
                props_data=props_data,
                ok=False,
                error=timeout_message,
                retry_log=retry_log,
            )
            print(f"render_remotion: {timeout_message}", file=sys.stderr)
            return 1
    duration = time.monotonic() - started
    finished_iso = _now_iso()
    exit_code = result.returncode

    output_size = None
    if out_path.exists():
        try:
            output_size = out_path.stat().st_size
        except OSError:
            pass

    ok = exit_code == 0 and out_path.exists()
    err_msg = None
    if exit_code != 0:
        err_msg = f"npx remotion render exited {exit_code}"
    elif not out_path.exists():
        err_msg = "render reported success but output file missing"

    _write_receipt(
        out_path=out_path,
        schema_args=args,
        tier_cfg=tier_cfg,
        cmd=cmd,
        started_iso=started_iso,
        finished_iso=finished_iso,
        duration_sec=duration,
        exit_code=exit_code,
        stderr_tail=stderr_tail,
        output_size=output_size,
        props_data=props_data,
        ok=ok,
        error=err_msg,
        retry_log=retry_log,
    )

    if not ok:
        print(f"render_remotion: {err_msg}", file=sys.stderr)
        if stderr_tail:
            print(stderr_tail, file=sys.stderr)
        return 1

    # Compact JSON success line for callers.
    print(json.dumps({
        "ok": True,
        "out": str(out_path),
        "receipt": str(_receipt_path_for(out_path)),
        "duration_sec": round(duration, 2),
        "size_bytes": output_size,
        "tier": args.tier,
        "composition": args.composition,
    }))
    return 0


def _receipt_path_for(out_path: Path) -> Path:
    return out_path.with_suffix(out_path.suffix + ".receipt.json")


def _write_receipt(
    *,
    out_path: Path,
    schema_args: argparse.Namespace,
    tier_cfg: dict,
    cmd: list[str],
    started_iso: str,
    finished_iso: str,
    duration_sec: float,
    exit_code: int,
    stderr_tail: str,
    output_size: int | None,
    props_data: dict | None,
    ok: bool,
    error: str | None,
    retry_log: list[dict] | None = None,
) -> None:
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "id": str(uuid.uuid4()),
        "started_at": started_iso,
        "finished_at": finished_iso,
        "duration_sec": round(duration_sec, 2),
        "ok": ok,
        "error": error,
        "exit_code": exit_code,
        "tool": {
            "name": "render_remotion.py",
            "command": cmd,
        },
        "project": str(Path(schema_args.project).resolve()),
        "entry": schema_args.entry,
        "composition": schema_args.composition,
        "tier": schema_args.tier,
        "tier_doc": tier_cfg["doc"],
        "codec": schema_args.codec or tier_cfg["codec"],
        "concurrency": schema_args.concurrency,
        "frames": schema_args.frames,
        "out": str(out_path),
        "out_size_bytes": output_size,
        "props_file": schema_args.props_file,
        "props_sha256": (
            hashlib.sha256(json.dumps(props_data, sort_keys=True).encode("utf-8")).hexdigest()
            if props_data is not None
            else None
        ),
        "stderr_tail": stderr_tail,
        "retries": retry_log or [],
    }
    try:
        _receipt_path_for(out_path).write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
        )
    except OSError as e:
        print(f"render_remotion: failed to write receipt: {e}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
