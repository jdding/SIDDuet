"""Fabricated CLI regressions for strict SID maps and support ties."""
import csv
import json
import math
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROFILE = "sr_sid_rolemap.topology.value_median.v2"


class SIDMapInterfaces(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.topology = self.base / "topology.csv"
        self.mapping = self.base / "map.csv"
        self.write_topology(["a", "b"], [1, 1])

    def write_csv(self, path, fields, rows):
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(fields)
            writer.writerows(rows)

    def write_topology(self, ids, supports, dataset="custom"):
        self.write_csv(self.topology,
                       ["dataset", "item_id", "profile_id", "search_support", "rec_support",
                        "topology_cell", "rsd_bucket", "rsi_mag_bucket"],
                       [[dataset, item, PROFILE, support, support,
                         "HH" if index % 2 else "LL", "H" if index % 2 else "L", "L"]
                        for index, (item, support) in enumerate(zip(ids, supports))])

    def write_map(self, rows):
        self.write_csv(self.mapping, ["dataset", "item_id", "sid"], rows)

    def cli(self, script):
        output = self.base / (script + ".csv")
        receipt = self.base / (script + ".json")
        for path in (output, receipt):
            path.unlink(missing_ok=True)
        args = [sys.executable, "-I", "-B", str(ROOT / "scripts" / (script + ".py")),
                "--topology", str(self.topology), "--sid-map", str(self.mapping),
                "--out-csv", str(output), "--out-json", str(receipt)]
        if script == "admit_sid_family":
            args += ["--family", "test"]
        result = subprocess.run(args, capture_output=True, text=True, cwd=self.base)
        return result, output, receipt

    def successful_cli(self, script):
        result, output, receipt = self.cli(script)
        self.assertEqual(result.returncode, 0, result.stderr)
        with output.open(newline="") as handle:
            csv_rows = list(csv.DictReader(handle))
        return json.loads(receipt.read_text()), csv_rows

    def test_rejects_bad_maps_before_output(self):
        invalid = {
            "empty SID": "custom,a,\ncustom,b,x\n",
            "blank SID": "custom,a,   \ncustom,b,x\n",
            "missing SID": "custom,a\ncustom,b,x\n",
            "extra column": "custom,a,x,extra\ncustom,b,x\n",
            "identical duplicate": "custom,a,x\ncustom,a,x\ncustom,b,x\n",
            "conflicting duplicate": "custom,a,x\ncustom,a,y\ncustom,b,x\n",
            "blank dataset": ",a,x\ncustom,b,x\n",
            "blank item": "custom, ,x\ncustom,b,x\n",
        }
        for name, body in invalid.items():
            for script in ("admit_sid_family", "evaluate_collision_diagnostic"):
                with self.subTest(case=name, script=script):
                    self.mapping.write_text("dataset,item_id,sid\n" + body)
                    result, output, receipt = self.cli(script)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(output.exists())
                    self.assertFalse(receipt.exists())

    def test_rejects_duplicate_or_missing_headers(self):
        for header in ("dataset,item_id,sid,sid", "dataset,item_id,code"):
            self.mapping.write_text(header + "\ncustom,a,x,x\ncustom,b,x,x\n")
            for script in ("admit_sid_family", "evaluate_collision_diagnostic"):
                with self.subTest(header=header, script=script):
                    result, output, receipt = self.cli(script)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(output.exists())
                    self.assertFalse(receipt.exists())

    def test_invalid_json_tokens_rejected_by_both_clis(self):
        for code in ("[]", "[true]", "[null]", "[[]]", "[{}]", "[1.0]", '[""]',
                     '["   "]', "[1,", "[NaN]"):
            self.write_map([["custom", "a", code], ["custom", "b", code]])
            for script in ("admit_sid_family", "evaluate_collision_diagnostic"):
                with self.subTest(code=code, script=script):
                    result, output, receipt = self.cli(script)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(output.exists())
                    self.assertFalse(receipt.exists())

    def test_json_whitespace_and_escaping_cli_equivalence(self):
        self.write_map([["custom", "a", '[1,"中"]'],
                        ["custom", "b", ' [ 1, "\\u4e2d" ] ']])
        admission, _ = self.successful_cli("admit_sid_family")
        self.assertEqual(admission["dataset_summaries"][0]["unique_sid_count"], 1)
        collision, _ = self.successful_cli("evaluate_collision_diagnostic")
        self.assertEqual(collision["collision_groups"], 1)

    def test_integer_and_string_tokens_stay_distinct(self):
        self.write_topology(["a", "b", "c", "d"], [1] * 4)
        self.write_map([["custom", item, code] for item, code in
                        zip("abcd", ("[1]", '["1"]', "[1]", '["1"]'))])
        admission, _ = self.successful_cli("admit_sid_family")
        self.assertEqual(admission["dataset_summaries"][0]["unique_sid_count"], 2)
        collision, _ = self.successful_cli("evaluate_collision_diagnostic")
        self.assertEqual(collision["collision_groups"], 2)

    def test_legacy_fixture_and_exact_keys(self):
        helper = runpy.run_path(str(ROOT / "scripts" / "sid_map_io.py"))
        fixture = ROOT / "samples" / "synthetic_sid_map.csv"
        with fixture.open(newline="") as handle:
            expected = {(r["dataset"], r["item_id"]): r["sid"] for r in csv.DictReader(handle)}
        self.assertEqual(helper["load_sid_map"](fixture), expected)
        self.write_topology([key[1] for key in expected], [1] * len(expected), dataset="demo")
        self.mapping = fixture
        admission, _ = self.successful_cli("admit_sid_family")
        self.assertEqual(admission["dataset_summaries"][0]["joined_items"], len(expected))
        self.assertEqual(admission["dataset_summaries"][0]["unique_sid_count"], len(set(expected.values())))
        collision, _ = self.successful_cli("evaluate_collision_diagnostic")
        self.assertGreater(collision["collision_groups"], 0)
        self.mapping = self.base / "map.csv"
        self.assertEqual(helper["canonical_sid"]("sid_alpha"), "sid_alpha")
        self.assertEqual(helper["canonical_sid"]([1, "中"]), '[1,"中"]')
        self.write_map([["custom", "01", "x"], ["custom", "1", "y"], ["other", "1", "z"]])
        self.assertEqual(len(helper["load_sid_map"](self.mapping)), 3)

    def test_support_tie_crossing_rank_ten_and_id_renaming_cli(self):
        supports = list(range(20, 12, -1)) + [1] * 4
        ids = [f"id{i:02}" for i in range(12)]
        self.write_topology(ids, supports)
        self.write_map([["custom", item, "opaque_code"] for item in ids])
        first, first_csv = self.successful_cli("evaluate_collision_diagnostic")
        with self.subTest(contract="schema and tie policy"):
            self.assertEqual(first["schema"], "sr_sid_rolemap.collision_diagnostic.v2")
            self.assertEqual(first["support_tie_policy"], "expected_discount_over_exact_support_ties")
        # Isolate one member of the rank-9..12 tie in its own topology cell.
        with self.topology.open(newline="") as handle:
            rows = list(csv.reader(handle))
        rows[9][5] = "tie_only"
        self.write_csv(self.topology, rows[0], rows[1:])
        first, first_csv = self.successful_cli("evaluate_collision_diagnostic")
        expected = round((1 / math.log2(10) + 1 / math.log2(11)) / 4, 6)
        for row in first["aggregates"]:
            if row["slice_type"] == "topology_cell" and row["slice_value"] == "tie_only":
                with self.subTest(contract="rank ten crossing", role=row["role"]):
                    self.assertEqual(row["ndcg10"], expected)
        # Reverse opaque IDs while preserving observations and slice membership.
        for row, renamed in zip(rows[1:], reversed(ids)):
            row[1] = renamed
        self.write_csv(self.topology, rows[0], list(reversed(rows[1:])))
        self.write_map([["custom", item, "opaque_code"] for item in reversed(ids)])
        second, second_csv = self.successful_cli("evaluate_collision_diagnostic")
        def without_hash(value):
            if isinstance(value, dict):
                return {k: without_hash(v) for k, v in value.items() if k != "topology_sha256"}
            if isinstance(value, list):
                return [without_hash(v) for v in value]
            return value
        with self.subTest(contract="JSON output ID invariance"):
            self.assertEqual(without_hash(first), without_hash(second))
        with self.subTest(contract="CSV output ID invariance"):
            self.assertEqual(without_hash(first_csv), without_hash(second_csv))


if __name__ == "__main__":
    unittest.main()
