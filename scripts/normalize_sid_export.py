#!/usr/bin/env python3
"""Stream one existing shared Qilin SID export into the RoleMap CSV interface.

This changes CSV representation only. Item IDs and complete token sequences
remain intact; no SID fitting, token generation or identity inference occurs.
The output map must remain local under the source artifact's access terms.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter
from pathlib import Path
from typing import TextIO

REQUIRED = {
    "schema_version",
    "dataset",
    "item_id",
    "system_id",
    "sid_family",
    "sid_role",
    "sid_tokens",
}


class HashedReader(io.RawIOBase):
    """Hash the exact input bytes consumed by the streaming CSV text reader."""

    def __init__(self, raw):
        self.raw = raw
        self.digest = hashlib.sha256()
        self.bytes = 0

    def readable(self):
        return True

    def readinto(self, buffer):
        size = self.raw.readinto(buffer)
        if size:
            self.digest.update(memoryview(buffer)[:size])
            self.bytes += size
        return size


class HashedWriter:
    """Hash UTF-8 output without retaining a second serialized map."""

    def __init__(self, target: TextIO):
        self.target = target
        self.digest = hashlib.sha256()
        self.bytes = 0

    def write(self, text: str):
        written = self.target.write(text)
        encoded = text.encode("utf-8")
        self.digest.update(encoded)
        self.bytes += len(encoded)
        return written


def normalize(source_path: Path, target: TextIO) -> tuple[dict[str, object], dict[str, object]]:
    seen: set[str] = set()
    lengths: Counter[int] = Counter()
    metadata: dict[str, set[str]] = {
        field: set() for field in ("schema_version", "system_id", "sid_family")
    }
    sid_counts: Counter[str] = Counter()
    row_count = 0
    output = HashedWriter(target)
    writer = csv.DictWriter(output, fieldnames=["dataset", "item_id", "sid"], lineterminator="\n")
    with source_path.open("rb") as raw:
        hashed = HashedReader(raw)
        with io.TextIOWrapper(io.BufferedReader(hashed), encoding="utf-8", newline="") as text:
            reader = csv.DictReader(text)
            fields = reader.fieldnames or []
            if len(fields) != len(set(fields)) or set(fields) != REQUIRED:
                raise ValueError("expected the seven-field shared SID source export")
            writer.writeheader()
            for row in reader:
                if set(row) != REQUIRED or any(value is None for value in row.values()):
                    raise ValueError("source CSV row does not match its header")
                if row["dataset"].lower() != "qilin":
                    raise ValueError("this converter accepts one Qilin export")
                identity = row["item_id"]
                if re.fullmatch(r"0|[1-9][0-9]*", identity) is None:
                    raise ValueError(
                        "item_id must use canonical nonnegative provider integer spelling"
                    )
                if identity in seen:
                    raise ValueError("duplicate item_id in source export")
                if row["sid_role"] != "shared":
                    raise ValueError(
                        "this converter requires shared SID rows, not role-specific assignments"
                    )
                for field in metadata:
                    if not row[field].strip():
                        raise ValueError("source identity metadata must be nonempty")
                    metadata[field].add(row[field])
                    if len(metadata[field]) != 1:
                        raise ValueError(
                            "source export mixes schema, system or SID-family identities"
                        )
                tokens = json.loads(row["sid_tokens"])
                if (
                    not isinstance(tokens, list)
                    or len(tokens) < 2
                    or not all(isinstance(token, str) and token.strip() for token in tokens)
                ):
                    raise ValueError(
                        "sid_tokens must be a JSON array of at least two nonempty strings"
                    )
                sid = json.dumps(tokens, ensure_ascii=False, separators=(",", ":"))
                writer.writerow({"dataset": "qilin", "item_id": identity, "sid": sid})
                seen.add(identity)
                sid_counts[sid] += 1
                lengths[len(tokens)] += 1
                row_count += 1
        source_hash = hashed.digest.hexdigest()
        source_bytes = hashed.bytes
    if not row_count:
        raise ValueError("source SID export is empty")
    stats = {
        "rows": row_count,
        "items": len(seen),
        "dataset": "qilin",
        "sid_role": "shared",
        "source_identity": {field: next(iter(values)) for field, values in metadata.items()},
        "token_lengths": dict(sorted(lengths.items())),
        "unique_sid_count": len(sid_counts),
        "collision_groups": sum(count > 1 for count in sid_counts.values()),
    }
    return {
        "sha256": source_hash,
        "bytes": source_bytes,
        **stats,
    }, {
        "schema": "dataset,item_id,sid",
        "sha256": output.digest.hexdigest(),
        "bytes": output.bytes,
        "rows": row_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out-csv", required=True, type=Path)
    parser.add_argument("--out-summary", required=True, type=Path)
    args = parser.parse_args()
    if args.out_csv.resolve() == args.out_summary.resolve():
        parser.error("CSV and summary require distinct fresh paths")
    for path in (args.out_csv, args.out_summary):
        if path.exists() or path.is_symlink():
            parser.error("output exists; choose fresh paths")
    # Streaming may encounter a bad row late. Only files exclusively created
    # by this invocation are removed on failure; existing artifacts are untouched.
    created: list[Path] = []
    try:
        for path in (args.out_csv, args.out_summary):
            path.parent.mkdir(parents=True, exist_ok=True)
        with args.out_csv.open("x", encoding="utf-8", newline="") as handle:
            created.append(args.out_csv)
            source, output = normalize(args.input, handle)
        summary = {
            "schema": "sr_sid_rolemap.sid_export_normalization.v1",
            "status": "PASS_SHARED_SID_EXPORT_NORMALIZATION",
            "source": source,
            "output": output,
            "transformation": "dataset spelling becomes qilin; item_id text and ordered full token values are preserved; sid is a canonical JSON list",
            "fit_provenance": "NOT_ESTABLISHED_BY_REPRESENTATION_CONVERSION",
            "release_boundary": "full source and normalized maps remain local; only license-cleared aggregate summary may be published",
        }
        with args.out_summary.open("x", encoding="utf-8") as handle:
            created.append(args.out_summary)
            handle.write(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    except Exception:
        for path in created:
            path.unlink()
        raise
    print(summary["status"])


if __name__ == "__main__":
    main()
