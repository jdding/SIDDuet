#!/usr/bin/env python3
"""Calibrate user-supplied paired role counts against two regrouping references."""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
POP_PATH = ROOT / "analysis/diagnostic_extension_20261019/code/population_analysis.py"
MAP_PATH = ROOT / "scripts/sid_map_io.py"
MAX_EXACT = 2**53
REFERENCES = ("band", "exact_total")
# All six summary metrics are in [0, 1]. Only tail comparisons use this
# absolute tolerance; reported statistics/ranges retain their original precision.
TAIL_TIE_ABSOLUTE_TOLERANCE = 1e-12


def load_path(name, path):
    """Load exact shipped helpers under isolated Python, independent of cwd/PYTHONPATH."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


POP = load_path("sidduet_frozen_population_kernels", POP_PATH)
SID_IO = load_path("sidduet_strict_sid_map_io", MAP_PATH)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def asset(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path)}


def read_counts(path):
    counts = defaultdict(dict)
    row_counts = defaultdict(int)
    totals = defaultdict(int)
    with Path(path).open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, strict=True)
        header = next(reader, None)
        required = ("dataset", "item_id", "role", "label", "count")
        if not header or len(header) != len(set(header)) or any(k not in header for k in required):
            raise ValueError("role counts require unique dataset,item_id,role,label,count columns")
        indices = [header.index(k) for k in required]
        for row in reader:
            if len(row) != len(header):
                raise ValueError(f"count row {reader.line_num} has incorrect CSV width")
            dataset, item, role, _label, raw = (row[i] for i in indices)
            if not dataset.strip() or not item.strip() or role not in ("search", "rec"):
                raise ValueError("counts require nonblank dataset/item keys and role search or rec")
            try:
                value = Decimal(raw)
            except InvalidOperation as exc:
                raise ValueError("counts must be nonnegative finite integers") from exc
            if not value.is_finite() or value < 0 or value != value.to_integral_value() or value > MAX_EXACT:
                raise ValueError("counts must be nonnegative finite integers within exact binary64 range")
            number = int(value)
            totals[dataset] += number
            if totals[dataset] > MAX_EXACT:
                raise ValueError("dataset count sum exceeds exact binary64 aggregation range (2**53)")
            pair = counts[dataset].setdefault(item, [0, 0])
            pair[role == "rec"] += number
            row_counts[dataset] += 1
    if not counts:
        raise ValueError("counts contain no datasets")
    datasets, cohorts = {}, []
    for dataset in sorted(counts):
        rows = counts[dataset]
        ids = sorted(item for item, pair in rows.items() if min(pair) > 0)
        if not ids:
            raise ValueError(f"dataset {dataset!r} has an empty common positive-support cohort")
        pairs = np.array([rows[item] for item in ids], dtype=np.int64)
        datasets[dataset] = {"ids": ids, "s": pairs[:, 0], "r": pairs[:, 1]}
        cohorts.append({"dataset": dataset, "input_rows": row_counts[dataset],
                        "input_items": len(rows), "common_items": len(ids),
                        "excluded_items": len(rows) - len(ids),
                        "excluded_missing_or_zero_search_items": sum(pair[0] == 0 for pair in rows.values()),
                        "excluded_missing_or_zero_rec_items": sum(pair[1] == 0 for pair in rows.values()),
                        "input_observations": totals[dataset],
                        "common_search_observations": int(pairs[:, 0].sum()),
                        "common_rec_observations": int(pairs[:, 1].sum())})
    return datasets, cohorts


def parse_maps(specs):
    result = {}
    for spec in specs:
        if "=" not in spec:
            raise ValueError("--sid-map requires name=path")
        name, path = spec.split("=", 1)
        if not name or name != name.strip() or any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
            raise ValueError("map names must be nonblank, trimmed and free of control characters")
        if name in result:
            raise ValueError("repeated map name: " + name)
        if not path:
            raise ValueError("map path must not be empty")
        result[name] = Path(path)
    return dict(sorted(result.items()))


def check_outputs(outputs, protected):
    resolved = [Path(p).resolve() for p in outputs]
    if len(set(resolved)) != len(resolved):
        raise ValueError("output paths alias one another")
    if set(resolved) & {Path(p).resolve() for p in protected}:
        raise ValueError("output path aliases an input or implementation file")
    for path in outputs:
        path = Path(path)
        if path.exists() or path.is_symlink():
            raise ValueError("output already exists: " + str(path))
        if not path.parent.is_dir():
            raise ValueError("output parent directory must already exist: " + str(path.parent))


def seed_for(seed, dataset, reference):
    material = json.dumps(["sidduet.count_reference.v1", seed, dataset, reference],
                          ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest(), "big")


def summary(stats, sizes):
    return POP.means(stats["jsd"], stats["disjoint"], sizes, stats["events"], sizes >= 2)


def empirical_p_with_ties(observed, values):
    """Treat summation-roundoff ties inclusively in the unchanged p kernel."""
    values = np.asarray(values, dtype=float)
    tied = np.abs(values - observed) <= TAIL_TIE_ABSOLUTE_TOLERANCE
    return POP.empirical_p(observed, np.where(tied, observed, values))


def reference_summary(observed, values, draws):
    result = {}
    for metric in POP.METRICS:
        values_for_metric = values[metric]
        if observed[metric] is None:
            result[metric] = {"draws": draws, "mean": None, "central_95pct": None,
                              "observed_minus_reference_mean": None, "two_sided_p": None}
        else:
            arr = np.asarray(values_for_metric, dtype=float)
            result[metric] = {"draws": draws, "mean": float(arr.mean()),
                              "central_95pct": [float(v) for v in np.percentile(arr, [2.5, 97.5])],
                              "observed_minus_reference_mean": float(observed[metric] - arr.mean()),
                              "two_sided_p": empirical_p_with_ties(observed[metric], arr)}
    return result


def calculate(args):
    if args.draws < 1 or args.seed < 0:
        raise ValueError("draws must be positive and seed must be nonnegative")
    maps = parse_maps(args.sid_map)
    implementation = [asset(path) for path in (Path(__file__), POP_PATH, MAP_PATH)]
    inputs = {"role_counts": asset(args.role_counts),
              "sid_maps": [{"name": name, **asset(path)} for name, path in maps.items()]}
    protected = [args.role_counts, *maps.values(), Path(__file__), POP_PATH, MAP_PATH]
    check_outputs((args.out_json, args.out_csv), protected)
    datasets, cohorts = read_counts(args.role_counts)
    mappings = {name: SID_IO.load_sid_map(path) for name, path in maps.items()}
    all_common = {(dataset, item) for dataset, data in datasets.items() for item in data["ids"]}
    coverage = []
    for name, mapping in mappings.items():
        if all_common - mapping.keys():
            raise ValueError("map coverage incomplete for common cohort: " + name)
        coverage.append({"name": name, "input_rows": len(mapping), "covered_common_items": len(all_common),
                         "unused_rows": len(mapping.keys() - all_common),
                         "datasets": [{"dataset": dataset, "common_items": len(data["ids"]),
                                       "unused_rows": sum(d == dataset and (d, i) not in all_common
                                                          for d, i in mapping)}
                                      for dataset, data in datasets.items()]})
    records = []
    for dataset, data in datasets.items():
        s, r = data["s"], data["r"]
        views = []
        for name, mapping in mappings.items():
            codes = [mapping[(dataset, item)] for item in data["ids"]]
            code_index = {code: i for i, code in enumerate(sorted(set(codes)))}
            group = np.array([code_index[code] for code in codes], dtype=np.int64)
            sizes = np.bincount(group, minlength=len(code_index)).astype(np.int64)
            observed = summary(POP.group_stats(s, r, group, sizes), sizes)
            collision = sizes >= 2
            record = {"dataset": dataset, "mapping": name,
                      "status": "ESTIMABLE" if np.any(collision) else "STRUCTURAL_NONCOLLISION_CONTROL",
                      "counts": {"common_items": len(s), "groups": len(sizes),
                                 "collision_groups": int(collision.sum()),
                                 "collision_items": int(sizes[collision].sum()),
                                 "singleton_groups": int((sizes == 1).sum())},
                      "observed": observed, "references": {}}
            views.append((record, group, sizes))
            records.append(record)
        for reference in REFERENCES:
            keys = POP.support_bands(s, r) if reference == "band" else s + r
            _, key_sizes = np.unique(keys, return_counts=True)
            stream = seed_for(args.seed, dataset, reference)
            rng = np.random.Generator(np.random.PCG64(stream))
            accumulators = [{metric: [] for metric in POP.METRICS} for _ in views]
            for _ in range(args.draws):
                permutation = POP.paired_permutation_indices(keys, rng)
                if not np.array_equal(keys, keys[permutation]):
                    raise ValueError("reference grouping key preservation failed")
                # One paired permutation is evaluated by every view, including all singleton slots.
                ps, pr = s[permutation], r[permutation]
                for (record, group, sizes), accumulator in zip(views, accumulators):
                    if record["status"] == "ESTIMABLE":
                        current = summary(POP.group_stats(ps, pr, group, sizes), sizes)
                        for metric, value in current.items():
                            accumulator[metric].append(value)
            for (record, _group, _sizes), accumulator in zip(views, accumulators):
                metrics = reference_summary(record["observed"], accumulator, args.draws)
                record["references"][reference] = {
                    "metrics": metrics, "primary_p": metrics["equal_group_jsd"]["two_sided_p"],
                    "primary_bh_q": None, "primary_by_q": None,
                    "strata": len(key_sizes), "permutable_strata": int((key_sizes > 1).sum()),
                    "permutable_slots": int(key_sizes[key_sizes > 1].sum()),
                    "draws": args.draws, "paired_key_checks": args.draws,
                    "rng_seed_sha256": format(stream, "064x")}
    families = []
    for reference in REFERENCES:
        estimable = [record for record in records if record["status"] == "ESTIMABLE"]
        adjusted = POP.bh([record["references"][reference]["primary_p"] for record in estimable])
        harmonic = sum(1 / k for k in range(1, len(estimable) + 1))
        for record, q in zip(estimable, adjusted):
            record["references"][reference]["primary_bh_q"] = q
            record["references"][reference]["primary_by_q"] = min(1.0, q * harmonic)
        families.append({"reference": reference, "metric": "equal_group_jsd", "size": len(estimable),
                         "members": [{"dataset": record["dataset"], "mapping": record["mapping"]}
                                     for record in estimable], "by_harmonic_factor": harmonic})
    for declaration in [inputs["role_counts"], *inputs["sid_maps"], *implementation]:
        if sha(declaration["path"]) != declaration["sha256"]:
            raise ValueError("input or implementation changed during calculation")
    return {"schema": "sidduet.count_reference_calibration.v1", "status": "COMPLETE_VALIDITY_CHECKS_PASSED",
            "seed": args.seed, "draws": args.draws, "inputs": inputs, "implementation": implementation,
            "inputs_rehashed_after": True, "runtime": {"python": sys.version, "numpy": np.__version__,
                                                      "platform": platform.platform(), "rng": "NumPy PCG64"},
            "cohorts": cohorts, "map_coverage": coverage, "results": records,
            "multiplicity_families": families,
            "protocol": {"common_cohort": "exact dataset/item keys; positive summed search and rec counts",
                         "permutation_universe": "all common items, including mapping singletons; entire (S,R) pairs move",
                         "band": "within integer floor(log2(S+R))", "exact_total": "within identical S+R",
                         "groups": "fixed SID groups; summary metrics exclude singleton groups",
                         "weights": "equal-group, item-count, or each state's actual group S+R volume",
                         "primary_metric": "equal_group_jsd",
                         "p": "min(1,2*min((1+#reference>=observed)/(B+1),(1+#reference<=observed)/(B+1))); reference values within the declared absolute tolerance of observed are treated as observed in both tails",
                         "tail_tie_absolute_tolerance": TAIL_TIE_ABSOLUTE_TOLERANCE,
                         "tail_tie_relative_tolerance": 0,
                         "tail_tie_scope": "all six bounded [0,1] summary metrics; comparison only, reported statistics and reference ranges remain unrounded",
                         "multiplicity": "BH and BY across all estimable dataset-by-map primary endpoints, separately for each reference; structural noncollision controls excluded",
                         "secondary_metrics": "descriptive summaries and unadjusted p values; no secondary FDR claim",
                         "range": "central 95 percent regrouping reference range, not an effect confidence interval",
                         "scope": "conditional paired-count regrouping calibration; not semantic quality, heldout utility or causal evidence",
                         "stream": "SHA256 of UTF-8 compact JSON [sidduet.count_reference.v1,seed,dataset,reference], interpreted big-endian as PCG64 seed; sorted exact item IDs",
                         "public_safety": "aggregate only; no item IDs, pairs, SID codes or joins"}}


CSV_FIELDS = ("dataset", "mapping", "reference", "status", "common_items", "groups", "collision_groups",
              "collision_items", "singleton_groups", "strata", "permutable_strata", "permutable_slots",
              "draws", "observed_equal_group_jsd", "reference_mean", "reference_q025", "reference_q975",
              "observed_minus_reference_mean", "two_sided_p", "bh_q", "by_q")


def write_outputs(args, result):
    # Repeat the exclusive-path validation immediately before creating either output.
    protected = [entry["path"] for entry in [result["inputs"]["role_counts"],
                 *result["inputs"]["sid_maps"], *result["implementation"]]]
    check_outputs((args.out_json, args.out_csv), protected)
    created = []
    try:
        with Path(args.out_json).open("x", encoding="utf-8") as json_handle:
            created.append(Path(args.out_json))
            with Path(args.out_csv).open("x", encoding="utf-8", newline="") as csv_handle:
                created.append(Path(args.out_csv))
                json.dump(result, json_handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
                json_handle.write("\n")
                writer = csv.DictWriter(csv_handle, fieldnames=CSV_FIELDS)
                writer.writeheader()
                for record in result["results"]:
                    for reference, summary_ref in record["references"].items():
                        primary = summary_ref["metrics"]["equal_group_jsd"]
                        bounds = primary["central_95pct"] or (None, None)
                        writer.writerow({"dataset": record["dataset"], "mapping": record["mapping"],
                                         "reference": reference, "status": record["status"], **record["counts"],
                                         **{key: summary_ref[key] for key in ("strata", "permutable_strata", "permutable_slots", "draws")},
                                         "observed_equal_group_jsd": record["observed"]["equal_group_jsd"],
                                         "reference_mean": primary["mean"], "reference_q025": bounds[0],
                                         "reference_q975": bounds[1],
                                         "observed_minus_reference_mean": primary["observed_minus_reference_mean"],
                                         "two_sided_p": summary_ref["primary_p"], "bh_q": summary_ref["primary_bh_q"],
                                         "by_q": summary_ref["primary_by_q"]})
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role-counts", type=Path, required=True)
    parser.add_argument("--sid-map", action="append", required=True, help="repeatable name=map.csv")
    parser.add_argument("--draws", type=int, default=1999)
    parser.add_argument("--seed", type=int, default=20261104)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-csv", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = calculate(args)
        write_outputs(args, result)
    except (ValueError, OSError, csv.Error, InvalidOperation) as exc:
        parser.error(str(exc))
    print(json.dumps({"status": result["status"], "dataset_map_endpoints": len(result["results"]),
                      "draws_per_reference": args.draws}))


if __name__ == "__main__":
    main()
