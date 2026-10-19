#!/usr/bin/env python3
"""Evaluate a pre-scored fixed-candidate ranking interface and aggregate NDCG@10."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path


TOPOLOGY_PROFILE_ID = "sr_sid_rolemap.topology.value_median.v2"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def is_true(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


def aggregate(units: list[dict[str, object]], field: str | None) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in units:
        value = "all" if field is None else str(row[field])
        grouped[
            (
                str(row["method_id"]),
                str(row["method_paradigm"]),
                str(row["dataset"]),
                str(row["role"]),
                value,
            )
        ].append(row)
    output: list[dict[str, object]] = []
    for (method_id, method_paradigm, dataset, role, value), rows in sorted(grouped.items()):
        output.append({
            "method_id": method_id,
            "method_paradigm": method_paradigm,
            "dataset": dataset,
            "role": role,
            "slice_type": "all" if field is None else field,
            "slice_value": value,
            "units": len(rows),
            "ndcg10": round(sum(float(row["ndcg10"]) for row in rows) / len(rows), 6),
            "hit10": round(sum(float(row["hit10"]) for row in rows) / len(rows), 6),
        })
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--out-csv", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    args = parser.parse_args()
    required = {
        "method_id",
        "method_paradigm",
        "score_direction",
        "dataset",
        "unit_id",
        "role",
        "candidate_id",
        "is_target",
        "score",
        "topology_cell",
        "rsd_bucket",
        "rsi_mag_bucket",
        "topology_profile_id",
        "topology_sha256",
    }
    groups: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    candidate_rows = read_csv(args.candidates)
    if not candidate_rows:
        raise ValueError("candidate input is empty")
    missing = required - set(candidate_rows[0])
    if missing:
        raise ValueError(f"candidate input missing fields: {sorted(missing)}")
    if any(row["topology_profile_id"] != TOPOLOGY_PROFILE_ID for row in candidate_rows):
        raise ValueError(f"candidate topology_profile_id must be {TOPOLOGY_PROFILE_ID} on every row")
    topology_hashes = {row["topology_sha256"] for row in candidate_rows}
    if len(topology_hashes) != 1:
        raise ValueError("candidate topology_sha256 must be constant across the input")
    topology_sha256 = next(iter(topology_hashes))
    if len(topology_sha256) != 64 or any(char not in "0123456789abcdef" for char in topology_sha256):
        raise ValueError("candidate topology_sha256 must be a lowercase SHA256")
    for row in candidate_rows:
        if row["method_paradigm"] not in {"generative", "discriminative", "hybrid"}:
            raise ValueError(f"invalid method_paradigm: {row['method_paradigm']}")
        if row["score_direction"] not in {"higher_is_better", "lower_is_better"}:
            raise ValueError(f"invalid score_direction: {row['score_direction']}")
        groups[(row["method_id"], row["dataset"], row["unit_id"], row["role"])].append(row)

    units: list[dict[str, object]] = []
    for (method_id, dataset, _, role), group in sorted(groups.items()):
        if len({row["candidate_id"] for row in group}) != len(group):
            raise ValueError("duplicate candidate_id in evaluation unit")
        if not all(math.isfinite(float(row["score"])) for row in group):
            raise ValueError("scores must be finite")
        targets = [row for row in group if is_true(row["is_target"])]
        if len(targets) != 1:
            raise ValueError("each unit must contain exactly one target")
        paradigms = {row["method_paradigm"] for row in group}
        directions = {row["score_direction"] for row in group}
        if len(paradigms) != 1 or len(directions) != 1:
            raise ValueError("method metadata must be constant within an evaluation unit")
        direction = next(iter(directions))
        target = targets[0]
        target_score = float(target["score"])
        greater = sum((float(row["score"]) > target_score) if direction == "higher_is_better"
                      else (float(row["score"]) < target_score) for row in group)
        tied = sum(float(row["score"]) == target_score for row in group)
        possible_ranks = range(greater + 1, greater + tied + 1)
        ndcg10 = sum(1.0 / math.log2(rank + 1) for rank in possible_ranks if rank <= 10) / tied
        hit10 = sum(rank <= 10 for rank in possible_ranks) / tied
        units.append({
            "method_id": method_id,
            "method_paradigm": next(iter(paradigms)),
            "dataset": dataset,
            "role": role,
            "topology_cell": target["topology_cell"],
            "rsd_bucket": target["rsd_bucket"],
            "rsi_mag_bucket": target["rsi_mag_bucket"],
            "ndcg10": ndcg10,
            "hit10": hit10,
        })
    rows = []
    for field in [None, "topology_cell", "rsd_bucket", "rsi_mag_bucket"]:
        rows.extend(aggregate(units, field))
    for row in rows:
        row["topology_profile_id"] = TOPOLOGY_PROFILE_ID
        row["topology_sha256"] = topology_sha256
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    payload = {
        "schema": "sr_sid_rolemap.fixed_candidate_evaluation.v3",
        "status": "pass",
        "tie_policy": "uniform_within_exact_score_ties",
        "topology_profile_id": TOPOLOGY_PROFILE_ID,
        "topology_sha256": topology_sha256,
        "evaluation_units": len(units),
        "methods": sorted({str(row["method_id"]) for row in units}),
        "paradigms": sorted({str(row["method_paradigm"]) for row in units}),
        "aggregates": rows,
        "boundary": "the script evaluates supplied scores; it does not train or reproduce a serving model",
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("PASS_FIXED_CANDIDATE_EVALUATION")


if __name__ == "__main__":
    main()
