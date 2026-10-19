#!/usr/bin/env python3
"""Closed-form request-conditional exposure allocation; no clicks enter fitting.

fit reads train/validation only. evaluate verifies the frozen identity bindings
before opening test. The native maps are components/views, not model rankings.
"""

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
from collections import defaultdict
import numpy as np

ROLES = ("search", "rec")
GRID = (0.1, 1.0, 10.0, 100.0, 1000.0)
SEED = 20261019
BOOTSTRAPS = 2000
SCHEMA = "rolemap.allocation_forecast.v1"


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    os.replace(str(tmp), str(path))


def read_requests(path, expected_split):
    rows = []
    seen = set()
    with open(path) as f:
        for number, line in enumerate(f, 1):
            r = json.loads(line)
            if r["split"] != expected_split:
                raise ValueError("Wrong split at line %s" % number)
            if r["role"] == "recommendation":
                r["role"] = "rec"
            if r["role"] not in ROLES:
                raise ValueError("Unknown role")
            if r["request_hash"] in seen:
                raise ValueError("Duplicate request hash")
            seen.add(r["request_hash"])
            if not r["user_hash"]:
                raise ValueError("Missing user hash")
            start, end = float(r["timestamp_start"]), float(r["timestamp_end"])
            if not (math.isfinite(start) and math.isfinite(end) and start <= end):
                raise ValueError("Invalid timestamp interval")
            r["exposed_item_ids"] = sorted(set(str(x) for x in r["exposed_item_ids"]))
            r["timestamp_start"], r["timestamp_end"] = start, end
            rows.append(r)
    return rows


class Mapping:
    def __init__(self, name, records):
        self.name = name
        if not records:
            raise ValueError("Empty item-to-code mapping")
        self.items = sorted(records)
        self.item_index = {item: i for i, item in enumerate(self.items)}
        codes = sorted(set(records.values()))
        code_index = {code: i for i, code in enumerate(codes)}
        self.group = np.asarray([code_index[records[i]] for i in self.items], dtype=np.int32)
        self.sizes = np.bincount(self.group, minlength=len(codes))
        self.uniform = 1.0 / self.sizes[self.group]
        self.collision = self.sizes[self.group] > 1
        self.codes = codes

    @classmethod
    def from_spec(cls, spec, universe=None):
        records = {}
        with open(spec["path"], newline="") as f:
            for row in csv.DictReader(f):
                item = str(row["item_id"])
                if universe is not None and item not in universe:
                    continue
                tokens = json.loads(row["sid"])
                if not isinstance(tokens, list) or not tokens:
                    raise ValueError("SID must be a nonempty token list")
                depth = spec.get("depth")
                if depth is not None:
                    if len(tokens) < depth:
                        raise ValueError("SID shorter than requested depth")
                    tokens = tokens[:depth]
                # Type-tagged JSON avoids mixing integer and string tokens.
                code = json.dumps(tokens, separators=(",", ":"), ensure_ascii=False)
                if item in records:
                    raise ValueError("Duplicate item in mapping")
                records[item] = code
        if universe is not None and set(records) != universe:
            raise ValueError("Mapping does not cover the exact declared cohort")
        return cls(spec["name"], records)


