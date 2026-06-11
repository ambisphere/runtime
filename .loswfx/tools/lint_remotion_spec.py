#!/usr/bin/env python3
"""Lint a Remotion spec markdown file written in the BEATS-blueprint style,
or check composition source files for brand-token discipline.

The "specs are code blueprints, not prose" pattern (lifted from
RinDig/Content-Agent-Routing-Promptbase animation-studio): a spec is a
markdown doc that ends every scene with a TypeScript `const BEATS = {}`
constant naming frame-stamped animation events, and inlines component
invocations as JSX-prop strings rather than describing them in prose.

This linter enforces the structural invariants. It does not interpret
narrative quality.

Checks (--spec mode, default):
  - SPEC_HAS_FRONTMATTER: a YAML front-matter block exists with the
    minimum keys: composition, fps, scenes (list).
  - SPEC_FRONTMATTER_DURATION_MATCHES: the front-matter `duration_frames`
    (if present) equals the sum of `scenes[*].duration_frames`.
  - EVERY_SCENE_HAS_BEATS: every scene named in the front-matter has a
    matching `## Scene N — <name>` heading followed somewhere below by a
    ```typescript const BEATS = { … }``` fenced block.
  - BEATS_FRAMES_MONOTONIC: the integer values inside the BEATS const are
    strictly non-decreasing in source order.
  - BEATS_FRAMES_WITHIN_SCENE: every BEATS frame value is in
    [scene_start, scene_start + scene_duration). scene_start is computed
    by walking the front-matter scene list.
  - BEATS_DENSITY_REASONABLE: every scene has at least 3 BEATS entries
    per second of duration (3 * scene_duration / fps), warn-only.
  - COMPONENTS_RESOLVE (optional, via --registry): every JSX-prop string
    inside the spec body references a component listed in the registry
    markdown (one component per `### <Name>` heading).

Checks (--check-tokens mode):
  - BRAND_TOKEN_LEAK: any hex literal (#RRGGBB or #RGB) in composition
    .tsx files outside the canonical brand.ts module is a finding. Warn
    by default; `--strict-tokens` promotes to error. Emitted per-file
    with line number so operators can locate the leak.

CLI:
  lint_remotion_spec.py --spec <path.md> [--registry <path.md>]
                        [--strict-density] [--json]
  lint_remotion_spec.py --check-tokens <dir>
                        [--tokens-module brand.ts]
                        [--strict-tokens] [--json]

Exit codes:
  0 — clean.
  1 — lint violations (or warnings with --strict-density / --strict-tokens).
  2 — operator error (file not found, malformed frontmatter, no scenes,
       --check-tokens directory missing).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path


FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
SCENE_HEADING_RE = re.compile(r"^##\s+Scene\s+(\d+)(?:\s*[—\-:]\s*(.+))?\s*$", re.MULTILINE)
BEATS_BLOCK_RE = re.compile(
    r"```(?:typescript|ts)\s*\n\s*(?:export\s+)?const\s+BEATS\s*(?::\s*[^\n=]+)?\s*=\s*\{(.*?)\}\s*(?:as\s+const\s*)?;?\s*\n```",
    re.DOTALL,
)
BEATS_ENTRY_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*:\s*(-?\d+)\s*,?\s*(?://.*)?$", re.MULTILINE)
COMPONENT_REF_RE = re.compile(r"<([A-Z][A-Za-z0-9]+)\b")
REGISTRY_NAME_RE = re.compile(r"^###\s+([A-Z][A-Za-z0-9]+)\s*$", re.MULTILINE)


@dataclass
class Violation:
    code: str
    severity: str  # error | warn
    detail: str
    scene_index: int | None = None


@dataclass
class Report:
    ok: bool
    violations: list[Violation] = field(default_factory=list)

    def add(self, *, code: str, detail: str, severity: str = "error", scene_index: int | None = None) -> None:
        self.violations.append(Violation(code=code, severity=severity, detail=detail, scene_index=scene_index))
        if severity == "error":
            self.ok = False

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "violations": [asdict(v) for v in self.violations],
        }


def _parse_frontmatter(text: str) -> tuple[dict | None, str | None]:
    """Return (frontmatter_dict, body) — both None on no-frontmatter.
    Tries pyyaml, falls back to a tiny dict parser sufficient for our
    field shape (scalars + simple lists of scalar/dict)."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None, text
    raw = m.group(1)
    body = text[m.end():]
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(raw)
        if not isinstance(data, dict):
            return None, body
        return data, body
    except ImportError:
        # Tiny parser: best-effort for `key: value` and nested `scenes:` list.
        return _parse_frontmatter_fallback(raw), body


