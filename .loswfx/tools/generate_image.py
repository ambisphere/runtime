#!/usr/bin/env python3
"""Generate supporting artwork or diagrams via OpenAI gpt-image-2.

For factory agents that need to produce visual artifacts — architecture
diagrams, workflow illustrations, design references, devlog hero images.
Modeled on grounded_review.py's OpenAI integration pattern.

Reads OPENAI_API_KEY from the environment. No key → exit 2 with clear
message. PNG output is written to the requested path.

When `.loswf/config.yaml` carries an `image_gen:` block, the tool also:

  - Reads the brand-voice style brief from a referenced Markdown section
    (`image_gen.style_brief.file` + `.section`) and prepends it to the
    `--prompt` value. Cached once per process. Bypass with `--no-style`.
  - Accepts `--batch <manifest.yaml>` to fan a list of images out across
    a Python threadpool (default 3 workers, configurable via
    `image_gen.batch.max_workers`).
  - Defaults `--out` to `.loswf/state/images/<slug>.png` when omitted.
  - Writes a structured receipt JSON alongside every generated PNG.

When the `image_gen:` block is absent, behavior is identical to the
pre-#590 tool: `--out` is required, no receipt is written, no injection
runs. Existing call sites that always pass `--out` continue to work
unmodified.

Mermaid input mode (#648):
  Pass `--mermaid <path>` instead of `--prompt` to render a structurally
  accurate diagram. The tool parses the Mermaid source, converts it to a
  deterministic English prompt that enumerates every node and edge
  verbatim, optionally uplifts via a baseline rendering (mermaid-cli
  `mmdc` if on $PATH, else https://kroki.io/mermaid/png) which is passed
  as a reference image to OpenAI's images.edit endpoint, and falls
  through to the images.generations path when neither renderer is
  reachable. Configured under `image_gen.mermaid:`. Supported diagram
  families: `stateDiagram[-v2]`, `sequenceDiagram`, `flowchart`/`graph`
  with `subgraph` blocks.

  `--prompt` and `--mermaid` are mutually exclusive; pass one or neither
  (with --batch). Both → exit 2.

CLI:
  generate_image.py (--prompt "..." | --mermaid path.mmd|.md)
                    [--out path.png]
                    [--size 1024x1024|1536x1024|1024x1536]
                    [--quality high|medium|low]
                    [--model gpt-image-2]
                    [--no-style]
                    [--batch manifest.yaml]

Exit codes:
  0 — image written.
  1 — generation failed (api error).
  2 — operator error (missing key, bad args, write failure).

Cost (indicative, gpt-image-2 launch pricing):
  1024x1024 high quality ~$0.04 per image.
  1536x1024 high quality ~$0.06 per image.
  images.edit pricing matches images.generations per Q1-2026 announcement.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

API_URL = "https://api.openai.com/v1/images/generations"
EDIT_API_URL = "https://api.openai.com/v1/images/edits"
DEFAULT_MODEL = "gpt-image-2"
SIZE_CHOICES = ("1024x1024", "1536x1024", "1024x1536")
QUALITY_CHOICES = ("high", "medium", "low")
DEFAULT_BATCH_WORKERS = 3
DEFAULT_KROKI_URL = "https://kroki.io"
DEFAULT_KROKI_TIMEOUT_SEC = 15
MERMAID_RENDER_TIMEOUT_SEC = 30
RECEIPT_SCHEMA = "loswf-image-gen-receipt-v1"
SUPPORTED_MERMAID_KINDS = ("stateDiagram", "sequenceDiagram", "flowchart", "graph")

# Cost map (USD per image, gpt-image-2 launch pricing). Used for the
# `cost_estimate` field in receipts. Conservative defaults — operators
# can override at the call site if pricing changes.
_COST_TABLE = {
    ("1024x1024", "high"): 0.04,
    ("1024x1024", "medium"): 0.02,
    ("1024x1024", "low"): 0.01,
    ("1536x1024", "high"): 0.06,
    ("1536x1024", "medium"): 0.03,
    ("1536x1024", "low"): 0.015,
    ("1024x1536", "high"): 0.06,
    ("1024x1536", "medium"): 0.03,
    ("1024x1536", "low"): 0.015,
}

# images.edit pricing per Q1-2026 announcement (confirmed via WebFetch on
# the OpenAI images API reference): identical to images.generations for
# gpt-image-2. Kept as a separate table so a future divergence is a
# one-line maintenance.
_EDIT_COST_TABLE = dict(_COST_TABLE)

# Cached state for per-process reuse. Architect doc §"Brand-voice
# injection" requires the style prefix be extracted once and reused.
_STYLE_PREFIX: str | None = None
_STYLE_RESOLVED: bool = False
_STYLE_LOCK = threading.Lock()
_CONFIG_CACHE: dict | None = None
_CONFIG_RESOLVED: bool = False
_CONFIG_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Config + style brief
# ---------------------------------------------------------------------------

def _project_root() -> Path:
    """Anchor for config + style-brief resolution. Mirrors the anchor
    logic in loswf_post_tool_use_log.py: prefer CLAUDE_PROJECT_DIR, fall
    back to cwd. Tests override via the env var."""
    p = os.environ.get("CLAUDE_PROJECT_DIR")
    if p:
        return Path(p)
    return Path.cwd()


def _load_config() -> dict | None:
    """Read `.loswf/config.yaml` once per process. Returns the parsed
    `image_gen:` block, or None when the block is absent or pyyaml is
    not installed. Absence is the backward-compat signal — the caller
    must treat None as "behave like the pre-#590 tool"."""
    global _CONFIG_CACHE, _CONFIG_RESOLVED
    with _CONFIG_LOCK:
        if _CONFIG_RESOLVED:
            return _CONFIG_CACHE

        block: dict | None = None
        cfg_path = _project_root() / ".loswf" / "config.yaml"
        if cfg_path.exists():
            try:
                import yaml  # type: ignore
                with cfg_path.open("r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                candidate = data.get("image_gen")
                if isinstance(candidate, dict):
                    block = candidate
            except ImportError:
                # pyyaml is a soft-dep per the architect doc constraints.
                # When missing, fall back to backward-compat behavior.
                pass
            except Exception:
                pass

        _CONFIG_CACHE = block
        _CONFIG_RESOLVED = True
        return block


def _extract_style_prefix(file_rel: str, section: str) -> str | None:
    """Parse a Markdown file, locate a `## ` heading whose text contains
    `section` (case-insensitive substring), and return the first fenced
    code block inside that section. Falls back to the section text with
    headings stripped when no fenced block is present.

    Returns None when the file is missing or the section is not found.
    Cached at the module level — first non-None result wins for the
    lifetime of the process."""
    global _STYLE_PREFIX, _STYLE_RESOLVED
    with _STYLE_LOCK:
        if _STYLE_RESOLVED:
            return _STYLE_PREFIX

        result: str | None = None
        path = _project_root() / file_rel
        if not path.exists():
            print(f"generate_image: style_brief.file not found: {path}",
                  file=sys.stderr)
        else:
            text = path.read_text(encoding="utf-8")
            needle = str(section).lower()

            # Walk top-level (## ) headings. Find the first one whose heading
            # text contains the needle. Then read until the next ## heading.
            lines = text.splitlines()
            start = None
            for i, line in enumerate(lines):
                if line.startswith("## ") and needle in line.lower():
                    start = i + 1
                    break
            if start is None:
                print(
                    f"generate_image: style_brief.section '{section}' not "
                    f"found in {path}", file=sys.stderr,
                )
            else:
                end = len(lines)
                for j in range(start, len(lines)):
                    if lines[j].startswith("## "):
                        end = j
                        break

                section_lines = lines[start:end]
                section_text = "\n".join(section_lines)

                m = re.search(r"```[^\n]*\n(.*?)\n```", section_text, re.DOTALL)
                if m:
                    result = m.group(1).strip()
                else:
                    cleaned = "\n".join(
                        l for l in section_lines if not l.startswith("#")
                    ).strip()
                    result = cleaned or None

        _STYLE_PREFIX = result
        _STYLE_RESOLVED = True
        return result


def _resolve_style_prefix(cfg: dict) -> str | None:
    """Walk the `style_brief` config entry, then call `_extract_style_prefix`."""
    sb = cfg.get("style_brief")
    if not isinstance(sb, dict):
        return None
    file_rel = sb.get("file") or "DESIGN.md"
    section = sb.get("section")
    if section is None:
        section = "9"
    return _extract_style_prefix(file_rel, str(section))


# ---------------------------------------------------------------------------
# Mermaid input mode (#648)
# ---------------------------------------------------------------------------

_MERMAID_FENCE_RE = re.compile(r"```mermaid\s*\n(.*?)\n```", re.DOTALL)
_MERMAID_TITLE_DIRECTIVE_RE = re.compile(r"^title:\s*(.+)$", re.MULTILINE)


def _load_mermaid_source(path: Path) -> str:
    """Read a `.mmd` file verbatim, or extract the first ```mermaid fence
    from a `.md` file. Empty or no-fence → exit 2 with a clear error."""
    if not path.exists():
        print(f"generate_image: mermaid source not found: {path}", file=sys.stderr)
        raise SystemExit(2)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".md":
        m = _MERMAID_FENCE_RE.search(text)
        if not m:
            print(f"generate_image: no ```mermaid fence in {path}", file=sys.stderr)
            raise SystemExit(2)
        body = m.group(1).strip()
    else:
        body = text.strip()
    if not body:
        print(f"generate_image: mermaid source is empty: {path}", file=sys.stderr)
        raise SystemExit(2)
    return body


