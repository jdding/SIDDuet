#!/usr/bin/env python3
"""Verify and reassemble checkpoint parts."""

from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path


def assemble(manifest: Path, out: Path) -> dict:
    spec = json.loads(manifest.read_text())
    root = manifest.parent.resolve()
    if spec["schema"] != "sr_sid_rolemap.checkpoint_parts.v1":
        raise ValueError("unsupported checkpoint manifest")
    if out.exists():
        raise ValueError("output already exists")
    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_name(out.name + ".partial")
    total = 0
    whole = hashlib.sha256()
    owned = False
    try:
        with partial.open("xb") as target:
            owned = True
            for row in spec["parts"]:
                source = (root / row["path"]).resolve()
                try:
                    source.relative_to(root)
                except ValueError:
                    raise ValueError("part path escapes the checkpoint directory")
                digest = hashlib.sha256()
                size = 0
                with source.open("rb") as handle:
                    for block in iter(lambda: handle.read(1 << 20), b""):
                        size += len(block)
                        total += len(block)
                        digest.update(block)
                        whole.update(block)
                        target.write(block)
                if size != row["bytes"] or digest.hexdigest() != row["sha256"]:
                    raise ValueError("checkpoint part integrity mismatch")
            if total != spec["bytes"] or whole.hexdigest() != spec["sha256"]:
                raise ValueError("assembled checkpoint integrity mismatch")
        if out.exists():
            raise ValueError("output was created during assembly")
        partial.rename(out)
    except Exception:
        if owned:
            partial.unlink(missing_ok=True)
        raise
    return {
        "status": "PASS_CHECKPOINT_ASSEMBLY",
        "bytes": total,
        "sha256": whole.hexdigest(),
        "parts": len(spec["parts"]),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(assemble(args.manifest, args.out)))


if __name__ == "__main__":
    main()
