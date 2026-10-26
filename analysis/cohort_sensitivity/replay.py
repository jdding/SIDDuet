#!/usr/bin/env python3
"""Replay training-only item eligibility on the two fixed Qilin windows."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ENGINE = HERE.parent / "reuse_validation" / "allocation_forecast.py"
spec = importlib.util.spec_from_file_location("allocation", ENGINE)
af = importlib.util.module_from_spec(spec)
spec.loader.exec_module(af)


def cached_fit(tr, va, m):
    counts, totals = af.count_training(tr, m)
    mass = counts.sum(axis=1)
    balanced = (
        (counts * (mass.sum() / (2 * mass))[:, None]).sum(axis=0)
        if np.all(mass > 0)
        else counts.sum(axis=0)
    )
    blind = []
    for kind, c in [("pooled", counts.sum(axis=0)), ("balanced", balanced)]:
        if kind == "balanced" and (not np.all(mass > 0)):
            continue
        for alpha in af.GRID:
            p = af.categorical(c, m, alpha)
            probs = np.vstack([p, p])
            blind.append(
                dict(
                    kind=kind,
                    alpha=alpha,
                    probabilities=probs,
                    validation=af.summarize_losses(af.request_losses(va, probs), va),
                )
            )
    b = af.choose(blind)
    aware = []
    for alpha in af.GRID:
        probs = np.vstack([af.categorical(c, m, alpha) for c in counts])
        aware.append(
            dict(
                kind="separate",
                alpha=alpha,
                probabilities=probs,
                validation=af.summarize_losses(af.request_losses(va, probs), va),
            )
        )
    for beta in af.GRID:
        probs = (counts + beta * b["probabilities"]) / (totals[:, m.group] + beta)
        aware.append(
            dict(
                kind="shrinkage",
                beta=beta,
                probabilities=probs,
                validation=af.summarize_losses(af.request_losses(va, probs), va),
            )
        )
    aware.append(
        dict(
            kind="fallback",
            source=b["kind"],
            alpha=b["alpha"],
            probabilities=b["probabilities"],
            validation=b["validation"],
        )
    )
    a = af.choose(aware, aware=True)
    for model in [b, a]:
        af.verify_probabilities(model["probabilities"], m)
    return dict(counts=counts, totals=totals, blind=b, aware=a, candidates=blind + aware)


def meta(f):
    return {z: {k: v for k, v in f[z].items() if k != "probabilities"} for z in ["blind", "aware"]}


def rolemean(x, en):
    return af.summarize_losses(x, en)


def delta(en, f):
    return af.request_losses(en, f["blind"]["probabilities"]) - af.request_losses(
        en, f["aware"]["probabilities"]
    )


def boot(en, columns, draws, seed, family, user_population):
    users = sorted(user_population)
    ui = {u: i for i, u in enumerate(users)}
    idx = np.asarray([ui[r["user_hash"]] for r in en["rows"]])
    k = len(columns)
    stats = np.zeros((len(users), 2, k + 1))
    for r in range(2):
        mask = en["request_roles"] == r
        stats[:, r, -1] = np.bincount(idx[mask], minlength=len(users))
        for j, x in enumerate(columns):
            stats[:, r, j] = np.bincount(idx[mask], weights=x[mask], minlength=len(users))
    rng = np.random.default_rng(seed)
    samples = []
    invalid = 0
    for start in range(0, draws, 100):
        size = min(100, draws - start)
        mult = np.zeros((size, len(users)))
        for i in range(size):
            mult[i] = np.bincount(
                rng.integers(0, len(users), size=len(users)), minlength=len(users)
            )
        sums = np.einsum("bu,urk->brk", mult, stats, optimize=True)
        valid = (sums[:, :, -1] > 0).all(axis=1)
        invalid += int((~valid).sum())
        samples.append((sums[valid, :, :-1] / sums[valid, :, -1, None]).mean(axis=1))
    x = np.concatenate(samples)
    return dict(
        users=len(users),
        draws=draws,
        valid_draws=len(x),
        invalid_draws=invalid,
        seed=seed,
        fixed_fits_and_groups=True,
        intervals=[
            dict(
                pointwise95=np.quantile(x[:, j], [0.025, 0.975]).tolist(),
                family95=np.quantile(
                    x[:, j], [0.025 / family, 0.975 + 0.025 * (1 - 1 / family)]
                ).tolist(),
            )
            for j in range(k)
        ],
    )


def user_coverage(rows, en):
    return {
        z: {
            r: dict(
                source_users=len({x["user_hash"] for x in rows[z] if x["role"] == r}),
                scored_users=len({x["user_hash"] for x in en[z]["rows"] if x["role"] == r}),
            )
            for r in af.ROLES
        }
        for z in rows
    }


def eligible_items(training_rows, catalog):
    """Require an earlier exposure in each task within the fixed catalog."""
    observed = {
        role: {
            item for row in training_rows if row["role"] == role for item in row["exposed_item_ids"]
        }
        for role in af.ROLES
    }
    return set(catalog) & observed["search"] & observed["rec"]


def check_bindings(inputs, contract):
    paths = [(REPO / name, digest) for name, digest in contract["repository_sha256"].items()]
    for window, directory in inputs.items():
        paths.extend(
            (directory / (split + ".jsonl"), digest)
            for split, digest in contract["windows"][window]["sha256"].items()
        )
    for path, expected in paths:
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Input does not match the fixed replay: " + str(path))


def run_window(name, directory, index, contract):
    catalog = set(map(str, json.loads((REPO / "data/native_exports/cohort.json").read_text())))
    mapping_spec = dict(
        name="gensar_shared2",
        path=str(REPO / "data/native_exports/native_maps/gensar_semantic.csv"),
        depth=2,
    )
    original = af.Mapping.from_spec(mapping_spec, catalog)
    rows = {
        split: af.read_requests(directory / (split + ".jsonl"), split)
        for split in ("train", "validation")
    }
    restricted = af.Mapping.from_spec(mapping_spec, eligible_items(rows["train"], original.items))
    encoded = {split: af.encode(values, restricted) for split, values in rows.items()}
    fitted = cached_fit(encoded["train"], encoded["validation"], restricted)
    # Eligibility and estimator selection are fixed before audit observations enter scoring.
    rows["audit"] = af.read_requests(directory / "audit.jsonl", "audit")
    encoded["audit"] = af.encode(rows["audit"], restricted)
    original_audit = af.encode(rows["audit"], original)
    original_users = {row["user_hash"] for row in original_audit["rows"]}
    restricted_users = {row["user_hash"] for row in encoded["audit"]["rows"]}
    if not restricted_users <= original_users:
        raise ValueError("Restricted audit users escaped the original population")
    gain = delta(encoded["audit"], fitted)
    result = dict(
        user_coverage=user_coverage(rows, encoded),
        items=len(restricted.items),
        groups=len(restricted.sizes),
        collision_groups=int(np.sum(restricted.sizes > 1)),
        fit=meta(fitted),
        coverage={split: value["coverage"] for split, value in encoded.items()},
        gain=rolemean(gain, encoded["audit"]),
        loss={
            kind: rolemean(
                af.request_losses(encoded["audit"], fitted[kind]["probabilities"]), encoded["audit"]
            )
            for kind in ("blind", "aware")
        },
        bootstrap=boot(
            encoded["audit"],
            [gain],
            contract["bootstrap_draws"],
            contract["seed"] + index,
            contract["interval_family_endpoints"],
            original_users | restricted_users,
        ),
    )
    return dict(window=name, training_only=result)


def compare(actual, expected, path="root"):
    """Check every exported field, allowing only numerical roundoff."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or actual.keys() != expected.keys():
            raise ValueError("Different fields at " + path)
        for key in expected:
            compare(actual[key], expected[key], path + "." + key)
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise ValueError("Different lengths at " + path)
        for index, (left, right) in enumerate(zip(actual, expected)):
            compare(left, right, f"{path}[{index}]")
    elif isinstance(expected, float):
        if not np.isfinite(actual) or abs(actual - expected) > 1e-12:
            raise ValueError("Numerical mismatch at " + path)
    elif actual != expected:
        raise ValueError("Different value at " + path)