# Node-id token: A | [*] | A[Label] | A((Label)) | A{Label} | A(Label)
_NID = r"(?:\[\*\]|[A-Za-z0-9_]+(?:\s*[\[\(\{][^\]\)\}\n]+[\]\)\}]+)?)"

# Edge syntaxes the parser handles. Order matters — `--text-->` must be
# tried before `-->` to avoid swallowing the label as a node id.
# Each pattern returns 2 or 3 groups; the caller infers labelled-vs-bare
# from group count via the regex's `groups` attribute. State-diagram
# trailing `: label` is captured by the optional `(?::\s*(.+))?` suffix.
_EDGE_PATTERNS = [
    # A -->|label| B
    re.compile(rf"^\s*({_NID})\s*-->\s*\|([^|]+)\|\s*({_NID})\s*(?::\s*(.+))?\s*$"),
    # A -- label --> B
    re.compile(rf"^\s*({_NID})\s*--\s+(.+?)\s+-->\s*({_NID})\s*(?::\s*(.+))?\s*$"),
    # A -.label.-> B
    re.compile(rf"^\s*({_NID})\s*-\.\s*(.+?)\s*\.->\s*({_NID})\s*(?::\s*(.+))?\s*$"),
    # A -.-> B (dotted, no label)
    re.compile(rf"^\s*({_NID})\s*-\.->\s*({_NID})\s*(?::\s*(.+))?\s*$"),
    # A --> B  with optional state-diagram-style `: label` trailing
    re.compile(rf"^\s*({_NID})\s*-->\s*({_NID})\s*(?::\s*(.+))?\s*$"),
]

