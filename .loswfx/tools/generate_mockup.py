#!/usr/bin/env python3
"""generate_mockup — deterministic LOSWFX UI mockups from a text wireframe.

A terse wireframe DSL (with a raw-HTML escape hatch) compiles to HTML styled
by the real `internal/api/webui/assets/tokens.css`, rendered headless via
Chrome to a screenshot. The image model is NOT the engine — because the brand
is intentionally flat (DESIGN.md §7: no shadows/gradients/glow), the raw
render is final-quality. `--polish` is an optional pass through
generate_image.py's images.edit path for cases that want texture.

Spec: docs/design/mockup-tool-spec.md.

  generate_mockup.py --in surface.mock --out out.png [--viewport 1536x1024] [--polish]
  generate_mockup.py --batch manifest.json     # {"mockups":[{in,out,viewport,polish}]}

The DSL vocabulary mirrors the design-system / templ components, so a mockup is
a serialization of real components and can't drift into a layout production
can't build. Status is always glyph + class, never color alone (DESIGN.md §3).
"""
from __future__ import annotations

import argparse
import hashlib
import html as htmllib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------
# §3 status glyph vocabulary — the char is paired with a g-* class, always.
# --------------------------------------------------------------------------
GLYPHS = {"ok": "✓", "warn": "!", "err": "✕", "idle": "○", "inflight": "⠋"}

# stance identity glyphs (distinct from status glyphs)
STANCE_GLYPHS = {
    "control room": "▣", "fleet": "▦", "definition": "◇",
    "bench": "▤", "client": "◎", "loop": "↻",
}

# bare words that are boolean flags rather than positional labels
FLAGS = {"active", "live", "primary", "ghost", "disabled", "collapsed", "done"}

REPO_ROOT = Path(__file__).resolve().parents[2]
TOKENS_PATH = REPO_ROOT / "internal" / "api" / "webui" / "assets" / "tokens.css"


# --------------------------------------------------------------------------
# Parse — DSL text -> Node tree
# --------------------------------------------------------------------------
class Node:
    __slots__ = ("kind", "args", "attrs", "children", "raw")

    def __init__(self, kind, args=None, attrs=None, raw=None):
        self.kind = kind
        self.args = args or []            # list[(text, tag|None)]
        self.attrs = attrs or {}          # dict[str, str|True]
        self.children = []                # list[Node]
        self.raw = raw                    # str for html: blocks

    def __repr__(self):  # pragma: no cover - debug aid
        return f"Node({self.kind!r}, args={self.args}, attrs={self.attrs})"


def _tokenize(s: str):
    """A line's content -> (keyword, args, attrs).

    Handles quoted positionals (optionally `"text":tag`), `key=value` with
    quoted values that may contain spaces, bare `name:tag` suffixes, and bare
    flags vs bare positional labels.
    """
    i, n = 0, len(s)
    args: list[tuple[str, str | None]] = []
    attrs: dict[str, object] = {}
    keyword = None

    def read_word(j):
        start = j
        while j < n and not s[j].isspace() and s[j] not in '="':
            j += 1
        return s[start:j], j

    while i < n:
        if s[i].isspace():
            i += 1
            continue
        if s[i] == '"':
            j = i + 1
            while j < n and s[j] != '"':
                j += 1
            text = s[i + 1:j]
            i = j + 1
            tag = None
            if i < n and s[i] == ':':
                i += 1
                word, i = read_word(i)
                tag = word
            args.append((text, tag))
            continue
        # bare chunk (head), maybe followed by '=' (attr) or ':' (tag)
        head, i = read_word(i)
        if i < n and s[i] == '=':
            i += 1
            if i < n and s[i] == '"':
                j = i + 1
                while j < n and s[j] != '"':
                    j += 1
                val = s[i + 1:j]
                i = j + 1
            else:
                val, i = read_word(i)
            attrs[head] = val
            continue
        # no '=' : keyword, flag, or positional (possibly name:tag)
        if keyword is None:
            keyword = head
            continue
        if ':' in head:
            name, tag = head.split(':', 1)
            args.append((name, tag))
        elif head in FLAGS:
            attrs[head] = True
        else:
            args.append((head, None))
    return keyword, args, attrs


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def parse_wireframe(text: str) -> Node:
    lines = text.split("\n")
    root: Node | None = None
    stack: list[tuple[int, Node]] = []  # (indent, node)
    i = 0
    while i < len(lines):
        raw = lines[i]
        if not raw.strip() or raw.lstrip().startswith("#"):
            i += 1
            continue
        indent = _indent_of(raw)
        content = raw.strip()

        if content == "html:":
            # consume strictly-more-indented following lines as raw HTML
            block, j = [], i + 1
            base = None
            while j < len(lines):
                ln = lines[j]
                if not ln.strip():
                    block.append("")
                    j += 1
                    continue
                if _indent_of(ln) <= indent:
                    break
                if base is None:
                    base = _indent_of(ln)
                block.append(ln[base:] if base else ln.lstrip())
                j += 1
            node = Node("html", raw="\n".join(block).strip("\n"))
            _attach(root, stack, indent, node)
            if root is None:
                root = node
            i = j
            continue

        keyword, args, attrs = _tokenize(content)
        node = Node(keyword, args=args, attrs=attrs)
        if root is None:
            root = node
            stack = [(indent, node)]
        else:
            _attach(root, stack, indent, node)
        i += 1
    if root is None:
        raise ValueError("empty wireframe")
    return root


