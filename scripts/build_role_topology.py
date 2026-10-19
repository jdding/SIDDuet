#!/usr/bin/env python3
"""Build the value-median v2 topology; continuous evidence precedes its bins."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import re
import sys
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_EVEN
from fractions import Fraction
from pathlib import Path


REQUIRED = {"dataset", "item_id", "role", "label", "count"}
ROLES = {"search", "rec"}
PROFILE_ID = "sr_sid_rolemap.topology.value_median.v2"
PROFILE_CONTRACT_SHA256 = "d2c333ffaff5008f2ddce74de688ef08727ed00744f47040b97e67d6de370a2f"
QUANTUM = Decimal("0.000000000001")
SCALE = 10**12
COMPONENTS = (
    ("js_divergence", "js_rank_key", "js_twice_rank"),
    ("neighbor_disagreement", "neighbor_rank_key", "neighbor_twice_rank"),
    ("top_label_mismatch", "top_label_rank_key", "top_label_twice_rank"),
)
FIELDS = [
    "dataset", "item_id", "profile_id", "search_support", "rec_support",
    "search_entropy", "rec_entropy", "js_divergence", "neighbor_disagreement",
    "top_label_mismatch", "rsd_score", "rsi_signed", "rsi_mag", "rsi_direction",
    "rsd_bucket", "rsi_mag_bucket", "topology_cell", "js_rank_key",
    "neighbor_rank_key", "top_label_rank_key", "js_twice_rank",
    "neighbor_twice_rank", "top_label_twice_rank", "rsd_numerator",
    "rsd_denominator", "rsi_split_key", "rsd_at_median", "rsi_at_median",
    "js_binary64", "rsd_binary64", "rsi_binary64",
]
SEMANTIC_INTS = [
    "js_rank_key", "neighbor_rank_key", "top_label_rank_key", "js_twice_rank",
    "neighbor_twice_rank", "top_label_twice_rank", "rsd_numerator",
    "rsd_denominator", "rsi_split_key", "rsd_at_median", "rsi_at_median",
]
SEMANTIC_FIELDS = ["dataset", "item_id", "profile_id", *SEMANTIC_INTS,
                   "rsi_direction", "rsd_bucket", "rsi_mag_bucket", "topology_cell"]


def item_order(value: str) -> tuple[int, int, str]:
    return (0, int(value), value) if re.fullmatch(r"0|[1-9][0-9]*", value) else (1, 0, value)


def numeric_key(value: float) -> int:
    if not math.isfinite(value):
        raise ValueError("numeric key requires a finite value")
    return int(Decimal(str(value)).quantize(QUANTUM, rounding=ROUND_HALF_EVEN) * SCALE)


def count_rows(path: Path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if (not reader.fieldnames or not REQUIRED.issubset(reader.fieldnames)
                or len(reader.fieldnames) != len(set(reader.fieldnames))):
            raise ValueError(f"input must contain unique columns including {sorted(REQUIRED)}")
        for row in reader:
            if None in row or any(row.get(field) is None for field in REQUIRED):
                raise ValueError("input row width does not match its header")
            role = row["role"].strip().lower()
            if role not in ROLES:
                raise ValueError(f"unsupported role: {row['role']}")
            count = float(row["count"])
            if not math.isfinite(count) or count < 0:
                raise ValueError("count must be finite and non-negative")
            if not all(row[field] for field in ("dataset", "item_id", "label")):
                raise ValueError("dataset, item_id and label must be nonempty")
            yield row["dataset"], row["item_id"], role, row["label"], count


def finite_sum(values) -> float:
    try:
        value = math.fsum(sorted(values))
    except OverflowError as exc:
        raise ValueError("aggregate support must be finite") from exc
    if not math.isfinite(value):
        raise ValueError("aggregate support must be finite")
    return value


def read_counts(path: Path, dataset_names: set[str] | None = None):
    seen: dict[tuple[str, str], int] = {}
    for dataset, item, role, _, count in count_rows(path):
        if dataset_names is not None:
            dataset_names.add(dataset)
        if count:
            key = dataset, item
            seen[key] = seen.get(key, 0) | (1 if role == "search" else 2)
    common = {key for key, roles in seen.items() if roles == 3}
    del seen
    parts = {key: {"search": defaultdict(list), "rec": defaultdict(list)} for key in common}
    for dataset, item, role, label, count in count_rows(path):
        if count and (dataset, item) in common:
            parts[(dataset, item)][role][label].append(count)
    grouped = {}
    for key, roles in parts.items():
        grouped[key] = {}
        for role, labels in roles.items():
            totals = {label: finite_sum(labels[label]) for label in sorted(labels)}
            finite_sum(totals.values())
            grouped[key][role] = totals
    return grouped


def distribution(counts):
    total = math.fsum(counts[label] for label in sorted(counts))
    return {label: counts[label] / total for label in sorted(counts)} if total else {}


def entropy(probabilities):
    return -math.fsum(probabilities[label] * math.log2(probabilities[label])
                      for label in sorted(probabilities) if probabilities[label] > 0)


def js_divergence(left, right):
    if left == right:
        return 0.0
    if set(left).isdisjoint(right):
        return 1.0
    terms = []
    for label in sorted(set(left) | set(right)):
        p, q = left.get(label, 0.0), right.get(label, 0.0)
        total = p + q
        if p:
            terms.append(0.5 * p * math.log2(2.0 * p / total))
        if q:
            terms.append(0.5 * q * math.log2(2.0 * q / total))
    return min(1.0, max(0.0, math.fsum(terms)))


def top_labels(counts, limit=3):
    return [label for label, _ in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:limit]]


def twice_average_ranks(rows, key_field):
    order = sorted(range(len(rows)), key=lambda idx: -rows[idx][key_field])
    ranks = [0] * len(rows)
    start = 0
    while start < len(order):
        end = start + 1
        key = rows[order[start]][key_field]
        while end < len(order) and rows[order[end]][key_field] == key:
            end += 1
        twice_rank = start + 1 + end
        for position in range(start, end):
            ranks[order[position]] = twice_rank
        start = end
    return ranks


def median(values):
    ordered = sorted(values)
    n = len(ordered)
    if not n:
        return None
    return Fraction(ordered[n // 2]) if n % 2 else (Fraction(ordered[n // 2 - 1]) + Fraction(ordered[n // 2])) / 2


def rsd_value(row):
    return Fraction(row["rsd_numerator"], row["rsd_denominator"])


def build(grouped):
    by_dataset = defaultdict(list)
    for (dataset, item_id), role_counts in sorted(grouped.items(), key=lambda pair: (pair[0][0], item_order(pair[0][1]))):
        search, rec = distribution(role_counts["search"]), distribution(role_counts["rec"])
        search_top, rec_top = top_labels(role_counts["search"]), top_labels(role_counts["rec"])
        union = set(search_top) | set(rec_top)
        search_entropy, rec_entropy = entropy(search), entropy(rec)
        rsi = (rec_entropy - search_entropy) / max(search_entropy, rec_entropy, 1e-12)
        row = {
            "dataset": dataset, "item_id": item_id, "profile_id": PROFILE_ID,
            "search_support": math.fsum(role_counts["search"][label] for label in sorted(role_counts["search"])),
            "rec_support": math.fsum(role_counts["rec"][label] for label in sorted(role_counts["rec"])),
            "search_entropy": search_entropy, "rec_entropy": rec_entropy,
            "js_divergence": js_divergence(search, rec),
            "neighbor_disagreement": 1.0 - len(set(search_top) & set(rec_top)) / len(union),
            "top_label_mismatch": float(search_top[0] != rec_top[0]),
            "rsi_signed": rsi, "rsi_mag": abs(rsi), "rsi_split_key": numeric_key(abs(rsi)),
            "rsi_direction": "rec_broader" if rsi > 0.05 else "search_broader" if rsi < -0.05 else "balanced",
        }
        for metric, key_field, _ in COMPONENTS:
            row[key_field] = numeric_key(row[metric])
        by_dataset[dataset].append(row)

    output = []
    for _, rows in sorted(by_dataset.items()):
        for _, key_field, rank_field in COMPONENTS:
            for row, rank in zip(rows, twice_average_ranks(rows, key_field)):
                row[rank_field] = rank
        for row in rows:
            score = sum((Fraction(2, 120 + row[rank_field]) for _, _, rank_field in COMPONENTS), Fraction())
            row["rsd_numerator"], row["rsd_denominator"] = score.numerator, score.denominator
            row["rsd_score"] = float(score)
        rsd_median = median([rsd_value(row) for row in rows])
        rsi_median = median([row["rsi_split_key"] for row in rows])
        for row in rows:
            score, rsi_key = rsd_value(row), row["rsi_split_key"]
            row["rsd_bucket"] = "high_rsd" if score > rsd_median else "low_rsd"
            row["rsi_mag_bucket"] = "high_rsi" if rsi_key > rsi_median else "low_rsi"
            row["rsd_at_median"], row["rsi_at_median"] = int(score == rsd_median), int(rsi_key == rsi_median)
            row["topology_cell"] = f"{row['rsd_bucket']}|{row['rsi_mag_bucket']}"
            for metric, field in (("js_divergence", "js_binary64"), ("rsd_score", "rsd_binary64"), ("rsi_signed", "rsi_binary64")):
                row[field] = row[metric].hex()
            output.append(row)
    return output


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: f"{value:.12g}" if isinstance(value, float) else value for key, value in row.items()})


def fraction_record(value):
    return None if value is None else {"numerator": value.numerator, "denominator": value.denominator}


def diagnostics(rows, dataset_names):
    result, cells, occupied = {}, {}, {}
    for dataset in sorted(dataset_names):
        selected = [row for row in rows if row["dataset"] == dataset]
        result[dataset] = {}
        for field, getter in (("rsd_score", rsd_value), ("rsi_mag", lambda row: row["rsi_split_key"])):
            values = [getter(row) for row in selected]
            middle = median(values)
            below = sum(value < middle for value in values)
            equal = sum(value == middle for value in values)
            above = sum(value > middle for value in values)
            zeros = sum(row[field] == 0 for row in selected)
            result[dataset][field] = {
                "comparison": "exact_rrf_fraction" if field == "rsd_score" else "q12_integer_units",
                "median": fraction_record(middle), "items": len(selected),
                "below_median_items": below, "at_median_items": equal, "above_median_items": above,
                "median_tie_items": equal, "low_items": below + equal, "high_items": above,
                "unique_decision_values": len(set(values)), "raw_zero_items": zeros,
                "decision_zero_items": sum(value == 0 for value in values),
                "key_zero_items": sum(value == 0 for value in values),
                "empty_high": above == 0, "degenerate_axis": len(set(values)) <= 1,
                "status": "pass" if selected else "no_common_support",
            }
        occupied[dataset] = []
        for rsd in ("low_rsd", "high_rsd"):
            for rsi in ("low_rsi", "high_rsi"):
                cell = f"{rsd}|{rsi}"
                count = sum(row["topology_cell"] == cell for row in selected)
                cells[f"{dataset}::{cell}"] = count
                if count:
                    occupied[dataset].append(cell)
    return result, dict(sorted(cells.items())), occupied


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def semantic_hash(rows):
    digest = hashlib.sha256()
    for row in rows:
        payload = {field: row[field] for field in SEMANTIC_FIELDS}
        digest.update((json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
    return digest.hexdigest()


def runtime_record():
    return {
        "python": sys.version, "implementation": platform.python_implementation(),
        "python_build": list(platform.python_build()), "python_compiler": platform.python_compiler(),
        "platform": platform.platform(), "system": platform.system(), "release": platform.release(),
        "os_version": platform.version(), "machine": platform.machine(), "libc": list(platform.libc_ver()),
        "math_extension_sha256": sha256(Path(math.__file__)) if getattr(math, "__file__", None) else None,
        "math_backend_scope": "CPython math extension and host libm; no universal cross-platform equivalence claim",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role-counts", type=Path, required=True)
    parser.add_argument("--out-csv", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    args = parser.parse_args()
    if args.out_csv.resolve() == args.out_json.resolve() or args.out_csv.exists() or args.out_json.exists():
        parser.error("outputs must use distinct fresh paths")
    try:
        dataset_names = set()
        rows = build(read_counts(args.role_counts, dataset_names))
        axis_diagnostics, cells, occupied = diagnostics(rows, dataset_names)
        write_csv(args.out_csv, rows)
        payload = {
            "schema": "sr_sid_rolemap.role_topology_summary.v2", "profile_id": PROFILE_ID,
            "profile_contract_sha256": PROFILE_CONTRACT_SHA256,
            "status": "pass" if rows else "no_common_support",
            "input": {"name": args.role_counts.name, "bytes": args.role_counts.stat().st_size, "sha256": sha256(args.role_counts)},
            "builder_sha256": sha256(Path(__file__)), "output_csv_sha256": sha256(args.out_csv),
            "semantic_key_rank_partition_sha256": semantic_hash(rows),
            "semantic_hash_encoding": "canonical output-order JSON lines; UTF-8; ensure_ascii=false; sorted keys; compact separators; LF",
            "semantic_hash_fields": SEMANTIC_FIELDS, "semantic_hash_integer_fields": SEMANTIC_INTS,
            "runtime": runtime_record(), "items": len(rows),
            "datasets": len({row["dataset"] for row in rows}), "input_datasets": len(dataset_names),
            "dataset_common_items": {dataset: sum(row["dataset"] == dataset for row in rows) for dataset in sorted(dataset_names)},
            "cell_counts": cells, "occupied_cells": occupied,
            "occupied_cell_counts": {dataset: len(values) for dataset, values in occupied.items()},
            "median_diagnostics": axis_diagnostics,
            "empty_high_axes": {dataset: [axis for axis, info in values.items() if info["empty_high"]] for dataset, values in axis_diagnostics.items()},
            "parameters": {
                "rrf_k": 60, "rsi_denominator_floor": 1e-12, "rsi_direction_epsilon": 0.05,
                "rsi_direction_comparison": "raw binary64 signed RSI; strictly > epsilon / < -epsilon; otherwise balanced",
                "rank_quantum": "0.000000000001", "rounding": "decimal half-even of shortest float string",
                "rank_ties": "average one-based ranks stored as twice-rank integers",
                "rsd_comparison": "exact sum of Fraction(2,120+twice_rank); no second quantization",
                "rsi_comparison": "Q12(abs(raw RSI)) integer units",
                "median": "ordinary exact median; arithmetic mean of central values for even n",
                "binning": "H iff value > median; L iff value <= median; all ties stay together",
                "item_order": "canonical ASCII integers numerically, then opaque IDs by Unicode string",
                "raw_float_csv_format": ".12g display only; exact decision fields and binary64 hex preserved",
                "q12_scope": "engineering equivalence relation, not a calibrated error bound or tunable parameter",
            },
        }
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        with args.out_json.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    except (ValueError, OverflowError, OSError, csv.Error) as exc:
        parser.error(str(exc))
    print("PASS_ROLE_TOPOLOGY_BUILDER" if rows else "NO_COMMON_ROLE_SUPPORT")


if __name__ == "__main__":
    main()