# Sequence-diagram message arrows: A->>B: message
_SEQ_MSG_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*(->>|-->>|->|-->)\s*([A-Za-z0-9_]+)\s*:\s*(.+)$")

# Node-label-in-brackets: A[Label text] or A((Label)) or A{Label}
_NODE_DEF_RE = re.compile(r"\b([A-Za-z0-9_]+)\s*[\[\({]+([^\]\)}]+)[\]\)}]+")

# State diagram: [*] --> S1, state S1, state "label" as S1
_STATE_LINE_RE = re.compile(r"^\s*state\s+(?:\"([^\"]+)\"\s+as\s+)?([A-Za-z0-9_]+)\s*$")


def _label_likely_truncated(label: str) -> bool:
    """Heuristic — the bracketed-label regex (`_NODE_DEF_RE`) uses a
    single negated character class that excludes ], ), } — which
    means it stops at the FIRST closing bracket regardless of nesting.
    A label like "Layer 0 (~800 tok)" gets captured as
    "Layer 0 (~800 tok" because the regex halted at the inner `)`.

    This heuristic catches the case: count opening vs closing brackets
    of each kind. If the counts disagree (more opens than closes for
    any pair), the regex almost certainly stopped early."""
    pairs = (("(", ")"), ("[", "]"), ("{", "}"))
    for opener, closer in pairs:
        if label.count(opener) > label.count(closer):
            return True
    return False


def _strip_node_decoration(raw: str) -> tuple[str, str | None]:
    """Given a token like `Build[Build node]` return ('Build', 'Build node')
    or `A` return ('A', None). Handles `[]`, `()`, `(())`, `{}`.

    Emits a stderr warning when the extracted label appears truncated
    (unbalanced brackets) — the operator usually meant to include
    everything inside the outer bracket pair, and the regex halted at
    the first inner closer. Doesn't fail the parse; the render will
    produce a degraded label that the operator can repair by
    re-spelling without inner brackets."""
    m = _NODE_DEF_RE.search(raw)
    if m:
        label = m.group(2).strip('"')
        if _label_likely_truncated(label):
            print(
                f"generate_image: WARN — node label appears truncated "
                f"on token {m.group(1)!r}: {label!r}. Mermaid's "
                f"bracket-label regex halts at the first inner closing "
                f"bracket of any kind. Re-spell with - or , instead of "
                f"parentheses inside the label, or use quoted strings.",
                file=sys.stderr,
            )
        return m.group(1), label
    # Bare id; trim any decoration leftovers.
    return raw.strip("[](){}\""), None


