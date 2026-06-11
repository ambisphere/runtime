#!/usr/bin/env python3
"""Unit tests for generate_mockup.

Run with: python3 -m unittest .loswf/tools/test_generate_mockup.py

Covers the testable core (functional core / imperative shell):
  1. DSL parser — indentation tree, quoted positionals, key=value attrs,
     boolean flags, `name:tag` suffixes, comments, the `html:` escape hatch.
  2. Compiler — component tree -> HTML; status is glyph + class, never
     color alone; active/stepper state classes.
  3. Tokens shell — tokens.css injection + a content-sensitive tokens_hash.
  4. Receipt shape.
  5. Render (integration, skipped when no headless Chrome is present).
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import generate_mockup as gm  # noqa: E402


class TestParser(unittest.TestCase):
    def test_keyword_positional_and_attr(self):
        root = gm.parse_wireframe("mockup control-room viewport=1536x1024\n")
        self.assertEqual(root.kind, "mockup")
        self.assertEqual(root.args, [("control-room", None)])
        self.assertEqual(root.attrs.get("viewport"), "1536x1024")

    def test_quoted_positional_flags_and_attrs(self):
        root = gm.parse_wireframe(
            "mockup x\n"
            '  stance "control room" active badge=2 glyph=control\n'
        )
        stance = root.children[0]
        self.assertEqual(stance.kind, "stance")
        self.assertEqual(stance.args, [("control room", None)])
        self.assertIs(stance.attrs.get("active"), True)
        self.assertEqual(stance.attrs.get("badge"), "2")
        self.assertEqual(stance.attrs.get("glyph"), "control")

    def test_indentation_builds_tree(self):
        root = gm.parse_wireframe(
            "mockup x\n"
            "  sidebar scope=\"acme/store\"\n"
            "    stance fleet\n"
            "  main\n"
        )
        self.assertEqual([c.kind for c in root.children], ["sidebar", "main"])
        sidebar = root.children[0]
        self.assertEqual(sidebar.attrs.get("scope"), "acme/store")
        self.assertEqual(sidebar.children[0].args, [("fleet", None)])

    def test_name_tag_suffix_on_bare_and_quoted(self):
        root = gm.parse_wireframe(
            "mockup x\n"
            "  stepper intake:done build:active ship\n"
            '  row "⠋ in build":inflight "system"\n'
        )
        stepper = root.children[0]
        self.assertEqual(
            stepper.args,
            [("intake", "done"), ("build", "active"), ("ship", None)],
        )
        row = root.children[1]
        self.assertEqual(row.args, [("⠋ in build", "inflight"), ("system", None)])

    def test_attr_value_with_spaces_in_quotes(self):
        root = gm.parse_wireframe(
            "mockup x\n"
            '  table cols="work item,owner,status,updated"\n'
        )
        self.assertEqual(
            root.children[0].attrs.get("cols"), "work item,owner,status,updated"
        )

    def test_comments_skipped(self):
        root = gm.parse_wireframe(
            "mockup x\n"
            "  # this is a note\n"
            "  stance fleet\n"
        )
        self.assertEqual([c.kind for c in root.children], ["stance"])

    def test_html_escape_hatch(self):
        root = gm.parse_wireframe(
            "mockup x\n"
            "  html:\n"
            '    <div class="c">hi var(--accent)</div>\n'
            "  stance fleet\n"
        )
        kinds = [c.kind for c in root.children]
        self.assertEqual(kinds, ["html", "stance"])
        self.assertIn('<div class="c">hi var(--accent)</div>', root.children[0].raw)


class TestCompiler(unittest.TestCase):
    def test_status_is_glyph_plus_class_never_color_alone(self):
        # A seg with a status glyph must emit BOTH the §3 glyph char and the
        # paired g-* class — color alone is banned (DESIGN.md §3 / PRODUCT P4).
        root = gm.parse_wireframe(
            "mockup x\n"
            "  main\n"
            '    stateline\n'
            '      seg "verdict" value="ok" glyph=ok\n'
        )
        html = gm.compile_html(root)
        self.assertIn("✓", html)        # the glyph char
        self.assertIn("g-ok", html)     # the paired class
        self.assertIn("verdict", html)

    def test_active_stance_marked(self):
        root = gm.parse_wireframe(
            "mockup x\n"
            '  sidebar\n'
            '    stance "control room" active\n'
            "    stance fleet\n"
        )
        html = gm.compile_html(root)
        # active stance carries the active class; inactive one does not get it
        self.assertRegex(html, r'class="stance active"[^>]*data-stance="control room"')
        self.assertNotRegex(html, r'class="stance active"[^>]*data-stance="fleet"')
        self.assertIn('data-stance="fleet"', html)

    def test_stepper_state_classes(self):
        root = gm.parse_wireframe(
            "mockup x\n"
            "  main\n"
            "    stepper intake:done build:active ship\n"
        )
        html = gm.compile_html(root)
        self.assertIn("done", html)
        self.assertIn("active", html)
        self.assertIn("intake", html)

    def test_glyph_map_all_states(self):
        for state, char in [("ok", "✓"), ("warn", "!"), ("err", "✕"),
                            ("idle", "○"), ("inflight", "⠋")]:
            self.assertEqual(gm.GLYPHS[state], char)

    def test_html_escape_hatch_passthrough(self):
        root = gm.parse_wireframe(
            "mockup x\n"
            "  html:\n"
            '    <div class="c">raw</div>\n'
        )
        html = gm.compile_html(root)
        self.assertIn('<div class="c">raw</div>', html)


class TestNewComponents(unittest.TestCase):
    def test_steprail_step_states(self):
        root = gm.parse_wireframe(
            "mockup x\n"
            '  steprail title="Setup"\n'
            '    step "1 GitHub" done\n'
            '    step "3 Agency" active\n'
            '    step "5 Ready"\n'
        )
        html = gm.compile_html(root)
        self.assertIn("steprail", html)
        self.assertRegex(html, r'class="step done"')
        self.assertRegex(html, r'class="step active"')
        self.assertIn("3 Agency", html)

    def test_checkrow_glyph_name_detail(self):
        root = gm.parse_wireframe(
            "mockup x\n"
            '  checkrow "provider reachable" detail="openrouter ok" glyph=ok\n'
        )
        html = gm.compile_html(root)
        self.assertIn("✓", html)
        self.assertIn("g-ok", html)
        self.assertIn("provider reachable", html)
        self.assertIn("openrouter ok", html)

    def test_pill(self):
        root = gm.parse_wireframe(
            "mockup x\n"
            "  pills\n"
            '    pill "work item"\n'
            '    pill "fleet" active\n'
        )
        html = gm.compile_html(root)
        self.assertIn("pill", html)
        self.assertIn("work item", html)
        self.assertRegex(html, r'class="pill active"')


class TestShellAndReceipt(unittest.TestCase):
    def test_build_document_injects_tokens_and_body(self):
        doc = gm.build_document("<main>hi</main>", tokens_css="--accent:#3d85c6;",
                                base_css=".x{}")
        self.assertIn("--accent:#3d85c6;", doc)
        self.assertIn("<main>hi</main>", doc)
        self.assertIn("<html", doc.lower())

    def test_tokens_hash_is_content_sensitive(self):
        a = gm.tokens_hash("--accent:#3d85c6;")
        b = gm.tokens_hash("--accent:#3d85c6;")
        c = gm.tokens_hash("--accent:#000000;")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_receipt_shape(self):
        r = gm.make_receipt(src="x.mock", source="mockup x\n",
                            tokens_css="--accent:#3d85c6;", viewport="1536x1024",
                            out="o.png", polished=False)
        for key in ("schema", "ts", "in", "source_hash", "tokens_hash",
                    "viewport", "polished", "out", "ok"):
            self.assertIn(key, r)
        self.assertEqual(r["schema"], "loswf-mockup-receipt-v1")
        self.assertFalse(r["polished"])


class TestRenderIntegration(unittest.TestCase):
    def test_render_produces_sized_png(self):
        chrome = gm.find_chrome()
        if not chrome:
            self.skipTest("no headless Chrome found")
        doc = gm.build_document(
            "<main style='width:100%;height:100%;background:#0a0a0a'></main>",
            tokens_css=":root{--bg:#0a0a0a}", base_css="body{margin:0}",
        )
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "r.png"
            gm.render_png(doc, out, viewport="800x600", chrome=chrome)
            self.assertTrue(out.exists() and out.stat().st_size > 0)
            w, h = gm.png_size(out)
            self.assertEqual((w, h), (800, 600))


if __name__ == "__main__":
    unittest.main()
