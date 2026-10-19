#!/usr/bin/env python3
"""Inspect shared request calendars and export a declared chronological window."""

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import resource
import time

import extract_exposures as original

BIN_SECONDS = 1800


def utc(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def normalize(row, role, provider, universe):
    key = "search_idx" if role == "search" else "request_idx"
    column = "search_result_details_with_idx" if role == "search" else "rec_result_details_with_idx"
    tkey = "search_timestamp" if role == "search" else "request_timestamp"
    if any(not original.valid_id(row.get(k)) for k in ("user_idx", "session_idx", key)):
        return None
    details = row.get(column)
    if not isinstance(details, list) or not details:
        return None
    if any(not isinstance(x, dict) or original.timestamp(x.get(tkey)) is None for x in details):
        return None
    times = [original.timestamp(x[tkey]) for x in details]
    items = {
        x.get("note_idx")
        for x in details
        if original.valid_id(x.get("note_idx")) and x["note_idx"] < original.CATALOG_SIZE
    }
    if not items:
        return None
    return dict(
        request_hash=original.stable_hash("qilin-native-request-v1", role, provider, row[key]),
        user_hash=original.stable_hash("p152-user", row["user_idx"]),
        role=role,
        provider_split=provider,
        timestamp_start=min(times),
        timestamp_end=max(times),
        exposed_item_ids=sorted(items & universe),
    )


def collision_items(path):
    groups = defaultdict(list)
    with Path(path).open(newline="") as handle:
        for row in csv.DictReader(handle):
            groups[tuple(json.loads(row["sid"])[:2])].append(int(row["item_id"]))
    return {item for members in groups.values() if len(members) > 1 for item in members}


def calendar(args):
    import pyarrow
    import pyarrow.parquet as pq

    started, cpu = time.monotonic(), time.process_time()
    if args.out.exists() or args.cache.exists():
        raise ValueError("Use new output and restricted-cache paths")
    original.check_hash(args.cohort, original.UNIVERSE_SHA)
    with args.cohort.open(newline="") as handle:
        universe = {int(x["item_id"]) for x in csv.DictReader(handle)}
    primary = collision_items(args.primary_map)
    bins = defaultdict(lambda: Counter())
    users = defaultdict(set)
    audits = {}
    sources = []
    seen = set()
    native = set()
    duplicate_native = 0
    args.cache.parent.mkdir(parents=True, exist_ok=True)
    args.cache.parent.chmod(0o700)
    ranges = {}
    with args.cache.open("x") as output:
        for role in original.ROLES:
            for provider in ("train", "test"):
                source = (
                    args.provider_root / (role + "_" + provider) / "train-00000-of-00001.parquet"
                )
                expected = original.SOURCE_SHA[(role, provider)]
                original.check_hash(source, expected)
                audit = Counter()
                column = (
                    "search_result_details_with_idx"
                    if role == "search"
                    else "rec_result_details_with_idx"
                )
                key = "search_idx" if role == "search" else "request_idx"
                for batch in pq.ParquetFile(source).iter_batches(
                    batch_size=2048, columns=["user_idx", "session_idx", key, column]
                ):
                    for row in batch.to_pylist():
                        audit["source_rows"] += 1
                        record = normalize(row, role, provider, universe)
                        if record is None:
                            audit["invalid_identity_time_or_exposure"] += 1
                            continue
                        if record["request_hash"] in seen:
                            raise ValueError("Duplicate request hash; identifier withheld")
                        seen.add(record["request_hash"])
                        native_key = (role, row[key])
                        duplicate_native += native_key in native
                        native.add(native_key)
                        audit["valid_requests"] += 1
                        original.update_range(
                            ranges,
                            role + "|" + provider,
                            record["timestamp_start"],
                            record["timestamp_end"],
                        )
                        output.write(
                            json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"
                        )
                        start = int(record["timestamp_start"] // BIN_SECONDS) * BIN_SECONDS
                        if record["timestamp_end"] >= start + BIN_SECONDS:
                            audit["crosses_half_hour_bin"] += 1
                            continue
                        bkey = (start, role)
                        bins[bkey]["requests"] += 1
                        bins[bkey]["cohort_requests"] += bool(record["exposed_item_ids"])
                        covered = bool(set(record["exposed_item_ids"]) & primary)
                        bins[bkey]["primary_collision_requests"] += covered
                        partition = original.validation_partition(record["user_hash"])
                        bins[bkey][partition + "_primary_requests"] += covered
                        users[bkey].add(record["user_hash"])
                original.check_hash(source, expected)
                audits[role + "|" + provider] = dict(audit)
                sources.append(
                    dict(role=role, provider=provider, sha256=expected, rows=audit["source_rows"])
                )
    starts = sorted({start for start, _ in bins})
    rows = []
    for start in starts:
        row = dict(
            start=start,
            end=start + BIN_SECONDS,
            utc_start=utc(start),
            utc_end=utc(start + BIN_SECONDS),
        )
        for role in original.ROLES:
            counts = bins[(start, role)]
            row.update(
                {
                    role + "_" + k: counts[k]
                    for k in [
                        "requests",
                        "cohort_requests",
                        "primary_collision_requests",
                        "validation_primary_requests",
                        "audit_primary_requests",
                    ]
                }
            )
            row[role + "_users"] = len(users[(start, role)])
        row["both_tasks_present"] = all(row[role + "_requests"] for role in original.ROLES)
        row["after_original_audit"] = start >= original.TEST_START
        rows.append(row)
    args.out.mkdir(parents=True)
    with (args.out / "CALENDAR_BINS.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    receipt = dict(
        schema="rolemap.calendar_coverage.v1",
        phase="COVERAGE_ONLY_NO_FIT_OR_LOSS",
        sources=sources,
        code_sha256=original.sha(__file__),
        cohort_sha256=original.sha(args.cohort),
        primary_map_sha256=original.sha(args.primary_map),
        cache_sha256=original.sha(args.cache),
        source_audits=audits,
        source_ranges=ranges,
        duplicate_native_ids_across_sources=duplicate_native,
        valid_requests=len(seen),
        bin_seconds=BIN_SECONDS,
        bins_total=len(rows),
        jointly_covered_bins=sum(bool(x["both_tasks_present"]) for x in rows),
        new_joint_bins=sum(
            bool(x["both_tasks_present"] and x["after_original_audit"]) for x in rows
        ),
        wall_seconds=time.monotonic() - started,
        cpu_seconds=time.process_time() - cpu,
        max_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        pyarrow=pyarrow.__version__,
        no_clicks_queries_histories_or_losses_used=True,
    )
    (args.out / "COVERAGE.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: receipt[k]
                for k in [
                    "phase",
                    "valid_requests",
                    "bins_total",
                    "jointly_covered_bins",
                    "new_joint_bins",
                    "duplicate_native_ids_across_sources",
                    "wall_seconds",
                ]
            }
        )
    )


def self_test():
    sample = dict(
        user_idx=7,
        session_idx=2,
        search_idx=4,
        search_result_details_with_idx=[
            dict(note_idx=1, search_timestamp=3),
            dict(note_idx=1, search_timestamp=4),
            dict(note_idx=9, search_timestamp=5),
        ],
    )
    row = normalize(sample, "search", "train", {1})
    assert (
        row["timestamp_start"] == 3 and row["timestamp_end"] == 5 and row["exposed_item_ids"] == [1]
    )
    sample["search_result_details_with_idx"][0]["search_timestamp"] = float("nan")
    assert normalize(sample, "search", "train", {1}) is None
    assert original.validation_partition("same-user") == original.validation_partition("same-user")
    print("PASS_SHARED_WINDOW_PARSER_CHECKS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["coverage", "self-test"], required=True)
    parser.add_argument("--provider-root", type=Path)
    parser.add_argument("--cohort", type=Path)
    parser.add_argument("--primary-map", type=Path)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.mode == "self-test":
        self_test()
    else:
        calendar(args)


if __name__ == "__main__":
    main()