def _parse_mermaid(source: str) -> dict:
    """Line-oriented tokenizer for the three supported diagram families.

    Returns: {kind, title, nodes: [{id, label}], edges: [{src, dst, label}],
              participants: [{id, label}], messages: [{src, dst, arrow, text}],
              subgraphs: [{id, label, members}]}.
    """
    lines = source.splitlines()
    kind: str | None = None
    title: str | None = None
    nodes: dict[str, str | None] = {}  # id -> label
    edges: list[dict] = []
    participants: dict[str, str | None] = {}
    messages: list[dict] = []
    subgraphs: list[dict] = []
    subgraph_stack: list[dict] = []

    # First non-blank non-comment line declares the kind.
    for raw in lines:
        s = raw.strip()
        if not s or s.startswith("%%"):
            continue
        head = s.split()[0]
        # Optional `title:` directive sits inside a `---\n…\n---` frontmatter
        # block at the top of the file; we extract it separately.
        # Detect kind from the head token.
        if head.startswith("stateDiagram"):
            kind = "stateDiagram"
        elif head == "sequenceDiagram":
            kind = "sequenceDiagram"
        elif head in ("flowchart", "graph"):
            kind = "flowchart"
        break

    # Title directive (inside the body, or front-matter style at top).
    tm = _MERMAID_TITLE_DIRECTIVE_RE.search(source)
    if tm:
        title = tm.group(1).strip().strip('"').strip("'")

    if kind is None:
        # Unknown — leave nodes/edges empty; the converter still emits a
        # degraded prompt but main() will reject before we get here.
        return {
            "kind": None, "title": title,
            "nodes": [], "edges": [],
            "participants": [], "messages": [],
            "subgraphs": [],
        }

    def _record_node(raw_token: str) -> str:
        node_id, label = _strip_node_decoration(raw_token)
        if node_id in ("", "[*]"):
            node_id = node_id or "_empty"
        if node_id not in nodes or (label and nodes[node_id] is None):
            nodes[node_id] = label
        if subgraph_stack:
            subgraph_stack[-1]["members"].append(node_id)
        return node_id

    for raw in lines:
        s = raw.strip()
        if not s or s.startswith("%%"):
            continue
        head = s.split()[0]
        if head in ("stateDiagram", "stateDiagram-v2", "sequenceDiagram",
                    "flowchart", "graph"):
            # Diagram header — already captured kind.
            continue

        # Subgraph open: `subgraph ID [Label]` or `subgraph ID Label` or `subgraph Label`
        m_sg = re.match(r"^subgraph\s+(.+)$", s)
        if m_sg:
            payload = m_sg.group(1).strip()
            # `ID [Label]` form
            mm = re.match(r"^([A-Za-z0-9_]+)\s*\[([^\]]+)\]\s*$", payload)
            if mm:
                sg = {"id": mm.group(1), "label": mm.group(2), "members": []}
            else:
                # `ID Label` or just `Label`
                parts = payload.split(maxsplit=1)
                if len(parts) == 2 and re.match(r"^[A-Za-z0-9_]+$", parts[0]):
                    sg = {"id": parts[0], "label": parts[1].strip(), "members": []}
                else:
                    sg = {"id": payload, "label": payload, "members": []}
            subgraph_stack.append(sg)
            subgraphs.append(sg)
            continue

        if s == "end" and subgraph_stack:
            subgraph_stack.pop()
            continue

        # Sequence-diagram constructs.
        if kind == "sequenceDiagram":
            m_part = re.match(r"^participant\s+(?:\"([^\"]+)\"\s+as\s+)?([A-Za-z0-9_]+)\s*$", s)
            if m_part:
                participants[m_part.group(2)] = m_part.group(1)
                continue
            m_msg = _SEQ_MSG_RE.match(s)
            if m_msg:
                src, arrow, dst, text = m_msg.groups()
                participants.setdefault(src, None)
                participants.setdefault(dst, None)
                messages.append({"src": src, "arrow": arrow, "dst": dst, "text": text.strip()})
                continue
            # Note over, activate/deactivate, etc — ignored for v1.
            continue

        # State-diagram `state Name` and `state "Label" as Name`.
        if kind == "stateDiagram":
            m_st = _STATE_LINE_RE.match(s)
            if m_st:
                label, node_id = m_st.groups()
                nodes[node_id] = label
                continue

        # Generic edges (flowchart + stateDiagram both use --> family).
        # Patterns return either (src, label, dst, trailing) or
        # (src, dst, trailing) — `len(groups)` distinguishes them.
        matched = False
        for pat in _EDGE_PATTERNS:
            m = pat.match(s)
            if not m:
                continue
            groups = m.groups()
            trailing = None
            if len(groups) == 4:
                src_raw, label, dst_raw, trailing = groups
            elif len(groups) == 3:
                src_raw, dst_raw, trailing = groups
                label = None
            else:
                src_raw, dst_raw = groups[0], groups[1]
                label = None
            # State-diagram convention: `A --> B: label` carries the label
            # as the trailing suffix when the primary label slot is empty.
            if not label and trailing:
                label = trailing
            src_id = _record_node(src_raw)
            dst_id = _record_node(dst_raw)
            edges.append({
                "src": src_id, "dst": dst_id,
                "label": (label or "").strip() or None,
            })
            matched = True
            break

        if matched:
            continue

        # Bare node line with decoration (e.g. `Build[Build]:::cls`)
        if _NODE_DEF_RE.search(s):
            _record_node(s)

    return {
        "kind": kind,
        "title": title,
        "nodes": [{"id": k, "label": v} for k, v in nodes.items()],
        "edges": edges,
        "participants": [{"id": k, "label": v} for k, v in participants.items()],
        "messages": messages,
        "subgraphs": [
            {"id": sg["id"], "label": sg["label"], "members": list(sg["members"])}
            for sg in subgraphs
        ],
    }


def _mermaid_to_prompt(parsed: dict) -> str:
    """Convert the parsed structure into a deterministic English prompt.

    Every node label and every edge label appears verbatim so a downstream
    LLM cannot hallucinate the diagram's contents.
    """
    kind = parsed.get("kind") or "diagram"
    parts: list[str] = []
    title = parsed.get("title")
    if title:
        parts.append(f'Title: "{title}".')
    parts.append(f"Render a {kind} diagram.")

    if kind == "sequenceDiagram":
        participants = parsed.get("participants") or []
        if participants:
            ptxt = ", ".join(
                f"'{p['id']}'" + (f" (alias '{p['label']}')" if p.get("label") else "")
                for p in participants
            )
            parts.append(f"Participants in order: {ptxt}.")
        messages = parsed.get("messages") or []
        if messages:
            mtxt = "; ".join(
                f"'{m['src']}' {m['arrow']} '{m['dst']}': \"{m['text']}\""
                for m in messages
            )
            parts.append(f"Messages: {mtxt}.")
    else:
        nodes = parsed.get("nodes") or []
        if nodes:
            ntxt = ", ".join(
                f"'{n['id']}'" + (f" (label \"{n['label']}\")" if n.get("label") else "")
                for n in nodes
            )
            parts.append(f"Nodes: {ntxt}.")
        edges = parsed.get("edges") or []
        if edges:
            etxt = "; ".join(
                f"'{e['src']}' -> '{e['dst']}'"
                + (f" labeled \"{e['label']}\"" if e.get("label") else "")
                for e in edges
            )
            parts.append(f"Edges: {etxt}.")
        subgraphs = parsed.get("subgraphs") or []
        if subgraphs:
            stxt = "; ".join(
                f"'{sg['id']}' (label \"{sg['label']}\", contains: "
                + ", ".join(f"'{m}'" for m in sg["members"]) + ")"
                for sg in subgraphs
            )
            parts.append(f"Subgraphs: {stxt}.")

    parts.append(
        "Use a clean, schematic style. Render every node label and every "
        "edge label exactly as written. Do not add or omit any node or edge."
    )
    return " ".join(parts)


