"""Tests for the SIDDuet package CLI and the three-workflow browser demo."""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CLIAndDemoTests(unittest.TestCase):
    def test_cli_version_and_verify_table2(self) -> None:
        ver = subprocess.run(
            [sys.executable, "-m", "sidduet.cli", "--version"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("0.4.0", ver.stdout)

        t2 = subprocess.run(
            [sys.executable, "-m", "sidduet.cli", "verify-table2"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        lines = [line for line in t2.stdout.strip().splitlines() if line]
        self.assertEqual(len(lines), 7)  # header + 6 rows (summary prints to stderr)
        self.assertTrue(lines[0].startswith("dataset,mapping,groups,observed_jsd"))
        self.assertTrue(
            any(line.startswith("kuaisar,grid,3462,0.132,0.158,0.154,60.60%") for line in lines[1:])
        )

    def test_browser_example_covers_three_workflows(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-I", "-B", str(ROOT / "demo/browser_example.py")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["version"], "0.4.0")

        wf1 = payload["workflow1"]
        self.assertEqual(wf1["common_items"], 8)
        self.assertEqual(wf1["collision_groups"], 2)
        self.assertEqual(len(wf1["groups"]), 2)
        self.assertGreaterEqual(wf1["observed_mean_jsd"], 0.0)
        self.assertLessEqual(wf1["observed_mean_jsd"], 1.0)
        self.assertEqual(wf1["band_reference"]["draws"], 199)
        self.assertEqual(wf1["exact_reference"]["draws"], 199)
        self.assertEqual(len(payload["table2"]), 6)

        self.assertEqual(payload["coverage"]["join_coverage"], 1.0)
        self.assertEqual(len(payload["metrics"]), 2)
        self.assertEqual(len(payload["table3"]), 2)

        self.assertGreater(payload["pooling_synthetic"]["pooled"]["macro_loss"], 0.0)
        self.assertGreater(payload["pooling_synthetic"]["task_conditioned"]["macro_loss"], 0.0)
        self.assertEqual(len(payload["table4"]), 6)
        self.assertEqual(len(payload["cohort_sensitivity"]), 2)

    def test_worker_file_list_matches_repo(self) -> None:
        worker_js = (ROOT / "demo/python-worker.js").read_text(encoding="utf-8")
        block = re.search(r"const FILES = \[(.*?)\];", worker_js, flags=re.S)
        self.assertIsNotNone(block)
        paths = re.findall(r'"([^"]+)"', block.group(1))
        self.assertGreaterEqual(len(paths), 15)
        for rel in paths:
            self.assertTrue((ROOT / rel).is_file(), f"Missing worker file: {rel}")


if __name__ == "__main__":
    unittest.main()
