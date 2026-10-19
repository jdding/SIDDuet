#!/usr/bin/env python3
"""Bind method candidate scores to the target item's RoleMap topology."""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
from collections import defaultdict
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


TOPOLOGY_PROFILE_ID = "sr_sid_rolemap.topology.value_median.v2"


def read_topology(path: Path) -> tuple[list[dict[str, str]], str]:
    rows = read_csv(path)
    if not rows:
        raise ValueError("topology input is empty")
    keys: set[tuple[str, str]] = set()
    for row in rows:
        if row.get("profile_id") != TOPOLOGY_PROFILE_ID:
            raise ValueError(f"topology profile_id must be {TOPOLOGY_PROFILE_ID} on every row")
        key = (row["dataset"], row["item_id"])
        if key in keys:
            raise ValueError(f"duplicate topology item: {key}")
        keys.add(key)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return rows, digest.hexdigest()


def is_true(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--topology", type=Path, required=True)
    parser.add_argument("--method-id", required=True)
    parser.add_argument(
        "--method-paradigm",
        choices=("generative", "discriminative", "hybrid"),
        required=True,
    )
    parser.add_argument(
        "--score-direction",
        choices=("higher_is_better", "lower_is_better"),
        required=True,
    )
    parser.add_argument("--out-csv", type=Path, required=True)
    args = parser.parse_args()

    scores = read_csv(args.scores)
    topology, topology_sha256 = read_topology(args.topology)
    score_fields = {"dataset", "unit_id", "role", "candidate_id", "is_target", "score"}
    topology_fields = {"dataset", "item_id", "topology_cell", "rsd_bucket", "rsi_mag_bucket"}
    if not scores:
        raise ValueError("score input is empty")
    missing_scores = score_fields - set(scores[0])
    missing_topology = topology_fields - set(topology[0])
    if missing_scores:
        raise ValueError(f"score input missing fields: {sorted(missing_scores)}")
    if missing_topology:
        raise ValueError(f"topology input missing fields: {sorted(missing_topology)}")

    topology_by_item: dict[tuple[str, str], dict[str, str]] = {}
    for row in topology:
        key = (row["dataset"], row["item_id"])
        topology_by_item[key] = row

    units: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in scores:
        units[(row["dataset"], row["unit_id"], row["role"])].append(row)

    output: list[dict[str, str]] = []
    for key, rows in sorted(units.items()):
        if len({row["candidate_id"] for row in rows}) != len(rows):
            raise ValueError(f"duplicate candidate_id in evaluation unit: {key}")
        targets = [row for row in rows if is_true(row["is_target"])]
        if len(targets) != 1:
            raise ValueError(f"each unit must contain exactly one target: {key}")
        target = targets[0]
        target_topology = topology_by_item.get((target["dataset"], target["candidate_id"]))
        if target_topology is None:
            raise ValueError(
                "target item is absent from topology: "
                f"dataset={target['dataset']} item_id={target['candidate_id']}"
            )
        for row in rows:
            if not math.isfinite(float(row["score"])):
                raise ValueError("scores must be finite")
            output.append({
                "method_id": args.method_id,
                "method_paradigm": args.method_paradigm,
                "score_direction": args.score_direction,
                "topology_profile_id": TOPOLOGY_PROFILE_ID,
                "topology_sha256": topology_sha256,
                "dataset": row["dataset"],
                "unit_id": row["unit_id"],
                "role": row["role"],
                "candidate_id": row["candidate_id"],
                "is_target": row["is_target"],
                "score": row["score"],
                "topology_cell": target_topology["topology_cell"],
                "rsd_bucket": target_topology["rsd_bucket"],
                "rsi_mag_bucket": target_topology["rsi_mag_bucket"],
            })

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output[0]))
        writer.writeheader()
        writer.writerows(output)
    print("PASS_METHOD_SCORE_ADAPTER")


if __name__ == "__main__":
    main()
