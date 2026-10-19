#!/usr/bin/env python3
"""Materialize JDsearch search/query-less proxy counts; query-less is not identified recommendation traffic."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


DATASET = "JDsearch"
EXPECTED_BEHAVIOR_FIELDS = [
    "query",
    "candidate_wid_list",
    "candidate_label_list",
    "history_qry_list",
    "history_wid_list",
    "history_type_list",
    "history_time_list",
]
EXPECTED_METADATA_FIELDS = [
    "wid",
    "name",
    "brand_id",
    "brand_name",
    "cate_id_1",
    "cate_name_1",
    "cate_id_2",
    "cate_name_2",
    "cate_id_3",
    "cate_name_3",
    "cate_id_4",
    "cate_name_4",
    "shop_id",
]


def split_list(value: str) -> list[str]:
    return value.split("_") if value else []


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def iter_behavior(path: Path, max_rows: int) -> Iterable[tuple[int, dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != EXPECTED_BEHAVIOR_FIELDS:
            raise ValueError(f"unexpected JDsearch behavior header: {reader.fieldnames}")
        for row_number, row in enumerate(reader, start=1):
            if max_rows and row_number > max_rows:
                break
            yield row_number, row


def parse_behavior_lists(
    row_number: int, row: dict[str, str]
) -> tuple[list[int], list[float], list[str], list[int]]:
    candidate_ids = [int(value) for value in split_list(row["candidate_wid_list"])]
    candidate_labels = [float(value) for value in split_list(row["candidate_label_list"])]
    history_queries = split_list(row["history_qry_list"])
    history_ids = [int(value) for value in split_list(row["history_wid_list"])]
    history_types = split_list(row["history_type_list"])
    history_times = split_list(row["history_time_list"])
    if len(candidate_ids) != len(candidate_labels):
        raise ValueError(f"behavior row {row_number}: candidate id/label length mismatch")
    if not (len(history_queries) == len(history_ids) == len(history_types)):
        raise ValueError(f"behavior row {row_number}: history query/item/type length mismatch")
    if len(history_times) != len(history_ids) + 1:
        raise ValueError(
            f"behavior row {row_number}: history_time must include one test-query entry"
        )
    return candidate_ids, candidate_labels, history_queries, history_ids


def collect_referenced_items(behavior: Path, max_rows: int) -> tuple[set[int], Counter[str]]:
    referenced: set[int] = set()
    audit: Counter[str] = Counter()
    for row_number, row in iter_behavior(behavior, max_rows):
        candidate_ids, candidate_labels, history_queries, history_ids = parse_behavior_lists(
            row_number, row
        )
        referenced.update(candidate_ids)
        referenced.update(history_ids)
        audit["behavior_rows"] += 1
        audit["candidate_appearances"] += len(candidate_ids)
        audit["positive_candidate_appearances"] += sum(label > 0 for label in candidate_labels)
        audit["history_appearances"] += len(history_ids)
        audit["queryless_history_appearances"] += sum(query == "-1" for query in history_queries)
    if not audit["behavior_rows"]:
        raise ValueError("JDsearch behavior input contains no data rows")
    return referenced, audit


def load_categories(metadata: Path, referenced: set[int]) -> tuple[dict[int, int], Counter[str]]:
    categories: dict[int, int] = {}
    audit: Counter[str] = Counter()
    with metadata.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != EXPECTED_METADATA_FIELDS:
            raise ValueError(f"unexpected JDsearch metadata header: {reader.fieldnames}")
        for row in reader:
            audit["metadata_rows"] += 1
            item_id = int(row["wid"])
            if item_id not in referenced:
                continue
            label = next(
                (
                    row[field]
                    for field in ("cate_id_4", "cate_id_3", "cate_id_2", "cate_id_1")
                    if row[field] and row[field] != "-1"
                ),
                None,
            )
            if label is None:
                audit["referenced_items_without_category"] += 1
                continue
            categories[item_id] = int(label)
            audit["referenced_items_with_category"] += 1
    audit["referenced_items_missing_metadata_or_category"] = len(referenced) - len(categories)
    if not categories:
        raise ValueError("no referenced JDsearch items could be joined to metadata categories")
    return categories, audit


def dominant_label(labels: list[int]) -> int:
    counts = Counter(labels)
    return min(counts, key=lambda label: (-counts[label], label))


def increment(store: dict[int, Counter[int]], item_id: int, label: int) -> None:
    store[item_id][label] += 1


def materialize_counts(
    behavior: Path,
    categories: dict[int, int],
    max_rows: int,
) -> tuple[dict[int, Counter[int]], dict[int, Counter[int]], Counter[str], list[dict[str, object]]]:
    search_counts: dict[int, Counter[int]] = defaultdict(Counter)
    rec_counts: dict[int, Counter[int]] = defaultdict(Counter)
    audit: Counter[str] = Counter()
    samples: list[dict[str, object]] = []

    for row_number, row in iter_behavior(behavior, max_rows):
        candidate_ids, candidate_labels, history_queries, history_ids = parse_behavior_lists(
            row_number, row
        )
        mapped_candidates = [
            (item_id, score, categories.get(item_id))
            for item_id, score in zip(candidate_ids, candidate_labels)
        ]
        engaged_labels = [
            category
            for _, score, category in mapped_candidates
            if score > 0 and category is not None
        ]
        exposed_labels = [category for _, _, category in mapped_candidates if category is not None]
        role_labels = engaged_labels or exposed_labels
        if role_labels:
            search_label = dominant_label(role_labels)
            source = "engaged" if engaged_labels else "exposure"
            audit[f"search_events_{source}"] += 1
            for item_id, _, category in mapped_candidates:
                if category is not None:
                    increment(search_counts, item_id, search_label)
                    audit["search_assignments"] += 1
            if len(samples) < 10:
                samples.append(
                    {
                        "row_number": row_number,
                        "role": "search",
                        "source": source,
                        "candidate_count": len(candidate_ids),
                        "mapped_candidate_count": len(exposed_labels),
                        "role_label": search_label,
                    }
                )
        else:
            audit["search_events_without_mapped_category"] += 1

        queryless = [
            (item_id, categories.get(item_id))
            for query, item_id in zip(history_queries, history_ids)
            if query == "-1"
        ]
        # JDsearch histories are reverse chronological. For each older query-less
        # item, the preceding element is its next newer query-less interaction.
        for index in range(1, len(queryless)):
            current_item, current_category = queryless[index]
            _, next_category = queryless[index - 1]
            if current_category is None or next_category is None:
                audit["rec_transitions_without_mapped_category"] += 1
                continue
            increment(rec_counts, current_item, next_category)
            audit["rec_assignments"] += 1
        audit["rec_sequences_with_transition"] += len(queryless) >= 2
        if len(samples) < 20 and len(queryless) >= 2:
            samples.append(
                {
                    "row_number": row_number,
                    "role": "rec",
                    "queryless_items": len(queryless),
                    "materialized_transitions": sum(
                        queryless[index][1] is not None and queryless[index - 1][1] is not None
                        for index in range(1, len(queryless))
                    ),
                    "direction": "older_item_to_next_newer_queryless_item_category",
                }
            )

    if not search_counts or not rec_counts:
        raise ValueError("JDsearch adapter produced an empty role surface")
    return search_counts, rec_counts, audit, samples


def write_counts(
    path: Path,
    search_counts: dict[int, Counter[int]],
    rec_counts: dict[int, Counter[int]],
) -> tuple[int, int]:
    common_items = sorted(set(search_counts) & set(rec_counts))
    if len(common_items) < 4:
        raise ValueError(
            f"JDsearch has only {len(common_items)} common items after materialization"
        )
    rows = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["dataset", "item_id", "role", "label", "count"], lineterminator="\n"
        )
        writer.writeheader()
        for item_id in common_items:
            for role, store in (("search", search_counts), ("rec", rec_counts)):
                for label, count in sorted(store[item_id].items()):
                    writer.writerow(
                        {
                            "dataset": DATASET,
                            "item_id": item_id,
                            "role": role,
                            "label": label,
                            "count": count,
                        }
                    )
                    rows += 1
    return len(common_items), rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--behavior", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--out-counts", type=Path, required=True)
    parser.add_argument("--out-summary", type=Path, required=True)
    parser.add_argument("--max-rows", type=int, default=0, help="0 means all behavior rows")
    parser.add_argument("--hash-inputs", action="store_true")
    args = parser.parse_args()
    if args.max_rows < 0:
        raise ValueError("max-rows must be non-negative")
    for path in (args.behavior, args.metadata):
        if not path.is_file():
            raise FileNotFoundError(path)

    started = time.time()
    referenced, input_audit = collect_referenced_items(args.behavior, args.max_rows)
    categories, metadata_audit = load_categories(args.metadata, referenced)
    search_counts, rec_counts, materialization_audit, samples = materialize_counts(
        args.behavior, categories, args.max_rows
    )
    common_items, output_rows = write_counts(args.out_counts, search_counts, rec_counts)

    payload = {
        "schema": "sr_sid_rolemap.jdsearch_role_adapter.v1",
        "status": "pass",
        "dataset": DATASET,
        "provider_source": "https://github.com/rucliujn/JDsearch",
        "provider_commit": "0cdbfb403c2b2abb195cac50bb0c8dc49ee0f143",
        "license": "CC-BY-NC-SA-4.0",
        "max_behavior_rows": args.max_rows or None,
        "referenced_items": len(referenced),
        "mapped_items": len(categories),
        "search_items": len(search_counts),
        "rec_items": len(rec_counts),
        "common_items": common_items,
        "output_rows": output_rows,
        "audits": {
            "input": dict(sorted(input_audit.items())),
            "metadata": dict(sorted(metadata_audit.items())),
            "materialization": dict(sorted(materialization_audit.items())),
        },
        "role_contract": {
            "taxonomy_label": "deepest available category id: cate_id_4, then 3, 2, 1",
            "search": "dominant engaged candidate category per test query; exposure fallback; assign to mapped candidate appearances",
            "recommendation": "for reverse-chronological query-less history, assign each older item the category of its next newer query-less item",
            "tie_break": "smallest numeric category id",
        },
        "input_sha256": {
            "behavior": sha256(args.behavior) if args.hash_inputs else None,
            "metadata": sha256(args.metadata) if args.hash_inputs else None,
        },
        "output_sha256": sha256(args.out_counts),
        "elapsed_seconds": round(time.time() - started, 3),
        "public_release_boundary": "publish code and aggregate QA only; do not publish raw logs, queries, trajectories, role counts, or item-level topology",
        "inspection_samples": samples,
    }
    args.out_summary.parent.mkdir(parents=True, exist_ok=True)
    args.out_summary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"PASS_JDSEARCH_ROLE_ADAPTER common_items={common_items} output_rows={output_rows}")


if __name__ == "__main__":
    main()
