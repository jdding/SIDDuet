#!/usr/bin/env python3
"""Evaluate role-support ranking inside SID collision groups and aggregate it."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
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


def aggregate(units: list[dict[str, object]], field: str | None) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in units:
        value = "all" if field is None else str(row[field])
        grouped[(str(row["dataset"]), str(row["role"]), value)].append(row)
    output: list[dict[str, object]] = []
    for (dataset, role, value), rows in sorted(grouped.items()):
        output.append({
            "dataset": dataset,
            "role": role,
            "slice_type": "all" if field is None else field,
            "slice_value": value,
            "units": len(rows),
            "ndcg10": round(sum(float(row["ndcg10"]) for row in rows) / len(rows), 6),
            "mean_group_size": round(sum(int(row["group_size"]) for row in rows) / len(rows), 6),
        })
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topology", type=Path, required=True)
    parser.add_argument("--sid-map", type=Path, required=True)
    parser.add_argument("--out-csv", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    args = parser.parse_args()

    topology, topology_sha256 = read_topology(args.topology)
    sid_lookup = {(row["dataset"], row["item_id"]): row["sid"] for row in read_csv(args.sid_map)}
    joined = [dict(row, sid=sid_lookup[(row["dataset"], row["item_id"])]) for row in topology if (row["dataset"], row["item_id"]) in sid_lookup]
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in joined:
        groups[(row["dataset"], row["sid"])].append(row)

    units: list[dict[str, object]] = []
    for (dataset, _), group in sorted(groups.items()):
        if len(group) < 2:
            continue
        for role in ["search", "rec"]:
            support = f"{role}_support"
            ranked = sorted(group, key=lambda row: (-float(row[support]), row["item_id"]))
            positions = {row["item_id"]: position for position, row in enumerate(ranked, start=1)}
            for row in group:
                position = positions[row["item_id"]]
                units.append({
                    "dataset": dataset,
                    "role": role,
                    "topology_cell": row["topology_cell"],
                    "rsd_bucket": row["rsd_bucket"],
                    "rsi_mag_bucket": row["rsi_mag_bucket"],
                    "group_size": len(group),
                    "ndcg10": 1.0 / math.log2(position + 1) if position <= 10 else 0.0,
                })
    if not units:
        raise ValueError("no SID collision groups with at least two items")
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
        "schema": "sr_sid_rolemap.collision_diagnostic.v1",
        "status": "pass",
        "topology_profile_id": TOPOLOGY_PROFILE_ID,
        "topology_sha256": topology_sha256,
        "joined_items": len(joined),
        "collision_groups": sum(len(group) >= 2 for group in groups.values()),
        "evaluation_units": len(units),
        "aggregates": rows,
        "release_boundary": "aggregate metrics only; target ranks and item-level joins are not emitted",
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("PASS_COLLISION_DIAGNOSTIC")


if __name__ == "__main__":
    main()