def self_test():
    rows = [
        dict(role="search", exposed_item_ids=["a", "b", "c"], user_hash="u", request_hash="s"),
        dict(role="rec", exposed_item_ids=["b", "d"], user_hash="u", request_hash="r"),
    ]
    assert eligible_items(rows, ["a", "b", "c", "d"]) == {"b"}
    mapping = af.Mapping("synthetic", {"a": "0", "b": "0", "c": "1", "d": "1"})
    encoded = af.encode(rows, mapping)
    assert np.allclose(np.bincount(encoded["requests"], weights=encoded["weights"]), 1)
    fitted = cached_fit(encoded, encoded, mapping)
    for kind in ("blind", "aware"):
        af.verify_probabilities(fitted[kind]["probabilities"], mapping)
    equal = {
        kind: {"probabilities": np.vstack([mapping.uniform, mapping.uniform])}
        for kind in ("blind", "aware")
    }
    assert np.all(delta(encoded, equal) == 0)
    interval = boot(encoded, [delta(encoded, equal)], 20, 1, 4, {"u"})
    assert interval["intervals"][0]["family95"] == [0.0, 0.0]
    compare({"x": [1.0]}, {"x": [1.0]})
    try:
        compare({"x": [1.1]}, {"x": [1.0]})
    except ValueError:
        pass
    else:
        raise AssertionError("Comparator accepted a changed result")
    print("PASS_COHORT_SELF_TEST")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--first-inputs", type=Path)
    parser.add_argument("--additional-inputs", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not all([args.first_inputs, args.additional_inputs, args.output]):
        parser.error("Provide both reconstructed input directories and a new output directory")
    output = args.output.expanduser().resolve()
    if output == REPO or REPO in output.parents:
        parser.error("Keep replay outputs outside the source checkout")
    if output.exists():
        parser.error("Output directory must be new")
    inputs = {
        "first": args.first_inputs.expanduser().resolve(),
        "additional": args.additional_inputs.expanduser().resolve(),
    }
    contract = json.loads((HERE / "INPUTS.json").read_text())
    check_bindings(inputs, contract)
    results = dict(
        schema="sidduet.training_cohort_sensitivity.v1",
        posthoc=True,
        windows=[
            run_window(name, directory, index, contract)
            for index, (name, directory) in enumerate(inputs.items())
        ],
    )
    check_bindings(inputs, contract)
    expected = json.loads((REPO / "reports/cohort_sensitivity/RESULTS.json").read_text())
    compare(results, expected)
    output.mkdir(parents=True)
    af.write_json(output / "RESULTS.json", results)
    af.write_json(
        output / "REPLAY.json",
        dict(
            status="PASS",
            tolerance=1e-12,
            windows=list(inputs),
            code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            engine_sha256=hashlib.sha256(ENGINE.read_bytes()).hexdigest(),
            numpy=np.__version__,
            request_rows_exported=False,
        ),
    )
    print("PASS_COHORT_REPLAY")


if __name__ == "__main__":
    main()
