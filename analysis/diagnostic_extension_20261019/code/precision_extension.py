#!/usr/bin/env python3
"""Fixed 1999-draw precision extension of two paired-count regrouping references."""
from __future__ import annotations
import argparse
import ast
import csv
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import resource
import sys
import time

for thread_variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[thread_variable] = "1"
import numpy as np

DRAWS, PREFIX, SECONDS_CAP, MEMORY_CAP = 1999, 199, 600, 1024**3
POPULATION_FUNCTIONS = ("item_key", "integer_count", "jsd_rows", "group_stats", "weighted_mean", "means", "strata", "describe", "empty_null", "add_null", "summarize_null", "support_bands", "paired_permutation_indices", "empirical_p", "bh", "read_inputs")
EXACT_FUNCTIONS = ("exact_classes", "exact_permutation_indices", "equal_nested", "check_permutation", "evaluate_mapping_views")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    with Path(path).open("x") as target:
        json.dump(value, target, indent=2, sort_keys=True, allow_nan=False)
        target.write("\n")


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def functions(path, names):
    parsed = ast.parse(Path(path).read_text())
    bodies = {node.name: ast.dump(node, include_attributes=False) for node in parsed.body if isinstance(node, ast.FunctionDef)}
    result = {name: hashlib.sha256(bodies[name].encode()).hexdigest() for name in names}
    constants = {"PROFILE", "DATASETS", "FAMILIES", "REPS", "EXPECTED_N", "PERCENTILES", "METRICS", "SIZE_LABELS", "SUPPORT_LABELS"}
    for node in parsed.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in constants:
                    result["constant:" + target.id] = hashlib.sha256(ast.dump(node.value, include_attributes=False).encode()).hexdigest()
    return result


def check_prefix(actual, expected):
    if actual.keys() != expected.keys():
        raise ValueError("Prefix strata changed")
    checked = 0
    for stratum, metrics in expected.items():
        if actual[stratum].keys() != metrics.keys():
            raise ValueError("Prefix metrics changed")
        for metric, values in metrics.items():
            if len(values) != PREFIX or actual[stratum][metric][:PREFIX] != values:
                raise ValueError(f"Prefix values changed: {stratum}/{metric}")
            checked += len(values)
    return checked


def resident_bytes():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if sys.platform == "darwin" else value * 1024