def _render_reference_image(source: str, cfg_mermaid: dict, tmp_dir: Path
                            ) -> tuple[Path | None, str | None]:
    """Try to produce a baseline PNG of the Mermaid source.

    Preference order:
      1. local `mmdc` (mermaid-cli) on $PATH.
      2. POST https://kroki.io/mermaid/png with the source as text/plain.
      3. None (caller falls back to images.generations with prompt only).

    Returns (path, renderer) where renderer is "mmdc" | "kroki" | None.
    The `disable_reference_image: true` config flag is a hard kill-switch
    that short-circuits both paths and returns (None, None).
    """
    if cfg_mermaid.get("disable_reference_image"):
        return None, None

    prefer_local = bool(cfg_mermaid.get("prefer_local", True))
    kroki_url = str(cfg_mermaid.get("kroki_url") or DEFAULT_KROKI_URL).rstrip("/")
    try:
        kroki_timeout = float(cfg_mermaid.get("kroki_timeout_sec", DEFAULT_KROKI_TIMEOUT_SEC))
    except (TypeError, ValueError):
        kroki_timeout = float(DEFAULT_KROKI_TIMEOUT_SEC)

    candidates: list[str] = []
    if prefer_local:
        candidates = ["mmdc", "kroki"]
    else:
        candidates = ["kroki", "mmdc"]

    for renderer in candidates:
        if renderer == "mmdc":
            if not shutil.which("mmdc"):
                continue
            in_path = tmp_dir / "in.mmd"
            out_path = tmp_dir / "out.png"
            in_path.write_text(source, encoding="utf-8")
            try:
                subprocess.run(
                    ["mmdc", "-i", str(in_path), "-o", str(out_path)],
                    timeout=MERMAID_RENDER_TIMEOUT_SEC,
                    check=True,
                    capture_output=True,
                )
                if out_path.exists() and out_path.stat().st_size > 0:
                    return out_path, "mmdc"
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
                continue
        elif renderer == "kroki":
            req = urllib.request.Request(
                f"{kroki_url}/mermaid/png",
                method="POST",
                headers={
                    "Content-Type": "text/plain",
                    "Accept": "image/png",
                    # kroki.io's front rejects urllib's default User-Agent
                    # with HTTP 403 (observed 2026-05-23); explicit UA
                    # lets the public endpoint accept the POST.
                    "User-Agent": "loswf-generate-image/1.0 (mermaid render)",
                },
                data=source.encode("utf-8"),
            )
            try:
                with urllib.request.urlopen(req, timeout=kroki_timeout) as resp:
                    body = resp.read()
                if body:
                    out_path = tmp_dir / "kroki.png"
                    out_path.write_bytes(body)
                    return out_path, "kroki"
            except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError):
                continue

    return None, None


def _post_images_edit(prompt: str, ref_png_path: Path, out: Path, *,
                       size: str, quality: str, model: str,
                       api_key: str, timeout: int = 240) -> Path:
    """Multipart POST to the images.edit endpoint with the reference PNG.

    Mirrors `generate()`'s 429-retry contract: one retry after sleeping
    for `x-ratelimit-reset-requests` seconds + 1.
    """
    attempts = 0
    while True:
        attempts += 1
        boundary = f"----loswf{uuid.uuid4().hex}"
        nl = "\r\n"
        body_parts: list[bytes] = []

        def _field(name: str, value: str) -> None:
            body_parts.append(
                f"--{boundary}{nl}"
                f'Content-Disposition: form-data; name="{name}"{nl}{nl}'
                f"{value}{nl}".encode("utf-8")
            )

        _field("model", model)
        _field("prompt", prompt)
        _field("size", size)
        if quality:
            _field("quality", quality)
        _field("n", "1")

        png_bytes = ref_png_path.read_bytes()
        body_parts.append(
            f"--{boundary}{nl}"
            f'Content-Disposition: form-data; name="image"; filename="ref.png"{nl}'
            f"Content-Type: image/png{nl}{nl}".encode("utf-8")
        )
        body_parts.append(png_bytes)
        body_parts.append(f"{nl}--{boundary}--{nl}".encode("utf-8"))
        body = b"".join(body_parts)

        req = urllib.request.Request(
            EDIT_API_URL,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            data=body,
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.load(resp)
            break
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            if e.code == 429 and attempts == 1:
                reset = e.headers.get("x-ratelimit-reset-requests") if e.headers else None
                try:
                    delay = float(reset) if reset is not None else 5.0
                except ValueError:
                    delay = 5.0
                time.sleep(max(0.0, delay) + 1.0)
                continue
            print(f"openai images.edit error {e.code}: {err_body[:500]}", file=sys.stderr)
            raise SystemExit(1)
        except urllib.error.URLError as e:
            print(f"openai images.edit unreachable: {e}", file=sys.stderr)
            raise SystemExit(1)

    items = data.get("data") or []
    if not items or "b64_json" not in items[0]:
        print(f"unexpected images.edit response shape: {json.dumps(data)[:500]}", file=sys.stderr)
        raise SystemExit(1)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(base64.b64decode(items[0]["b64_json"]))
    return out


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(prompt: str, limit: int = 48) -> str:
    """Deterministic filename slug. First `limit` chars of the prompt,
    lowercased, non-alphanumeric runs collapsed to `-`, trimmed of
    leading/trailing `-`. Empty slugs fall back to a short prompt hash
    so two empty prompts don't collide."""
    s = _SLUG_RE.sub("-", prompt.lower()).strip("-")
    s = s[:limit].strip("-")
    if not s:
        s = "image-" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8]
    return s


def _default_out_path(prompt: str) -> Path:
    """`.loswf/state/images/<slug>.png` anchored to the project root.
    Used when `--out` is omitted and the `image_gen:` block is present."""
    return _project_root() / ".loswf" / "state" / "images" / f"{_slug(prompt)}.png"


