#!/usr/bin/env python3
"""Build local Qilin role-label counts from provider Parquet files.

Only the optional Parquet reader needs PyArrow. Outputs retain provider item
keys and must stay local; the JSON summary contains aggregates and file hashes.
The labels summarize observed train+test behavior, not a training-only feature.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import time
from collections import Counter
from pathlib import Path


DATASET = "qilin"
FEEDBACK = ("click", "like", "collect", "comment", "share", "page_time")
SPLITS = (
    ("search_train", "search", "search_result_details_with_idx"),
    ("search_test", "search", "search_result_details_with_idx"),
    ("recommendation_train", "rec", "rec_result_details_with_idx"),
    ("recommendation_test", "rec", "rec_result_details_with_idx"),
)


def item_key(value):
    """Return the exact integer provider key; never truncate fractional IDs."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def category(value):
    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    label = str(value).strip()
    return label if label and label.lower() not in {"nan", "none", "null"} else None


def positive(value):
    if value is None:
        return False
    try:
        number = float(value)
    except (ValueError, TypeError):
        raise ValueError("feedback must be numeric or missing") from None
    return math.isfinite(number) and number > 0


def add_notes(rows, labels, audit):
    for row in rows:
        audit["rows_seen"] += 1
        key = item_key(row.get("note_idx"))
        if key is None:
            audit["excluded_missing_or_invalid_item_id"] += 1
            continue
        label = category(row.get("taxonomy2_id"))
        if label is None:
            label = category(row.get("taxonomy1_id"))
            if label is not None:
                audit["level1_fallback_rows"] += 1
        if label is None:
            audit["excluded_missing_taxonomy"] += 1
            continue
        audit["rows_with_label"] += 1
        if key in labels:
            if labels[key] != label:
                raise ValueError("conflicting taxonomy labels for one provider item")
            audit["duplicate_identical_item_rows"] += 1
        labels[key] = label


def add_event(details, role, labels, counts, audit):
    audit["events_seen"] += 1
    if details is None:
        audit["events_empty_or_missing_details"] += 1
        return
    if not isinstance(details, list):
        raise ValueError("result details must be a list or null")
    if not details:
        audit["events_empty_or_missing_details"] += 1
        return
    valid = []
    engaged = Counter()
    exposed = Counter()
    for detail in details:
        audit["appearances_seen"] += 1
        if detail is None:
            audit["excluded_null_detail"] += 1
            continue
        if not isinstance(detail, dict):
            raise ValueError("each result appearance must be a struct or null")
        key = item_key(detail.get("note_idx"))
        if key is None:
            audit["excluded_missing_or_invalid_item_id"] += 1
            continue
        label = labels.get(key)
        if label is None:
            audit["excluded_missing_taxonomy_or_catalog_item"] += 1
            continue
        valid.append(key)
        exposed[label] += 1
        if any(positive(detail.get(field)) for field in FEEDBACK):
            engaged[label] += 1
            audit["valid_engaged_appearances"] += 1
    if not valid:
        audit["events_without_valid_appearances"] += 1
        return
    source = engaged if engaged else exposed
    label = min(source, key=lambda name: (-source[name], name))
    audit["events_with_engaged_label" if engaged else "events_with_exposure_fallback"] += 1
    audit["valid_appearances"] += len(valid)
    audit["duplicate_valid_appearances_within_event"] += len(valid) - len(set(valid))
    for key in valid:
        counts[(key, role, label)] += 1


def parquet_rows(path, columns, batch_size, limit):
    try:
        import pyarrow.parquet as pq
    except ImportError:
        raise SystemExit("Provider reading requires optional PyArrow; no dependency was installed.")
    emitted = 0
    batch_size = min(batch_size, limit) if limit is not None else batch_size
    for batch in pq.ParquetFile(path).iter_batches(batch_size=batch_size, columns=columns):
        if limit is not None:
            batch = batch.slice(0, min(batch.num_rows, limit - emitted))
        rows = batch.to_pylist()
        yield from rows
        emitted += len(rows)
        if limit is not None and emitted >= limit:
            break


