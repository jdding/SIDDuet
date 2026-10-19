#!/usr/bin/env python3
"""Build public-safe topology and report-card summaries from inspection samples."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def sid_field(rows: list[dict[str, str]]) -> str:
    if rows and "hashed_sid" in rows[0]:
        return "hashed_sid"
    return "synthetic_sid"


def item_field(rows: list[dict[str, str]]) -> str:
    if rows and "hashed_item_id" in rows[0]:
        return "hashed_item_id"
    return "synthetic_item_id"


def summarize(rows: list[dict[str, str]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if not rows:
        return [], []
    sid_col = sid_field(rows)
    item_col = item_field(rows)
    by_dataset: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_dataset[row["dataset"]].append(row)

    report_cards: list[dict[str, object]] = []
    topology_rows: list[dict[str, object]] = []
    for dataset, group in sorted(by_dataset.items()):
        sid_counts = Counter(row[sid_col] for row in group)
        collided_items = sum(1 for row in group if sid_counts[row[sid_col]] > 1)
        topology_counts = Counter(row["topology_cell"] for row in group)
        report_cards.append(
            {
                "dataset": dataset,
                "items": len({row[item_col] for row in group}),
                "unique_sid_count": len(sid_counts),
                "collision_rate": round(collided_items / max(len(group), 1), 6),
                "topology_cells": len(topology_counts),
                "sample_type": group[0].get("sample_type", "unknown"),
            }
        )
        for cell, count in sorted(topology_counts.items()):
            cell_rows = [row for row in group if row["topology_cell"] == cell]
            cell_sid_counts = Counter(row[sid_col] for row in cell_rows)
            cell_collided = sum(1 for row in cell_rows if cell_sid_counts[row[sid_col]] > 1)
            topology_rows.append(
                {
                    "dataset": dataset,
                    "topology_cell": cell,
                    "items": count,
                    "unique_sid_count": len(cell_sid_counts),
                    "collision_rate": round(cell_collided / max(count, 1), 6),
                    "rsd_bucket": cell_rows[0].get("rsd_bucket", ""),
                    "rsi_mag_bucket": cell_rows[0].get("rsi_mag_bucket", ""),
                    "sample_type": cell_rows[0].get("sample_type", "unknown"),
                }
            )
    return report_cards, topology_rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--out-csv", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    args = parser.parse_args()

    rows = read_rows(args.sample)
    report_cards, topology_rows = summarize(rows)
    write_csv(args.out_csv, topology_rows)
    package_root = Path(__file__).resolve().parents[1]
    try:
        sample_path = args.sample.resolve().relative_to(package_root).as_posix()
    except ValueError:
        sample_path = args.sample.name
    payload = {
        "status": "pass",
        "sample": sample_path,
        "report_cards": report_cards,
        "topology_rows": topology_rows,
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("PASS_PUBLIC_SUMMARY_BUILDER")
    print(f"wrote {args.out_csv}")
    print(f"wrote {args.out_json}")


if __name__ == "__main__":
    main()
