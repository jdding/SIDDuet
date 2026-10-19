#!/usr/bin/env python3
"""Check whether Qilin role splits meet a declared shared global time cutoff.

This CPU audit reads provider parquet and an existing SID export. It does not
train a model, infer leakage effects, or regenerate a SID quantizer.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

SPLITS = (
    ("search", "train", "search_train", "search_result_details_with_idx", "search_timestamp"),
    ("search", "test", "search_test", "search_result_details_with_idx", "search_timestamp"),
    ("rec", "train", "recommendation_train", "rec_result_details_with_idx", "request_timestamp"),
    ("rec", "test", "recommendation_test", "rec_result_details_with_idx", "request_timestamp"),
)

@dataclass(frozen=True)
class Request:
    role: str
    split: str
    start: float
    end: float
    targets: tuple[int, ...]

def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def item_id(value):
    if value is None or isinstance(value, bool):
        raise ValueError("item ID must be a nonnegative integer")
    text = str(value)
    if not text.isdecimal():
        raise ValueError("item ID must use its provider integer namespace")
    return int(text)

def load_map(path):
    ids = set()
    lengths = Counter()
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        if not {"dataset", "item_id"}.issubset(fields):
            raise ValueError("SID CSV requires dataset,item_id and sid or sid_tokens")
        field = "sid_tokens" if "sid_tokens" in fields else "sid"
        if field not in fields:
            raise ValueError("SID CSV requires sid or sid_tokens")
        for row in reader:
            if row["dataset"].lower() != "qilin":
                raise ValueError("this case accepts one Qilin map, not mixed datasets")
            value = item_id(row["item_id"])
            if value in ids:
                raise ValueError("duplicate item ID in SID map")
            tokens = json.loads(row[field])
            if not isinstance(tokens, list) or len(tokens) < 2 or not all(isinstance(t, str) and t for t in tokens):
                raise ValueError("SID must be a JSON array of at least two nonempty string tokens")
            if "sid_role" in fields and row["sid_role"] != "shared":
                raise ValueError("the case requires a shared SID export")
            ids.add(value)
            lengths[len(tokens)] += 1
    if not ids:
        raise ValueError("empty SID map")
    return ids, {"items": len(ids), "token_lengths": dict(sorted(lengths.items()))}

def read_requests(root, pq):
    records = []
    inventory = []
    for role, split, directory, column, timestamp in SPLITS:
        paths = sorted((root / directory).glob("*.parquet"))
        if not paths:
            raise ValueError("missing provider split: " + directory)
        rows = missing_time = 0
        for path in paths:
            parquet = pq.ParquetFile(path)
            inventory.append({"relative_path": str(path.relative_to(root)), "sha256": sha256(path), "bytes": path.stat().st_size})
            for batch in parquet.iter_batches(batch_size=1024, columns=[column], use_threads=False):
                for details in batch.column(0).to_pylist():
                    rows += 1
                    timestamps = []
                    targets = set()
                    for detail in details or []:
                        if detail is None:
                            continue
                        if not isinstance(detail, dict):
                            raise ValueError("provider result details must be structs or null")
                        value = detail.get(timestamp)
                        if value is not None:
                            number = float(value)
                            if not math.isfinite(number):
                                raise ValueError("nonfinite provider timestamp")
                            timestamps.append(number)
                        click = detail.get("click")
                        if click is not None:
                            click = float(click)
                            if not math.isfinite(click):
                                raise ValueError("nonfinite provider click")
                            if click > 0:
                                targets.add(item_id(detail.get("note_idx")))
                    if not timestamps:
                        missing_time += 1
                        continue
                    records.append(Request(role, split, min(timestamps), max(timestamps), tuple(sorted(targets))))
        inventory.append({"provider_split": directory, "rows": rows, "rows_without_timestamp": missing_time})
        if missing_time:
            raise ValueError("timestamp-less requests cannot silently disappear from the shared split")
    return records, inventory

def check_catalog(root, mapped, pq):
    paths = sorted((root / "notes").glob("*.parquet"))
    if not paths:
        raise ValueError("static provider notes are needed to bind the item namespace")
    catalog = set()
    inventory = []
    for path in paths:
        inventory.append({"relative_path": str(path.relative_to(root)), "sha256": sha256(path), "bytes": path.stat().st_size})
        for batch in pq.ParquetFile(path).iter_batches(batch_size=65536, columns=["note_idx"], use_threads=False):
            for value in batch.column(0).to_pylist():
                idx = item_id(value)
                if idx in catalog:
                    raise ValueError("duplicate static provider note ID")
                catalog.add(idx)
    if not mapped.issubset(catalog):
        raise ValueError("SID IDs are outside the static provider namespace; supply the actual ID bridge")
    return catalog, inventory

def partition(records, fraction):
    if not 0 < fraction < 1:
        raise ValueError("train fraction must be between zero and one")
    test = [r for r in records if r.split == "test"]
    provider_train = [r for r in records if r.split == "train"]
    if not test or not provider_train:
        raise ValueError("provider train and test must both be nonempty")
    anchor = min(r.start for r in test)
    before = [r for r in provider_train if r.end < anchor]
    crossing = [r for r in provider_train if r.start < anchor <= r.end]
    after = [r for r in provider_train if r.start >= anchor]
    if not before:
        raise ValueError("no development surface before the shared test anchor")
    ends = sorted(r.end for r in before)
    cut = ends[math.ceil(fraction * len(ends)) - 1]
    train = [r for r in before if r.end < cut]
    valid = [r for r in before if r.start >= cut]
    excluded = [r for r in before if r.start < cut <= r.end]
    assert len(provider_train) == len(before) + len(crossing) + len(after)
    assert len(before) == len(train) + len(valid) + len(excluded)
    return {"test_anchor": anchor, "validation_start": cut}, {
        "provider_train": provider_train, "before_test_anchor": before,
        "crossing_test_anchor": crossing, "starting_at_or_after_test_anchor": after,
        "train": train, "validation": valid, "crossing_validation_boundary": excluded,
        "test": test,
    }

def summarize(records, mapped):
    result = {}
    for role in ("search", "rec"):
        subset = [r for r in records if r.role == role]
        targets = set(t for r in subset for t in r.targets)
        assignments = sum(len(r.targets) for r in subset)
        mapped_assignments = sum(sum(t in mapped for t in r.targets) for r in subset)
        result[role] = {
            "requests": len(subset), "positive_requests": sum(bool(r.targets) for r in subset),
            "mapped_positive_requests": sum(any(t in mapped for t in r.targets) for r in subset),
            "positive_target_assignments": assignments,
            "mapped_positive_target_assignments": mapped_assignments,
            "mapped_assignment_fraction": mapped_assignments / assignments if assignments else None,
            "unique_positive_targets": len(targets), "mapped_unique_positive_targets": len(targets & mapped),
        }
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qilin-root", type=Path, required=True)
    parser.add_argument("--sid-map", type=Path, required=True)
    parser.add_argument("--train-fraction", type=float, default=0.85)
    parser.add_argument("--out-json", type=Path, required=True)
    args = parser.parse_args()
    if args.out_json.exists():
        parser.error("output exists; choose a fresh path")
    try:
        import pyarrow
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise SystemExit("Provider parquet reading requires optional pyarrow==21.0.0; see docs/REAL_REUSE_CASE.md") from exc
    started = time.monotonic()
    records, inventory = read_requests(args.qilin_root, pq)
    boundaries, partitions = partition(records, args.train_fraction)
    mapped, sid = load_map(args.sid_map)
    catalog, note_inventory = check_catalog(args.qilin_root, mapped, pq)
    if any(t not in catalog for r in records for t in r.targets):
        raise ValueError("a positive provider target is outside the static catalog")
    summaries = {name: summarize(rows, mapped) for name, rows in partitions.items()}
    if any(summaries[name][role]["mapped_positive_requests"] == 0
           for name in ("train", "validation", "test") for role in ("search", "rec")):
        raise ValueError("one role/split has no mapped positive request")
    violates = bool(partitions["crossing_test_anchor"] or partitions["starting_at_or_after_test_anchor"])
    payload = {
        "schema": "sr_sid_rolemap.shared_time_boundary_case.v1",
        "status": "PASS_SHARED_TIME_BOUNDARY_AUDIT",
        "question": "Can provider role-specific train partitions be pooled unchanged under one declared global future cutoff?",
        "boundaries": boundaries, "train_fraction": args.train_fraction,
        "decisions": {
            "pool_provider_train_unchanged": "REJECT_UNDER_DECLARED_GLOBAL_CUTOFF" if violates else "ADMIT_UNDER_DECLARED_GLOBAL_CUTOFF",
            "next_action": "keep provider tests intact; exclude crossing/post-anchor train requests; freeze validation before SID filtering" if violates else "keep the verified split; audit SID fit provenance separately",
            "sid_fit_provenance": "NOT_ESTABLISHED_BY_CSV_OR_IDENTITY_COVERAGE",
        },
        "partition_counts": {name: len(rows) for name, rows in partitions.items()},
        "role_support": summaries,
        "sid_map": {"sha256": sha256(args.sid_map), **sid, "identity_namespace": "provider note_idx checked against static notes"},
        "static_catalog_items": len(catalog),
        "inputs": inventory + note_inventory,
        "runtime": {"pyarrow": pyarrow.__version__, "wall_seconds": round(time.monotonic() - started, 6)},
        "interpretation": [
            "Conditional split admission, not evidence that provider splits are erroneous.",
            "No ranking, decoding, leakage effect, shared-vs-separate utility or semantic conflict is measured.",
            "This does not rerun SID fitting or verify that a supplied map used only admissible training behavior.",
            "A non-author recipient must provide a lawful real SID export in the declared provider namespace.",
        ],
        "release_boundary": "aggregate output only; no user, query, request, target ID, SID assignment or full join is emitted",
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    with args.out_json.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(payload["status"])
    print(payload["decisions"]["pool_provider_train_unchanged"])

if __name__ == "__main__":
    main()
