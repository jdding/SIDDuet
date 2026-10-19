#!/usr/bin/env python3
"""Report paired bootstrap sensitivity for the original and additional windows."""

import argparse
import csv
import json
from pathlib import Path
import time
import numpy as np

import multiplicity_sensitivity as paired


def compare(args):
    started = time.monotonic()
    if args.out.exists():
        raise ValueError("Choose a new output directory")
    inputs = [
        ("original", args.original_scores, args.original_results),
        ("shared", args.shared_scores, args.shared_results),
    ]
    references = [json.loads(path.read_text()) for _, _, path in inputs]
    names = [
        {x["name"] for x in ref["results"] if x["status"] == "EVALUATED"} for ref in references
    ]
    if names[0] != names[1] or len(names[0]) != 5:
        raise ValueError("Expected the same five estimable views in both windows")
    checks = paired.self_test()
    results = []
    hashes = {}
    primary_users = {}
    max_error = 0.0
    for (window, folder, path), ref in zip(inputs, references):
        hashes[window + "_reference_results"] = paired.digest(path)
        if [x["name"] for x in ref["results"] if x["primary"]] != ["gensar_shared2"]:
            raise ValueError("Original primary changed")
        for view in ref["results"]:
            if view["status"] != "EVALUATED":
                continue
            name = view["name"]
            if Path(name).name != name:
                raise ValueError("View name cannot be a path")
            source = folder / (name + "_scores.jsonl")
            before = paired.digest(source)
            rows = paired.read_scores(source)
            stats = paired.user_statistics(rows)
            draws, missing = paired.bootstrap(stats, args.draws, int(ref["bootstrap_seed"]))
            if missing:
                raise ValueError("A draw omits one task; no fallback was declared")
            original = np.quantile(draws[: int(ref["bootstrap_draws"])], [0.025, 0.975], axis=0)
            points = paired.differences(stats.sum(axis=0))
            errors = []
            for j, role in enumerate(("search", "rec", "macro")):
                errors.extend(abs(original[:, j] - view["bootstrap"]["intervals"][role]))
                errors.append(abs(points[j] - view["delta_nats"][role]))
            error = float(max(errors))
            max_error = max(max_error, error)
            if error > 1e-12 or len(stats) != view["bootstrap"]["users"]:
                raise ValueError("Original intervals or estimates were not reconstructed")
            if paired.digest(source) != before:
                raise ValueError("Loss input changed")
            hashes[window + "/" + source.name] = before
            results.append(
                dict(
                    window=window,
                    name=name,
                    primary=bool(view["primary"]),
                    users=len(stats),
                    scored_requests=len(rows),
                    blind_loss_nats=view["blind_loss"],
                    aware_loss_nats=view["aware_loss"],
                    delta_nats=view["delta_nats"],
                    original_ci95_nats=original[:, 2].tolist(),
                    extended_ci95_nats=np.quantile(draws[:, 2], [0.025, 0.975]).tolist(),
                    within_window_family95_nats=np.quantile(draws[:, 2], [0.005, 0.995]).tolist(),
                    two_window_family95_nats=np.quantile(draws[:, 2], [0.0025, 0.9975]).tolist(),
                    reconstruction_max_abs_error=error,
                )
            )
            if view["primary"]:
                primary_users[window] = {x["user_hash"] for x in rows}
            print(
                json.dumps(dict(window=window, view=name, status="RECONSTRUCTED_AND_RESAMPLED")),
                flush=True,
            )
    for (_, _, path), ref in zip(inputs, references):
        if (
            paired.digest(path)
            != hashes[("original" if ref is references[0] else "shared") + "_reference_results"]
        ):
            raise ValueError("Reference results changed")
    payload = dict(
        schema="rolemap.two_window_sensitivity.v1",
        status="COMPLETE",
        draws=args.draws,
        within_window_family_size=5,
        combined_family_size=10,
        nominal_family_coverage=0.95,
        within_window_marginal_coverage=0.99,
        combined_marginal_coverage=0.995,
        primary="gensar_shared2",
        primary_users_in_both_windows=len(primary_users["original"] & primary_users["shared"]),
        max_original_reconstruction_error=max_error,
        source_sha256=hashes,
        code_sha256=paired.digest(__file__),
        paired_bootstrap_code_sha256=paired.digest(paired.__file__),
        numpy=np.__version__,
        synthetic_checks=checks,
        results=results,
        seconds=time.monotonic() - started,
        scope="Retrospective fixed-cohort, fixed-map and fixed-fit conditional bootstrap; approximate coverage. Shared users and source reuse do not imply independent replications. No new neural training or primary switch.",
    )
    args.out.mkdir(parents=True)
    (args.out / "TWO_WINDOW_SENSITIVITY.json").write_text(json.dumps(payload, indent=2) + "\n")
    with (args.out / "TWO_WINDOW_SENSITIVITY.csv").open("w", newline="") as handle:
        fields = [
            "window",
            "view",
            "primary",
            "delta_nats",
            "ci95_low",
            "ci95_high",
            "within5_low",
            "within5_high",
            "across10_low",
            "across10_high",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in results:
            writer.writerow(
                dict(
                    window=row["window"],
                    view=row["name"],
                    primary=row["primary"],
                    delta_nats=row["delta_nats"]["macro"],
                    ci95_low=row["original_ci95_nats"][0],
                    ci95_high=row["original_ci95_nats"][1],
                    within5_low=row["within_window_family95_nats"][0],
                    within5_high=row["within_window_family95_nats"][1],
                    across10_low=row["two_window_family95_nats"][0],
                    across10_high=row["two_window_family95_nats"][1],
                )
            )
    print(
        json.dumps(
            {
                k: payload[k]
                for k in ["status", "draws", "max_original_reconstruction_error", "seconds"]
            }
        )
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original-scores", type=Path, required=True)
    p.add_argument("--original-results", type=Path, required=True)
    p.add_argument("--shared-scores", type=Path, required=True)
    p.add_argument("--shared-results", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--draws", type=int, default=40000)
    args = p.parse_args()
    if args.draws < 40000:
        p.error("This protocol requires at least 40,000 draws")
    compare(args)


if __name__ == "__main__":
    main()
