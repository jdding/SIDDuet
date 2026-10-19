#!/usr/bin/env python3
"""Reproduce the fixed UniSAR predictions and diagnostic results."""

from __future__ import annotations
import argparse, csv, hashlib, json, math, os, platform, subprocess, sys, time
from pathlib import Path
import numpy, pandas, torch, yaml

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def max_numeric_error(actual, expected):
    if isinstance(expected, dict):
        if set(actual) != set(expected):
            raise ValueError("result keys differ")
        return max((max_numeric_error(actual[k], v) for k, v in expected.items()), default=0.0)
    if isinstance(expected, list):
        if len(actual) != len(expected):
            raise ValueError("result lengths differ")
        return max((max_numeric_error(x, y) for x, y in zip(actual, expected)), default=0.0)
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        if not math.isfinite(float(actual)):
            raise ValueError("nonfinite result")
        if isinstance(expected, int) and actual != expected:
            raise ValueError("integer result differs")
        return abs(actual - expected)
    if actual != expected:
        raise ValueError("nonnumeric result differs")
    return 0.0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-root", type=Path, required=True)
    parser.add_argument("--official-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    options = parser.parse_args()
    options.out.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    spec = json.loads((ROOT / "analysis/model_reuse/REPLAY_INPUTS.json").read_text())
    steps = []
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONNOUSERSITE"] = "1"
    for base, rows in [
        (options.processed_root, spec["provider_files"]),
        (options.official_root, spec["source_files"]),
    ]:
        for row in rows:
            p = base / row["path"]
            if not p.is_file() or sha(p) != row["sha256"]:
                raise ValueError("input/source identity mismatch: " + row["path"])

    def run(name, args):
        begin = time.monotonic()
        proc = subprocess.run(
            [sys.executable, *map(str, args)], cwd=ROOT, env=env, text=True, capture_output=True
        )
        (options.out / (name + ".log")).write_text(proc.stdout + proc.stderr)
        steps.append(
            {"step": name, "returncode": proc.returncode, "seconds": time.monotonic() - begin}
        )
        if proc.returncode:
            raise RuntimeError(name + " failed; see its local log")
        print(name, "PASS", flush=True)

    run(
        "assemble",
        [
            "-I",
            ROOT / "scripts/assemble_checkpoint.py",
            "--manifest",
            ROOT / spec["checkpoint_manifest"],
            "--out",
            options.out / "checkpoint.pt",
        ],
    )
    for name, count in [("small", 1024), ("full", 22699)]:
        run(
            "prepare_" + name,
            [
                ROOT / "analysis/model_reuse/prepare_observations.py",
                "--processed-root",
                options.processed_root,
                "--users",
                count,
                "--out",
                options.out / name,
            ],
        )
        run(
            "import_" + name,
            [
                "-I",
                ROOT / "scripts/import_role_counts.py",
                "--input",
                options.out / name / "platform_counts.csv",
                "--config",
                ROOT / "analysis/model_reuse/count_fields.example.json",
                "--out-csv",
                options.out / (name + "_counts.csv"),
                "--out-json",
                options.out / (name + "_import.json"),
            ],
        )
        run(
            "topology_" + name,
            [
                "-I",
                ROOT / "scripts/build_role_topology.py",
                "--role-counts",
                options.out / (name + "_counts.csv"),
                "--out-csv",
                options.out / (name + "_topology.csv"),
                "--out-json",
                options.out / (name + "_topology.json"),
            ],
        )
        if (
            sha(options.out / (name + "_topology.csv"))
            != spec["expected"][name + "_topology_sha256"]
        ):
            raise ValueError(name + " topology differs")
    run(
        "admit_small",
        [
            "-I",
            ROOT / "scripts/admit_sid_family.py",
            "--topology",
            options.out / "small_topology.csv",
            "--sid-map",
            options.out / "small/catalog_path_map.csv",
            "--family",
            "catalog_category_path",
            "--out-csv",
            options.out / "admission.csv",
            "--out-json",
            options.out / "admission.json",
        ],
    )
    ck = json.loads((ROOT / spec["checkpoint_manifest"]).read_text())
    run(
        "predict",
        [
            ROOT / "analysis/model_reuse/export_unisar_scores.py",
            "--official-root",
            options.official_root,
            "--processed-root",
            options.processed_root,
            "--checkpoint",
            options.out / "checkpoint.pt",
            "--expected-checkpoint",
            ck["sha256"],
            "--users",
            options.out / "full/selected_users.json",
            "--topology",
            options.out / "full_topology.csv",
            "--out",
            options.out / "predictions",
            "--per-role",
            200000,
            "--batch-size",
            64,
        ],
    )
    bitwise = {
        name: sha(options.out / "predictions" / name) == h
        for name, h in spec["expected"]["prediction_output_sha256"].items()
    }
    if not all(bitwise.values()):
        raise ValueError("prediction byte replay failed: " + str(bitwise))
    run(
        "adapt",
        [
            "-I",
            ROOT / "scripts/adapt_method_scores.py",
            "--scores",
            options.out / "predictions/covered_scores.csv",
            "--topology",
            options.out / "full_topology.csv",
            "--method-id",
            "unisar_processed_kuaisar",
            "--method-paradigm",
            "discriminative",
            "--score-direction",
            "higher_is_better",
            "--out-csv",
            options.out / "adapted.csv",
        ],
    )
    run(
        "evaluate",
        [
            "-I",
            ROOT / "scripts/evaluate_fixed_candidates.py",
            "--candidates",
            options.out / "adapted.csv",
            "--out-csv",
            options.out / "metrics.csv",
            "--out-json",
            options.out / "metrics.json",
        ],
    )
    golden = ROOT / "reports/model_reuse"
    if json.loads((options.out / "metrics.json").read_text()) != json.loads(
        (golden / "public_evaluator.json").read_text()
    ):
        raise ValueError("public evaluator output differs")
    run(
        "analyze",
        [
            ROOT / "analysis/model_reuse/analyze_predictions.py",
            "--units",
            options.out / "predictions/units.csv",
            "--topology",
            options.out / "full_topology.csv",
            "--inference",
            options.out / "predictions/INFERENCE.json",
            "--out",
            options.out / "analysis",
        ],
    )
    actual = json.loads((options.out / "analysis/RESULTS.json").read_text())["roles"]
    expected = json.loads((golden / "RESULTS.json").read_text())["roles"]
    error = max_numeric_error(actual, expected)
    if error > 1e-12:
        raise ValueError("diagnostic/bootstrap numeric result differs")
    run(
        "tie_sensitivity",
        [
            ROOT / "analysis/model_reuse/tie_policy_sensitivity.py",
            "--scores",
            options.out / "predictions/all_scores.csv",
            "--units",
            options.out / "predictions/units.csv",
            "--inference",
            options.out / "predictions/INFERENCE.json",
            "--out",
            options.out / "tie_sensitivity.json",
        ],
    )
    actual_ties = json.loads((options.out / "tie_sensitivity.json").read_text())["roles"]
    expected_ties = json.loads((golden / "tie_policy_sensitivity.json").read_text())["roles"]
    tie_error = max_numeric_error(actual_ties, expected_ties)
    if tie_error > 1e-12:
        raise ValueError("tie sensitivity differs")
    runtime = {
        "python": platform.python_version(),
        "system": platform.system(),
        "machine": platform.machine(),
        "torch": torch.__version__,
        "numpy": numpy.__version__,
        "pandas": pandas.__version__,
        "PyYAML": yaml.__version__,
        "device": "cpu",
        "threads": 4,
    }
    report = {
        "schema": "sr_sid_rolemap.full_checkpoint_replay.v1",
        "status": "PASS_FULL_CHECKPOINT_REPLAY",
        "steps": steps,
        "runtime": runtime,
        "seconds": time.monotonic() - start,
        "checkpoint_sha256": ck["sha256"],
        "checkpoint_from_package": True,
        "raw_provider_rows_from_package": False,
        "original_author_source_from_package": False,
        "full_test_requests": 166981,
        "score_values_replayed": 16698100,
        "prediction_files_bitwise_equal": bitwise,
        "small_and_full_topologies_bitwise_equal": True,
        "public_evaluator_object_equal": True,
        "diagnostic_max_abs_error": float(error),
        "tie_sensitivity_max_abs_error": float(tie_error),
        "new_training": False,
        "package_code_sha256": {
            p.relative_to(ROOT).as_posix(): sha(p)
            for p in sorted(ROOT.rglob("*.py"))
            if not set(p.relative_to(ROOT).parts) & {"outputs", "__pycache__"}
        },
        "limits": (
            "Automated clean-directory replay. The recorded runtime defines the exact byte-replay"
            " claim; other hardware/library versions are not certified. Not external adoption."
        ),
    }
    (options.out / "REPLAY.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps({k: v for k, v in report.items() if k not in ["steps", "package_code_sha256"]}),
        flush=True,
    )


if __name__ == "__main__":
    main()
