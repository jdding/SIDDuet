#!/usr/bin/env python3
"""Materialize deterministic role-label counts from normalized role events."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


REQUIRED = {"dataset", "role", "event_id", "item_id", "item_label", "engaged"}
ROLES = {"search", "rec"}
TRUE_VALUES = {"1", "true", "yes", "y"}
FALSE_VALUES = {"0", "false", "no", "n"}


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValueError(f"engaged must be one of {sorted(TRUE_VALUES | FALSE_VALUES)}")


def parse_weight(value: str) -> int:
    normalized = value.strip() or "1"
    try:
        weight = int(normalized)
    except ValueError as exc:
        raise ValueError("weight must be a positive integer") from exc
    if weight <= 0:
        raise ValueError("weight must be a positive integer")
    return weight


def read_events(path: Path) -> dict[tuple[str, str, str], list[dict[str, object]]]:
    events: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    event_weights: dict[tuple[str, str, str], int] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not REQUIRED.issubset(reader.fieldnames):
            raise ValueError(f"input must contain {sorted(REQUIRED)}")
        for line_number, row in enumerate(reader, start=2):
            dataset = row["dataset"].strip()
            role = row["role"].strip().lower()
            event_id = row["event_id"].strip()
            item_id = row["item_id"].strip()
            item_label = row["item_label"].strip()
            if not all((dataset, event_id, item_id, item_label)):
                raise ValueError(f"line {line_number}: identifiers and labels must be non-empty")
            if role not in ROLES:
                raise ValueError(f"line {line_number}: unsupported role {row['role']!r}")
            weight = parse_weight(row.get("weight", "1"))
            key = (dataset, role, event_id)
            if key in event_weights and event_weights[key] != weight:
                raise ValueError(f"line {line_number}: weight must be constant within an event")
            event_weights[key] = weight
            events[key].append(
                {
                    "item_id": item_id,
                    "item_label": item_label,
                    "engaged": parse_bool(row["engaged"]),
                    "weight": weight,
                }
            )
    if not events:
        raise ValueError("input contains no events")
    return events


def dominant_label(rows: list[dict[str, object]]) -> tuple[str, str]:
    engaged = Counter(str(row["item_label"]) for row in rows if bool(row["engaged"]))
    source = engaged if engaged else Counter(str(row["item_label"]) for row in rows)
    return min(
        source, key=lambda label: (-source[label], label)
    ), "engaged" if engaged else "exposure"


def materialize(
    events: dict[tuple[str, str, str], list[dict[str, object]]],
) -> tuple[list[dict[str, object]], Counter[str]]:
    counts: Counter[tuple[str, str, str, str]] = Counter()
    label_sources: Counter[str] = Counter()
    for (dataset, role, _event_id), rows in sorted(events.items()):
        role_label, source = dominant_label(rows)
        label_sources[source] += 1
        for row in rows:
            counts[(dataset, str(row["item_id"]), role, role_label)] += int(row["weight"])

    role_order = {"search": 0, "rec": 1}
    ordered = sorted(counts, key=lambda key: (key[0], key[1], role_order[key[2]], key[3]))
    output = [
        {
            "dataset": dataset,
            "item_id": item_id,
            "role": role,
            "label": label,
            "count": counts[(dataset, item_id, role, label)],
        }
        for dataset, item_id, role, label in ordered
    ]
    return output, label_sources


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["dataset", "item_id", "role", "label", "count"], lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--out-csv", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    args = parser.parse_args()

    events = read_events(args.events)
    rows, label_sources = materialize(events)
    write_csv(args.out_csv, rows)
    payload = {
        "schema": "sr_sid_rolemap.role_label_materialization.v1",
        "status": "pass",
        "events": len(events),
        "output_rows": len(rows),
        "datasets": sorted({row["dataset"] for row in rows}),
        "roles": sorted({row["role"] for row in rows}),
        "label_source_events": dict(sorted(label_sources.items())),
        "parameters": {
            "dominant_label": "highest frequency; lexicographically smallest label on ties",
            "fallback": "use all exposed item labels when no row is engaged",
            "event_weight": "positive integer multiplicity, constant within each event",
            "item_assignment": "assign the event role label to every item appearance",
        },
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("PASS_ROLE_LABEL_MATERIALIZER")


if __name__ == "__main__":
    main()