def _receipt_path(out: Path) -> Path:
    return out.with_suffix(".json")


# ---------------------------------------------------------------------------
# Receipt writer
# ---------------------------------------------------------------------------

def _cost_estimate(size: str, quality: str) -> float | None:
    return _COST_TABLE.get((size, quality))


def _write_receipt(
    out: Path,
    *,
    prompt_raw: str,
    prompt_final: str,
    style_injected: bool,
    no_style: bool,
    size: str,
    quality: str,
    model: str,
    ok: bool,
    error: str | None,
    mode: str = "prompt",
    mermaid: dict | None = None,
) -> Path:
    """Write the receipt JSON next to the PNG. Returns the receipt path.

    `mode` is "prompt" (legacy) or "mermaid". `mermaid` carries renderer
    metadata when mode == "mermaid"; both keys are omitted from the
    receipt body when they default, preserving v1 consumer back-compat.
    """
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "prompt_raw": prompt_raw,
        "prompt_final": prompt_final,
        "prompt_hash": hashlib.sha256(prompt_final.encode("utf-8")).hexdigest(),
        "style_injected": style_injected,
        "no_style": no_style,
        "out": str(out.resolve()) if out.exists() else str(out),
        "out_path": str(out),
        "size": size,
        "quality": quality,
        "model": model,
        "cost_estimate": _cost_estimate(size, quality),
        "caller_pid": os.getppid(),
        "ok": ok,
        "error": error,
    }
    if mode and mode != "prompt":
        receipt["mode"] = mode
    if mermaid is not None:
        receipt["mermaid"] = mermaid
    rpath = _receipt_path(out)
    rpath.parent.mkdir(parents=True, exist_ok=True)
    rpath.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return rpath


# ---------------------------------------------------------------------------
# OpenAI call
# ---------------------------------------------------------------------------

def _post_once(prompt: str, *, size: str, quality: str, model: str,
               api_key: str, timeout: int):
    """Single POST. Returns (data_dict, None) on success; raises on
    HTTPError so the caller can handle 429 retries deterministically."""
    payload = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "n": 1,
    }
    if quality:
        payload["quality"] = quality

    req = urllib.request.Request(
        API_URL,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload).encode("utf-8"),
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def generate(prompt: str, out: Path, *, size: str, quality: str,
             model: str, api_key: str, timeout: int = 240,
             max_transient_retries: int = 2) -> Path:
    """POST to the images endpoint and write the resulting PNG.

    Retry shape:
      - 429 (rate limit): one retry after sleeping for the
        `x-ratelimit-reset-requests` header value + 1s margin.
      - Transient network failures (TimeoutError, socket.timeout,
        urllib URLError wrapping a timeout): up to `max_transient_retries`
        retries with exponential backoff (10s, 30s).
      - 5xx server errors: also retried under the transient bucket.
      - Other HTTP errors (400, 401, 403, 404): no retry — exit 1.

    Network unreachability after exhausting retries propagates as exit 1
    with a clear stderr message naming what was tried."""
    import socket  # local import; only this function needs it
    attempts = 0
    transient_attempts = 0
    rate_limit_attempts = 0
    backoff_schedule = [10, 30]  # seconds between transient retries
    while True:
        attempts += 1
        try:
            data = _post_once(
                prompt, size=size, quality=quality,
                model=model, api_key=api_key, timeout=timeout,
            )
            break
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if e.code == 429 and rate_limit_attempts == 0:
                rate_limit_attempts += 1
                reset = e.headers.get("x-ratelimit-reset-requests") if e.headers else None
                try:
                    delay = float(reset) if reset is not None else 5.0
                except ValueError:
                    delay = 5.0
                print(
                    f"openai api rate-limited (attempt {attempts}); "
                    f"sleeping {delay + 1:.1f}s",
                    file=sys.stderr,
                )
                time.sleep(max(0.0, delay) + 1.0)
                continue
            if 500 <= e.code < 600 and transient_attempts < max_transient_retries:
                delay = backoff_schedule[transient_attempts]
                transient_attempts += 1
                print(
                    f"openai api {e.code} (attempt {attempts}); "
                    f"retrying in {delay}s",
                    file=sys.stderr,
                )
                time.sleep(delay)
                continue
            print(f"openai api error {e.code}: {body[:500]}", file=sys.stderr)
            raise SystemExit(1)
        except (TimeoutError, socket.timeout) as e:
            if transient_attempts < max_transient_retries:
                delay = backoff_schedule[transient_attempts]
                transient_attempts += 1
                print(
                    f"openai api read timed out (attempt {attempts}); "
                    f"retrying in {delay}s",
                    file=sys.stderr,
                )
                time.sleep(delay)
                continue
            print(
                f"openai api persistently timed out after {attempts} attempts: {e}",
                file=sys.stderr,
            )
            raise SystemExit(1)
        except urllib.error.URLError as e:
            # URLError can wrap a timeout or a connection refusal.
            inner = e.reason
            is_timeout = isinstance(inner, (TimeoutError, socket.timeout))
            if is_timeout and transient_attempts < max_transient_retries:
                delay = backoff_schedule[transient_attempts]
                transient_attempts += 1
                print(
                    f"openai api connect timed out (attempt {attempts}); "
                    f"retrying in {delay}s",
                    file=sys.stderr,
                )
                time.sleep(delay)
                continue
            print(f"openai api unreachable: {e}", file=sys.stderr)
            raise SystemExit(1)

    items = data.get("data") or []
    if not items or "b64_json" not in items[0]:
        print(f"unexpected response shape: {json.dumps(data)[:500]}", file=sys.stderr)
        raise SystemExit(1)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(base64.b64decode(items[0]["b64_json"]))
    return out