def encode(rows, mapping):
    """One flattened target vector per mapping, reused by every hyperparameter."""
    flat_items, flat_weights, flat_requests = [], [], []
    scored = []
    coverage = {
        r: dict(
            source_requests=0,
            mapped_requests=0,
            scored_requests=0,
            singleton_only_requests=0,
            no_mapped_requests=0,
            mapped_member_appearances=0,
            collision_member_appearances=0,
        )
        for r in ROLES
    }
    for row in rows:
        cov = coverage[row["role"]]
        cov["source_requests"] += 1
        members = [
            mapping.item_index[x] for x in row["exposed_item_ids"] if x in mapping.item_index
        ]
        cov["mapped_member_appearances"] += len(members)
        if not members:
            cov["no_mapped_requests"] += 1
            continue
        cov["mapped_requests"] += 1
        groups = defaultdict(list)
        for item in members:
            if mapping.collision[item]:
                groups[int(mapping.group[item])].append(item)
        if not groups:
            cov["singleton_only_requests"] += 1
            continue
        request_index = len(scored)
        scored.append(row)
        cov["scored_requests"] += 1
        for group in sorted(groups):
            values = groups[group]
            weight = 1.0 / (len(groups) * len(values))
            flat_items.extend(values)
            flat_weights.extend([weight] * len(values))
            flat_requests.extend([request_index] * len(values))
            cov["collision_member_appearances"] += len(values)
    request_roles = np.asarray([ROLES.index(x["role"]) for x in scored], dtype=np.int8)
    return dict(
        items=np.asarray(flat_items, dtype=np.int32),
        weights=np.asarray(flat_weights, dtype=np.float64),
        requests=np.asarray(flat_requests, dtype=np.int32),
        request_roles=request_roles,
        rows=scored,
        coverage=coverage,
    )


def count_training(encoded, mapping):
    counts = np.zeros((2, len(mapping.items)), dtype=np.float64)
    flat_roles = encoded["request_roles"][encoded["requests"]]
    for role in range(2):
        selected = flat_roles == role
        counts[role] = np.bincount(
            encoded["items"][selected],
            weights=encoded["weights"][selected],
            minlength=len(mapping.items),
        )
    totals = np.vstack(
        [np.bincount(mapping.group, weights=c, minlength=len(mapping.sizes)) for c in counts]
    )
    return counts, totals


def categorical(counts, mapping, alpha):
    totals = np.bincount(mapping.group, weights=counts, minlength=len(mapping.sizes))
    return (counts + alpha * mapping.uniform) / (totals[mapping.group] + alpha)


def verify_probabilities(probs, mapping):
    probs = np.asarray(probs, dtype=float)
    if (
        probs.shape != (2, len(mapping.items))
        or not np.all(np.isfinite(probs))
        or np.any(probs <= 0)
    ):
        raise ValueError("Invalid predictive probabilities")
    for p in probs:
        totals = np.bincount(mapping.group, weights=p, minlength=len(mapping.sizes))
        if not np.allclose(totals, 1.0, rtol=1e-11, atol=1e-11):
            raise ValueError("Predictive probabilities do not normalize within group")


def request_losses(encoded, probabilities):
    if not len(encoded["rows"]):
        return np.asarray([], dtype=float)
    roles = encoded["request_roles"][encoded["requests"]]
    targets = probabilities[roles, encoded["items"]]
    if np.any(targets <= 0):
        raise ValueError("Nonpositive probability")
    return np.bincount(
        encoded["requests"],
        weights=encoded["weights"] * -np.log(targets),
        minlength=len(encoded["rows"]),
    )


def summarize_losses(losses, encoded):
    means = {}
    for role, name in enumerate(ROLES):
        x = losses[encoded["request_roles"] == role]
        means[name] = float(np.mean(x)) if len(x) else None
    means["macro"] = (
        sum(means[r] for r in ROLES) / 2 if all(means[r] is not None for r in ROLES) else None
    )
    return means


def choose(candidates, aware=False):
    valid = [c for c in candidates if c["validation"]["macro"] is not None]
    if not valid:
        raise ValueError("Both roles need scored validation requests; no macro selection possible")

    # Exact floating comparison, then declared deterministic complexity tie-break.
    def key(c):
        if not aware:
            complexity = (0 if c["kind"] == "pooled" else 1, c["alpha"])
        elif c["kind"] == "fallback":
            complexity = (0, 0)
        elif c["kind"] == "shrinkage":
            complexity = (1, -c["beta"])
        else:
            complexity = (2, c["alpha"])
        return (c["validation"]["macro"], complexity)

    return min(valid, key=key)


