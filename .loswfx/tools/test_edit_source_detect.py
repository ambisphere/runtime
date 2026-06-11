#!/usr/bin/env python3
"""Unit tests for edit_source_detect.

Run with: python3 -m unittest .loswf/tools/test_edit_source_detect.py

Covers the three operative behaviors:

1. Below-threshold patterns don't surface.
2. At-or-above threshold (count AND engagements) patterns surface
   as findings with the expected shape.
3. Methodology-only revisions (frontmatter shape) are honored.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import edit_source_detect as esd  # noqa: E402


def _write_feedback(
    shadow_root: Path, engagement: str, name: str, frontmatter: dict, body: str = "n/a"
) -> Path:
    feedback_dir = shadow_root / "engagements" / engagement / "feedback"
    feedback_dir.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    for k, v in frontmatter.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append("")
    lines.append(body)
    path = feedback_dir / f"{name}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class TestParseFrontmatter(unittest.TestCase):
    def test_returns_dict_on_well_formed_input(self) -> None:
        text = "---\nskill: foo\nrevision-kind: bar\n---\nbody\n"
        self.assertEqual(
            esd.parse_frontmatter(text),
            {"skill": "foo", "revision-kind": "bar"},
        )

    def test_returns_none_when_no_fence(self) -> None:
        self.assertIsNone(esd.parse_frontmatter("no fence here"))

    def test_returns_none_on_unterminated_fence(self) -> None:
        self.assertIsNone(esd.parse_frontmatter("---\nskill: foo\n(no close)\n"))


class TestDetect(unittest.TestCase):
    def test_below_threshold_emits_nothing(self) -> None:
        revisions = [
            {"skill": "iteration-plan", "revision-kind": "risk-up", "engagement": "client-a", "path": "x"},
            {"skill": "iteration-plan", "revision-kind": "risk-up", "engagement": "client-a", "path": "y"},
        ]
        # 2 occurrences but only 1 engagement — both thresholds violated.
        self.assertEqual(esd.detect(revisions, 3, 2), [])

    def test_at_threshold_emits_finding(self) -> None:
        revisions = [
            {"skill": "iteration-plan", "revision-kind": "risk-up", "engagement": "client-a", "path": "a"},
            {"skill": "iteration-plan", "revision-kind": "risk-up", "engagement": "client-a", "path": "b"},
            {"skill": "iteration-plan", "revision-kind": "risk-up", "engagement": "client-b", "path": "c"},
        ]
        findings = esd.detect(revisions, 3, 2)
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f["skill"], "iteration-plan")
        self.assertEqual(f["revision-kind"], "risk-up")
        self.assertEqual(f["count"], 3)
        self.assertEqual(f["engagements"], ["client-a", "client-b"])
        self.assertIn("iteration-plan", f["proposed-prompt-change"])

    def test_groups_independently(self) -> None:
        # Two distinct (skill, revision-kind) groups; only one
        # crosses thresholds.
        revisions = [
            {"skill": "iteration-plan", "revision-kind": "risk-up", "engagement": "a", "path": "1"},
            {"skill": "iteration-plan", "revision-kind": "risk-up", "engagement": "b", "path": "2"},
            {"skill": "iteration-plan", "revision-kind": "risk-up", "engagement": "c", "path": "3"},
            {"skill": "engagement-plan", "revision-kind": "scope-trim", "engagement": "a", "path": "4"},
        ]
        findings = esd.detect(revisions, 3, 2)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["skill"], "iteration-plan")


class TestCollectRevisions(unittest.TestCase):
    def test_skips_files_without_required_keys(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            shadow = Path(td)
            _write_feedback(shadow, "client-a", "missing-skill", {"engagement": "client-a"})
            _write_feedback(
                shadow,
                "client-a",
                "valid",
                {"skill": "x", "revision-kind": "y", "engagement": "client-a"},
            )
            rows = esd.collect_revisions(shadow)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["skill"], "x")

    def test_accepts_revision_kind_alias(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            shadow = Path(td)
            _write_feedback(
                shadow,
                "client-a",
                "alias",
                {"skill": "x", "revision_kind": "y", "engagement": "client-a"},
            )
            rows = esd.collect_revisions(shadow)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["revision-kind"], "y")

    def test_handles_missing_engagements_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(esd.collect_revisions(Path(td)), [])

    def test_artifact_rows_carry_source_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            shadow = Path(td)
            _write_feedback(
                shadow,
                "client-a",
                "valid",
                {"skill": "x", "revision-kind": "y", "engagement": "client-a"},
            )
            rows = esd.collect_revisions(shadow)
            self.assertEqual(rows[0]["source"], "artifact")


class TestLedgerChannel(unittest.TestCase):
    def _write_ledger(self, path: Path, lines: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for line in lines:
                f.write(json.dumps(line) + "\n")

    def test_read_ledger_filters_to_feedback_cascade(self) -> None:
        import json as _json
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "events.jsonl"
            self._write_ledger(path, [
                {"id": "evt-1", "type": "feedback.cascade.applied",
                 "data": {"skill": "iteration-plan", "revision-kind": "risk-up", "engagement": "client-a"}},
                {"id": "evt-2", "type": "approval.decided",
                 "data": {"skill": "x", "revision-kind": "y", "engagement": "z"}},
                {"id": "evt-3", "type": "feedback.cascade.applied",
                 "data": {"skill": "iteration-plan", "revision-kind": "risk-up", "engagement": "client-b"}},
            ])
            rows = esd.read_ledger_events(path)
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(r["source"] == "ledger" for r in rows))
            self.assertEqual({r["engagement"] for r in rows}, {"client-a", "client-b"})
            del _json

    def test_read_ledger_returns_empty_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(esd.read_ledger_events(Path(td) / "no-such.jsonl"), [])

    def test_read_ledger_skips_malformed_lines(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "events.jsonl"
            path.write_text(
                "not json\n"
                + json.dumps({"type": "feedback.cascade.x",
                              "data": {"skill": "s", "revision-kind": "rk", "engagement": "e"}}) + "\n",
                encoding="utf-8",
            )
            rows = esd.read_ledger_events(path)
            self.assertEqual(len(rows), 1)

    def test_collect_revisions_merges_artifact_and_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            shadow = Path(td)
            _write_feedback(
                shadow,
                "client-a",
                "art",
                {"skill": "iteration-plan", "revision-kind": "risk-up", "engagement": "client-a"},
            )
            ledger = shadow / "ledger.jsonl"
            self._write_ledger(ledger, [
                {"id": "evt-1", "type": "feedback.cascade.applied",
                 "data": {"skill": "iteration-plan", "revision-kind": "risk-up", "engagement": "client-b"}},
            ])
            rows = esd.collect_revisions(shadow, ledger_path=ledger)
            sources = {r["source"] for r in rows}
            self.assertEqual(sources, {"artifact", "ledger"})
            self.assertEqual(len(rows), 2)


class TestEndToEnd(unittest.TestCase):
    def test_main_writes_findings_and_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            shadow = Path(td) / "shadow"
            for i, engagement in enumerate(["client-a", "client-a", "client-b"]):
                _write_feedback(
                    shadow,
                    engagement,
                    f"rev-{i}",
                    {"skill": "iteration-plan", "revision-kind": "risk-up", "engagement": engagement},
                )
            out = Path(td) / "findings.jsonl"
            receipt = Path(td) / "receipt.json"
            rc = esd.main(
                [
                    "--shadow",
                    str(shadow),
                    "--threshold-count",
                    "3",
                    "--threshold-engagements",
                    "2",
                    "--out",
                    str(out),
                    "--receipt",
                    str(receipt),
                ]
            )
            self.assertEqual(rc, 0)
            findings_text = out.read_text(encoding="utf-8").strip()
            self.assertNotEqual(findings_text, "")
            finding = json.loads(findings_text)
            self.assertEqual(finding["skill"], "iteration-plan")
            self.assertEqual(finding["count"], 3)
            receipt_data = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(receipt_data["revisions_scanned"], 3)
            self.assertEqual(receipt_data["findings_count"], 1)

    def test_main_exit_1_on_missing_shadow(self) -> None:
        rc = esd.main(["--shadow", "/no/such/path"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