def _attach(root, stack, indent, node):
    while stack and stack[-1][0] >= indent:
        stack.pop()
    if stack:
        stack[-1][1].children.append(node)
    stack.append((indent, node))


# --------------------------------------------------------------------------
# Compile — Node tree -> HTML body
# --------------------------------------------------------------------------
def _esc(t: str) -> str:
    return htmllib.escape(t, quote=True)


def _glyph_span(state: str) -> str:
    state = (state or "").strip()
    char = GLYPHS.get(state)
    if not char:
        return ""
    return f'<span class="g g-{_esc(state)}">{char}</span>'


def compile_html(root: Node) -> str:
    if root.kind != "mockup":
        return "".join(_render(c) for c in [root])
    return "".join(_render(c) for c in root.children)


def _render(node: Node) -> str:
    fn = _RENDERERS.get(node.kind)
    if fn:
        return fn(node)
    # unknown component: render children inside a neutral div so the DSL is
    # forgiving rather than fatal.
    inner = "".join(_render(c) for c in node.children)
    return f'<div class="{_esc(node.kind)}">{inner}</div>'


def _label(node: Node) -> str:
    return node.args[0][0] if node.args else ""


def _r_sidebar(node):
    scope = node.attrs.get("scope")
    chip = f'<span class="scope">{_esc(scope)}</span>' if isinstance(scope, str) else ""
    stances = "".join(_render(c) for c in node.children if c.kind == "stance")
    others = "".join(_render(c) for c in node.children if c.kind != "stance")
    collapsed = " collapsed" if node.attrs.get("collapsed") else ""
    return (
        f'<aside class="sidebar{collapsed}">'
        f'<div class="brand"><div class="mark">LOSWFX</div>{chip}</div>'
        f'<nav class="stances">{stances}</nav>{others}'
        f'<div class="collapse">«</div></aside>'
    )


def _r_stance(node):
    label = _label(node)
    active = " active" if node.attrs.get("active") else ""
    glyph = STANCE_GLYPHS.get(label, "•")
    badge = node.attrs.get("badge")
    badge_html = f'<span class="badge">{_esc(str(badge))}</span>' if isinstance(badge, str) else ""
    return (
        f'<div class="stance{active}" data-stance="{_esc(label)}">'
        f'<span class="g">{glyph}</span><span class="lbl">{_esc(label)}</span>{badge_html}</div>'
    )


def _r_main(node):
    edges = [c for c in node.children if c.kind == "drawer-edge"]
    body = [c for c in node.children if c.kind != "drawer-edge"]
    inner = "".join(_render(c) for c in body)
    edge_html = "".join(_render(c) for c in edges)
    pad = " has-edge" if edges else ""
    return f'<div class="main{pad}"><div class="content">{inner}</div>{edge_html}</div>'


def _r_topbar(node):
    return f'<header class="topbar">{"".join(_render(c) for c in node.children)}</header>'


def _r_rail(node):
    label = _label(node)
    live = '<span class="live"><span class="dot">●</span> live</span>' if node.attrs.get("live") else ""
    return f'<div class="rail"><span class="ring">○</span> {_esc(label)}{live}</div>'


def _r_stateline(node):
    return f'<div class="state">{"".join(_render(c) for c in node.children)}</div>'


