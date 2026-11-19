#!/usr/bin/env python3
"""Recompute SIDDuet Table 2 from the frozen public aggregate inputs."""

import csv
import json
import math
from pathlib import Path
import sys


REPORTS = Path(__file__).resolve().parents[1] / "reports" / "diagnostics_mc1999_20261020"
DATASETS = ("kuaisar", "qilin")
MAPS = ("grid", "rq-vae", "resid-gaoq")
REFERENCES = ("band", "exact")
DRAWS = 1999


def check(condition, message):
    if not condition:
        raise ValueError(message)


def close(left, right):
    return math.isclose(left, right, rel_tol=0, abs_tol=1e-12)


def verify():
    source = json.loads((REPORTS / "TABLE2_NULL_MEANS.json").read_text(encoding="utf-8"))
    check(source["schema"] == "sidduet.table2_null_means.v1", "unexpected draws format")
    draws = source["draw_means"]
    published = json.loads((REPORTS / "MC1999_RESULTS.json").read_text(encoding="utf-8"))
    keys = {f"{ref}/{ds}/{view}" for ref in REFERENCES for ds in DATASETS for view in MAPS}
    cases = {
        "/".join(row[key] for key in ("reference", "dataset", "mapping_family")): row
        for row in published["results"]
    }
    check(len(published["results"]) == len(keys) and set(cases) == set(draws) == keys,
          "unexpected Table 2 comparisons")
    observations = {}
    means = {}
    for ref in REFERENCES:
        family = []
        for ds in DATASETS:
            for view in MAPS:
                key = f"{ref}/{ds}/{view}"
                row = cases[key]
                group = row["observed"]["all_collision_groups"]
                n = group["groups"]
                leaders = group["disjoint_argmax_groups"]
                observed = group["means"]["equal_group_jsd"]
                value = (n, observed, leaders)
                check(0 <= leaders <= n and n > 0 and 0 <= observed <= 1
                      and close(leaders / n, group["means"]["equal_group_disjoint"]),
                      f"invalid observed statistics for {key}")
                check(observations.setdefault((ds, view), value) == value,
                      f"the reference changes the observed cohort for {key}")
                values = draws[key]
                check(len(values) == DRAWS and all(0 <= v <= 1 for v in values),
                      f"invalid reference draws for {key}")
                mean = math.fsum(values) / DRAWS
                lower = 1 + sum(value <= observed for value in values)
                upper = 1 + sum(value >= observed for value in values)
                p = min(1.0, 2 * min(lower, upper) / (DRAWS + 1))
                reported = row["summaries"]["all_collision_groups"]["equal_group_jsd"]
                check(close(mean, reported["mean"]) and close(p, row["p_two_sided"]),
                      f"reference mean or p value mismatch for {key}")
                means[key] = mean
                family.append((p, row, key))

        harmonic = math.fsum(1 / rank for rank in range(1, len(family) + 1))
        q = 1.0
        ordered = sorted(family, key=lambda entry: entry[0])
        for rank, (p, row, key) in reversed(list(enumerate(ordered, 1))):
            q = min(q, len(family) * p / rank)
            check(close(q, row["BH_six"]) and close(min(1.0, q * harmonic), row["BY_six"]),
                  f"BH or BY mismatch for {key}")

    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(("dataset", "mapping", "groups", "observed_jsd", "band_mean",
                     "exact_total_mean", "disjoint_leaders"))
    for (ds, view), (n, observed, leaders) in observations.items():
        writer.writerow((ds, view, n, f"{observed:.3f}", f"{means[f'band/{ds}/{view}']:.3f}",
                         f"{means[f'exact/{ds}/{view}']:.3f}", f"{100 * leaders / n:.2f}%"))
    print("Verified 12 means and p values, and two six-comparison BH/BY families.", file=sys.stderr)


if __name__ == "__main__":
    try:
        verify()
    except (KeyError, OSError, TypeError, ValueError) as exc:
        sys.exit(f"Table 2 verification failed: {exc}")
