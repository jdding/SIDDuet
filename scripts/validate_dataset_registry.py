#!/usr/bin/env python3
"""Validate the public dataset-admission registry and Table 2 boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


LEVELS = {
    "registered_main",
    "priority_candidate",
    "method_carrier_only",
    "derived_role_extension",
    "literature_only",
}
REQUIRED = {
    "dataset_id",
    "title",
    "role_evidence",
    "access_status",
    "admission_level",
    "topology_status",
    "common_items",
    "source_url",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.registry.read_text(encoding="utf-8"))
    if payload.get("schema") != "sr_sid_rolemap.dataset_admission_registry.v1":
        raise ValueError("unexpected dataset registry schema")
    if set(payload.get("levels", [])) != LEVELS:
        raise ValueError("dataset admission levels are incomplete")
    rows = payload.get("datasets", [])
    if not rows:
        raise ValueError("dataset registry is empty")
    ids: set[str] = set()
    registered: set[str] = set()
    for row in rows:
        missing = REQUIRED - set(row)
        if missing:
            raise ValueError(f"dataset row missing fields: {sorted(missing)}")
        dataset_id = row["dataset_id"]
        if dataset_id in ids:
            raise ValueError(f"duplicate dataset_id: {dataset_id}")
        ids.add(dataset_id)
        if row["admission_level"] not in LEVELS:
            raise ValueError(f"invalid admission_level: {row['admission_level']}")
        if not str(row["source_url"]).startswith("https://"):
            raise ValueError(f"dataset source must be an HTTPS URL: {dataset_id}")
        if row["admission_level"] == "registered_main":
            registered.add(dataset_id)
            if row["topology_status"] != "materialized":
                raise ValueError(f"registered dataset lacks materialized topology: {dataset_id}")
            if not isinstance(row["common_items"], int) or row["common_items"] <= 0:
                raise ValueError(f"registered dataset lacks positive common_items: {dataset_id}")
        elif row["topology_status"] == "materialized":
            raise ValueError(f"non-registered dataset claims materialized topology: {dataset_id}")
    if registered != {"kuaisar", "qilin"}:
        raise ValueError(f"unexpected Table 2 dataset set: {sorted(registered)}")
    print("PASS_DATASET_ADMISSION_REGISTRY")


if __name__ == "__main__":
    main()