def _parse_frontmatter_fallback(raw: str) -> dict | None:
    out: dict = {}
    lines = raw.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        if ":" not in line:
            i += 1
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if val == "" and i + 1 < len(lines) and lines[i + 1].lstrip().startswith("-"):
            # List on subsequent lines.
            items: list = []
            i += 1
            while i < len(lines) and lines[i].lstrip().startswith("-"):
                item_line = lines[i].lstrip()[1:].strip()
                if item_line and ":" in item_line:
                    # Inline dict: `- key: v` followed by more `  key: v` lines.
                    item: dict = {}
                    k1, _, v1 = item_line.partition(":")
                    item[k1.strip()] = _coerce(v1.strip())
                    i += 1
                    while i < len(lines) and lines[i].startswith("    ") and ":" in lines[i]:
                        sub = lines[i].strip()
                        k2, _, v2 = sub.partition(":")
                        item[k2.strip()] = _coerce(v2.strip())
                        i += 1
                    items.append(item)
                else:
                    items.append(_coerce(item_line))
                    i += 1
            out[key] = items
            continue
        out[key] = _coerce(val)
        i += 1
    return out


def _coerce(v: str):
    if v == "":
        return None
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    return v.strip('"').strip("'")


def lint(spec_text: str, registry_text: str | None, strict_density: bool) -> Report:
    report = Report(ok=True)

    fm, body = _parse_frontmatter(spec_text)
    if fm is None:
        report.add(code="SPEC_HAS_FRONTMATTER", detail="no YAML front-matter block found at top of spec")
        return report

    if not all(k in fm for k in ("composition", "fps", "scenes")):
        missing = [k for k in ("composition", "fps", "scenes") if k not in fm]
        report.add(
            code="SPEC_HAS_FRONTMATTER",
            detail=f"front-matter missing required keys: {', '.join(missing)}",
        )
        return report

    scenes = fm.get("scenes") or []
    if not isinstance(scenes, list) or not scenes:
        report.add(code="SPEC_HAS_FRONTMATTER", detail="scenes list is empty or not a list")
        return report

    fps = fm.get("fps") or 30
    try:
        fps = int(fps)
    except (TypeError, ValueError):
        report.add(code="SPEC_HAS_FRONTMATTER", detail=f"fps must be an integer, got {fm.get('fps')!r}")
        return report

    scene_specs: list[dict] = []
    for idx, scene in enumerate(scenes):
        if isinstance(scene, dict):
            name = str(scene.get("name") or scene.get("title") or f"scene-{idx + 1}")
            duration = scene.get("duration_frames")
        else:
            name = str(scene)
            duration = None
        if duration is None:
            report.add(
                code="SPEC_HAS_FRONTMATTER",
                detail=f"scene {idx + 1} ({name!r}) missing duration_frames",
                scene_index=idx,
            )
            continue
        try:
            duration = int(duration)
        except (TypeError, ValueError):
            report.add(
                code="SPEC_HAS_FRONTMATTER",
                detail=f"scene {idx + 1} duration_frames must be int, got {duration!r}",
                scene_index=idx,
            )
            continue
        scene_specs.append({"index": idx, "name": name, "duration": duration})

    if not scene_specs:
        report.add(code="SPEC_HAS_FRONTMATTER", detail="no scenes with valid duration_frames")
        return report

    total = sum(s["duration"] for s in scene_specs)
    if "duration_frames" in fm:
        try:
            declared = int(fm["duration_frames"])
        except (TypeError, ValueError):
            declared = None
        if declared is not None and declared != total:
            report.add(
                code="SPEC_FRONTMATTER_DURATION_MATCHES",
                detail=f"duration_frames {declared} ≠ sum of scene durations {total}",
            )

    # Find scene headings + BEATS blocks in the body.
    scene_headings = list(SCENE_HEADING_RE.finditer(body))
    if len(scene_headings) < len(scene_specs):
        report.add(
            code="EVERY_SCENE_HAS_BEATS",
            detail=(
                f"front-matter declares {len(scene_specs)} scenes but body has "
                f"{len(scene_headings)} `## Scene N` headings"
            ),
        )

    # Compute scene start frames by walking the front-matter order.
    cursor = 0
    starts = {}
    for s in scene_specs:
        starts[s["index"]] = cursor
        cursor += s["duration"]

    # For each scene heading found in body, extract its BEATS block (the
    # first ```typescript const BEATS``` after the heading and before the
    # next heading).
    body_len = len(body)
    for i, heading_match in enumerate(scene_headings):
        scene_num = int(heading_match.group(1))
        scene_idx = scene_num - 1
        section_start = heading_match.end()
        section_end = scene_headings[i + 1].start() if i + 1 < len(scene_headings) else body_len
        section = body[section_start:section_end]

        beats_match = BEATS_BLOCK_RE.search(section)
        if not beats_match:
            report.add(
                code="EVERY_SCENE_HAS_BEATS",
                detail=f"scene {scene_num} has no `const BEATS = {{ … }}` block",
                scene_index=scene_idx,
            )
            continue

        entries = BEATS_ENTRY_RE.findall(beats_match.group(1))
        if not entries:
            report.add(
                code="EVERY_SCENE_HAS_BEATS",
                detail=f"scene {scene_num} BEATS block is empty",
                scene_index=scene_idx,
            )
            continue

        # Monotonicity within the block.
        last = -10**9
        for name, val_s in entries:
            val = int(val_s)
            if val < last:
                report.add(
                    code="BEATS_FRAMES_MONOTONIC",
                    detail=(
                        f"scene {scene_num}: BEATS frame {name}={val} < previous {last} "
                        "(entries must be non-decreasing in source order)"
                    ),
                    scene_index=scene_idx,
                )
                break
            last = val

        if scene_idx in starts:
            scene_start = starts[scene_idx]
            scene_end = scene_start + scene_specs[scene_num - 1]["duration"] if scene_num - 1 < len(scene_specs) else None
            for name, val_s in entries:
                val = int(val_s)
                if scene_end is None:
                    continue
                if val < scene_start or val >= scene_end:
                    report.add(
                        code="BEATS_FRAMES_WITHIN_SCENE",
                        detail=(
                            f"scene {scene_num}: BEATS {name}={val} outside scene window "
                            f"[{scene_start}, {scene_end})"
                        ),
                        scene_index=scene_idx,
                    )

        # Density: 3 entries per second.
        duration = scene_specs[scene_num - 1]["duration"] if scene_num - 1 < len(scene_specs) else None
        if duration:
            seconds = duration / fps
            need = max(3, int(round(3 * seconds)))
            if len(entries) < need:
                severity = "error" if strict_density else "warn"
                report.add(
                    code="BEATS_DENSITY_REASONABLE",
                    detail=(
                        f"scene {scene_num}: {len(entries)} BEATS entries for "
                        f"{seconds:.1f}s — recommend ≥{need}"
                    ),
                    scene_index=scene_idx,
                    severity=severity,
                )

    # Component-resolution check, if registry provided.
    if registry_text:
        registry_names = set(REGISTRY_NAME_RE.findall(registry_text))
        # Common stdlib React components we don't lint. Caller can extend
        # via registry markdown.
        builtin = {
            "Sequence", "Series", "Composition", "Audio", "Video", "Img", "AbsoluteFill",
            "Loop", "Freeze", "OffthreadVideo", "IFrame", "Still",
        }
        referenced = set(COMPONENT_REF_RE.findall(body)) - builtin
        unknown = sorted(referenced - registry_names)
        if unknown:
            report.add(
                code="COMPONENTS_RESOLVE",
                detail=(
                    "components referenced in spec body not in registry: "
                    f"{', '.join(unknown)}"
                ),
            )

    return report


