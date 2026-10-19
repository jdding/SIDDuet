#!/usr/bin/env python3
"""Inspect a specified SID collision group."""

import argparse, csv, hashlib, json
from collections import Counter
from pathlib import Path

PROFILE = "sr_sid_rolemap.topology.value_median.v2"
SALT = "sr_sid_rolemap_r089_public_safe_v1"


def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def hashed(*parts):
    return hashlib.sha256("::".join([SALT, *map(str, parts)]).encode()).hexdigest()[:12]


def itemkey(s):
    return (
        (0, int(s))
        if s.isascii() and s.isdigit() and (s == "0" or not s.startswith("0"))
        else (1, s)
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--topology", type=Path, required=True)
    p.add_argument("--sid-map", type=Path, required=True)
    p.add_argument("--sid-column", default="sid")
    p.add_argument("--sid-hash", required=True)
    p.add_argument("--dataset", required=True)
    p.add_argument("--out-json", type=Path, required=True)
    p.add_argument("--out-csv", type=Path, required=True)
    args = p.parse_args()
    if (
        args.out_json.exists()
        or args.out_csv.exists()
        or args.out_json.resolve() == args.out_csv.resolve()
    ):
        p.error("outputs must use distinct fresh paths")
    topology = {}
    for r in csv.DictReader(args.topology.open(newline="")):
        if r.get("profile_id") != PROFILE:
            raise ValueError("topology profile mismatch")
        key = (r["dataset"], r["item_id"])
        if key in topology:
            raise ValueError("duplicate topology item")
        topology[key] = r
    members = []
    raw_sids = set()
    seen = set()
    for r in csv.DictReader(args.sid_map.open(newline="")):
        if r["dataset"] != args.dataset:
            continue
        key = (r["dataset"], r["item_id"])
        if key in seen:
            raise ValueError("duplicate SID item")
        seen.add(key)
        sid = r[args.sid_column]
        if hashed("sid", sid) == args.sid_hash:
            raw_sids.add(sid)
            if key not in topology:
                raise ValueError("selected group member absent from topology")
            members.append(topology[key])
    if len(raw_sids) != 1 or len(members) < 2:
        raise ValueError("selected SID hash must identify one collision group")
    cells = Counter(r["topology_cell"] for r in members)
    for x in ["low_rsd", "high_rsd"]:
        for y in ["low_rsi", "high_rsi"]:
            cells.setdefault(x + "|" + y, 0)

    def ranked(role):
        return sorted(
            members,
            key=lambda r: (
                -float(r[role + "_support"]),
                -sum(float(r[f]) for f in ["search_support", "rec_support"]),
                itemkey(r["item_id"]),
            ),
        )

    leaders = {}
    sample = []
    for role in ["search", "rec"]:
        ordered = ranked(role)
        lead = ordered[0]
        leaders[role] = {
            "item_hash": hashed(args.dataset, lead["item_id"]),
            "search_support": float(lead["search_support"]),
            "rec_support": float(lead["rec_support"]),
            "topology_cell": lead["topology_cell"],
        }
        for n, r in enumerate(ordered[:8], 1):
            sample.append(
                {
                    "surface": role + "_support_leaders",
                    "surface_rank": n,
                    "dataset": args.dataset,
                    "item_hash": hashed(args.dataset, r["item_id"]),
                    "search_support": r["search_support"],
                    "rec_support": r["rec_support"],
                    "profile_id": PROFILE,
                    "topology_cell": r["topology_cell"],
                    "rsd_score": r["rsd_score"],
                    "rsi_signed": r["rsi_signed"],
                    "rsd_at_median": r["rsd_at_median"],
                    "rsi_at_median": r["rsi_at_median"],
                }
            )
    membership = hashlib.sha256(
        "".join(
            r["item_id"] + "\n" for r in sorted(members, key=lambda r: itemkey(r["item_id"]))
        ).encode()
    ).hexdigest()
    report = {
        "schema": "sr_sid_rolemap.fixed_collision_case.v2",
        "status": "pass",
        "topology_profile_id": PROFILE,
        "topology_sha256": sha(args.topology),
        "sid_map_sha256": sha(args.sid_map),
        "dataset": args.dataset,
        "sid_hash": args.sid_hash,
        "group_size": len(members),
        "membership_sha256": membership,
        "cell_counts": dict(sorted(cells.items())),
        "support_sums": {
            role: sum(float(r[role + "_support"]) for r in members) for role in ["search", "rec"]
        },
        "leaders": leaders,
        "leaders_are_different": leaders["search"]["item_hash"] != leaders["rec"]["item_hash"],
        "selection": (
            "Group fixed by its archived SID hash before v2 reconstruction; no new cell-based "
            "selection. SID hash uses the literal supplied SID field, preserving the archived "
            "representation."
        ),
        "hash_salt_label": SALT,
        "public_safety": {
            "raw_item_ids_in_outputs": False,
            "raw_sid_tokens_in_outputs": False,
            "query_or_user_data_in_outputs": False,
        },
        "claim_boundary": (
            "Role-support heterogeneity only. Cell names mean strictly above or at/below a "
            "dataset median; empty high cells are valid. Neither a low label nor this selected "
            "case establishes semantic compatibility, model harm, or utility."
        ),
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("x", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(sample[0]))
        w.writeheader()
        w.writerows(sample)
    with args.out_json.open("x") as f:
        f.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("PASS_FIXED_COLLISION_CASE")


if __name__ == "__main__":
    main()