def fit_view(train, validation, mapping):
    tr, va = encode(train, mapping), encode(validation, mapping)
    if not np.any(mapping.collision):
        return dict(
            name=mapping.name,
            status="NO_COLLISION_CONTROL",
            train_coverage=tr["coverage"],
            validation_coverage=va["coverage"],
            items=mapping.items,
            group=mapping.group.tolist(),
            groups=len(mapping.sizes),
            collision_groups=0,
        )
    counts, totals = count_training(tr, mapping)
    request_mass = counts.sum(axis=1)
    balanced_available = bool(np.all(request_mass > 0))
    balanced = (
        (counts * (request_mass.sum() / (2 * request_mass))[:, None]).sum(axis=0)
        if balanced_available
        else counts.sum(axis=0)
    )
    blind = []
    for kind, c in [("pooled", counts.sum(axis=0)), ("balanced", balanced)]:
        if kind == "balanced" and not balanced_available:
            continue
        for alpha in GRID:
            p = categorical(c, mapping, alpha)
            probs = np.vstack([p, p])
            blind.append(
                dict(
                    kind=kind,
                    alpha=alpha,
                    probabilities=probs,
                    validation=summarize_losses(request_losses(va, probs), va),
                )
            )
    selected_blind = choose(blind)
    aware = []
    for alpha in GRID:
        probs = np.vstack([categorical(c, mapping, alpha) for c in counts])
        aware.append(
            dict(
                kind="separate",
                alpha=alpha,
                probabilities=probs,
                validation=summarize_losses(request_losses(va, probs), va),
            )
        )
    for beta in GRID:
        probs = (counts + beta * selected_blind["probabilities"]) / (
            totals[:, mapping.group] + beta
        )
        aware.append(
            dict(
                kind="shrinkage",
                beta=beta,
                probabilities=probs,
                validation=summarize_losses(request_losses(va, probs), va),
            )
        )
    aware.append(
        dict(
            kind="fallback",
            source=selected_blind["kind"],
            alpha=selected_blind["alpha"],
            probabilities=selected_blind["probabilities"],
            validation=selected_blind["validation"],
        )
    )
    selected_aware = choose(aware, aware=True)
    for model in (selected_blind, selected_aware):
        verify_probabilities(model["probabilities"], mapping)

    def metadata(c):
        return {k: v for k, v in c.items() if k != "probabilities"}

    return dict(
        name=mapping.name,
        status="FITTED",
        items=mapping.items,
        group=mapping.group.tolist(),
        groups=len(mapping.sizes),
        collision_groups=int(np.sum(mapping.sizes > 1)),
        train_coverage=tr["coverage"],
        validation_coverage=va["coverage"],
        train_role_request_mass=request_mass.tolist(),
        balanced_available=balanced_available,
        train_supported_groups_by_role=[int(np.sum(x > 0)) for x in totals],
        train_any_supported_groups=int(np.sum(totals.sum(axis=0) > 0)),
        train_counts=counts.tolist(),
        selected_blind=metadata(selected_blind),
        selected_aware=metadata(selected_aware),
        validation_candidates=[metadata(x) for x in blind + aware],
        blind_probabilities=selected_blind["probabilities"].tolist(),
        aware_probabilities=selected_aware["probabilities"].tolist(),
    )


def cluster_bootstrap(rows, blind_loss, aware_loss, draws=BOOTSTRAPS, seed=SEED):
    """Aggregate by user; one O(users) multiplicity vector per bootstrap draw."""
    users = sorted(set(r["user_hash"] for r in rows))
    if not users:
        return dict(status="NO_SCORED_USERS", users=0, intervals=None)
    ui = {u: n for n, u in enumerate(users)}
    stats = np.zeros((len(users), 6), dtype=float)
    for row, b, a in zip(rows, blind_loss, aware_loss):
        j = ROLES.index(row["role"]) * 3
        stats[ui[row["user_hash"]], j : j + 3] += (b, a, 1.0)
    rng = np.random.default_rng(seed)
    samples = []
    undefined = 0
    for _ in range(draws):
        multiplicity = np.bincount(
            rng.integers(0, len(users), size=len(users)), minlength=len(users)
        )
        sums = multiplicity @ stats
        if not sums[2] or not sums[5]:
            undefined += 1
            continue
        bs, ass = sums[0] / sums[2], sums[1] / sums[2]
        br, ar = sums[3] / sums[5], sums[4] / sums[5]
        samples.append([bs - ass, br - ar, ((bs - ass) + (br - ar)) / 2])
    intervals = None
    if samples:
        bounds = np.quantile(np.asarray(samples), [0.025, 0.975], axis=0)
        intervals = {
            name: bounds[:, j].tolist() for j, name in enumerate(("search", "rec", "macro"))
        }
    return dict(
        status="OK" if not undefined else "SOME_DRAWS_MISSING_ROLE",
        users=len(users),
        draws=draws,
        valid_draws=len(samples),
        undefined_role_draws=undefined,
        seed=seed,
        intervals=intervals,
    )


