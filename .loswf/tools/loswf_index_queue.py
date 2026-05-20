#!/usr/bin/env python3
"""Runtime-neutral semantic-index enqueue tool.

Appends edited file paths to .loswf/state/index-queue for incremental
re-embedding by `bin/loswf-index update`. Designed to be invoked from any
host runtime via a thin hook shim — the Claude PostToolUse hook at
`.claude/hooks/loswf_post_edit_index.py` is the reference caller.

Hard requirements (inherited from the original Claude-coupled hook):
- NEVER blocks. Returns within milliseconds.
- NEVER raises. All errors silently swallowed — index hiccups must not break
  the calling runtime's turn.
- Skips paths that don't match .loswf/config.yaml `code_search.paths`.
- On missing code_search block: logs to .loswf/state/index-queue.errors and,
  if LOSWF_SELF_HOSTED != "1", emits a remediation string to stderr.
"""
import datetime
import json
import os
import sys
from pathlib import Path

QUEUE = Path(".loswf/state/index-queue")
ERRORS = Path(".loswf/state/index-queue.errors")
CONFIG = Path(".loswf/config.yaml")


def get_paths():
    """Return (paths, exclude) from .loswf/config.yaml `code_search:`.

    Tri-state return values:
      (None, None) — the `code_search:` header never appeared (missing block)
      ([], [])     — header present but no list items were scanned
      ([..], [..]) — header present with entries

    Tiny hand-rolled YAML — avoids a dep on PyYAML for a hot hook."""
    if not CONFIG.exists():
        return None, None
    try:
        text = CONFIG.read_text()
    except Exception:
        return None, None
    in_cs = False
    seen_header = False
    paths, exclude = [], []
    cur = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("code_search:"):
            in_cs = True
            seen_header = True
            continue
        if in_cs:
            stripped = line.lstrip(" ")
            indent = len(line) - len(stripped)
            if indent == 0 and stripped:
                # left the block
                break
            if stripped.startswith("paths:"):
                # inline form: paths: [a, b, c]
                after = stripped[len("paths:"):].strip()
                if after.startswith("[") and after.endswith("]"):
                    for item in after[1:-1].split(","):
                        v = item.strip().strip('"').strip("'")
                        if v:
                            paths.append(v)
                    cur = None
                else:
                    cur = paths
                continue
            if stripped.startswith("exclude:"):
                after = stripped[len("exclude:"):].strip()
                if after.startswith("[") and after.endswith("]"):
                    for item in after[1:-1].split(","):
                        v = item.strip().strip('"').strip("'")
                        if v:
                            exclude.append(v)
                    cur = None
                else:
                    cur = exclude
                continue
            if cur is not None and stripped.startswith("- "):
                val = stripped[2:].strip().strip('"').strip("'")
                cur.append(val)
            elif stripped and not stripped.startswith("- "):
                cur = None
    if not seen_header:
        return None, None
    return paths, exclude


def is_indexable(rel_path, paths, exclude):
    if not paths:
        return False
    if not any(rel_path.startswith(p) for p in paths):
        return False
    if not rel_path.endswith((".ts", ".py", ".go")):
        return False
    base = rel_path.rsplit("/", 1)[-1]
    for ex in exclude:
        if ex.replace("*", "") in base:
            return False
    return True


def _log_missing_block():
    """Record the drift. Swallow all errors — this is a hot hook."""
    try:
        ERRORS.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with open(ERRORS, "a") as f:
            f.write(f"{stamp} code_search missing in .loswf/config.yaml\n")
    except Exception:
        pass
    if os.environ.get("LOSWF_SELF_HOSTED") != "1":
        try:
            sys.stderr.write(
                "loswf: code_search missing in .loswf/config.yaml — add the block "
                "(see .loswf/config.example.yaml or specs/SRS.md §4.7) to restore "
                "semantic index coverage.\n"
            )
        except Exception:
            pass


def enqueue(rel_path):
    """Append rel_path to the index queue. Swallow all errors."""
    try:
        QUEUE.parent.mkdir(parents=True, exist_ok=True)
        with open(QUEUE, "a") as f:
            f.write(rel_path + "\n")
    except Exception:
        pass


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    if payload.get("tool_name") not in ("Write", "Edit", "MultiEdit"):
        return 0

    file_path = payload.get("tool_input", {}).get("file_path", "")
    if not file_path:
        return 0

    cwd = os.getcwd()
    try:
        rel = os.path.relpath(file_path, cwd)
    except Exception:
        return 0
    if rel.startswith(".."):
        return 0

    paths, exclude = get_paths()
    if paths is None:
        _log_missing_block()
        return 0
    if not is_indexable(rel, paths, exclude):
        return 0

    enqueue(rel)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
