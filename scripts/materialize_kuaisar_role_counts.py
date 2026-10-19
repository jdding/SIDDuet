#!/usr/bin/env python3
"""Build local KuaiSAR role-label counts from provider CSV files.

Requires pandas 2.2.3. The registered KuaiSAR extraction functions are retained
unchanged. Outputs contain item-role counts only; provider inputs stay local.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    import pandas as pd
except ImportError:
    raise SystemExit("Provider reading requires optional pandas==2.2.3; no dependency was installed.") from None


def _top_value(frame: pd.DataFrame, key: str, value: str, count_name: str) -> pd.DataFrame:
    counts = (
        frame.groupby([key, value], dropna=False)
        .size()
        .reset_index(name=count_name)
        .sort_values([key, count_name, value], ascending=[True, False, True])
    )
    return counts.drop_duplicates(key, keep="first")


def load_kuaisar_metadata(data_root: Path, needed_item_ids: set[int], chunksize: int) -> pd.DataFrame:
    usecols = ["item_id", "first_level_category_id", "second_level_category_id"]
    chunks: list[pd.DataFrame] = []
    for chunk in pd.read_csv(data_root / "item_features.csv", usecols=usecols, chunksize=chunksize):
        keep = chunk[chunk["item_id"].isin(needed_item_ids)]
        if not keep.empty:
            chunks.append(keep.copy())
    if not chunks:
        return pd.DataFrame(columns=usecols)
    meta = pd.concat(chunks, ignore_index=True)
    meta = meta.dropna(subset=["item_id", "second_level_category_id"]).copy()
    meta["item_id"] = meta["item_id"].astype("int64")
    meta["label"] = meta["second_level_category_id"].astype(str)
    return meta[["item_id", "label", "first_level_category_id", "second_level_category_id"]].drop_duplicates(
        "item_id", keep="first"
    )


def counter_dict_from_pairs(frame: pd.DataFrame, item_col: str, label_col: str) -> dict[int, Counter[str]]:
    counts = frame.groupby([item_col, label_col], dropna=False).size().reset_index(name="n")
    out: dict[int, Counter[str]] = defaultdict(Counter)
    for row in counts.itertuples(index=False):
        out[int(getattr(row, item_col))][str(getattr(row, label_col))] += int(row.n)
    return dict(out)


def kuaisar_role_counts(data_root: Path, chunksize: int) -> tuple[dict[int, Counter[str]], dict[int, Counter[str]]]:
    src = pd.read_csv(data_root / "src_inter.csv", usecols=["keyword", "item_id"])
    rec = pd.read_csv(data_root / "rec_inter.csv", usecols=["user_id", "item_id", "timestamp"])
    src = src.dropna(subset=["keyword", "item_id"]).copy()
    rec = rec.dropna(subset=["user_id", "item_id"]).copy()
    src["item_id"] = src["item_id"].astype("int64")
    rec["item_id"] = rec["item_id"].astype("int64")

    rec = rec.sort_values(["user_id", "timestamp", "item_id"])
    rec["next_item_id"] = rec.groupby("user_id")["item_id"].shift(-1)
    rec_pairs = rec[["item_id", "next_item_id"]].dropna().copy()
    rec_pairs["next_item_id"] = rec_pairs["next_item_id"].astype("int64")

    needed = set(src["item_id"].tolist())
    needed.update(rec_pairs["item_id"].tolist())
    needed.update(rec_pairs["next_item_id"].tolist())
    meta = load_kuaisar_metadata(data_root, needed, chunksize)

    src_meta = src.merge(meta[["item_id", "label"]], on="item_id", how="inner")
    query_top = _top_value(src_meta, "keyword", "label", "query_label_count").rename(
        columns={"label": "query_role_label"}
    )
    search_pairs = src[["item_id", "keyword"]].merge(query_top[["keyword", "query_role_label"]], on="keyword")
    search_counts = counter_dict_from_pairs(search_pairs, "item_id", "query_role_label")

    next_meta = meta[["item_id", "label"]].rename(columns={"item_id": "next_item_id", "label": "next_role_label"})
    rec_labeled = rec_pairs.merge(next_meta, on="next_item_id", how="inner")
    rec_counts = counter_dict_from_pairs(rec_labeled, "item_id", "next_role_label")
    return search_counts, rec_counts


def input_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_counts(path: Path, search_counts, rec_counts) -> dict[str, Any]:
    rows = 0
    role_rows: Counter[str] = Counter()
    appearances: Counter[str] = Counter()
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["dataset", "item_id", "role", "label", "count"])
        for item_id in sorted(set(search_counts) | set(rec_counts), key=lambda key: str(key)):
            for role, mapping in (("search", search_counts), ("rec", rec_counts)):
                for label, count in sorted(mapping.get(item_id, {}).items(), key=lambda pair: str(pair[0])):
                    writer.writerow(["kuaisar", str(item_id), role, str(label), count])
                    rows += 1
                    role_rows[role] += 1
                    appearances[role] += count
    common = set(search_counts) & set(rec_counts)
    return {
        "output_rows": rows,
        "role_count_rows": dict(sorted(role_rows.items())),
        "role_appearances": dict(sorted(appearances.items())),
        "unique_items_by_role": {"search": len(search_counts), "rec": len(rec_counts)},
        "common_item_universe": {
            "items": len(common),
            "search_appearances": sum(sum(search_counts[key].values()) for key in common),
            "rec_appearances": sum(sum(rec_counts[key].values()) for key in common),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kuaisar-root", type=Path, required=True)
    parser.add_argument("--out-counts", type=Path, required=True)
    parser.add_argument("--out-summary", type=Path, required=True)
    parser.add_argument("--hash-inputs", action="store_true", help="Bind all three complete provider files by SHA-256")
    args = parser.parse_args()
    if args.out_counts.exists() or args.out_summary.exists():
        parser.error("output exists; choose fresh paths")
    if args.out_counts.resolve() == args.out_summary.resolve():
        parser.error("count and summary outputs must be different paths")
    input_paths = [args.kuaisar_root / name for name in ("src_inter.csv", "rec_inter.csv", "item_features.csv")]
    if any(not path.is_file() for path in input_paths):
        parser.error("provider root must contain src_inter.csv, rec_inter.csv and item_features.csv")
    if any(output.resolve() in {path.resolve() for path in input_paths} for output in (args.out_counts, args.out_summary)):
        parser.error("outputs must not replace provider inputs")
    started = time.monotonic()
    inputs = [
        {
            "path_relative_to_provider": path.name,
            "bytes": path.stat().st_size,
            "sha256": input_hash(path) if args.hash_inputs else None,
        }
        for path in input_paths
    ]
    search_counts, rec_counts = kuaisar_role_counts(args.kuaisar_root, 500_000)
    if not search_counts or not rec_counts:
        raise ValueError("provider extraction must retain both role surfaces")
    if args.hash_inputs:
        for path, entry in zip(input_paths, inputs):
            if input_hash(path) != entry["sha256"]:
                raise ValueError("provider input changed during extraction")
    args.out_counts.parent.mkdir(parents=True, exist_ok=True)
    stats = write_counts(args.out_counts, search_counts, rec_counts)
    payload = {
        "schema": "sr_sid_rolemap.kuaisar_provider_role_counts.v1",
        "status": "COMPLETE_LOCAL_MATERIALIZATION",
        "dataset": "kuaisar",
        **stats,
        "input_hashes_computed": args.hash_inputs,
        "input_hashes_verified_unchanged": args.hash_inputs,
        "inputs": inputs,
        "output_bytes": args.out_counts.stat().st_size,
        "output_sha256": input_hash(args.out_counts),
        "runtime": {
            "pandas": pd.__version__,
            "numpy": importlib.metadata.version("numpy"),
        },
        "wall_seconds": time.monotonic() - started,
        "protocol": {
            "metadata_chunksize": 500_000,
            "item_label": "second_level_category_id; retain the first nonmissing metadata row per item",
            "search": "two-pass keyword dominant second-level category; lexical category ties; assign the keyword label to every retained exposure, including items without metadata",
            "rec": "sort user_id,timestamp,item_id; pair each current item with the next item within its user; use the next item's available second-level category",
            "count": "retain repeated appearances; no positive-only filter or target-size constraint",
            "scope": "descriptive observed role counts, not training features",
        },
        "release_boundary": "Counts retain provider item identities and remain local; only aggregate QA and input hashes are intended for public review.",
    }
    args.out_summary.parent.mkdir(parents=True, exist_ok=True)
    with args.out_summary.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(payload["status"])


if __name__ == "__main__":
    main()
