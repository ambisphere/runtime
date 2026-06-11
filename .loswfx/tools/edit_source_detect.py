#!/usr/bin/env python3
"""edit_source_detect — surface recurring operator revisions as candidate
skill-prompt changes.

Reads feedback-cascade artifacts from the shadow repo
(`engagements/<repo>/feedback/*.md`) and groups them by
(skill, revision-kind). When a group's occurrence count crosses the
threshold AND spans the minimum distinct engagements, emit a finding:
the pattern is no longer a one-off operator fix — it's evidence that
the skill's prompt should change.

This is the M50 Track C closure on ICM §6.3 — the edit-source
principle. The finding is a candidate, not an automatic PR.

Feedback frontmatter shape (read by this tool):

    ---
    skill: <skill-name>
    revision-kind: <slug>
    engagement: <client-or-repo-name>
    date: <YYYY-MM-DD>
    ---
    <freeform body — the operator's revision rationale>

Exit codes:
  0 — clean run. Findings (if any) emitted to --out (or stdout).
  1 — tool error (missing shadow path, malformed feedback, etc.).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

try:
    import yaml  # type: ignore
except ImportError:
    print(
        "edit_source_detect: pyyaml is required (pip install pyyaml).",
        file=sys.stderr,
    )
    sys.exit(1)


def parse_frontmatter(text: str) -> dict | None:
    """Return the parsed YAML frontmatter dict, or None if the document
    has no leading `---` fence."""
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return None
    after = stripped[3:].lstrip("\n")
    end = after.find("\n---")
    if end < 0:
        return None
    block = after[:end]
    try:
        loaded = yaml.safe_load(block) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(loaded, dict):
        return None
    return loaded


def iter_feedback_files(shadow_root: Path) -> Iterable[Path]:
    """Yield every `engagements/*/feedback/*.md` path under shadow_root."""
    engagements = shadow_root / "engagements"
    if not engagements.is_dir():
        return
    for repo_dir in sorted(engagements.iterdir()):
        feedback_dir = repo_dir / "feedback"
        if not feedback_dir.is_dir():
            continue
        for path in sorted(feedback_dir.glob("*.md")):
            yield path


def collect_revisions(
    shadow_root: Path, ledger_path: Path | None = None
) -> list[dict]:
    """Walk the shadow + optional ledger and return one dict per
    revision source.

    Files missing required frontmatter keys are skipped silently;
    they're not the detector's concern. Ledger events that don't
    carry the (skill, revision-kind, engagement) tuple are also
    skipped silently — they're either unrelated event types or
    pre-M58 events without the field.

    Each returned row carries a `source` field — "artifact" for
    rows derived from feedback markdown, "ledger" for rows
    derived from feedback.cascade.* events.
    """
    out: list[dict] = []
    for path in iter_feedback_files(shadow_root):
        meta = parse_frontmatter(path.read_text(encoding="utf-8"))
        if meta is None:
            continue
        skill = meta.get("skill")
        revision_kind = meta.get("revision-kind") or meta.get("revision_kind")
        engagement = meta.get("engagement")
        if not (skill and revision_kind and engagement):
            continue
        out.append(
            {
                "skill": str(skill).strip(),
                "revision-kind": str(revision_kind).strip(),
                "engagement": str(engagement).strip(),
                "path": str(path),
                "source": "artifact",
            }
        )
    if ledger_path is not None:
        out.extend(read_ledger_events(ledger_path))
    return out


def read_ledger_events(path: Path) -> list[dict]:
    """Stream the JSONL ledger and yield revision dicts derived
    from `feedback.cascade.*` events.

    Each event's `data` block must carry `skill`,
    `revision_kind` (or `revision-kind`), and `engagement` for
    the row to count. Malformed JSON lines are skipped silently.
    """
    out: list[dict] = []
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            etype = evt.get("type", "")
            if not isinstance(etype, str) or not etype.startswith("feedback.cascade."):
                continue
            data = evt.get("data") or {}
            if not isinstance(data, dict):
                continue
            skill = data.get("skill")
            revision_kind = data.get("revision-kind") or data.get("revision_kind")
            engagement = data.get("engagement")
            if not (skill and revision_kind and engagement):
                continue
            out.append(
                {
                    "skill": str(skill).strip(),
                    "revision-kind": str(revision_kind).strip(),
                    "engagement": str(engagement).strip(),
                    "path": f"ledger:{evt.get('id', '')}",
                    "source": "ledger",
                }
            )
    return out


def detect(
    revisions: list[dict],
    threshold_count: int,
    threshold_engagements: int,
) -> list[dict]:
    """Group revisions by (skill, revision-kind); emit a finding when
    count >= threshold_count AND distinct engagements >= threshold_engagements.
    """
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in revisions:
        grouped[(r["skill"], r["revision-kind"])].append(r)

    findings: list[dict] = []
    for (skill, rev_kind), entries in sorted(grouped.items()):
        engagements = sorted({e["engagement"] for e in entries})
        if len(entries) < threshold_count:
            continue
        if len(engagements) < threshold_engagements:
            continue
        findings.append(
            {
                "skill": skill,
                "revision-kind": rev_kind,
                "count": len(entries),
                "engagements": engagements,
                "evidence": [e["path"] for e in entries],
                "proposed-prompt-change": (
                    f"Operators have revised {skill} for "
                    f"'{rev_kind}' {len(entries)} times across "
                    f"{len(engagements)} engagements. Consider "
                    f"updating skills/{skill}/SKILL.md to address "
                    f"this pattern at the prompt level."
                ),
            }
        )
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="edit_source_detect",
        description="Surface recurring operator revisions as candidate prompt changes.",
    )
    parser.add_argument(
        "--shadow",
        required=True,
        help="Path to the shadow repo root (contains engagements/).",
    )
    parser.add_argument(
        "--threshold-count",
        type=int,
        default=3,
        help="Minimum total occurrences before a pattern surfaces (default 3).",
    )
    parser.add_argument(
        "--threshold-engagements",
        type=int,
        default=2,
        help="Minimum distinct engagements before a pattern surfaces (default 2).",
    )
    parser.add_argument(
        "--out",
        default="-",
        help="Output path for JSONL findings; '-' writes to stdout (default).",
    )
    parser.add_argument(
        "--receipt",
        default=None,
        help="Optional path to write a JSON receipt of the run.",
    )
    parser.add_argument(
        "--include-ledger",
        default=None,
        help=(
            "Explicit path to a .loswf/state/events.jsonl ledger. "
            "When unspecified, defaults to <shadow>/.loswf/state/events.jsonl "
            "if present. Use --no-ledger to opt out."
        ),
    )
    parser.add_argument(
        "--no-ledger",
        action="store_true",
        help="Skip the ledger channel entirely (artifact-only behaviour).",
    )
    args = parser.parse_args(argv)

    shadow = Path(args.shadow)
    if not shadow.is_dir():
        print(f"edit_source_detect: shadow path not found: {shadow}", file=sys.stderr)
        return 1

    ledger_path: Path | None
    if args.no_ledger:
        ledger_path = None
    elif args.include_ledger:
        ledger_path = Path(args.include_ledger)
    else:
        candidate = shadow / ".loswf" / "state" / "events.jsonl"
        ledger_path = candidate if candidate.exists() else None

    revisions = collect_revisions(shadow, ledger_path=ledger_path)
    findings = detect(
        revisions,
        threshold_count=args.threshold_count,
        threshold_engagements=args.threshold_engagements,
    )

    lines = [json.dumps(f, sort_keys=True) for f in findings]
    payload = ("\n".join(lines) + "\n") if lines else ""
    if args.out == "-":
        sys.stdout.write(payload)
    else:
        Path(args.out).write_text(payload, encoding="utf-8")

    if args.receipt:
        receipt = {
            "tool": "edit_source_detect",
            "shadow": str(shadow),
            "threshold_count": args.threshold_count,
            "threshold_engagements": args.threshold_engagements,
            "revisions_scanned": len(revisions),
            "findings_count": len(findings),
        }
        Path(args.receipt).write_text(
            json.dumps(receipt, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