def common_window(rows):
    ranges = {}
    for role in ROLES:
        part = [r for r in rows if r["role"] == role]
        if not part:
            raise ValueError("Common-window fit requires both train roles")
        ranges[role] = [
            min(r["timestamp_start"] for r in part),
            max(r["timestamp_end"] for r in part),
        ]
    start, end = max(x[0] for x in ranges.values()), min(x[1] for x in ranges.values())
    if start > end:
        raise ValueError("No common train time window")
    selected = [r for r in rows if r["timestamp_start"] >= start and r["timestamp_end"] <= end]
    return selected, dict(
        role_ranges=ranges,
        common_range=[start, end],
        source_requests=len(rows),
        retained_requests=len(selected),
    )


def default_specs():
    previous = (
        Path(__file__).resolve().parents[2] / "WWW4_DECISION_VALIDATION_20261019" / "restricted"
    )
    semantic = previous / "native_gensar_export_r1/semantic_native_complete.csv"
    collab = previous / "native_gensar_export_r1/collaborate_native_complete.csv"
    specs = [
        dict(name="gensar_shared2", path=str(semantic), depth=2),
        dict(name="gensar_semantic_complete", path=str(semantic)),
        dict(name="gensar_collaborative_complete", path=str(collab)),
    ]
    for d in (1, 2, 3):
        specs.append(
            dict(
                name="gaoq_depth%d" % d,
                path=str(previous / ("native_gaoq_r1/gaoq_depth%d.csv" % d)),
            )
        )
    return dict(
        maps=specs,
        paired_shared_prefix=[dict(left=str(semantic), right=str(collab), depth=2)],
        universe=str(previous / "native_features_r1/item_ids.json"),
    )


def load_specs(args):
    data = (
        json.loads(Path(args.maps_manifest).read_text()) if args.maps_manifest else default_specs()
    )
    paths = set(x["path"] for x in data["maps"])
    for pair in data.get("paired_shared_prefix", []):
        paths.update((pair["left"], pair["right"]))

        def first(path):
            result = {}
            with open(path, newline="") as f:
                for row in csv.DictReader(f):
                    item = str(row["item_id"])
                    if item in result:
                        raise ValueError("Duplicate item in paired prefix export")
                    result[item] = json.loads(row["sid"])[: pair["depth"]]
            return result

        left, right = first(pair["left"]), first(pair["right"])
        if left != right:
            raise ValueError("Native complete views do not have identical shared prefixes")
    universe = None
    if data.get("universe"):
        universe = set(str(x) for x in json.load(open(data["universe"])))
        paths.add(data["universe"])
    return data, universe, sorted(paths)


def identities(args, map_paths, include_inputs=True):
    paths = [str(Path(__file__).resolve()), str(Path(args.protocol).resolve())] + map_paths
    if args.maps_manifest:
        paths.append(str(Path(args.maps_manifest).resolve()))
    if args.manifest:
        paths.append(str(Path(args.manifest).resolve()))
    if include_inputs:
        paths += [
            str((Path(args.input) / x).resolve()) for x in ("train.jsonl", "validation.jsonl")
        ]
    return {str(Path(p).resolve()): digest(p) for p in sorted(set(paths))}


