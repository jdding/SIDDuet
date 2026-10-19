#!/usr/bin/env python3
"""Partition a frozen request census using a declared shared time interval."""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import time

import extract_exposures as original
from shared_window import collision_items


def split_for(row, start, end):
    if row["timestamp_end"] < start:
        return "train"
    if row["timestamp_start"] >= start and row["timestamp_end"] < end:
        return original.validation_partition(row["user_hash"])
    return None


def export(args):
    begun = time.monotonic()
    if args.out.exists():
        raise ValueError("Output directory must be new")
    coverage = json.loads(args.coverage.read_text())
    original.check_hash(args.cache, coverage["cache_sha256"])
    original.check_hash(args.primary_map, coverage["primary_map_sha256"])
    config = json.loads(args.window.read_text())
    start, end = config["start"], config["end"]
    if not start < end or start < original.TEST_START:
        raise ValueError("Need a nonempty interval after the original audit")
    primary = collision_items(args.primary_map)
    args.out.mkdir(parents=True)
    args.out.chmod(0o700)
    counts = defaultdict(Counter)
    users = defaultdict(set)
    ranges = {}
    excluded = Counter()
    output = {split: args.out / (split + ".jsonl") for split in ("train", "validation", "audit")}
    handles = {split: path.open("x") for split, path in output.items()}
    seen = set()
    try:
        with args.cache.open() as handle:
            for line in handle:
                row = json.loads(line)
                if row["request_hash"] in seen:
                    raise ValueError("Duplicate request in census")
                seen.add(row["request_hash"])
                split = split_for(row, start, end)
                if split is None:
                    excluded["outside_or_crossing_interval"] += 1
                    continue
                row["split"] = split
                row["source_chronological_split"] = "train" if split == "train" else "shared_window"
                role = row["role"]
                key = split + "|" + role
                counts[key]["requests"] += 1
                counts[key]["cohort_exposed_requests"] += bool(row["exposed_item_ids"])
                counts[key]["primary_collision_requests"] += bool(
                    set(row["exposed_item_ids"]) & primary
                )
                counts[key]["provider_" + row["provider_split"]] += 1
                users[key].add(row["user_hash"])
                original.update_range(ranges, key, row["timestamp_start"], row["timestamp_end"])
                handles[split].write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    finally:
        for handle in handles.values():
            handle.close()
    if any(
        not counts[split + "|" + role]["primary_collision_requests"]
        for split in output
        for role in original.ROLES
    ):
        raise ValueError("A split/task has no primary collision exposure; inspect coverage")
    if (users["validation|search"] | users["validation|recommendation"]) & (
        users["audit|search"] | users["audit|recommendation"]
    ):
        raise ValueError("Tuning/audit user overlap")
    if max(ranges["train|" + role]["max_end"] for role in original.ROLES) >= min(
        ranges[split + "|" + role]["min_start"]
        for role in original.ROLES
        for split in ("validation", "audit")
    ):
        raise ValueError("Training is not earlier")
    original.check_hash(args.cache, coverage["cache_sha256"])
    receipt = dict(
        schema="rolemap.shared_window_extraction.v1",
        status="COMPLETE_EXTRACTION_NO_FIT",
        window=config,
        cache_sha256=coverage["cache_sha256"],
        coverage_sha256=original.sha(args.coverage),
        protocol_sha256=original.sha(args.protocol),
        window_config_sha256=original.sha(args.window),
        code_sha256=original.sha(__file__),
        original_parser_sha256=original.sha(Path(original.__file__)),
        counts={k: dict(v) for k, v in counts.items()},
        unique_users={k: len(v) for k, v in users.items()},
        output_timestamp_ranges=ranges,
        excluded=dict(excluded),
        outputs={
            split: dict(sha256=original.sha(path), bytes=path.stat().st_size)
            for split, path in output.items()
        },
        user_partition="Original SHA256('rolemap-allocation-val-v1|' + user_hash), joint across tasks",
        wall_seconds=time.monotonic() - begun,
    )
    (args.out / "EXTRACTION_RECEIPT.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({k: receipt[k] for k in ["status", "counts", "unique_users", "wall_seconds"]}))


def self_test():
    row = dict(timestamp_start=9, timestamp_end=9, user_hash="fixed")
    assert split_for(row, 10, 20) == "train"
    row.update(timestamp_start=9, timestamp_end=10)
    assert split_for(row, 10, 20) is None
    row.update(timestamp_start=10, timestamp_end=10)
    assert split_for(row, 10, 20) == original.validation_partition("fixed")
    row.update(timestamp_start=19, timestamp_end=20)
    assert split_for(row, 10, 20) is None
    print("PASS_SHARED_WINDOW_BOUNDARY_CHECKS")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--self-test", action="store_true")
    for name in ("cache", "coverage", "window", "protocol", "primary-map", "out"):
        p.add_argument("--" + name, type=Path)
    args = p.parse_args()
    if args.self_test:
        self_test()
    elif not all(
        [args.cache, args.coverage, args.window, args.protocol, args.primary_map, args.out]
    ):
        p.error("All input paths and a new --out are required")
    else:
        export(args)


if __name__ == "__main__":
    main()