# Hex literal regex used by --check-tokens. Matches #RRGGBB or #RGB,
# not embedded in a longer hex sequence. We accept lower/upper hex.
HEX_LITERAL_RE = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")


def check_tokens(src_dir: Path, tokens_module: str, strict: bool) -> Report:
    """Walk *.tsx files under src_dir and warn on hex literals outside
    the tokens module. Returns a Report whose violations carry file +
    line info embedded in detail."""
    report = Report(ok=True)
    if not src_dir.exists() or not src_dir.is_dir():
        report.add(code="BRAND_TOKEN_LEAK", detail=f"--check-tokens path not a directory: {src_dir}")
        return report

    tokens_name = tokens_module
    # Accept either bare name (brand.ts) or relative path (src/brand.ts).
    tokens_basenames = {tokens_name, Path(tokens_name).name}

    leaks_by_file: dict[str, list[tuple[int, str]]] = {}
    for path in sorted(src_dir.rglob("*.tsx")):
        if path.name in tokens_basenames:
            continue
        # Also skip the .ts tokens module itself if it happens to live
        # under src_dir (which it should). We only walk .tsx for leak
        # checks since brand decisions belong in code that renders.
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        file_leaks: list[tuple[int, str]] = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            # Skip comment lines to reduce false positives. A bare //
            # at the line start is the common case in TS.
            stripped = line.lstrip()
            if stripped.startswith("//") or stripped.startswith("*"):
                continue
            for m in HEX_LITERAL_RE.finditer(line):
                file_leaks.append((lineno, m.group(0)))
        if file_leaks:
            leaks_by_file[str(path)] = file_leaks

    severity = "error" if strict else "warn"
    for file_path, leaks in leaks_by_file.items():
        for lineno, hex_val in leaks:
            report.add(
                code="BRAND_TOKEN_LEAK",
                detail=f"{file_path}:{lineno}: hex literal {hex_val} outside tokens module ({tokens_module})",
                severity=severity,
            )

    return report


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="lint_remotion_spec.py")
    p.add_argument("--spec", help="Path to the spec markdown file (--spec mode).")
    p.add_argument("--check-tokens", dest="check_tokens", help="Walk this directory's .tsx files and warn on hex literals outside the tokens module.")
    p.add_argument("--tokens-module", default="brand.ts", help="Name of the tokens module to skip in --check-tokens mode. Default: brand.ts.")
    p.add_argument("--registry", help="Optional path to a component-registry markdown file (--spec mode).")
    p.add_argument("--strict-density", action="store_true", help="Treat density warnings as errors.")
    p.add_argument("--strict-tokens", action="store_true", help="Treat BRAND_TOKEN_LEAK warnings as errors.")
    p.add_argument("--json", action="store_true", help="Emit JSON output instead of human text.")
    args = p.parse_args(argv)
    if not args.spec and not args.check_tokens:
        p.error("one of --spec or --check-tokens is required")
    return args


