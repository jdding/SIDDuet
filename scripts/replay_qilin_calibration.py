#!/usr/bin/env python3
"""Calibrate the released GenSAR prefix on the pinned Qilin snapshot."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "data" / "native_exports"
VIEW = "gensar_shared2"
SEED = 20261104
DRAWS = 1999


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_script(script, *args):
    subprocess.run([sys.executable, "-I", "-B", str(ROOT / "scripts" / script),
                    *map(str, args)], check=True)


def write_prefix(path):
    with (NATIVE / "cohort.csv").open(newline="", encoding="utf-8") as source:
        universe = {row["item_id"] for row in csv.DictReader(source)}
    definition = next(row for row in json.loads((NATIVE / "MAPS.json").read_text())["maps"]
                      if row["name"] == VIEW)
    with (NATIVE / definition["path"]).open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    if len(rows) != len(universe) or {row["item_id"] for row in rows} != universe:
        raise ValueError("released GenSAR map does not match the fixed cohort")
    with path.open("x", newline="", encoding="utf-8") as target:
        writer = csv.writer(target, lineterminator="\n")
        writer.writerow(("dataset", "item_id", "sid"))
        for row in rows:
            tokens = json.loads(row["sid"])
            if not isinstance(tokens, list) or len(tokens) < definition["depth"]:
                raise ValueError("released GenSAR map is missing a prefix")
            writer.writerow(("qilin", row["item_id"],
                             json.dumps(tokens[:definition["depth"]], separators=(",", ":"))))
    return len(universe)


def replay(provider_root):
    spec = json.loads((NATIVE / "QILIN_CALIBRATION_INPUTS.json").read_text(encoding="utf-8"))
    expected = spec["files"]
    folders = {Path(name).parent for name in expected}
    found = {file.relative_to(provider_root).as_posix()
             for folder in folders for file in (provider_root / folder).glob("*.parquet")}
    if found != expected.keys():
        raise ValueError("provider Parquet set does not match the pinned Qilin snapshot")
    if any(sha256(provider_root / name) != digest for name, digest in expected.items()):
        raise ValueError("provider Parquet SHA-256 does not match the pinned Qilin snapshot")

    with tempfile.TemporaryDirectory(prefix="sidduet-qilin-") as scratch:
        local = Path(scratch)
        counts, inputs = local / "counts.csv", local / "import.json"
        prefix_map, result = local / "prefix.csv", local / "calibration.json"
        universe = write_prefix(prefix_map)
        run_script("materialize_qilin_role_counts.py", "--qilin-root", provider_root,
                   "--out-counts", counts, "--out-summary", inputs, "--hash-inputs")
        imported = json.loads(inputs.read_text(encoding="utf-8"))
        if {row["path_relative_to_provider"]: row["sha256"] for row in imported["inputs"]} != expected:
            raise ValueError("provider input changed during import")
        run_script("calibrate_task_allocation.py", "--role-counts", counts,
                   "--sid-map", f"{VIEW}={prefix_map}", "--draws", DRAWS, "--seed", SEED,
                   "--out-json", result, "--out-csv", local / "calibration.csv")
        calibration = json.loads(result.read_text(encoding="utf-8"))

    coverage, = calibration["map_coverage"]
    summary, = calibration["results"]
    if coverage["covered_common_items"] != universe or coverage["unused_rows"]:
        raise ValueError("Qilin observations and the released cohort do not completely join")
    if summary["status"] != "ESTIMABLE":
        raise ValueError("the fixed shared prefix has no multi-item groups")
    return {
        "schema": "sidduet.qilin_public_calibration_example.v1",
        "scope": "Descriptive calibration of the released GenSAR prefix on the pinned Qilin inputs.",
        "provider_revision": spec["revision"],
        "provider_files_sha256": expected,
        "role_counts_sha256": imported["output_sha256"],
        "prefix_map_sha256": calibration["inputs"]["sid_maps"][0]["sha256"],
        "seed": calibration["seed"],
        "draws": calibration["draws"],
        "paired_items": universe,
        "mapped_paired_items": coverage["covered_common_items"],
        "map_coverage": coverage["covered_common_items"] / universe,
        "result": summary,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-root", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True, help="fresh aggregate report path")
    args = parser.parse_args()
    if args.out_json.exists() or args.out_json.is_symlink() or not args.out_json.parent.is_dir():
        parser.error("choose a fresh JSON path in an existing directory")
    try:
        report = replay(args.provider_root.resolve())
        with args.out_json.open("x", encoding="utf-8") as target:
            json.dump(report, target, indent=2, sort_keys=True, allow_nan=False)
            target.write("\n")
    except (KeyError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        sys.exit(f"Qilin calibration replay failed: {exc}")
    print("PASS_QILIN_CALIBRATION_EXAMPLE")


if __name__ == "__main__":
    main()