def _r_seg(node):
    label = _label(node)
    value = node.attrs.get("value", "")
    glyph = _glyph_span(node.attrs.get("glyph", "")) if isinstance(node.attrs.get("glyph"), str) else ""
    val = f' <b>{_esc(str(value))}</b>' if value != "" else ""
    return f'<span class="seg-item"><span class="k">{_esc(label)}</span> {glyph}{val}</span>'


def _r_stepper(node):
    parts = []
    for idx, (name, state) in enumerate(node.args):
        cls = f" {state}" if state in ("done", "active", "warn", "err") else ""
        marker = {"warn": "!", "err": "✕"}.get(state, "")
        if idx:
            seg_done = " done" if node.args[idx - 1][1] == "done" else ""
            parts.append(f'<div class="seg{seg_done}"></div>')
        parts.append(f'<div class="node{cls}"><div class="dot2">{marker}</div>{_esc(name)}</div>')
    return f'<div class="stepper">{"".join(parts)}</div>'


def _r_table(node):
    cols = [c.strip() for c in str(node.attrs.get("cols", "")).split(",") if c.strip()]
    n = max(len(cols), 1)
    grid = "1fr " + " ".join(["max-content"] * (n - 1)) if n > 1 else "1fr"
    style = f'style="grid-template-columns:{grid}"'
    hd = "".join(f"<span>{_esc(c)}</span>" for c in cols)
    rows = "".join(_render_row(r, n, style) for r in node.children if r.kind == "row")
    return f'<div class="work"><div class="hd" {style}>{hd}</div>{rows}</div>'


def _render_row(node, n, style):
    cells = []
    for idx, (text, tag) in enumerate(node.args):
        cls = []
        if idx == 0:
            cls.append("title")
        if tag in GLYPHS or tag in ("ok", "warn", "err", "idle", "inflight"):
            cls.append("st-" + tag)
        elif idx > 0:
            cls.append("mut")
        c = f' class="{" ".join(cls)}"' if cls else ""
        cells.append(f"<span{c}>{_esc(text)}</span>")
    return f'<div class="row" {style}>{"".join(cells)}</div>'


def _r_card(node):
    title = node.attrs.get("title")
    t = f'<div class="card-title">{_esc(title)}</div>' if isinstance(title, str) else ""
    return f'<div class="card">{t}{"".join(_render(c) for c in node.children)}</div>'


def _r_button(node):
    label = _label(node)
    variant = "primary" if node.attrs.get("primary") else ("ghost" if node.attrs.get("ghost") else "")
    dis = " disabled" if node.attrs.get("disabled") else ""
    attr = ' disabled' if node.attrs.get("disabled") else ""
    return f'<button class="btn {variant}{dis}"{attr}>{_esc(label)}</button>'


def _r_glyph(node):
    return _glyph_span(_label(node) or node.attrs.get("state", ""))


def _r_drawer(node):
    title = node.attrs.get("title", "")
    return (
        f'<aside class="drawer"><header class="drawer-h">{_esc(str(title))}</header>'
        f'{"".join(_render(c) for c in node.children)}</aside>'
    )


def _r_drawer_edge(node):
    return f'<div class="edge"><span>{_esc(_label(node) or "evidence")}</span></div>'


def _r_html(node):
    return node.raw or ""


def _r_steprail(node):
    title = node.attrs.get("title", "")
    steps = "".join(_render(c) for c in node.children if c.kind == "step")
    return (
        f'<aside class="steprail"><div class="brand"><div class="mark">LOSWFX</div>'
        f'<div class="rail-title">{_esc(str(title))}</div></div>'
        f'<ol class="steps">{steps}</ol></aside>'
    )


def _r_step(node):
    state = "done" if node.attrs.get("done") else ("active" if node.attrs.get("active") else "dim")
    marker = "✓" if state == "done" else "●"
    return f'<li class="step {state}"><span class="step-g">{marker}</span> {_esc(_label(node))}</li>'


def _r_checkrow(node):
    glyph = _glyph_span(node.attrs.get("glyph", "")) if isinstance(node.attrs.get("glyph"), str) else ""
    detail = node.attrs.get("detail", "")
    det = f'<span class="cr-detail">{_esc(str(detail))}</span>' if detail else ""
    sub = "".join(_render(c) for c in node.children)
    sub_html = f'<div class="cr-sub">{sub}</div>' if sub else ""
    return (
        f'<div class="checkrow">{glyph}<span class="cr-name">{_esc(_label(node))}</span>{det}</div>'
        f'{sub_html}'
    )