def _print_human(report: Report, label: str) -> None:
    if report.ok and not report.violations:
        print(f"lint_remotion_spec: {label} clean")
        return
    for v in report.violations:
        marker = "✗" if v.severity == "error" else "⚠"
        scene = f" scene={v.scene_index + 1}" if v.scene_index is not None else ""
        print(f"{marker} {v.code}{scene}: {v.detail}")
    errors = sum(1 for v in report.violations if v.severity == "error")
    warnings = sum(1 for v in report.violations if v.severity == "warn")
    print(f"lint_remotion_spec: {errors} errors, {warnings} warnings")


def main(argv: list[str]) -> int:
    args = _parse_args(argv)

    if args.check_tokens:
        report = check_tokens(Path(args.check_tokens), args.tokens_module, args.strict_tokens)
        if args.json:
            print(json.dumps(report.as_dict(), indent=2))
        else:
            _print_human(report, f"tokens-check {args.check_tokens}")
        return 0 if report.ok else 1

    spec_path = Path(args.spec)
    if not spec_path.exists():
        print(f"lint_remotion_spec: spec not found: {spec_path}", file=sys.stderr)
        return 2
    spec_text = spec_path.read_text(encoding="utf-8")
    registry_text = None
    if args.registry:
        rp = Path(args.registry)
        if not rp.exists():
            print(f"lint_remotion_spec: registry not found: {rp}", file=sys.stderr)
            return 2
        registry_text = rp.read_text(encoding="utf-8")

    report = lint(spec_text, registry_text, args.strict_density)

    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        _print_human(report, spec_path.name)

    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