def input_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_counts(path, counts):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["dataset", "item_id", "role", "label", "count"])
        for (key, role, label), count in sorted(counts.items(), key=lambda row: (str(row[0][0]), row[0][1] != "search", row[0][2])):
            writer.writerow([DATASET, key, role, label, count])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qilin-root", type=Path, required=True)
    parser.add_argument("--out-counts", type=Path, required=True)
    parser.add_argument("--out-summary", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--profile-rows", type=int, help="Bound notes AND events per file; partial output is not a dataset result")
    parser.add_argument("--hash-inputs", action="store_true", help="Stream all required input bytes for SHA-256 binding")
    args = parser.parse_args()
    if args.batch_size <= 0 or (args.profile_rows is not None and args.profile_rows <= 0):
        parser.error("batch size and profile rows must be positive")
    if args.profile_rows is not None and args.hash_inputs:
        parser.error("bounded profiling cannot request a full input-hash scan")
    if args.out_counts.exists() or args.out_summary.exists():
        parser.error("output exists; choose fresh paths")
    started = time.monotonic()
    note_paths = sorted((args.qilin_root / "notes").glob("*.parquet"))
    if not note_paths:
        raise ValueError("no notes shards found")
    split_paths = []
    for name, role, column in SPLITS:
        paths = sorted((args.qilin_root / name).glob("*.parquet"))
        if not paths:
            raise ValueError("a required provider split is missing")
        split_paths.extend((name, role, column, path) for path in paths)
    labels, counts = {}, Counter()
    notes_audit, split_audits = Counter(), {}
    inputs = []
    for path in note_paths:
        add_notes(parquet_rows(path, ["note_idx", "taxonomy2_id", "taxonomy1_id"], args.batch_size, args.profile_rows), labels, notes_audit)
    for name, role, column, path in split_paths:
        audit = split_audits.setdefault(name, Counter())
        for row in parquet_rows(path, [column], args.batch_size, args.profile_rows):
            add_event(row[column], role, labels, counts, audit)
    for path in note_paths + [entry[3] for entry in split_paths]:
        inputs.append({"path_relative_to_provider": str(path.relative_to(args.qilin_root)), "bytes": path.stat().st_size,
                       "sha256": input_hash(path) if args.hash_inputs else None})
    for audit in split_audits.values():
        assert audit["appearances_seen"] == sum(audit[key] for key in (
            "valid_appearances", "excluded_null_detail", "excluded_missing_or_invalid_item_id", "excluded_missing_taxonomy_or_catalog_item"))
        assert audit["events_seen"] == sum(audit[key] for key in (
            "events_empty_or_missing_details", "events_without_valid_appearances", "events_with_engaged_label", "events_with_exposure_fallback"))
    assert notes_audit["rows_seen"] == sum(notes_audit[key] for key in (
        "rows_with_label", "excluded_missing_or_invalid_item_id", "excluded_missing_taxonomy"))
    write_counts(args.out_counts, counts)
    payload = {
        "schema": "sr_sid_rolemap.qilin_provider_role_counts.v1",
        "status": "PROFILE_ONLY" if args.profile_rows is not None else "COMPLETE_LOCAL_MATERIALIZATION",
        "dataset": DATASET, "profile_rows_per_file": args.profile_rows,
        "input_hashes_verified": False, "input_hashes_computed": args.hash_inputs,
        "inputs": inputs, "notes": dict(sorted(notes_audit.items())), "labeled_catalog_items": len(labels),
        "splits": {name: dict(sorted(audit.items())) for name, audit in sorted(split_audits.items())},
        "output_rows": len(counts), "output_appearances": sum(counts.values()),
        "output_sha256": input_hash(args.out_counts), "wall_seconds": time.monotonic() - started,
        "protocol": {"category": "taxonomy2_id with taxonomy1_id fallback; exclude missing IDs/taxonomy",
                     "engagement": "any finite positive click/like/collect/comment/share/page_time",
                     "event_label": "dominant engaged category, else exposures; lexical string tie-break",
                     "assignment": "count every retained appearance, including duplicates",
                     "scope": "both provider train and test; descriptive topology, not training features"},
        "release_boundary": "Counts retain original item keys and remain local; only this aggregate summary may be reviewed for release.",
    }
    args.out_summary.parent.mkdir(parents=True, exist_ok=True)
    with args.out_summary.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(payload["status"])


if __name__ == "__main__":
    main()