def fit(args):
    started = time.time()
    specs, universe, map_paths = load_specs(args)
    before = identities(args, map_paths)
    export_manifest = json.load(open(args.manifest)) if args.manifest else None
    if export_manifest is not None:
        for split in ("train", "validation"):
            expected = export_manifest["outputs"][split]["sha256"]
            if digest(Path(args.input) / (split + ".jsonl")) != expected:
                raise ValueError("Exporter output binding mismatch: " + split)
    train = read_requests(Path(args.input) / "train.jsonl", "train")
    validation = read_requests(Path(args.input) / "validation.jsonl", "validation")
    if set(r["request_hash"] for r in train) & set(r["request_hash"] for r in validation):
        raise ValueError("Train/validation requests overlap")
    if (
        train
        and validation
        and max(r["timestamp_end"] for r in train) >= min(r["timestamp_start"] for r in validation)
    ):
        raise ValueError("Train and validation time intervals overlap")
    window = None
    if args.common_window:
        train, window = common_window(train)
    views = []
    for spec in specs["maps"]:
        mapping = Mapping.from_spec(spec, universe)
        views.append(fit_view(train, validation, mapping))
    if identities(args, map_paths) != before:
        raise ValueError("Inputs changed during fitting")
    frozen = dict(
        schema=SCHEMA,
        phase="FROZEN_WITHOUT_TEST_ACCESS",
        bindings=before,
        common_window=window,
        map_specs=specs,
        extraction_outputs=export_manifest.get("outputs", {}) if export_manifest else {},
        primary="gensar_shared2",
        views=views,
        alpha_beta_grid=list(GRID),
        train_request_hashes=sorted(r["request_hash"] for r in train),
        validation_request_hashes=sorted(r["request_hash"] for r in validation),
        validation_user_hashes=sorted(set(r["user_hash"] for r in validation)),
        train_max_timestamp=max(r["timestamp_end"] for r in train) if train else None,
        validation_max_timestamp=max(r["timestamp_end"] for r in validation)
        if validation
        else None,
        elapsed_seconds=time.time() - started,
        estimand="request-conditional exposure-allocation; natural-log loss; retrospective temporal validation",
    )
    out = Path(args.out)
    restricted = out / "restricted"
    restricted.mkdir(parents=True, exist_ok=True)
    os.chmod(restricted, 0o700)
    model_path = restricted / "FITTED.json"
    write_json(model_path, frozen)
    write_json(
        out / "FIT_RECEIPT.json",
        dict(
            schema=SCHEMA,
            model_path=str(model_path.resolve()),
            fitted_sha256=digest(model_path),
            bindings=before,
            test_accessed=False,
            common_window=window,
            elapsed_seconds=time.time() - started,
            validation=[
                {
                    k: v
                    for k, v in view.items()
                    if k
                    in (
                        "name",
                        "status",
                        "selected_blind",
                        "selected_aware",
                        "validation_candidates",
                        "train_coverage",
                        "validation_coverage",
                        "train_supported_groups_by_role",
                        "train_any_supported_groups",
                        "balanced_available",
                    )
                }
                for view in views
            ],
        ),
    )
    print(json.dumps(dict(status="FROZEN", fitted=str(model_path), seconds=time.time() - started)))