def _r_pills(node):
    return f'<div class="pills">{"".join(_render(c) for c in node.children)}</div>'


def _r_pill(node):
    active = " active" if node.attrs.get("active") else ""
    return f'<span class="pill{active}">{_esc(_label(node))}</span>'


_RENDERERS = {
    "sidebar": _r_sidebar, "stance": _r_stance, "main": _r_main, "topbar": _r_topbar,
    "rail": _r_rail, "stateline": _r_stateline, "seg": _r_seg, "stepper": _r_stepper,
    "table": _r_table, "card": _r_card, "panel": _r_card, "button": _r_button,
    "glyph": _r_glyph, "drawer": _r_drawer, "drawer-edge": _r_drawer_edge, "html": _r_html,
    "steprail": _r_steprail, "step": _r_step, "checkrow": _r_checkrow,
    "pills": _r_pills, "pill": _r_pill,
}


# --------------------------------------------------------------------------
# Shell — wrap body in the tokens + base CSS document
# --------------------------------------------------------------------------
BASE_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{background:var(--bg);color:var(--text);font-family:var(--font-sans);
  font-size:var(--fs-2);display:flex;-webkit-font-smoothing:antialiased}
.sidebar{width:216px;flex:0 0 216px;background:var(--surface-2);
  border-right:1px solid var(--border);display:flex;flex-direction:column;padding:var(--sp-4) 0}
.sidebar.collapsed{width:56px;flex-basis:56px}
.sidebar.collapsed .lbl,.sidebar.collapsed .scope,.sidebar.collapsed .badge,.sidebar.collapsed .mark{display:none}
.brand{padding:0 var(--sp-4) var(--sp-4)}
.mark{font-family:var(--font-mono);font-weight:700;letter-spacing:.04em}
.scope{display:inline-block;margin-top:var(--sp-2);font-family:var(--font-mono);
  font-size:var(--fs-0);color:var(--muted);border:1px solid var(--border);
  border-radius:var(--radius);padding:1px var(--sp-2)}
.stances{margin-top:var(--sp-2);display:flex;flex-direction:column}
.stance{display:flex;align-items:center;gap:var(--sp-3);padding:var(--sp-2) var(--sp-4);
  color:var(--muted);font-size:var(--fs-1);border-left:2px solid transparent}
