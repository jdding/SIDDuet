"""Rank collision groups by allocation JSD for upper-tail human inspection."""

from __future__ import annotations

import argparse
import csv
from itertools import islice
from pathlib import Path
import sys


def rank_groups(scores):
    """Use all collision groups for the inclusive percentile, even when exporting only K."""
    ordered = sorted(scores, key=lambda sid: (-scores[sid], sid))
    for position, sid in enumerate(ordered):
        if position == 0 or scores[sid] != scores[ordered[position - 1]]:
            rank = position + 1
            percentile = 100.0 * (len(ordered) - position) / len(ordered)
        yield sid, rank, percentile


LEADER_FIELDS = ("item", "ties", "search_count", "search_share", "rec_count", "rec_share")
FIELDS = ["dataset", "mapping", "sid", "rank", "percentile", "collision_groups", "size",
          "jsd", "search_total", "rec_total"] + [
    f"{role}_leader_{field}" for role in ("search", "rec") for field in LEADER_FIELDS
]


def inspect(args, calibration):
    import numpy as np

    maps = calibration.parse_maps(args.sid_map)
    calibration.check_outputs([args.out_csv], [args.role_counts, *maps.values(), __file__])
    datasets, _ = calibration.read_counts(args.role_counts)
    mappings = {name: calibration.SID_IO.load_sid_map(path) for name, path in maps.items()}
    calibration.map_coverage(datasets, mappings)

    rows, coverage = [], []
    for dataset, data in datasets.items():
        ids, search, rec = data["ids"], data["s"], data["r"]
        for name, mapping in mappings.items():
            labels, group, sizes = calibration.group_index(dataset, ids, mapping)
            stats = calibration.POP.group_stats(search, rec, group, sizes)
            scores = {g: stats["jsd"][g] for g in np.flatnonzero(sizes >= 2)}
            offsets = np.r_[0, sizes.cumsum()]
            members = group.argsort(kind="stable")
            for g, rank, percentile in islice(rank_groups(scores), args.top_groups):
                indices = members[offsets[g]:offsets[g + 1]]
                st, rt = int(stats["search"][g]), int(stats["rec"][g])
                row = dict(dataset=dataset, mapping=name, sid=labels[g], rank=rank,
                           percentile=percentile, collision_groups=len(scores), size=int(sizes[g]),
                           jsd=float(scores[g]), search_total=st, rec_total=rt)
                for role, counts in (("search", search), ("rec", rec)):
                    # Stable group membership preserves lexical item order for tied maxima.
                    leader = indices[np.argmax(counts[indices])]
                    s, r = int(search[leader]), int(rec[leader])
                    values = (ids[leader], int(stats[role + "_argmax_count"][g]), s, s / st, r, r / rt)
                    row.update({f"{role}_leader_{key}": val for key, val in zip(LEADER_FIELDS, values)})
                rows.append(row)
            coverage.append(dict(dataset=dataset, mapping=name, covered_common_items=len(ids),
                                 common_items=len(ids), collision_groups=len(scores),
                                 exported_groups=min(len(scores), args.top_groups)))

    with args.out_csv.open("x", newline="", encoding="utf-8") as output:
        try:
            writer = csv.DictWriter(output, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
            output.flush()
        except BaseException:
            args.out_csv.unlink()
            raise
    return coverage


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import calibrate_task_allocation as calibration
    parser = argparse.ArgumentParser(description=__doc__,
                                     epilog="High JSD describes observed shares. It does not validate a code split.")
    calibration.add_input_arguments(parser)
    parser.add_argument("--top-groups", type=int, default=10, metavar="K",
                        help="maximum rows per dataset and map (default 10)")
    parser.add_argument("--out-csv", type=Path, required=True,
                        help="fresh local CSV path for group and leader identifiers")
    args = parser.parse_args()
    if args.top_groups < 1:
        parser.error("--top-groups must be positive")
    try:
        coverage = inspect(args, calibration)
    except (ValueError, OSError, csv.Error) as exc:
        parser.error(str(exc))
    for entry in coverage:
        print(f"{entry['dataset']} / {entry['mapping']}: "
              f"{entry['covered_common_items']}/{entry['common_items']} common items covered, "
              f"{entry['exported_groups']}/{entry['collision_groups']} collision groups exported")


if __name__ == "__main__":
    main()
