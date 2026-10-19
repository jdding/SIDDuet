#!/usr/bin/env python3
"""Validate the public method-admission registry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


LEVELS = {"literature_only", "interface_specified", "adapter_verified", "rolemap_executed"}
PARADIGMS = {"generative", "discriminative", "hybrid"}
SURFACES = {
    "fixed_candidate_ranking",
    "full_catalog_prefix_survival",
    "full_catalog_complete_sid_recovery",
}
REQUIRED = {
    "method_id",
    "title",
    "year",
    "paradigm",
    "sid_use",
    "code_status",
    "data_status",
    "admission_level",
    "supported_surfaces",
    "source_url",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.registry.read_text(encoding="utf-8"))
    if payload.get("schema") != "sr_sid_rolemap.method_admission_registry.v2":
        raise ValueError("unexpected method registry schema")
    methods = payload.get("methods")
    if not isinstance(methods, list) or not methods:
        raise ValueError("method registry is empty")
    ids: set[str] = set()
    paradigms: set[str] = set()
    for row in methods:
        missing = REQUIRED - set(row)
        if missing:
            raise ValueError(f"method row missing fields: {sorted(missing)}")
        method_id = str(row["method_id"])
        if method_id in ids:
            raise ValueError(f"duplicate method_id: {method_id}")
        ids.add(method_id)
        paradigm = str(row["paradigm"])
        if paradigm not in PARADIGMS:
            raise ValueError(f"invalid paradigm for {method_id}: {paradigm}")
        paradigms.add(paradigm)
        if row["admission_level"] not in LEVELS:
            raise ValueError(f"invalid admission level for {method_id}")
        surfaces = set(row["supported_surfaces"])
        if not surfaces or not surfaces <= SURFACES:
            raise ValueError(f"invalid supported surfaces for {method_id}")
    if not {"generative", "discriminative"} <= paradigms:
        raise ValueError("registry must cover generative and discriminative paradigms")
    partitions = payload.get("scope_partitions")
    if not isinstance(partitions, dict):
        raise ValueError("scope_partitions must be an object")
    required_partitions = {
        "core_reference",
        "core_external",
        "priority_protocol",
        "shared_sid_literature_boundary",
        "adjacent_non_sid",
    }
    if set(partitions) != required_partitions:
        raise ValueError("unexpected scope_partitions")
    partitioned = [str(method_id) for values in partitions.values() for method_id in values]
    if len(partitioned) != len(set(partitioned)) or set(partitioned) != ids:
        raise ValueError("scope_partitions must cover every method exactly once")
    forbidden_core_sid_use = {
        "shared_atomic_item_identity",
        "joint_atomic_item_identifiers",
        "single_atomic_item_token",
        "candidate_conditioned_yes_no",
    }
    rows_by_id = {str(row["method_id"]): row for row in methods}
    for method_id in partitions["core_reference"] + partitions["core_external"]:
        if rows_by_id[method_id]["sid_use"] in forbidden_core_sid_use:
            raise ValueError(f"non-SID method admitted to core: {method_id}")
    print("PASS_METHOD_ADMISSION_REGISTRY")


if __name__ == "__main__":
    main()