.stance .g{font-family:var(--font-mono);width:1.1em;text-align:center;opacity:.8}
.stance.active{color:var(--accent);border-left-color:var(--accent);background:#15212c;font-weight:600}
.stance.active .g{opacity:1}
.badge{margin-left:auto;background:var(--accent);color:var(--accent-ink);
  font-family:var(--font-mono);font-size:var(--fs-0);border-radius:var(--radius);padding:0 6px;font-weight:700}
.collapse{margin-top:auto;padding:var(--sp-3) var(--sp-4);color:var(--muted);font-family:var(--font-mono)}
.main{flex:1;display:flex;flex-direction:column;min-width:0;position:relative}
.content{flex:1;display:flex;flex-direction:column;min-width:0}
.main.has-edge .content{padding-right:34px}
.topbar{display:flex;align-items:center;gap:var(--sp-4);padding:var(--sp-3) var(--sp-5);
  border-bottom:1px solid var(--border);background:var(--surface-2)}
.rail{display:flex;align-items:center;gap:var(--sp-2);padding:var(--sp-3) var(--sp-5);
  border-bottom:1px solid var(--border);color:var(--muted);font-size:var(--fs-1)}
.rail .ring{color:var(--accent)}
.rail .live{margin-left:auto;color:var(--ok);font-family:var(--font-mono);font-size:var(--fs-0)}
.state{display:flex;gap:var(--sp-5);padding:var(--sp-4) var(--sp-5);
  font-family:var(--font-mono);font-size:var(--fs-1);border-bottom:1px solid var(--border)}
.state .k{color:var(--muted)}
.state b{color:var(--text);font-weight:400}
.g-ok{color:var(--ok)}.g-warn{color:var(--warn)}.g-err{color:var(--err)}
.g-idle{color:var(--muted)}.g-inflight{color:var(--accent)}
.stepper{display:flex;align-items:center;padding:var(--sp-6) var(--sp-5) var(--sp-5)}
.node{display:flex;flex-direction:column;align-items:center;gap:var(--sp-2);font-size:var(--fs-0);color:var(--muted)}
.dot2{width:14px;height:14px;border-radius:50%;border:1.5px solid var(--border)}
.node.done .dot2{border-color:var(--ok);background:var(--ok)}
.node.active .dot2{border-color:var(--accent);background:var(--accent);box-shadow:0 0 0 3px #15212c}
.node.active{color:var(--accent);font-family:var(--font-mono)}
.node .dot2{display:flex;align-items:center;justify-content:center;font-family:var(--font-mono);font-size:10px;color:var(--bg)}
.node.warn .dot2{border-color:var(--warn);background:var(--warn)}
.node.warn{color:var(--warn);font-family:var(--font-mono)}
.node.err .dot2{border-color:var(--err);background:var(--err)}
.node.err{color:var(--err);font-family:var(--font-mono)}
.seg{height:1px;flex:1;background:var(--border);margin:0 var(--sp-2);position:relative;top:-9px}
.seg.done{background:var(--ok)}
.work{margin:var(--sp-3) var(--sp-5)}
.work .hd,.work .row{display:grid;gap:var(--sp-3);padding:var(--sp-3);align-items:center}
.work .hd{color:var(--muted);font-size:var(--fs-0);text-transform:uppercase;letter-spacing:.06em;border-bottom:1px solid var(--border)}
.work .row{font-family:var(--font-mono);font-size:var(--fs-1);border-bottom:1px solid var(--border)}
.work .row .title{font-family:var(--font-sans);color:var(--text)}
.work .row .mut{color:var(--muted)}
.work .row .st-inflight{color:var(--accent)}.work .row .st-idle{color:var(--muted)}
.work .row .st-ok{color:var(--ok)}.work .row .st-warn{color:var(--warn)}.work .row .st-err{color:var(--err)}
.card{border:1px solid var(--border);background:var(--surface);border-radius:var(--radius);
  padding:var(--sp-4);margin:var(--sp-3) var(--sp-5)}
.card-title{font-size:var(--fs-3);margin-bottom:var(--sp-3)}
.btn{font-family:var(--font-mono);font-size:var(--fs-1);border-radius:var(--radius);
  padding:var(--sp-2) var(--sp-4);border:1px solid var(--border);background:transparent;color:var(--text)}
.btn.primary{background:var(--accent);color:var(--accent-ink);border-color:var(--accent)}
.btn.disabled{opacity:.4}
.drawer{position:absolute;top:0;right:0;height:100%;width:33%;background:var(--surface);
  border-left:1px solid var(--border);padding:var(--sp-4)}
.drawer-h{font-size:var(--fs-3);margin-bottom:var(--sp-3)}
.edge{position:absolute;top:0;right:0;height:100%;width:34px;border-left:1px solid var(--border);
  background:var(--surface);display:flex;align-items:center;justify-content:center}
.edge span{writing-mode:vertical-rl;transform:rotate(180deg);color:var(--muted);
  font-size:var(--fs-0);letter-spacing:.12em;text-transform:uppercase}
.steprail{width:240px;flex:0 0 240px;background:var(--surface-2);
  border-right:1px solid var(--border);padding:var(--sp-4)}
.rail-title{color:var(--muted);font-size:var(--fs-0);text-transform:uppercase;
  letter-spacing:.08em;margin-top:var(--sp-2)}
.steps{list-style:none;margin-top:var(--sp-5);display:flex;flex-direction:column;gap:var(--sp-4)}
.step{display:flex;align-items:center;gap:var(--sp-3);font-size:var(--fs-1);color:var(--muted)}
.step .step-g{font-family:var(--font-mono);width:1.2em;text-align:center}
.step.done{color:var(--text)}.step.done .step-g{color:var(--ok)}
.step.active{color:var(--accent);font-weight:600}.step.active .step-g{color:var(--accent)}
.step.dim{color:var(--muted);opacity:.6}
.checkrow{display:flex;align-items:center;gap:var(--sp-3);padding:var(--sp-3) var(--sp-5);
  border-bottom:1px solid var(--border);font-size:var(--fs-1)}
.checkrow .cr-name{min-width:200px}
.checkrow .cr-detail{color:var(--muted);font-family:var(--font-mono);font-size:var(--fs-0)}
.cr-sub{margin:0 var(--sp-5) var(--sp-3);padding:var(--sp-3);border:1px solid var(--border);
  background:var(--surface);border-radius:var(--radius);font-size:var(--fs-1)}
.pills{display:flex;gap:var(--sp-2);flex-wrap:wrap;padding:var(--sp-3) var(--sp-5)}
.pill{font-family:var(--font-mono);font-size:var(--fs-0);color:var(--muted);
  border:1px solid var(--border);border-radius:var(--radius);padding:1px var(--sp-2)}
.pill.active{color:var(--accent);border-color:var(--accent)}
"""


def build_document(body_html: str, *, tokens_css: str, base_css: str, fonts_css: str = "") -> str:
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<style>{fonts_css}\n:root{{{tokens_css}}}\n{base_css}</style></head>"
        f"<body>{body_html}</body></html>"
    )


def read_tokens_css() -> str:
    """Read the live tokens.css :root body (the canonical values)."""
    raw = TOKENS_PATH.read_text(encoding="utf-8")
    start = raw.find("{")
    end = raw.rfind("}")
    return raw[start + 1:end].strip() if 0 <= start < end else raw


def tokens_hash(tokens_css: str) -> str:
    return hashlib.sha256(tokens_css.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------
# Render — imperative shell (headless Chrome)
# --------------------------------------------------------------------------
_CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
]


def find_chrome() -> str | None:
    env = os.environ.get("CHROME_BIN")
    if env and (Path(env).exists() or shutil.which(env)):
        return env
    for c in _CHROME_CANDIDATES:
        if Path(c).exists():
            return c
        w = shutil.which(c)
        if w:
            return w
    return None


def render_png(html: str, out: Path, *, viewport: str = "1536x1024", chrome: str | None = None) -> Path:
    chrome = chrome or find_chrome()
    if not chrome:
        raise SystemExit("generate_mockup: no headless Chrome found (set CHROME_BIN)")
    w, h = viewport.lower().split("x")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        page = Path(d) / "page.html"
        page.write_text(html, encoding="utf-8")
        subprocess.run(
            [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
             "--force-device-scale-factor=1", f"--window-size={w},{h}",
             f"--screenshot={out}", page.as_uri()],
            check=True, capture_output=True, timeout=120,
        )
    if not out.exists() or out.stat().st_size == 0:
        raise SystemExit("generate_mockup: render produced no output")
    return out


def png_size(path: Path) -> tuple[int, int]:
    data = Path(path).read_bytes()
    w, h = struct.unpack(">II", data[16:24])
    return w, h


# --------------------------------------------------------------------------
# Receipt
# --------------------------------------------------------------------------
def make_receipt(*, src, source, tokens_css, viewport, out, polished, error=None) -> dict:
    return {
        "schema": "loswf-mockup-receipt-v1",
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "in": str(src),
        "source_hash": hashlib.sha256(source.encode("utf-8")).hexdigest()[:16],
        "tokens_hash": tokens_hash(tokens_css),
        "viewport": viewport,
        "polished": bool(polished),
        "out": str(out),
        "ok": error is None,
        "error": error,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _run_one(src: Path, out: Path, viewport: str, polish: bool) -> dict:
    source = Path(src).read_text(encoding="utf-8")
    tokens_css = read_tokens_css()
    body = compile_html(parse_wireframe(source))
    doc = build_document(body, tokens_css=tokens_css, base_css=BASE_CSS)
    render_png(doc, out, viewport=viewport)
    if polish:
        _polish(out)
    receipt = make_receipt(src=src, source=source, tokens_css=tokens_css,
                           viewport=viewport, out=out, polished=polish)
    Path(out).with_suffix(".json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


def _polish(out: Path) -> None:
    """Optional images.edit pass via the sibling tool (kept thin)."""
    import generate_image  # noqa: F401  (imported lazily; only when --polish)
    raise SystemExit("generate_mockup: --polish not yet wired (see spec §6)")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Render a LOSWFX UI mockup from a text wireframe.")
    p.add_argument("--in", dest="src", type=Path)
    p.add_argument("--out", type=Path)
    p.add_argument("--viewport", default="1536x1024")
    p.add_argument("--polish", action="store_true")
    p.add_argument("--batch", type=Path)
    a = p.parse_args(argv)

    if a.batch:
        manifest = json.loads(Path(a.batch).read_text(encoding="utf-8"))
        for e in manifest.get("mockups", []):
            r = _run_one(Path(e["in"]), Path(e["out"]),
                         e.get("viewport", a.viewport), bool(e.get("polish")))
            print(json.dumps(r))
        return 0
    if not a.src or not a.out:
        p.error("--in and --out are required (or use --batch)")
    print(json.dumps(_run_one(a.src, a.out, a.viewport, a.polish)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
