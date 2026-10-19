#!/usr/bin/env python3
"""Join a SID family to a RoleMap topology and emit aggregate admission metrics."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
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


def unique_map(rows: list[dict[str, str]], value: str) -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    for row in rows:
        key = (row["dataset"], row["item_id"])
        if key in result:
            raise ValueError(f"duplicate item row: {key}")
        result[key] = row[value]
    return result


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topology", type=Path, required=True)
    parser.add_argument("--sid-map", type=Path, required=True)
    parser.add_argument("--family", required=True)
    parser.add_argument("--out-csv", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    args = parser.parse_args()

    topology_rows, topology_sha256 = read_topology(args.topology)
    sid_lookup = unique_map(read_csv(args.sid_map), "sid")
    joined = [dict(row, sid=sid_lookup[(row["dataset"], row["item_id"])]) for row in topology_rows if (row["dataset"], row["item_id"]) in sid_lookup]
    if not joined:
        raise ValueError("SID map has no overlap with topology")

    cell_rows: list[dict[str, object]] = []
    dataset_summaries: list[dict[str, object]] = []
    for dataset in sorted({row["dataset"] for row in topology_rows}):
        universe = [row for row in topology_rows if row["dataset"] == dataset]
        group = [row for row in joined if row["dataset"] == dataset]
        sids = {row["sid"] for row in group}
        sid_cells: dict[str, set[str]] = defaultdict(set)
        for row in group:
            sid_cells[row["sid"]].add(row["topology_cell"])
        rates: list[float] = []
        for cell in sorted({row["topology_cell"] for row in group}):
            subset = [row for row in group if row["topology_cell"] == cell]
            unique = len({row["sid"] for row in subset})
            rate = 1.0 - unique / len(subset)
            rates.append(rate)
            cell_rows.append({
                "dataset": dataset,
                "family": args.family,
                "topology_profile_id": TOPOLOGY_PROFILE_ID,
                "topology_sha256": topology_sha256,
                "topology_cell": cell,
                "items": len(subset),
                "unique_sid_count": unique,
                "unique_sid_ratio": round(unique / len(subset), 6),
                "collision_rate": round(rate, 6),
            })
        dataset_summaries.append({
            "dataset": dataset,
            "family": args.family,
            "topology_profile_id": TOPOLOGY_PROFILE_ID,
            "topology_sha256": topology_sha256,
            "topology_items": len(universe),
            "joined_items": len(group),
            "join_coverage": round(len(group) / len(universe), 6) if universe else 0.0,
            "unique_sid_count": len(sids),
            "unique_sid_ratio": round(len(sids) / len(group), 6) if group else None,
            "collision_rate": round(1.0 - len(sids) / len(group), 6) if group else None,
            "cell_collision_rate_spread": round(max(rates) - min(rates), 6) if rates else None,
            "mixed_cell_sid_count": sum(len(cells) > 1 for cells in sid_cells.values()),
            "max_topology_cells_per_sid": max((len(cells) for cells in sid_cells.values()), default=0),
        })

    write_csv(args.out_csv, cell_rows)
    payload = {
        "schema": "sr_sid_rolemap.sid_family_admission.v1",
        "status": "pass",
        "family": args.family,
        "topology_profile_id": TOPOLOGY_PROFILE_ID,
        "topology_sha256": topology_sha256,
        "dataset_summaries": dataset_summaries,
        "release_boundary": "aggregate outputs only; full SID maps and item-level topology joins remain local",
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("PASS_SID_FAMILY_ADMISSION")


if __name__ == "__main__":
    main()
