"""Run the shipped synthetic workflow without requiring child processes."""

from __future__ import annotations

import contextlib
import csv
import io
import json
from pathlib import Path
import runpy
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run_example() -> dict:
    steps = []
    scripts = str(ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)

    with tempfile.TemporaryDirectory(prefix="rolemap-browser-") as folder:
        output = Path(folder)

        def run(script, arguments):
            previous = sys.argv
            capture = io.StringIO()
            sys.argv = [script, *map(str, arguments)]
            try:
                with contextlib.redirect_stdout(capture):
                    runpy.run_path(str(ROOT / "scripts" / script), run_name="__main__")
            finally:
                sys.argv = previous
            steps.append({"script": script, "output": capture.getvalue().strip()})

        run(
            "materialize_role_label_counts.py",
            [
                "--events",
                ROOT / "samples/synthetic_role_events.csv",
                "--out-csv",
                output / "counts.csv",
                "--out-json",
                output / "counts.json",
            ],
        )
        run(
            "build_role_topology.py",
            [
                "--role-counts",
                output / "counts.csv",
                "--out-csv",
                output / "topology.csv",
                "--out-json",
                output / "topology.json",
            ],
        )
        run(
            "admit_sid_family.py",
            [
                "--topology",
                output / "topology.csv",
                "--sid-map",
                ROOT / "samples/synthetic_sid_map.csv",
                "--family",
                "synthetic_demo",
                "--out-csv",
                output / "admission.csv",
                "--out-json",
                output / "admission.json",
            ],
        )
        run(
            "evaluate_collision_diagnostic.py",
            [
                "--topology",
                output / "topology.csv",
                "--sid-map",
                ROOT / "samples/synthetic_sid_map.csv",
                "--out-csv",
                output / "collision.csv",
                "--out-json",
                output / "collision.json",
            ],
        )
        run(
            "adapt_method_scores.py",
            [
                "--scores",
                ROOT / "samples/synthetic_method_scores.csv",
                "--topology",
                output / "topology.csv",
                "--method-id",
                "synthetic_demo",
                "--method-paradigm",
                "discriminative",
                "--score-direction",
                "higher_is_better",
                "--out-csv",
                output / "adapted.csv",
            ],
        )
        run(
            "evaluate_fixed_candidates.py",
            [
                "--candidates",
                output / "adapted.csv",
                "--out-csv",
                output / "metrics.csv",
                "--out-json",
                output / "metrics.json",
            ],
        )

        def load(name):
            return json.loads((output / name).read_text())

        with (output / "topology.csv").open(newline="") as handle:
            items = list(csv.DictReader(handle))
        coverage = load("admission.json")["dataset_summaries"][0]
        metrics = [row for row in load("metrics.json")["aggregates"] if row["slice_type"] == "all"]
        if len(items) != 8 or coverage["join_coverage"] != 1.0:
            raise ValueError("synthetic item or map coverage differs from the fixture")
        if {row["role"] for row in metrics} != {"search", "rec"}:
            raise ValueError("both task metrics are required")
        return {
            "status": "pass",
            "synthetic": True,
            "profile_id": "sr_sid_rolemap.topology.value_median.v2",
            "topology": [
                {
                    "item": row["item_id"],
                    "search_support": float(row["search_support"]),
                    "rec_support": float(row["rec_support"]),
                    "rsd": float(row["rsd_score"]),
                    "rsi": float(row["rsi_signed"]),
                    "cell": row["topology_cell"],
                }
                for row in items
            ],
            "coverage": {
                key: coverage[key]
                for key in ("topology_items", "joined_items", "join_coverage", "unique_sid_count")
            },
            "metrics": [
                {key: row[key] for key in ("role", "units", "ndcg10", "hit10")} for row in metrics
            ],
            "steps": steps,
            "python": sys.version.split()[0],
        }


if __name__ == "__main__":
    print(json.dumps(run_example()))
