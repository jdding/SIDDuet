import csv, json, subprocess, sys, tempfile, unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/import_role_counts.py"


class ImportContract(unittest.TestCase):
    def run_import(self, rows):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        p = Path(td.name)
        (p / "i.csv").write_text("sku,scene,category,n\n" + rows)
        (p / "c.json").write_text(
            json.dumps(
                {
                    "dataset": "own",
                    "fields": {
                        "item_id": "sku",
                        "role": "scene",
                        "label": "category",
                        "count": "n",
                    },
                    "role_values": {"query": "search", "feed": "rec"},
                }
            )
        )
        r = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--input",
                str(p / "i.csv"),
                "--config",
                str(p / "c.json"),
                "--out-csv",
                str(p / "o.csv"),
                "--out-json",
                str(p / "o.json"),
            ],
            capture_output=True,
        )
        return p, r

    def test_duplicate_counts_preserved_by_field_mapping(self):
        p, r = self.run_import("a,query,x,2\na,query,x,3\na,feed,y,4\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        with (p / "o.csv").open() as f:
            out = list(csv.DictReader(f))
        self.assertEqual(
            {(v["role"], v["label"]): int(v["count"]) for v in out},
            {("search", "x"): 5, ("rec", "y"): 4},
        )

    def test_unknown_task_is_rejected_without_output(self):
        p, r = self.run_import("a,browse,x,1\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((p / "o.csv").exists())

    def test_invalid_count_is_rejected(self):
        for n in ["0", "-1", "1.5"]:
            p, r = self.run_import("a,query,x," + n + "\n")
            self.assertNotEqual(r.returncode, 0)
            self.assertFalse((p / "o.csv").exists())


if __name__ == "__main__":
    unittest.main()