def evaluate(args):
    started = time.time()
    if not args.fitted:
        raise ValueError("--fitted and its sibling FIT_RECEIPT.json are required")
    model_path = Path(args.fitted).resolve()
    receipt_path = model_path.parent.parent / "FIT_RECEIPT.json"
    receipt = json.loads(Path(receipt_path).read_text())
    if receipt["fitted_sha256"] != digest(model_path) or receipt.get("test_accessed") is not False:
        raise ValueError("Frozen model receipt mismatch")
    frozen = json.loads(Path(model_path).read_text())
    if frozen["schema"] != SCHEMA or frozen["phase"] != "FROZEN_WITHOUT_TEST_ACCESS":
        raise ValueError("Not an admissible frozen fit")
    # Check every binding, including code/protocol/map/source manifest, before test.
    for path, expected in frozen["bindings"].items():
        if digest(path) != expected:
            raise ValueError("Frozen source binding mismatch: " + path)
    current_code = str(Path(__file__).resolve())
    if frozen["bindings"].get(current_code) != digest(current_code):
        raise ValueError("Evaluation engine differs from frozen fit")
    evaluation_split = getattr(args, "evaluation_split", "audit")
    test_path = Path(args.input) / (evaluation_split + ".jsonl")
    before = digest(test_path)
    expected = frozen.get("extraction_outputs", {}).get(evaluation_split, {}).get("sha256")
    evaluation_manifest_sha = None
    if args.manifest:
        evaluation_manifest = json.load(open(args.manifest))
        candidate = evaluation_manifest.get("outputs", {}).get(evaluation_split, {}).get("sha256")
        if candidate is not None:
            if expected is not None and expected != candidate:
                raise ValueError("Evaluation manifest disagrees with frozen heldout binding")
            expected = candidate
            evaluation_manifest_sha = digest(args.manifest)
    if expected is not None and before != expected:
        raise ValueError("Heldout export binding mismatch")
    test = read_requests(test_path, evaluation_split)
    trainval = set(frozen["train_request_hashes"]) | set(frozen["validation_request_hashes"])
    if any(r["request_hash"] in trainval for r in test):
        raise ValueError("Test request appears in fit/validation")
    if evaluation_split == "audit":
        tuning_users = set(frozen["validation_user_hashes"])
        if any(r["user_hash"] in tuning_users for r in test):
            raise ValueError("Audit and tuning users overlap")
        if (
            test
            and frozen["train_max_timestamp"] is not None
            and min(r["timestamp_start"] for r in test) <= frozen["train_max_timestamp"]
        ):
            raise ValueError("Train and audit time intervals overlap")
    elif (
        test
        and frozen["validation_max_timestamp"] is not None
        and min(r["timestamp_start"] for r in test) <= frozen["validation_max_timestamp"]
    ):
        raise ValueError("Validation and test time intervals overlap")
    out = Path(args.out)
    restricted = out / "restricted"
    restricted.mkdir(parents=True, exist_ok=True)
    os.chmod(restricted, 0o700)
    results, flat = [], []
    for view in frozen["views"]:
        records = {i: str(g) for i, g in zip(view["items"], view["group"])}
        mapping = Mapping(view["name"], records)
        # Serialized groups are numeric catalog order; reconstruct exactly.
        mapping.group = np.asarray(view["group"], dtype=np.int32)
        mapping.sizes = np.bincount(mapping.group)
        mapping.uniform = 1.0 / mapping.sizes[mapping.group]
        mapping.collision = mapping.sizes[mapping.group] > 1
        en = encode(test, mapping)
        if view["status"] == "NO_COLLISION_CONTROL":
            results.append(
                dict(
                    name=view["name"],
                    status="NO_COLLISION_CONTROL",
                    coverage=en["coverage"],
                    primary=False,
                    loss=None,
                    interval=None,
                )
            )
            continue
        blind, aware = (
            np.asarray(view["blind_probabilities"]),
            np.asarray(view["aware_probabilities"]),
        )
        verify_probabilities(blind, mapping)
        verify_probabilities(aware, mapping)
        bl, al = request_losses(en, blind), request_losses(en, aware)
        bs, ass = summarize_losses(bl, en), summarize_losses(al, en)
        delta = {
            k: bs[k] - ass[k] if bs[k] is not None and ass[k] is not None else None for k in bs
        }
        boot = cluster_bootstrap(en["rows"], bl, al)
        counts = np.asarray(view["train_counts"])
        support = counts.sum(axis=0)
        group_support = np.bincount(mapping.group, weights=support, minlength=len(mapping.sizes))
        cold = dict(
            member_appearances=int(np.sum(support[en["items"]] == 0)),
            group_member_appearances=int(np.sum(group_support[mapping.group[en["items"]]] == 0)),
        )
        for role, role_name in enumerate(ROLES):
            mask = en["request_roles"][en["requests"]] == role
            rs = np.bincount(mapping.group, weights=counts[role], minlength=len(mapping.sizes))
            cold[role_name + "_role_unseen_member_appearances"] = int(
                np.sum(counts[role, en["items"][mask]] == 0)
            )
            cold[role_name + "_role_unseen_group_member_appearances"] = int(
                np.sum(rs[mapping.group[en["items"][mask]]] == 0)
            )
        row_path = restricted / (view["name"] + "_scores.jsonl")
        with open(row_path, "w") as f:
            for row, b, a in zip(en["rows"], bl, al):
                f.write(
                    json.dumps(
                        dict(
                            request_hash=row["request_hash"],
                            user_hash=row["user_hash"],
                            role=row["role"],
                            blind_loss=float(b),
                            aware_loss=float(a),
                            delta=float(b - a),
                        )
                    )
                    + "\n"
                )
        result = dict(
            name=view["name"],
            status="EVALUATED",
            primary=view["name"] == frozen["primary"],
            coverage=en["coverage"],
            cold_support=cold,
            blind_loss=bs,
            aware_loss=ass,
            delta_nats=delta,
            bootstrap=boot,
            selected_blind=view["selected_blind"],
            selected_aware=view["selected_aware"],
        )
        results.append(result)
        for role in ("search", "rec", "macro"):
            ci = boot["intervals"][role] if boot["intervals"] else [None, None]
            flat.append(
                dict(
                    mapping=view["name"],
                    role=role,
                    blind_loss_nats=bs[role],
                    aware_loss_nats=ass[role],
                    improvement_nats=delta[role],
                    ci95_low=ci[0],
                    ci95_high=ci[1],
                )
            )
    if digest(test_path) != before:
        raise ValueError("Test changed during evaluation")
    write_json(
        out / "RESULTS.json",
        dict(
            schema=SCHEMA,
            fitted_sha256=digest(model_path),
            evaluation_split=evaluation_split,
            evaluation_sha256=before,
            evaluation_manifest_sha256=evaluation_manifest_sha,
            source_bindings=frozen["bindings"],
            common_window=frozen["common_window"],
            bootstrap_seed=SEED,
            bootstrap_draws=BOOTSTRAPS,
            results=results,
            elapsed_seconds=time.time() - started,
            note="Raw losses across granularities are not a method quality ranking.",
        ),
    )
    with open(out / "RESULTS.csv", "w", newline="") as f:
        names = [
            "mapping",
            "role",
            "blind_loss_nats",
            "aware_loss_nats",
            "improvement_nats",
            "ci95_low",
            "ci95_high",
        ]
        writer = csv.DictWriter(f, fieldnames=names)
        writer.writeheader()
        writer.writerows(flat)
    print(json.dumps(dict(status="EVALUATED", output=str(out), seconds=time.time() - started)))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", required=True, choices=("self-test", "fit", "evaluate"))
    p.add_argument("--input")
    p.add_argument("--out")
    p.add_argument("--fitted")
    p.add_argument("--evaluation-split", choices=("audit", "test"), default="audit")
    p.add_argument("--maps-manifest")
    p.add_argument("--manifest", help="Exporter source/provenance manifest; hashed before fit")
    p.add_argument(
        "--protocol", default=str(Path(__file__).resolve().parent.parent / "PROTOCOL.md")
    )
    p.add_argument("--common-window", action="store_true")
    args = p.parse_args()
    if args.mode == "self-test":
        import unittest

        suite = unittest.defaultTestLoader.discover(
            str(Path(__file__).parent), pattern="test_allocation_forecast.py"
        )
        success = unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()
        sys.exit(0 if success else 1)
    if not args.input or not args.out:
        p.error("--input and --out required")
    (fit if args.mode == "fit" else evaluate)(args)


if __name__ == "__main__":
    main()