# ---------------------------------------------------------------------------
# Single-item dispatch (used by both interactive and batch paths)
# ---------------------------------------------------------------------------

def _build_final_prompt(prompt: str, *, no_style: bool, cfg: dict | None
                        ) -> tuple[str, bool]:
    """Returns (final_prompt, style_injected). Pulls the cached style
    prefix when config is present and --no-style is absent."""
    if no_style or cfg is None:
        return prompt, False
    prefix = _resolve_style_prefix(cfg)
    if not prefix:
        return prompt, False
    return f"{prefix}\n\n{prompt}", True


def _mermaid_default_slug(parsed: dict, mermaid_path: Path) -> str:
    """Slug derivation for --mermaid when --out is omitted.

    Prefer the Mermaid `title:` directive when present; else the source
    filename stem. Both are run through `_slug` for determinism.
    """
    title = (parsed.get("title") or "").strip()
    if title:
        return _slug(title)
    return _slug(mermaid_path.stem)


def _run_one(
    *,
    prompt: str | None,
    out: Path | None,
    size: str,
    quality: str,
    model: str,
    api_key: str,
    no_style: bool,
    cfg: dict | None,
    mermaid_path: Path | None = None,
) -> dict:
    """Execute one image generation. Returns the receipt payload.

    Exactly one of `prompt` or `mermaid_path` must be set. With
    `mermaid_path`, the tool parses the Mermaid source, converts it to a
    structured English prompt, optionally produces a baseline rendering
    via mmdc/kroki, and routes through images.edit when a reference PNG
    is available — otherwise falls through to images.generations with
    the converted prompt.
    """
    if (prompt is None) == (mermaid_path is None):
        raise SystemExit(
            "generate_image: exactly one of `prompt` or `mermaid_path` must be set"
        )

    mode = "prompt"
    mermaid_meta: dict | None = None
    parsed: dict | None = None
    raw_prompt_for_receipt = prompt or ""
    converted_prompt: str | None = None
    ref_path: Path | None = None
    renderer: str | None = None
    tmp_ctx: tempfile.TemporaryDirectory | None = None

    if mermaid_path is not None:
        mode = "mermaid"
        source = _load_mermaid_source(mermaid_path)
        parsed = _parse_mermaid(source)
        if parsed.get("kind") not in SUPPORTED_MERMAID_KINDS:
            print(
                f"generate_image: unsupported Mermaid diagram kind: "
                f"{parsed.get('kind')!r}; supported: "
                f"{', '.join(SUPPORTED_MERMAID_KINDS)}",
                file=sys.stderr,
            )
            raise SystemExit(2)
        converted_prompt = _mermaid_to_prompt(parsed)
        raw_prompt_for_receipt = converted_prompt

        cfg_mermaid = (cfg or {}).get("mermaid") or {}
        tmp_ctx = tempfile.TemporaryDirectory(prefix="loswf-mermaid-")
        ref_path, renderer = _render_reference_image(
            source, cfg_mermaid, Path(tmp_ctx.name),
        )
        mermaid_meta = {
            "source_path": str(mermaid_path),
            "source_hash": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "kind": parsed.get("kind"),
            "node_count": len(parsed.get("nodes") or []) + len(parsed.get("participants") or []),
            "edge_count": len(parsed.get("edges") or []) + len(parsed.get("messages") or []),
            "renderer": renderer,
            "reference_image_used": ref_path is not None,
        }
        prompt = converted_prompt

    final_prompt, style_injected = _build_final_prompt(
        prompt, no_style=no_style, cfg=cfg,
    )

    # Default-out path resolves only when the image_gen block is present.
    # Backward compat: without the block, --out is required and we never
    # synthesize a path here.
    if out is None:
        if cfg is None:
            if tmp_ctx is not None:
                tmp_ctx.cleanup()
            raise SystemExit(
                "generate_image: --out is required when image_gen: is not "
                "configured in .loswf/config.yaml"
            )
        if mermaid_path is not None and parsed is not None:
            out = _project_root() / ".loswf" / "state" / "images" / (
                _mermaid_default_slug(parsed, mermaid_path) + ".png"
            )
        else:
            out = _default_out_path(prompt or "")

    error: str | None = None
    ok = True
    try:
        if mermaid_path is not None and ref_path is not None:
            _post_images_edit(
                final_prompt, ref_path, out,
                size=size, quality=quality,
                model=model, api_key=api_key,
            )
        else:
            generate(
                final_prompt, out,
                size=size, quality=quality,
                model=model, api_key=api_key,
            )
    except SystemExit as e:
        ok = False
        error = f"exit {e.code}"
        # Write the receipt before re-raising so failures are inspectable.
        if cfg is not None:
            _write_receipt(
                out,
                prompt_raw=raw_prompt_for_receipt,
                prompt_final=final_prompt,
                style_injected=style_injected,
                no_style=no_style,
                size=size,
                quality=quality,
                model=model,
                ok=ok,
                error=error,
                mode=mode,
                mermaid=mermaid_meta,
            )
        raise
    finally:
        if tmp_ctx is not None:
            tmp_ctx.cleanup()

    receipt_path: Path | None = None
    if cfg is not None:
        receipt_path = _write_receipt(
            out,
            prompt_raw=raw_prompt_for_receipt,
            prompt_final=final_prompt,
            style_injected=style_injected,
            no_style=no_style,
            size=size,
            quality=quality,
            model=model,
            ok=ok,
            error=error,
            mode=mode,
            mermaid=mermaid_meta,
        )

    return {
        "ok": ok,
        "path": str(out),
        "size": size,
        "model": model,
        "style_injected": style_injected,
        "receipt": str(receipt_path) if receipt_path else None,
        "mode": mode,
        "renderer": renderer,
    }


