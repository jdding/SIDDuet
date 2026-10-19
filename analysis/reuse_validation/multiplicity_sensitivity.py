#!/usr/bin/env python3
"""Check frozen exposure losses and report a Bonferroni bootstrap sensitivity."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import time

import numpy as np

ROLES = ("search", "rec")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_scores(path):
    rows = []
    seen = set()
    with Path(path).open() as handle:
        for line in handle:
            row = json.loads(line)
            if row["role"] not in ROLES or not row["user_hash"]:
                raise ValueError("Each score needs a known role and a stable user key")
            key = row["request_hash"]
            if key in seen:
                raise ValueError("Duplicate request in a view")
            seen.add(key)
            values = [float(row[name]) for name in ("blind_loss", "aware_loss")]
            if not np.isfinite(values).all():
                raise ValueError("Non-finite loss")
            if abs(values[0] - values[1] - float(row["delta"])) > 1e-12:
                raise ValueError("Recorded loss difference disagrees")
            rows.append(row)
    if {row["role"] for row in rows} != set(ROLES):
        raise ValueError("Both tasks need scored requests")
    return rows


def user_statistics(rows):
    users = sorted({row["user_hash"] for row in rows})
    index = {user: i for i, user in enumerate(users)}
    stats = np.zeros((len(users), 6), dtype=float)
    for row in rows:
        offset = ROLES.index(row["role"]) * 3
        stats[index[row["user_hash"]], offset : offset + 3] += (
            float(row["blind_loss"]),
            float(row["aware_loss"]),
            1.0,
        )
    return stats


def differences(sums):
    search = sums[0] / sums[2] - sums[1] / sums[2]
    rec = sums[3] / sums[5] - sums[4] / sums[5]
    return np.asarray([search, rec, (search + rec) / 2])


def bootstrap(stats, draws, seed):
    # The sorted users, random stream and six-column reduction match the original engine.
    rng = np.random.default_rng(seed)
    samples = []
    undefined = 0
    for _ in range(draws):
        weights = np.bincount(rng.integers(0, len(stats), size=len(stats)), minlength=len(stats))
        sums = weights @ stats
        if not sums[2] or not sums[5]:
            undefined += 1
            continue
        samples.append(differences(sums))
    return np.asarray(samples), undefined


def self_test():
    rows = []
    for user, effect in [("one", 0.1), ("two", 0.4), ("three", 0.7)]:
        for role, delta in [("search", effect), ("rec", -effect)]:
            rows.append(dict(user_hash=user, role=role, blind_loss=1.0 + delta, aware_loss=1.0))
    samples, missing = bootstrap(user_statistics(rows), 1000, 17)
    assert not missing
    # Opposite task effects cancel on every jointly resampled user draw.
    assert np.max(np.abs(samples[:, 2])) < 1e-12
    narrow = np.quantile(samples[:, 0], [0.025, 0.975])
    wide = np.quantile(samples[:, 0], [0.005, 0.995])
    assert wide[0] <= narrow[0] and wide[1] >= narrow[1]
    assert np.ptp(samples[:, 0]) > 0.1
    return dict(paired_user_cancellation=True, wider_interval_contains_narrower=True)


def analyze(scores_dir, reference_path, out, draws=20000, alpha=0.05):
    started = time.monotonic()
    reference = json.loads(Path(reference_path).read_text())
    views = [row for row in reference["results"] if row["status"] == "EVALUATED"]
    controls = [
        row["name"] for row in reference["results"] if row["status"] == "NO_COLLISION_CONTROL"
    ]
    family_size = len(views)
    if not family_size:
        raise ValueError("No estimable views")
    original_draws = int(reference["bootstrap_draws"])
    seed = int(reference["bootstrap_seed"])
    if draws < original_draws:
        raise ValueError("Need at least the original draw count to verify reconstruction")
    out = Path(out)
    if out.exists():
        raise ValueError("Choose a new output directory")
    checks = self_test()
    results = []
    max_error = 0.0
    input_hashes = {}
    for view in views:
        name = view["name"]
        if Path(name).name != name or name in (".", ".."):
            raise ValueError("View names cannot be paths")
        source = Path(scores_dir) / (name + "_scores.jsonl")
        before = digest(source)
        rows = read_scores(source)
        stats = user_statistics(rows)
        samples, missing = bootstrap(stats, draws, seed)
        if missing:
            raise ValueError("A bootstrap draw omits a task; an explicit policy is required")
        original = np.quantile(samples[:original_draws], [0.025, 0.975], axis=0)
        point = differences(stats.sum(axis=0))
        errors = []
        for j, role in enumerate(("search", "rec", "macro")):
            errors.extend(abs(original[:, j] - view["bootstrap"]["intervals"][role]))
            errors.append(abs(point[j] - view["delta_nats"][role]))
        error = float(max(errors))
        max_error = max(max_error, error)
        if error > 1e-12 or len(stats) != view["bootstrap"]["users"]:
            raise ValueError("Original estimate or interval reconstruction failed: " + name)
        quantiles = [alpha / (2 * family_size), 1 - alpha / (2 * family_size)]
        adjusted = np.quantile(samples[:, 2], quantiles)
        marginal = np.quantile(samples[:, 2], [0.025, 0.975])
        if digest(source) != before:
            raise ValueError("Input changed during analysis")
        input_hashes[source.name] = before
        results.append(
            dict(
                name=name,
                primary=bool(view["primary"]),
                users=len(stats),
                scored_requests=len(rows),
                delta_nats=float(view["delta_nats"]["macro"]),
                original_ci95_nats=original[:, 2].tolist(),
                extended_ci95_nats=marginal.tolist(),
                bonferroni_interval_nats=adjusted.tolist(),
                bonferroni_excludes_zero=bool(adjusted[0] > 0 or adjusted[1] < 0),
                reconstruction_max_abs_error=error,
            )
        )
    payload = dict(
        schema="rolemap.multiplicity_sensitivity.v1",
        status="PASS_ORIGINAL_RECONSTRUCTION_AND_MULTIPLICITY_SENSITIVITY",
        analysis_status="posthoc_sensitivity_of_previously_reported_audit",
        family_size=family_size,
        excluded_no_collision_controls=controls,
        method="Bonferroni marginal percentile user-cluster bootstrap intervals",
        nominal_family_coverage=1 - alpha,
        marginal_interval_coverage=1 - alpha / family_size,
        interval_quantiles=[alpha / (2 * family_size), 1 - alpha / (2 * family_size)],
        draws=draws,
        original_draws_reproduced=original_draws,
        seed=seed,
        reconstruction_max_abs_error=max_error,
        source_score_sha256=input_hashes,
        reference_results_sha256=digest(reference_path),
        analysis_code_sha256=digest(__file__),
        runtime=dict(numpy=np.__version__),
        synthetic_checks=checks,
        results=results,
        limits="Conditional on fixed maps, fits, cohort and window; approximate bootstrap "
        "family coverage. More draws add no observations. No primary switch or p-values.",
        new_training=False,
        model_calls=0,
        elapsed_seconds=time.monotonic() - started,
    )
    out.mkdir(parents=True)
    (out / "MULTIPLICITY_SENSITIVITY.json").write_text(json.dumps(payload, indent=2) + "\n")
    fields = [
        "name",
        "primary",
        "delta_nats",
        "original_ci95_low",
        "original_ci95_high",
        "bonferroni_low",
        "bonferroni_high",
        "bonferroni_excludes_zero",
    ]
    with (out / "MULTIPLICITY_SENSITIVITY.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in results:
            writer.writerow(
                dict(
                    name=row["name"],
                    primary=row["primary"],
                    delta_nats=row["delta_nats"],
                    original_ci95_low=row["original_ci95_nats"][0],
                    original_ci95_high=row["original_ci95_nats"][1],
                    bonferroni_low=row["bonferroni_interval_nats"][0],
                    bonferroni_high=row["bonferroni_interval_nats"][1],
                    bonferroni_excludes_zero=row["bonferroni_excludes_zero"],
                )
            )
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores-dir", type=Path)
    parser.add_argument("--reference-results", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--draws", type=int, default=20000)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test()))
        return
    if not all([args.scores_dir, args.reference_results, args.out]):
        parser.error("--scores-dir, --reference-results and --out are required")
    result = analyze(args.scores_dir, args.reference_results, args.out, args.draws)
    print(
        json.dumps(
            {
                "status": result["status"],
                "family_size": result["family_size"],
                "draws": result["draws"],
                "max_reconstruction_error": result["reconstruction_max_abs_error"],
                "results": [
                    {
                        k: r[k]
                        for k in [
                            "name",
                            "delta_nats",
                            "bonferroni_interval_nats",
                            "bonferroni_excludes_zero",
                        ]
                    }
                    for r in result["results"]
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
