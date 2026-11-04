"""Strict, stdlib-only SID map CSV and token-list identity contract."""

from __future__ import annotations

import csv
import json
from pathlib import Path


def canonical_sid(value: str | list[str | int]) -> str:
    """Normalize JSON token lists; preserve legacy nonempty opaque strings."""
    if isinstance(value, str):
        if not value.strip():
            raise ValueError("SID must not be empty or blank")
        if not value.lstrip().startswith("["):
            return value
        try:
            tokens = json.loads(value)
        except (ValueError, TypeError) as exc:
            raise ValueError("SID token list must be valid JSON") from exc
    else:
        tokens = value
    if not isinstance(tokens, list) or not tokens:
        raise ValueError("SID token list must be a nonempty list")
    for token in tokens:
        if type(token) is int:
            continue
        if isinstance(token, str) and token.strip():
            continue
        raise ValueError("SID tokens must be nonblank strings or integers (not booleans)")
    return json.dumps(tokens, ensure_ascii=False, separators=(",", ":"))


def load_sid_map(path: str | Path) -> dict[tuple[str, str], str]:
    """Read exact dataset/item keys, rejecting malformed or ambiguous CSV rows."""
    result: dict[tuple[str, str], str] = {}
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, strict=True)
        header = next(reader, None)
        if not header or len(header) != len(set(header)):
            raise ValueError("SID map requires a header with unique column names")
        required = ("dataset", "item_id", "sid")
        if any(field not in header for field in required):
            raise ValueError("SID map requires dataset,item_id,sid columns")
        indices = [header.index(field) for field in required]
        for row in reader:
            if len(row) != len(header):
                raise ValueError(f"SID map row {reader.line_num} has incorrect CSV width")
            dataset, item, sid = (row[index] for index in indices)
            if not dataset.strip() or not item.strip():
                raise ValueError(f"SID map row {reader.line_num} has a blank dataset/item key")
            key = (dataset, item)
            if key in result:
                raise ValueError(f"duplicate SID map item: {key}")
            result[key] = canonical_sid(sid)
    return result
