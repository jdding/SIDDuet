#!/usr/bin/env python3
"""Evaluate tie-preserving cut sensitivity and quadrant occupancy."""

from __future__ import annotations
import argparse
import bisect
import csv
import hashlib
import json
import math
import platform
import resource
import sys
import tempfile
import time
from collections import Counter
from fractions import Fraction
from pathlib import Path
import numpy as np

PROFILE = "sr_sid_rolemap.topology.value_median.v2"
QUANTILES = (Fraction(1, 4), Fraction(1, 2), Fraction(3, 4))
CELLS = ("HH", "HL", "LH", "LL")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def fraction(x):
    return {"numerator": x.numerator, "denominator": x.denominator}


def exact_quantile(values, q):
    if not values:
        return None
    a = sorted(values)
    n = len(a)
    if q == Fraction(1, 2):
        return Fraction(a[n // 2]) if n % 2 else (Fraction(a[n // 2 - 1]) + Fraction(a[n // 2])) / 2
    if q not in (Fraction(1, 4), Fraction(3, 4)):
        raise ValueError("unplanned quantile")
    # Integer arithmetic implements ceil(q*N), without float boundary error.
    rank = (q.numerator * n + q.denominator - 1) // q.denominator
    return Fraction(a[rank - 1])


def axis_description(values, cut):
    n = len(values)
    counts = Counter(values)
    if not n:
        return {
            "items": 0,
            "unique_values": 0,
            "cut": None,
            "below": 0,
            "equal": 0,
            "above": 0,
            "low": 0,
            "high": 0,
            "largest_tie_items": 0,
            "largest_tie_fraction": None,
            "largest_tie_values": [],
            "cut_is_largest_tie": False,
            "unique_low": 0,
            "unique_high": 0,
        }
    largest = max(counts.values())
    ties = sorted(v for v, c in counts.items() if c == largest)
    lo = sum(c for v, c in counts.items() if v <= cut)
    eq = counts.get(cut, 0)
    return {
        "items": n,
        "unique_values": len(counts),
        "cut": fraction(Fraction(cut)),
        "below": lo - eq,
        "equal": eq,
        "above": n - lo,
        "low": lo,
        "high": n - lo,
        "equal_cut_fraction": eq / n,
        "largest_tie_items": largest,
        "largest_tie_fraction": largest / n,
        "largest_tie_values": [fraction(Fraction(v)) for v in ties],
        "cut_is_largest_tie": cut in ties,
        "unique_low": sum(v <= cut for v in counts),
        "unique_high": sum(v > cut for v in counts),
    }


def allocation(points, cut_x, cut_y):
    groups = {c: [] for c in CELLS}
    for x, y in points:
        cell = ("H" if x > cut_x else "L") + ("H" if y > cut_y else "L")
        groups[cell].append((x, y))
    counts = {cell: len(group) for cell, group in groups.items()}
    n = len(points)
    if sum(counts.values()) != n:
        raise AssertionError("count conservation")
    return {
        "counts": counts,
        "items": n,
        "occupied_quadrants": sum(c > 0 for c in counts.values()),
        "minimum_quadrant_items": min(counts.values()),
        "minimum_quadrant_fraction": min(counts.values()) / n if n else None,
        "distinct_values_by_quadrant": {
            cell: {
                "items": len(group),
                "unique_rsd": len({x for x, _ in group}),
                "unique_rsi_keys": len({y for _, y in group}),
                "unique_coordinate_pairs": len(set(group)),
            }
            for cell, group in groups.items()
        },
    }


def grid(points):
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    out = []
    for qx in QUANTILES:
        for qy in QUANTILES:
            cx = exact_quantile(xs, qx)
            cy = exact_quantile(ys, qy)
            if points:
                alloc = allocation(points, cx, cy)
            else:
                alloc = allocation([], Fraction(), Fraction())
            out.append(
                {
                    "q_rsd": str(qx),
                    "q_abs_rsi": str(qy),
                    "rsd_axis": axis_description(xs, cx),
                    "abs_rsi_key_axis": axis_description(ys, cy),
                    **alloc,
                }
            )
    return out


def runs(indices):
    indices = list(map(int, indices))
    if not indices:
        return []
    out = []
    start = prev = indices[0]
    for x in indices[1:]:
        if x != prev + 1:
            out.append((start, prev))
            start = x
        prev = x
    out.append((start, prev))
    return out


def cut_interval(values, index):
    # The interval describes all real cuts with exactly this L-prefix.
    return {
        "lower_inclusive": fraction(Fraction(values[index - 1])) if index else None,
        "upper_exclusive": fraction(Fraction(values[index])) if index < len(values) else None,
    }


def canonical_cut(values, index):
    return (
        Fraction(values[index - 1]) if index else Fraction(values[0]) - 1 if values else Fraction()
    )


def feasibility(points):
    xs = sorted({x for x, _ in points})
    ys = sorted({y for _, y in points})
    u = len(xs)
    v = len(ys)
    n = len(points)
    xm = {x: i + 1 for i, x in enumerate(xs)}
    ym = {y: i + 1 for i, y in enumerate(ys)}
    prefix = np.zeros((u + 1, v + 1), dtype=np.int64)
    for (x, y), count in Counter(points).items():
        prefix[xm[x], ym[y]] = count
    # Both cumsums are explicitly in place; no second full matrix is allocated.
    np.cumsum(prefix, axis=0, out=prefix)
    np.cumsum(prefix, axis=1, out=prefix)
    if int(prefix[-1, -1]) != n:
        raise AssertionError("prefix conservation")
    marginal_y = prefix[-1, :]
    best = -1
    maximizers = []
    pairs = 0
    representative = None
    for i in range(u + 1):
        ll = prefix[i, :]
        marginal_x = int(prefix[i, -1])
        smallest = np.minimum(ll, marginal_x - ll)
        np.minimum(smallest, marginal_y - ll, out=smallest)
        np.minimum(smallest, n - marginal_x - marginal_y + ll, out=smallest)
        row_best = int(smallest.max())
        indices = np.flatnonzero(smallest == row_best)
        if row_best > best:
            best = row_best
            maximizers = []
            pairs = 0
            representative = None
        if row_best == best:
            if representative is None:
                representative = (i, int(indices[0]))
            pairs += len(indices)
            for start, end in runs(indices):
                maximizers.append(
                    {
                        "rsd_boundary_index": i,
                        "rsi_boundary_start": start,
                        "rsi_boundary_end": end,
                        "boundary_pairs_in_run": end - start + 1,
                        "rsd_cut_interval": cut_interval(xs, i),
                        "rsi_cut_union_interval": {
                            "lower_inclusive": cut_interval(ys, start)["lower_inclusive"],
                            "upper_exclusive": cut_interval(ys, end)["upper_exclusive"],
                        },
                    }
                )
    i, j = representative
    cx = canonical_cut(xs, i)
    cy = canonical_cut(ys, j)
    return {
        "items": n,
        "unique_rsd_values": u,
        "unique_abs_rsi_keys": v,
        "boundary_pairs_examined": (u + 1) * (v + 1),
        "matrix_shape": [u + 1, v + 1],
        "matrix_bytes": int(prefix.nbytes),
        "maximum_minimum_quadrant_items": best,
        "maximum_minimum_quadrant_fraction": best / n if n else None,
        "maximizing_boundary_pairs": pairs,
        "maximizing_interval_runs": len(maximizers),
        "representative": {
            "lexicographic_order": "rsd boundary index, then rsi boundary index",
            "rsd_boundary_index": i,
            "rsi_boundary_index": j,
            "rsd_cut": fraction(cx),
            "abs_rsi_key_cut": fraction(cy),
            "rsd_cut_interval": cut_interval(xs, i),
            "rsi_cut_interval": cut_interval(ys, j),
            **allocation(points, cx, cy),
        },
        "all_maximizing_interval_runs": maximizers,
    }


def read_points(path):
    points = []
    refs = []
    seen = set()
    dataset = None
    with Path(path).open(newline="") as f:
        rd = csv.DictReader(f)
        required = {
            "dataset",
            "item_id",
            "profile_id",
            "rsd_numerator",
            "rsd_denominator",
            "rsi_split_key",
            "rsd_bucket",
            "rsi_mag_bucket",
            "rsd_at_median",
            "rsi_at_median",
        }
        if (
            not rd.fieldnames
            or not required.issubset(rd.fieldnames)
            or len(rd.fieldnames) != len(set(rd.fieldnames))
        ):
            raise ValueError("topology header")
        for row in rd:
            if None in row or any(row[k] is None for k in required):
                raise ValueError("row width")
            if row["profile_id"] != PROFILE:
                raise ValueError("wrong profile")
            if dataset is None:
                dataset = row["dataset"]
            if row["dataset"] != dataset or not row["item_id"] or row["item_id"] in seen:
                raise ValueError("mixed dataset or duplicate ID")
            seen.add(row["item_id"])
            x = Fraction(int(row["rsd_numerator"]), int(row["rsd_denominator"]))
            y = int(row["rsi_split_key"])
            if x < 0 or not 0 <= y <= 10**12:
                raise ValueError("coordinate range")
            points.append((x, y))
            refs.append(
                (
                    row["rsd_bucket"],
                    row["rsi_mag_bucket"],
                    int(row["rsd_at_median"]),
                    int(row["rsi_at_median"]),
                )
            )
    if not points:
        raise ValueError("empty actual topology")
    mx = exact_quantile([x for x, _ in points], Fraction(1, 2))
    my = exact_quantile([y for _, y in points], Fraction(1, 2))
    for (x, y), (xb, yb, xf, yf) in zip(points, refs):
        if (
            xb != ("high_rsd" if x > mx else "low_rsd")
            or yb != ("high_rsi" if y > my else "low_rsi")
            or xf != int(x == mx)
            or yf != int(y == my)
        ):
            raise ValueError("v2 median correspondence")
    return dataset, points


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def verify_provenance(receipt, plan, inputs):
    expected = {
        "script_sha256": sha(__file__),
        "plan_sha256": sha(plan),
        "inputs_sha256": sha(inputs),
    }
    if receipt:
        d = json.loads(Path(receipt).read_text())
        if any(d.get(k) != v for k, v in expected.items()):
            raise ValueError("supplied receipt binding mismatch")
    return expected


def execute(args):
    if args.out.exists():
        raise ValueError("output must be fresh")
    bindings = verify_provenance(args.provenance_receipt, args.plan, args.inputs)
    manifest = json.loads(args.inputs.read_text())
    declared = {Path(a["path"]).resolve(): a["sha256"] for a in manifest["assets"]}
    before = sha(args.topology)
    if declared.get(args.topology.resolve()) != before:
        raise ValueError("topology SHA differs from manifest")
    started = time.perf_counter()
    dataset, points = read_points(args.topology)
    sensitivity = grid(points)
    bound = feasibility(points)
    if sha(args.topology) != before:
        raise ValueError("topology changed during diagnostic")
    args.out.mkdir(parents=True)
    output = {
        "dataset": dataset,
        "profile_id": PROFILE,
        "analysis_kind": "post-primary fixed-score numerical-cut sensitivity and geometric upper bound",
        "inputs": {
            "topology_sha256": before,
            **bindings,
            "provenance_receipt_sha256": sha(args.provenance_receipt)
            if args.provenance_receipt
            else None,
        },
        "items": len(points),
        "v2_median_correspondence_checked_items": len(points),
        "nine_quantile_pairs": sensitivity,
        "feasibility_bound": {
            k: v for k, v in bound.items() if k != "all_maximizing_interval_runs"
        },
        "interpretation_limits": [
            "all cuts preserve complete equality blocks",
            "no replacement protocol selected",
            "geometric occupancy upper bound is not evidence of useful or predictive bins",
            "no old count target, model or training",
        ],
        "runtime": {
            "python": sys.version,
            "numpy": np.__version__,
            "platform": platform.platform(),
            "elapsed_seconds": time.perf_counter() - started,
            "peak_rss_native_units": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "peak_rss_units": "bytes on macOS; kibibytes on Linux",
            "execution_surface": "dedicated independent local CPU CLI; no model, API, GPU or training launcher",
        },
    }
    write_json(args.out / "summary.json", output)
    write_json(args.out / "all_maximizing_cut_classes.json", bound["all_maximizing_interval_runs"])
    with (args.out / "nine_pairs.csv").open("x", newline="") as f:
        fields = [
            "q_rsd",
            "q_abs_rsi",
            "HH",
            "HL",
            "LH",
            "LL",
            "occupied_quadrants",
            "minimum_quadrant_items",
            "minimum_quadrant_fraction",
        ]
        wr = csv.DictWriter(f, fieldnames=fields)
        wr.writeheader()
        for r in sensitivity:
            wr.writerow(
                {
                    "q_rsd": r["q_rsd"],
                    "q_abs_rsi": r["q_abs_rsi"],
                    **r["counts"],
                    "occupied_quadrants": r["occupied_quadrants"],
                    "minimum_quadrant_items": r["minimum_quadrant_items"],
                    "minimum_quadrant_fraction": r["minimum_quadrant_fraction"],
                }
            )
    receipt = {
        "status": "PASS",
        "dataset": dataset,
        "items": len(points),
        "bindings": bindings,
        "topology_sha256": before,
        "outputs": {p.name: sha(p) for p in sorted(args.out.iterdir())},
        "script_sha256": sha(__file__),
    }
    write_json(args.out / "receipt.json", receipt)
    print(
        json.dumps(
            {
                "status": "PASS",
                "dataset": dataset,
                "items": len(points),
                "elapsed_seconds": output["runtime"]["elapsed_seconds"],
                "output": str(args.out),
            }
        )
    )


def self_test(out):
    if out.exists():
        raise ValueError("test output fresh")
    out.mkdir(parents=True)
    checks = []

    def ck(name, test):
        if not test:
            raise AssertionError(name)
        checks.append(name)

    ck(
        "ordinary even Fraction median",
        exact_quantile([Fraction(1, 3), Fraction(1, 2)], Fraction(1, 2)) == Fraction(5, 12),
    )
    ck("quartile lower nearest rank", exact_quantile([1, 2, 3, 4], Fraction(1, 4)) == 1)
    ck("quartile upper nearest rank", exact_quantile([1, 2, 3, 4], Fraction(3, 4)) == 3)
    ck(
        "median differs from nearest rank on even N",
        exact_quantile([1, 2, 3, 4], Fraction(1, 2)) == Fraction(5, 2),
    )
    plateau = [(Fraction(1), 0)] * 7 + [(Fraction(0), 1)] * 3
    tied = [(Fraction(1, 3), 0)] * 8
    empty = []
    checker = [(Fraction(x), y) for x, y in [(0, 0), (0, 1), (1, 0), (1, 1)]]
    for name, pts in [
        ("plateau", plateau),
        ("all_tied", tied),
        ("empty", empty),
        ("checker", checker),
        ("proportional_diagonal", [(Fraction(i), i) for i in range(4)]),
        ("negative_diagonal", [(Fraction(i), 3 - i) for i in range(4)]),
    ]:
        g = grid(pts)
        b = feasibility(pts)
        ck(name + " nine pairs", len(g) == 9)
        ck(name + " each quadrant conserves", all(sum(r["counts"].values()) == len(pts) for r in g))
        xs = sorted({x for x, _ in pts})
        ys = sorted({y for _, y in pts})
        brute = []
        for i in range(len(xs) + 1):
            for j in range(len(ys) + 1):
                brute.append(
                    (
                        allocation(pts, canonical_cut(xs, i), canonical_cut(ys, j))[
                            "minimum_quadrant_items"
                        ],
                        i,
                        j,
                    )
                )
        best = max(k[0] for k in brute)
        pairs = {(i, j) for v, i, j in brute if v == best}
        expanded = {
            (r["rsd_boundary_index"], j)
            for r in b["all_maximizing_interval_runs"]
            for j in range(r["rsi_boundary_start"], r["rsi_boundary_end"] + 1)
        }
        ck(name + " exhaustive brute-force bound", b["maximum_minimum_quadrant_items"] == best)
        ck(
            name + " all maximizing runs lossless",
            expanded == pairs and b["maximizing_boundary_pairs"] == len(pairs),
        )
        ck(
            name + " lexicographic representative",
            (b["representative"]["rsd_boundary_index"], b["representative"]["rsi_boundary_index"])
            == min(pairs),
        )
        ck(name + " order invariant", b == feasibility(list(reversed(pts))))
    ck(
        "plateau maximum cannot split equality block",
        all(r["rsd_axis"]["equal"] in (3, 7) for r in grid(plateau)),
    )
    ck("all tied grid leaves all in LL", all(r["counts"]["LL"] == 8 for r in grid(tied)))
    ck(
        "checker bound min quadrant one",
        feasibility(checker)["maximum_minimum_quadrant_items"] == 1,
    )
    # Deterministic random small universes compare every cut to brute force.
    rng = np.random.Generator(np.random.PCG64(20261019))
    for seed in range(10):
        pts = [(Fraction(int(x), 7), int(y)) for x, y in rng.integers(0, 6, size=(31, 2))]
        b = feasibility(pts)
        xs = sorted({x for x, _ in pts})
        ys = sorted({y for _, y in pts})
        brute = {
            (i, j): allocation(pts, canonical_cut(xs, i), canonical_cut(ys, j))[
                "minimum_quadrant_items"
            ]
            for i in range(len(xs) + 1)
            for j in range(len(ys) + 1)
        }
        ck(
            "random brute-force bound " + str(seed),
            b["maximum_minimum_quadrant_items"] == max(brute.values()),
        )
        expanded = {
            (r["rsd_boundary_index"], j)
            for r in b["all_maximizing_interval_runs"]
            for j in range(r["rsi_boundary_start"], r["rsi_boundary_end"] + 1)
        }
        ck(
            "random all max classes " + str(seed),
            expanded == {k for k, v in brute.items() if v == max(brute.values())},
        )
    # Correspondence and fail-closed input/provenance tests use fabricated CSVs only.
    top = out / "fabricated.csv"
    fields = [
        "dataset",
        "item_id",
        "profile_id",
        "rsd_numerator",
        "rsd_denominator",
        "rsi_split_key",
        "rsd_bucket",
        "rsi_mag_bucket",
        "rsd_at_median",
        "rsi_at_median",
    ]
    mx = exact_quantile([x for x, _ in checker], Fraction(1, 2))
    my = exact_quantile([y for _, y in checker], Fraction(1, 2))
    rows = []
    for i, (x, y) in enumerate(checker):
        rows.append(
            dict(
                zip(
                    fields,
                    [
                        "fabricated",
                        str(i),
                        PROFILE,
                        x.numerator,
                        x.denominator,
                        y,
                        "high_rsd" if x > mx else "low_rsd",
                        "high_rsi" if y > my else "low_rsi",
                        int(x == mx),
                        int(y == my),
                    ],
                )
            )
        )
    with top.open("x", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    ds, pts = read_points(top)
    ck("v2 median correspondence checked", ds == "fabricated" and pts == checker)
    manifest = out / "inputs.json"
    write_json(manifest, {"assets": [{"path": str(top), "sha256": sha(top)}]})
    plan = out / "plan.md"
    plan.write_text("fabricated test plan only\n")
    accept = out / "accept.json"
    write_json(
        accept,
        {
            "script_sha256": sha(__file__),
            "plan_sha256": sha(plan),
            "inputs_sha256": sha(manifest),
        },
    )
    args = argparse.Namespace(
        out=out / "accepted_fabricated_run",
        topology=top,
        plan=plan,
        inputs=manifest,
        provenance_receipt=accept,
    )
    execute(args)
    ck(
        "all fabricated aggregate outputs contain no item IDs",
        not any("item_id" in p.read_text() for p in args.out.iterdir()),
    )
    try:
        execute(args)
        ck("fresh-output refusal", False)
    except ValueError:
        ck("fresh-output refusal", True)
    bad = json.loads(accept.read_text())
    bad["script_sha256"] = "0" * 64
    write_json(accept, bad)
    try:
        verify_provenance(accept, plan, manifest)
        ck("provenance hash mismatch refused", False)
    except ValueError:
        ck("provenance hash mismatch refused", True)
    bad["script_sha256"] = sha(__file__)
    write_json(accept, bad)
    badmanifest = json.loads(manifest.read_text())
    badmanifest["assets"][0]["sha256"] = "0" * 64
    write_json(manifest, badmanifest)
    bad["inputs_sha256"] = sha(manifest)
    write_json(accept, bad)
    args.out = out / "bad_input_output"
    try:
        execute(args)
        ck("input hash mismatch refused", False)
    except ValueError:
        ck("input hash mismatch refused", True)
    benchmark = [(Fraction(i % 4420, 100000), int((i * 37) % 3263)) for i in range(100000)]
    start = time.perf_counter()
    bench = feasibility(benchmark)
    elapsed = time.perf_counter() - start
    ck("matrix-scale fabricated benchmark dimensions", bench["matrix_shape"] == [4421, 3264])
    ck("matrix-scale full coverage", bench["boundary_pairs_examined"] == 4421 * 3264)
    receipt = {
        "status": "PASS",
        "assertions": len(checks),
        "checks": checks,
        "script_sha256": sha(__file__),
        "real_data_aggregated": False,
        "benchmark": {
            "fabricated_items": len(benchmark),
            "matrix_shape": bench["matrix_shape"],
            "matrix_bytes": bench["matrix_bytes"],
            "elapsed_seconds": elapsed,
            "peak_rss_native_units": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "peak_rss_units": "bytes on macOS; kibibytes on Linux",
        },
        "python": sys.version,
        "numpy": np.__version__,
    }
    write_json(out / "RECEIPT.json", receipt)
    print(json.dumps(receipt))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--self-test", type=Path)
    p.add_argument("--inputs", type=Path)
    p.add_argument("--plan", type=Path)
    p.add_argument("--topology", type=Path)
    p.add_argument("--out", type=Path)
    p.add_argument(
        "--provenance-receipt", "--acceptance-receipt", dest="provenance_receipt", type=Path
    )
    a = p.parse_args()
    if a.self_test:
        if any([a.inputs, a.plan, a.topology, a.out, a.provenance_receipt]):
            p.error("self-test exclusive")
        self_test(a.self_test)
        return
    if not all([a.inputs, a.plan, a.topology, a.out]):
        p.error("all real-run bindings required")
    execute(a)


if __name__ == "__main__":
    main()