# ---------------------------------------------------------------------------
# Batch driver
# ---------------------------------------------------------------------------

def _load_manifest(path: Path) -> list[dict]:
    """Parse a `--batch` manifest. Schema (architect doc §"Batch manifest
    schema"):

      images:
        - prompt: "..."
          out: optional/path.png
          size: optional
          quality: optional
    """
    try:
        import yaml  # type: ignore
    except ImportError:
        print("generate_image: pyyaml not installed; --batch requires pyyaml",
              file=sys.stderr)
        raise SystemExit(2)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = data.get("images")
    if not isinstance(items, list) or not items:
        print(f"generate_image: manifest {path} has no `images:` list",
              file=sys.stderr)
        raise SystemExit(2)
    return items


def _run_batch(
    manifest_path: Path,
    *,
    default_size: str,
    default_quality: str,
    model: str,
    api_key: str,
    no_style: bool,
    cfg: dict | None,
    max_workers: int,
) -> list[dict]:
    items = _load_manifest(manifest_path)

    def _job(entry: dict) -> dict:
        prompt = entry.get("prompt")
        mermaid_raw = entry.get("mermaid")
        if bool(prompt) == bool(mermaid_raw):
            raise SystemExit(
                "generate_image: manifest entry must set exactly one of "
                "`prompt:` or `mermaid:`"
            )
        out_raw = entry.get("out")
        out = Path(out_raw) if out_raw else None
        size = entry.get("size") or default_size
        quality = entry.get("quality") or default_quality
        return _run_one(
            prompt=prompt, out=out,
            mermaid_path=(Path(mermaid_raw) if mermaid_raw else None),
            size=size, quality=quality, model=model, api_key=api_key,
            no_style=no_style, cfg=cfg,
        )

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        # Preserve input order in the output stream so operators can
        # correlate stdout lines with manifest entries.
        for r in pool.map(_job, items):
            results.append(r)
    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _reset_caches_for_tests() -> None:
    """Test helper — clear module-level caches between unit tests."""
    global _STYLE_PREFIX, _STYLE_RESOLVED, _CONFIG_CACHE, _CONFIG_RESOLVED
    _STYLE_PREFIX = None
    _STYLE_RESOLVED = False
    _CONFIG_CACHE = None
    _CONFIG_RESOLVED = False


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Generate supporting artwork or diagrams via OpenAI gpt-image-2."
    )
    p.add_argument("--prompt",
                   help="natural-language prompt describing the desired image")
    p.add_argument("--mermaid", type=Path,
                   help="path to a .mmd file or a .md file containing a "
                        "```mermaid fence; renders a structurally accurate "
                        "diagram (mutually exclusive with --prompt)")
    p.add_argument("--out", type=Path,
                   help="output PNG path (defaults to .loswf/state/images/<slug>.png "
                        "when image_gen: is configured)")
    p.add_argument("--size", default="1536x1024", choices=SIZE_CHOICES)
    p.add_argument("--quality", default="high", choices=QUALITY_CHOICES)
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"OpenAI image model (default: {DEFAULT_MODEL})")
    p.add_argument("--no-style", action="store_true",
                   help="bypass brand-voice injection")
    p.add_argument("--batch", type=Path,
                   help="path to a YAML manifest; fan out across a threadpool")
    args = p.parse_args(argv)

    # Mutex enforcement (PRD-648 §5 Must, plan step 1).
    if args.prompt and args.mermaid:
        print(
            "generate_image: --prompt and --mermaid are mutually exclusive; "
            "pass --mermaid alone for structural diagrams",
            file=sys.stderr,
        )
        return 2

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("generate_image: OPENAI_API_KEY not set in environment",
              file=sys.stderr)
        return 2

    cfg = _load_config()

    if args.batch:
        max_workers = DEFAULT_BATCH_WORKERS
        if cfg is not None:
            batch_cfg = cfg.get("batch") or {}
            try:
                max_workers = int(batch_cfg.get("max_workers", DEFAULT_BATCH_WORKERS))
            except (TypeError, ValueError):
                max_workers = DEFAULT_BATCH_WORKERS
        results = _run_batch(
            args.batch,
            default_size=args.size,
            default_quality=args.quality,
            model=args.model,
            api_key=api_key,
            no_style=args.no_style,
            cfg=cfg,
            max_workers=max_workers,
        )
        for r in results:
            print(json.dumps(r))
        return 0

    # Single-image mode.
    if not args.prompt and not args.mermaid:
        print("generate_image: --prompt or --mermaid is required (or use --batch)",
              file=sys.stderr)
        return 2

    # Backward compat: when no image_gen: block, --out remains required.
    if args.out is None and cfg is None:
        print("generate_image: --out is required when image_gen: is not "
              "configured in .loswf/config.yaml", file=sys.stderr)
        return 2

    result = _run_one(
        prompt=args.prompt,
        mermaid_path=args.mermaid,
        out=args.out,
        size=args.size,
        quality=args.quality,
        model=args.model,
        api_key=api_key,
        no_style=args.no_style,
        cfg=cfg,
    )
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