def runtime():
    if sys.version_info[:3] != (3, 12, 14) or np.__version__ != "2.3.5":
        raise RuntimeError("This frozen extension requires CPython 3.12.14 and NumPy 2.3.5")
    return {"python": sys.version, "numpy": np.__version__, "executable": sys.executable, "platform": platform.platform(), "threads": {k: os.environ[k] for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")}}


def configuration(args):
    paths = {name: Path(getattr(args, name)).resolve() for name in ("inputs", "population_code", "exact_code", "primary_baseline", "exact_baseline", "plan")}
    for name in ("primary_draws", "exact_draws", "equivalent_population_code", "equivalent_exact_code"):
        if getattr(args, name):
            paths[name] = Path(getattr(args, name)).resolve()
    if ("primary_draws" in paths) != ("exact_draws" in paths):
        raise ValueError("Supply both persisted baseline draw files or neither")
    manifest = json.loads(paths["inputs"].read_text())
    names = {d + "_topology_v2.csv" for d in ("kuaisar", "qilin")} | {f + "_normalized_sid.csv" for f in ("grid", "rq-vae", "resid-gaoq")}
    assets = [a for a in manifest["assets"] if Path(a["path"]).name in names]
    if len(assets) != 5:
        raise ValueError("Expected the same five scientific inputs")
    for asset in assets:
        path = Path(asset["path"])
        if path.stat().st_size != asset["bytes"] or digest(path) != asset["sha256"]:
            raise ValueError("Scientific input hash/length mismatch: " + path.name)
    bindings = {name: {"path": str(path), "bytes": path.stat().st_size, "sha256": digest(path)} for name, path in paths.items()}
    scientific = {"population": functions(paths["population_code"], POPULATION_FUNCTIONS), "exact": functions(paths["exact_code"], EXACT_FUNCTIONS)}
    for name, key, names_used in (("equivalent_population_code", "population", POPULATION_FUNCTIONS), ("equivalent_exact_code", "exact", EXACT_FUNCTIONS)):
        if name in paths and functions(paths[name], names_used) != scientific[key]:
            raise ValueError("Supplied equivalent scientific functions differ: " + name)
    return {"bindings": bindings, "scientific_inputs": assets, "scientific_function_ast_sha256": scientific, "driver_sha256": digest(__file__), "output": str(args.out.resolve()), "draws": DRAWS, "prefix": PREFIX, "runtime": runtime(), "seed_bases": {"band": 20262018, "exact": 20263018}, "datasets": ["kuaisar", "qilin"], "families": ["grid", "rq-vae", "resid-gaoq"]}


def baselines(args):
    primary = json.loads(args.primary_baseline.read_text())
    exact = json.loads(args.exact_baseline.read_text())
    old = {"band": {(r["dataset"], r["mapping_family"]): r for r in primary["results"]}, "exact": {(r["dataset"], r["mapping_family"]): r for r in exact["results"]}}
    if len(old["band"]) != 6 or old["band"].keys() != old["exact"].keys():
        raise ValueError("Expected the same six baseline strata")
    persisted = {}
    if args.primary_draws:
        band = json.loads(args.primary_draws.read_text())
        persisted["band"] = {key: record["B"] for key, record in band.items()}
        persisted["exact"] = json.loads(args.exact_draws.read_text())
        for reference in persisted:
            for record in persisted[reference].values():
                check_prefix(record, record)
    return old, persisted


def preflight(args):
    config = configuration(args)
    h = load(args.population_code, "mc1999_population")
    e = load(args.exact_code, "mc1999_exact")
    old, persisted = baselines(args)
    assert h.REPS == e.REPS == PREFIX
    assert h.empirical_p(2, [1] * DRAWS) == 0.001
    assert h.bh([0.01] * 6) == [0.01] * 6
    assert check_prefix({"x": {"y": [None] * DRAWS}}, {"x": {"y": [None] * PREFIX}}) == PREFIX
    for di, dataset in enumerate(h.DATASETS):
        for family in h.FAMILIES:
            for reference, control, seed in (("band", "control_B", 20262018), ("exact", "control_B_exact", 20263018)):
                record = old[reference][dataset, family]
                assert record[control]["draws"] == PREFIX and record[control]["seed"] == seed + di
                if reference in persisted:
                    summary = h.summarize_null(persisted[reference][dataset + "/" + family], record["observed"])
                    e.equal_nested(summary, record[control]["summaries"])
    if args.out.exists():
        raise FileExistsError("Choose the frozen fresh output; do not overwrite: " + str(args.out))
    write_json(args.preflight_record, {"status": "PREFLIGHT_PASS", "config": config, "baseline_draws_present": bool(persisted), "random_draws_executed": 0, "estimates_recomputed": False, "original_cli_draw_option": False, "scope": "Only paired band/exact-total references; no Control A, models, APIs, GPU, tuning, thresholds, or original-source edits", "expected_seconds": [60, 180], "hard_cap_seconds": SECONDS_CAP, "memory_target_bytes": MEMORY_CAP, "prefix_validation": "Every persisted aggregate value; exact-total permutation SHA256; reconstructed 199 summaries; 1e-14 observed tolerance"})
    print(json.dumps({"status": "PREFLIGHT_PASS", "random_draws_executed": 0, "record": str(args.preflight_record)}, sort_keys=True))


def execute(args):
    locked = json.loads(args.preflight_record.read_text())
    config = configuration(args)
    if locked["status"] != "PREFLIGHT_PASS" or config != locked["config"]:
        raise ValueError("Frozen preflight binding changed; stop without fallback")
    if args.out.exists():
        raise FileExistsError("Refuse to overwrite existing output")
    args.out.mkdir()
    started = time.monotonic()
    draws, hashes, records, prefix_checks = {}, {}, [], []
    try:
        h, e = load(args.population_code, "mc1999_population"), load(args.exact_code, "mc1999_exact")
        old, persisted = baselines(args)
        data, _ = h.read_inputs(args.inputs)
        for di, dataset in enumerate(h.DATASETS):
            d = data[dataset]
            s, r = d["s"], d["r"]
            states = {}
            for family in h.FAMILIES:
                mapping = d[family]
                stats = h.group_stats(s, r, mapping["groups"], mapping["sizes"])
                masks = h.strata(mapping["sizes"], stats)
                observed = h.describe(stats, mapping["sizes"], masks)
                for reference in old:
                    baseline = old[reference][dataset, family]
                    e.equal_nested(observed, baseline["observed"])
                    assert baseline["items"] == len(s) and baseline["sid_groups"] == len(mapping["sizes"])
                states[family] = {"groups": mapping["groups"], "sizes": mapping["sizes"], "observed": stats, "masks": masks, "description": observed}
            bands = h.support_bands(s, r)
            classes, mobility = e.exact_classes(s, r)
            for reference, seed in (("band", 20262018 + di), ("exact", 20263018 + di)):
                rng = np.random.Generator(np.random.PCG64(seed))
                accum = {family: h.empty_null(state["masks"]) for family, state in states.items()}
                permutation_hashes = []
                hashes[reference + "/" + dataset] = permutation_hashes
                for family in states:
                    draws[reference + "/" + dataset + "/" + family] = accum[family]
                for index in range(DRAWS):
                    if time.monotonic() - started > SECONDS_CAP or resident_bytes() > MEMORY_CAP:
                        raise RuntimeError("Frozen time or memory cap exceeded; no reduced draw count")
                    if reference == "band":
                        perm = h.paired_permutation_indices(bands, rng)
                        if len(np.unique(perm)) != len(s) or not np.all(bands[perm] == bands):
                            raise ValueError("Band/global pair invariants failed")
                    else:
                        perm = e.exact_permutation_indices(classes, len(s), rng)
                        e.check_permutation(s, r, perm, classes, list(states.values()))
                    permutation_hashes.append(hashlib.sha256(perm.tobytes()).hexdigest())
                    values = e.evaluate_mapping_views(s, r, perm, states, h)
                    for family, state in states.items():
                        h.add_null(accum[family], values[family], state["sizes"], state["masks"])
                    if index == PREFIX - 1:
                        for family, state in states.items():
                            key = dataset + "/" + family
                            baseline = old[reference][dataset, family]
                            control = "control_B" if reference == "band" else "control_B_exact"
                            e.equal_nested(h.summarize_null(accum[family], state["description"]), baseline[control]["summaries"])
                            count = check_prefix(accum[family], persisted[reference][key]) if reference in persisted else 0
                            if reference == "exact" and permutation_hashes != baseline[control]["draw_permutation_sha256"]:
                                raise ValueError("Exact-total permutation prefix hashes changed")
                            prefix_checks.append({"reference": reference, "dataset": dataset, "mapping_family": family, "aggregate_values_exactly_equal": count, "summary_tolerance": 1e-14, "permutation_sha256_equal": reference == "exact"})
                    if (index + 1) % 200 == 0:
                        print(json.dumps({"reference": reference, "dataset": dataset, "draws": index + 1, "seconds": time.monotonic() - started}), flush=True)
                hashes[reference + "/" + dataset] = permutation_hashes
                for family, state in states.items():
                    key = dataset + "/" + family
                    draws[reference + "/" + key] = accum[family]
                    summaries = h.summarize_null(accum[family], state["description"])
                    metric = summaries["all_collision_groups"]["equal_group_jsd"]
                    control = "control_B" if reference == "band" else "control_B_exact"
                    baseline = old[reference][dataset, family][control]["summaries"]["all_collision_groups"]["equal_group_jsd"]
                    observed = state["description"]["all_collision_groups"]["means"]["equal_group_jsd"]
                    mean = metric["mean"]
                    baseline_record = old[reference][dataset, family]
                    old_inference = {"p_two_sided": baseline_record["primary_control_B_two_sided_p" if reference == "band" else "primary_supplementary_two_sided_p"], "BH_six": baseline_record["primary_B_BH_adjusted_p_across_six" if reference == "band" else "primary_supplementary_BH_adjusted_p_across_six"], "BY_six": baseline_record["primary_B_BY_adjusted_p_dependency_sensitivity" if reference == "band" else "primary_supplementary_BY_adjusted_p_dependency_sensitivity"]}
                    records.append({"reference": reference, "dataset": dataset, "mapping_family": family, "seed": seed, "draws": DRAWS, "observed": state["description"], "observed_unchanged_tolerance": 1e-14, "summaries": summaries, "p_two_sided": h.empirical_p(observed, accum[family]["all_collision_groups"]["equal_group_jsd"]), "direction": "below" if observed < mean else "above" if observed > mean else "equal", "baseline_199": baseline, "baseline_inference_199": old_inference, "mean_shift": mean - baseline["mean"], "range_endpoint_shifts": [a - b for a, b in zip(metric["central_95pct"], baseline["central_95pct"])], "mean_mcse": float(np.std(accum[family]["all_collision_groups"]["equal_group_jsd"], ddof=1) / math.sqrt(DRAWS)), "mobility": mobility if reference == "exact" else None})
        for reference in ("band", "exact"):
            family_records = [r for r in records if r["reference"] == reference]
            for record, q in zip(family_records, h.bh([r["p_two_sided"] for r in family_records])):
                record["BH_six"], record["BY_six"] = q, min(1.0, q * sum(1 / k for k in range(1, 7)))
        if configuration(args) != config:
            raise ValueError("Bound source/input/plan/baseline identity changed during execution")
        write_json(args.out / "NULL_AGGREGATE_DRAWS.json", draws)
        write_json(args.out / "PERMUTATION_SHA256.json", hashes)
        write_json(args.out / "MC1999_RESULTS.json", {"schema": "rolemap.paired_regrouping_precision.v1", "draws": DRAWS, "prefix": PREFIX, "status": "COMPLETE", "results": records, "prefix_checks": prefix_checks, "scope": "Numerical precision extension only; two separate six-comparison families; no new data, independent replication, causal or predictive claim"})
        with (args.out / "COMPARISON.csv").open("x", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=["reference", "dataset", "mapping_family", "observed", "mean_199", "mean_1999", "q025_199", "q025_1999", "q975_199", "q975_1999", "effect_199", "effect_1999", "mean_shift", "p_199", "p_two_sided", "BH_199", "BH_six", "BY_199", "BY_six", "direction"])
            writer.writeheader()
            for r in records:
                old_metric, new_metric = r["baseline_199"], r["summaries"]["all_collision_groups"]["equal_group_jsd"]
                row = {key: r[key] for key in ("reference", "dataset", "mapping_family", "mean_shift", "p_two_sided", "BH_six", "BY_six", "direction")}
                row.update(p_199=r["baseline_inference_199"]["p_two_sided"], BH_199=r["baseline_inference_199"]["BH_six"], BY_199=r["baseline_inference_199"]["BY_six"])
                row.update(observed=r["observed"]["all_collision_groups"]["means"]["equal_group_jsd"], mean_199=old_metric["mean"], mean_1999=new_metric["mean"], q025_199=old_metric["central_95pct"][0], q025_1999=new_metric["central_95pct"][0], q975_199=old_metric["central_95pct"][1], q975_1999=new_metric["central_95pct"][1], effect_199=old_metric["observed_minus_null_mean"], effect_1999=new_metric["observed_minus_null_mean"])
                writer.writerow(row)
        write_json(args.out / "EXECUTION_RECEIPT.json", {"status": "COMPLETE", "config": config, "preflight_sha256": digest(args.preflight_record), "elapsed_seconds": time.monotonic() - started, "maxrss_bytes": resident_bytes(), "prefix_checks": prefix_checks, "no_models_api_gpu": True, "outputs": [{"name": p.name, "bytes": p.stat().st_size, "sha256": digest(p)} for p in sorted(args.out.iterdir())]})
    except Exception as exc:
        write_json(args.out / "FAILURE_RECEIPT.json", {"status": "FAILED_STOP_NO_FALLBACK", "exception": str(exc), "elapsed_seconds": time.monotonic() - started, "config": config})
        write_json(args.out / "PARTIAL_DRAWS.json", draws)
        write_json(args.out / "PARTIAL_PERMUTATION_SHA256.json", hashes)
        raise
    print(json.dumps({"status": "COMPLETE", "seconds": time.monotonic() - started, "out": str(args.out)}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("preflight", "run"), default="preflight")
    for name in ("inputs", "population-code", "exact-code", "primary-baseline", "exact-baseline", "out", "plan", "preflight-record"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("primary-draws", "exact-draws", "equivalent-population-code", "equivalent-exact-code"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    preflight(args) if args.mode == "preflight" else execute(args)


if __name__ == "__main__":
    main()
