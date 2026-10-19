#!/usr/bin/env python3
"""Compare observed task allocations with fixed count-regrouping references."""

from __future__ import annotations
import argparse, csv, hashlib, itertools, json, math, os, platform, resource, sys, time
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
import numpy as np

PROFILE = "sr_sid_rolemap.topology.value_median.v2"
DATASETS = ("kuaisar", "qilin")
FAMILIES = ("grid", "rq-vae", "resid-gaoq")
REPS = 199
CASE_MEMBERSHIP = "367cfdc83b6ce1d93d9dea2010b5fb1621432ca84c83a1eced56756bae303d51"
EXPECTED_N = {"kuaisar": 97729, "qilin": 20540}
PERCENTILES = (0, 25, 50, 75, 90, 100)
METRICS = (
    "equal_group_jsd",
    "item_weighted_jsd",
    "observation_weighted_jsd",
    "equal_group_disjoint",
    "item_weighted_disjoint",
    "observation_weighted_disjoint",
)
SIZE_LABELS = ("2", "3-5", "6-20", "21-100", ">100")
SUPPORT_LABELS = ("1", "(1,5]", "(5,20]", "(20,100]", ">100")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def emit(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("x") as f:
        json.dump(obj, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")


def item_key(x):
    return (
        (0, int(x))
        if x.isascii() and x.isdigit() and (x == "0" or not x.startswith("0"))
        else (1, x)
    )


def integer_count(value):
    d = Decimal(value)
    if not d.is_finite() or d < 0 or d != d.to_integral_value():
        raise ValueError("supports must be finite nonnegative integer observation counts")
    n = int(d)
    if n > 2**53:
        raise ValueError("count exceeds exact binary64 aggregation range")
    return n


def jsd_rows(s, r):
    """Rows are groups, columns are members; zero simulated cells are allowed."""
    s = np.asarray(s, dtype=np.float64)
    r = np.asarray(r, dtype=np.float64)
    st, rt = s.sum(axis=-1, keepdims=True), r.sum(axis=-1, keepdims=True)
    if np.any(st <= 0) or np.any(rt <= 0):
        raise ValueError("group must have positive search and recommendation totals")
    p, q = s / st, r / rt
    m = (p + q) / 2
    contribution = np.zeros_like(p)
    for v in (p, q):
        mask = v > 0
        term = np.zeros_like(v)
        term[mask] = v[mask] * np.log2(v[mask] / m[mask])
        contribution += term / 2
    result = contribution.sum(axis=-1)
    if np.any(~np.isfinite(result)) or np.any(result < -1e-12) or np.any(result > 1 + 1e-12):
        raise ValueError("JSD outside numerical validity tolerance")
    return np.clip(result, 0, 1)


def group_stats(s, r, group, sizes):
    """One pass over items; no event array. Group labels are contiguous integers."""
    ng = len(sizes)
    s, r = np.asarray(s, dtype=np.int64), np.asarray(r, dtype=np.int64)
    st = np.bincount(group, weights=s, minlength=ng)
    rt = np.bincount(group, weights=r, minlength=ng)
    if np.any(st <= 0) or np.any(rt <= 0):
        raise ValueError("a complete common-item group lost a task total")
    p, q = s / st[group], r / rt[group]
    m = (p + q) / 2
    terms = np.zeros(len(s), dtype=np.float64)
    for v in (p, q):
        mask = v > 0
        terms[mask] += v[mask] * np.log2(v[mask] / m[mask]) / 2
    js = np.bincount(group, weights=terms, minlength=ng)
    if np.any(~np.isfinite(js)) or np.any(js < -1e-12) or np.any(js > 1 + 1e-12):
        raise ValueError("JSD outside numerical validity tolerance")
    js = np.clip(js, 0, 1)
    mxs = np.zeros(ng, dtype=np.int64)
    mxr = np.zeros(ng, dtype=np.int64)
    np.maximum.at(mxs, group, s)
    np.maximum.at(mxr, group, r)
    maxs, maxr = s == mxs[group], r == mxr[group]
    overlap = np.bincount(group, weights=maxs & maxr, minlength=ng).astype(np.int64)
    disjoint = overlap == 0
    return {
        "jsd": js,
        "disjoint": disjoint,
        "search": st,
        "rec": rt,
        "events": st + rt,
        "search_argmax_count": np.bincount(group, weights=maxs, minlength=ng).astype(np.int64),
        "rec_argmax_count": np.bincount(group, weights=maxr, minlength=ng).astype(np.int64),
        "argmax_overlap_count": overlap,
    }


def weighted_mean(v, w):
    den = float(np.sum(w))
    return None if den == 0 else float(np.dot(v, w) / den)


def means(js, disjoint, sizes, events, mask):
    if not np.any(mask):
        return {k: None for k in METRICS}
    j, d, n, e = js[mask], disjoint[mask].astype(float), sizes[mask], events[mask]
    return dict(
        zip(
            METRICS,
            (
                float(j.mean()),
                weighted_mean(j, n),
                weighted_mean(j, e),
                float(d.mean()),
                weighted_mean(d, n),
                weighted_mean(d, e),
            ),
        )
    )


def strata(sizes, observed):
    collision = sizes >= 2
    min_support = np.minimum(observed["search"], observed["rec"]) / sizes
    # Exact bounds in the frozen contract: [1,1], (1,5], (5,20], (20,100], >100.
    support = np.searchsorted(np.array([1, 5, 20, 100], dtype=float), min_support, side="left")
    if np.any(min_support < 1):
        raise ValueError("common-item support lower than one per member")
    size = np.searchsorted(np.array([2, 5, 20, 100]), sizes, side="left")
    output = {"all_collision_groups": collision}
    output.update({"size:" + k: collision & (size == i) for i, k in enumerate(SIZE_LABELS)})
    output.update(
        {"support:" + k: collision & (support == i) for i, k in enumerate(SUPPORT_LABELS)}
    )
    return output


def describe(observed, sizes, masks):
    result = {}
    for label, mask in masks.items():
        n = int(mask.sum())
        result[label] = {
            "groups": n,
            "items": int(sizes[mask].sum()),
            "search_observations": int(observed["search"][mask].sum()),
            "rec_observations": int(observed["rec"][mask].sum()),
            "disjoint_argmax_groups": int(observed["disjoint"][mask].sum()),
            "search_argmax_tied_groups": int((observed["search_argmax_count"][mask] > 1).sum()),
            "rec_argmax_tied_groups": int((observed["rec_argmax_count"][mask] > 1).sum()),
            "means": means(observed["jsd"], observed["disjoint"], sizes, observed["events"], mask),
            "jsd_percentiles": None
            if not n
            else dict(
                zip(
                    map(str, PERCENTILES),
                    map(float, np.percentile(observed["jsd"][mask], PERCENTILES)),
                )
            ),
        }
    return result


def empty_null(masks):
    return {label: {k: [] for k in METRICS} for label in masks}


def add_null(accum, stats, sizes, masks):
    for label, mask in masks.items():
        vals = means(stats["jsd"], stats["disjoint"], sizes, stats["events"], mask)
        for k in METRICS:
            accum[label][k].append(vals[k])


def summarize_null(accum, observed):
    output = {}
    for label, metrics in accum.items():
        output[label] = {}
        for name, values in metrics.items():
            if all(v is None for v in values):
                output[label][name] = {
                    "draws": len(values),
                    "mean": None,
                    "central_95pct": None,
                    "observed_minus_null_mean": None,
                }
            elif any(v is None for v in values):
                raise ValueError("simulation denominators changed")
            else:
                arr = np.array(values)
                obs = observed[label]["means"][name]
                output[label][name] = {
                    "draws": len(values),
                    "mean": float(arr.mean()),
                    "central_95pct": list(map(float, np.percentile(arr, [2.5, 97.5]))),
                    "observed_minus_null_mean": float(obs - arr.mean()),
                }
    return output


def hypergeom_control(s, r, group, sizes, masks, seed):
    rng = np.random.Generator(np.random.PCG64(seed))
    ng = len(sizes)
    alljs = np.full((REPS, ng), np.nan)
    alldisjoint = np.zeros((REPS, ng), dtype=bool)
    order = np.argsort(group, kind="stable")
    offsets = np.concatenate(([0], np.cumsum(sizes)))
    exact_marginal_checks = 0
    for g in np.flatnonzero(sizes >= 2):
        idx = order[offsets[g] : offsets[g + 1]]
        colors, nsample = s[idx] + r[idx], int(s[idx].sum())
        if int(colors.sum()) >= 10**9:
            raise ValueError("Control A marginal sampler refuses per-group total >= 1e9")
        sampled = rng.multivariate_hypergeometric(colors, nsample, size=REPS, method="marginals")
        other = colors[None, :] - sampled
        if not (
            np.all(sampled >= 0)
            and np.all(sampled <= colors)
            and np.all(sampled.sum(axis=1) == nsample)
            and np.all(other.sum(axis=1) == int(r[idx].sum()))
            and np.all(sampled + other == colors)
        ):
            raise ValueError("hypergeometric exact marginals violated")
        exact_marginal_checks += REPS
        alljs[:, g] = jsd_rows(sampled, other)
        smx, rmx = sampled.max(axis=1, keepdims=True), other.max(axis=1, keepdims=True)
        alldisjoint[:, g] = ~np.any((sampled == smx) & (other == rmx), axis=1)
    base = group_stats(s, r, group, sizes)
    accum = empty_null(masks)
    for b in range(REPS):
        add_null(
            accum,
            {"jsd": alljs[b], "disjoint": alldisjoint[b], "events": base["events"]},
            sizes,
            masks,
        )
    return accum, alljs, exact_marginal_checks


def support_bands(s, r):
    # bit_length avoids a floating log2 rounding at exact powers of two.
    n = s + r
    return np.fromiter((int(x).bit_length() - 1 for x in n), dtype=np.int64, count=len(n))


def paired_permutation_indices(bands, rng):
    indices = np.arange(len(bands), dtype=np.int64)
    for band in np.unique(bands):
        slots = np.flatnonzero(bands == band)
        indices[slots] = rng.permutation(slots)
    return indices


def empirical_p(observed, null):
    values = np.asarray(null, dtype=float)
    return float(
        min(
            1,
            2
            * min(
                (1 + np.count_nonzero(values >= observed)) / (len(values) + 1),
                (1 + np.count_nonzero(values <= observed)) / (len(values) + 1),
            ),
        )
    )


def bh(pvalues):
    order = np.argsort(pvalues, kind="stable")
    m = len(pvalues)
    out = np.zeros(m)
    current = 1.0
    for k in range(m - 1, -1, -1):
        i = order[k]
        current = min(current, pvalues[i] * m / (k + 1))
        out[i] = current
    return out.tolist()


def read_inputs(manifest):
    spec = json.loads(Path(manifest).read_text())
    assets = spec["assets"]
    if spec["profile_id"] != PROFILE:
        raise ValueError("wrong declared profile")
    byname = {Path(a["path"]).name: a for a in assets}
    chosen = [byname[d + "_topology_v2.csv"] for d in DATASETS] + [
        byname[f + "_normalized_sid.csv"] for f in FAMILIES
    ]
    for a in chosen:
        p = Path(a["path"])
        if p.stat().st_size != a["bytes"] or sha(p) != a["sha256"]:
            raise ValueError("declared input hash/length mismatch: " + p.name)
    top = {}
    for dataset in DATASETS:
        rows = {}
        for row in csv.DictReader(open(byname[dataset + "_topology_v2.csv"]["path"], newline="")):
            if row["dataset"] != dataset or row["profile_id"] != PROFILE:
                raise ValueError("dataset/profile mismatch")
            item = row["item_id"]
            if item in rows:
                raise ValueError("duplicate topology item")
            pair = integer_count(row["search_support"]), integer_count(row["rec_support"])
            if min(pair) < 1:
                raise ValueError("common-item support must be positive for both roles")
            rows[item] = pair
        ids = sorted(rows, key=item_key)
        if len(ids) != EXPECTED_N[dataset]:
            raise ValueError("unexpected topology universe size")
        values = np.array([rows[i] for i in ids], dtype=np.int64)
        if sum(int(x) for x in values.flat) > 2**53:
            raise ValueError("dataset total exceeds exact sum range")
        top[dataset] = {
            "ids": ids,
            "index": {x: i for i, x in enumerate(ids)},
            "s": values[:, 0],
            "r": values[:, 1],
        }
    for family in FAMILIES:
        seen = {d: {} for d in DATASETS}
        for row in csv.DictReader(open(byname[family + "_normalized_sid.csv"]["path"], newline="")):
            d, i, sid = row["dataset"], row["item_id"], row["sid"]
            if d not in top or i not in top[d]["index"] or not sid:
                raise ValueError("map outside declared common universe")
            if i in seen[d]:
                raise ValueError("duplicate SID map item")
            seen[d][i] = sid
        for dataset in DATASETS:
            ids = top[dataset]["ids"]
            if set(seen[dataset]) != set(ids):
                raise ValueError("mapping coverage incomplete")
            sids = sorted(set(seen[dataset].values()))
            sididx = {s: i for i, s in enumerate(sids)}
            groups = np.array([sididx[seen[dataset][i]] for i in ids], dtype=np.int64)
            sizes = np.bincount(groups, minlength=len(sids)).astype(np.int64)
            top[dataset][family] = {"groups": groups, "sizes": sizes, "sids": sids}
    return top, chosen


def check_admission(admission_dir, dataset, family, sizes, n):
    path = Path(admission_dir) / (dataset + "_" + family + ".json")
    payload = json.loads(path.read_text())
    summaries = [s for s in payload["dataset_summaries"] if s["dataset"] == dataset]
    if len(summaries) != 1:
        raise ValueError("expected single existing admission dataset")
    summary = summaries[0]
    actual = {
        "joined_items": n,
        "topology_items": n,
        "join_coverage": 1.0,
        "unique_sid_count": len(sizes),
        "unique_sid_ratio": round(len(sizes) / n, 6),
        "collision_rate": round(1 - len(sizes) / n, 6),
    }
    if summary["topology_profile_id"] != PROFILE or any(summary[k] != v for k, v in actual.items()):
        raise ValueError("existing admission counters mismatch")
    return {
        "path": str(path),
        "sha256": sha(path),
        "observed_matches": actual,
        "note": "Existing collision_rate is 1 - uniqueSID/items, distinct from item fraction in non-singleton groups.",
    }


def match_fixed_case(data, family, stats):
    if family != "resid-gaoq":
        return None
    groups, sizes = data[family]["groups"], data[family]["sizes"]
    for g in np.flatnonzero(sizes == 275):
        members = [data["ids"][i] for i in np.flatnonzero(groups == g)]
        digest = hashlib.sha256("".join(i + "\n" for i in members).encode()).hexdigest()
        if digest == CASE_MEMBERSHIP:
            v = float(stats["jsd"][g])
            population = stats["jsd"][sizes >= 2]
            return {
                "selection": "exact conserved archived membership SHA; no new group selection",
                "membership_sha256": digest,
                "group_size": 275,
                "search_observations": int(stats["search"][g]),
                "rec_observations": int(stats["rec"][g]),
                "jsd": v,
                "disjoint_argmax_sets": bool(stats["disjoint"][g]),
                "collision_groups_denominator": len(population),
                "percentile_fraction_strictly_below": float(np.mean(population < v)),
                "percentile_fraction_at_or_below": float(np.mean(population <= v)),
            }
    return None


def run(args):
    start = time.perf_counter()
    out = Path(args.out)
    restricted = Path(args.restricted_out)
    if out.exists() or restricted.exists():
        raise ValueError("real execution requires fresh output directories")
    script_hash = sha(__file__)
    manifest_hash = sha(args.inputs)
    contract_hash = sha(args.contract)
    if args.provenance_receipt:
        receipt_data = json.loads(Path(args.provenance_receipt).read_text())
        if (
            receipt_data.get("population_code_sha256") != script_hash
            or receipt_data.get("contract_sha256") != contract_hash
        ):
            raise ValueError("supplied receipt must bind this code and contract")
    out.mkdir(parents=True)
    restricted.mkdir(parents=True)
    data, assets = read_inputs(args.inputs)
    records = []
    internal = {}
    null_draws = {}
    extras = []
    case = None
    for di, dataset in enumerate(DATASETS):
        d = data[dataset]
        s, r = d["s"], d["r"]
        states = {}
        for fi, family in enumerate(FAMILIES):
            group, sizes = d[family]["groups"], d[family]["sizes"]
            stats = group_stats(s, r, group, sizes)
            masks = strata(sizes, stats)
            observed = describe(stats, sizes, masks)
            admission = check_admission(args.admissions, dataset, family, sizes, len(s))
            extras.append(admission)
            astart = time.perf_counter()
            anull, ajs, mchecks = hypergeom_control(
                s, r, group, sizes, masks, 20261018 + di * 3 + fi
            )
            rec = {
                "dataset": dataset,
                "mapping_family": family,
                "items": len(s),
                "sid_groups": len(sizes),
                "singleton_groups": int((sizes == 1).sum()),
                "singleton_items": int((sizes == 1).sum()),
                "collision_groups": int((sizes >= 2).sum()),
                "collision_items": int(sizes[sizes >= 2].sum()),
                "existing_admission_check": admission,
                "observed": observed,
                "control_A": {
                    "seed": 20261018 + di * 3 + fi,
                    "draws": REPS,
                    "exact_sample_marginal_checks": mchecks,
                    "elapsed_seconds": time.perf_counter() - astart,
                    "summaries": summarize_null(anull, observed),
                },
            }
            if dataset == "kuaisar" and family == "resid-gaoq":
                case = match_fixed_case(d, family, stats)
            states[family] = {
                "group": group,
                "sizes": sizes,
                "observed": stats,
                "masks": masks,
                "record": rec,
                "a_group_mean": np.nanmean(ajs[:, sizes >= 2], axis=0),
                "a_group_interval": np.nanpercentile(ajs[:, sizes >= 2], [2.5, 97.5], axis=0),
                "b_accum": empty_null(masks),
                "b_js": np.full((REPS, len(sizes)), np.nan),
            }
            null_draws[dataset + "/" + family] = {"A": anull}
            del ajs
            print(
                json.dumps(
                    {
                        "phase": "control_A_complete",
                        "dataset": dataset,
                        "family": family,
                        "elapsed_seconds": time.perf_counter() - start,
                    }
                ),
                flush=True,
            )
        bands = support_bands(s, r)
        rng = np.random.Generator(np.random.PCG64(20262018 + di))
        bstart = time.perf_counter()
        permutation_checks = 0
        for b in range(REPS):
            perm = paired_permutation_indices(bands, rng)
            if not (len(np.unique(perm)) == len(s) and np.all(bands[perm] == bands)):
                raise ValueError("Control B did not preserve support bands or global paired counts")
            permutation_checks += 1
            for family, state in states.items():
                stats = group_stats(s[perm], r[perm], state["group"], state["sizes"])
                add_null(state["b_accum"], stats, state["sizes"], state["masks"])
                state["b_js"][b] = stats["jsd"]
        for family, state in states.items():
            rec = state["record"]
            rec["control_B"] = {
                "seed": 20262018 + di,
                "draws": REPS,
                "dataset_permutations_shared_across_families": True,
                "global_pair_and_slot_support_band_checks": permutation_checks,
                "elapsed_dataset_seconds": time.perf_counter() - bstart,
                "stratum_membership": "fixed from observed groups",
                "summaries": summarize_null(state["b_accum"], rec["observed"]),
            }
            ov = rec["observed"]["all_collision_groups"]["means"]["equal_group_jsd"]
            nv = state["b_accum"]["all_collision_groups"]["equal_group_jsd"]
            rec["primary_control_B_two_sided_p"] = empirical_p(ov, nv)
            null_draws[dataset + "/" + family]["B"] = state["b_accum"]
            bjs = state["b_js"]
            collision = state["sizes"] >= 2
            bm = bjs[:, collision].mean(axis=0)
            bi = np.percentile(bjs[:, collision], [2.5, 97.5], axis=0)
            p = restricted / (dataset + "_" + family + "_groups.csv")
            cols = [
                "dataset",
                "mapping_family",
                "restricted_sid_group",
                "members",
                "search_observations",
                "rec_observations",
                "jsd",
                "argmax_disjoint",
                "search_argmax_count",
                "rec_argmax_count",
                "argmax_overlap_count",
                "A_mean_jsd",
                "A_q025_jsd",
                "A_q975_jsd",
                "B_mean_jsd",
                "B_q025_jsd",
                "B_q975_jsd",
            ]
            with p.open("x", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=cols)
                writer.writeheader()
                j = 0
                for g, n in enumerate(state["sizes"]):
                    st = state["observed"]
                    row = dict(
                        zip(
                            cols[:11],
                            [
                                dataset,
                                family,
                                d[family]["sids"][g],
                                int(n),
                                int(st["search"][g]),
                                int(st["rec"][g]),
                                float(st["jsd"][g]),
                                bool(st["disjoint"][g]),
                                int(st["search_argmax_count"][g]),
                                int(st["rec_argmax_count"][g]),
                                int(st["argmax_overlap_count"][g]),
                            ],
                        )
                    )
                    for k in cols[11:]:
                        row[k] = ""
                    if n >= 2:
                        row.update(
                            dict(
                                zip(
                                    cols[11:],
                                    [
                                        float(state["a_group_mean"][j]),
                                        float(state["a_group_interval"][0, j]),
                                        float(state["a_group_interval"][1, j]),
                                        float(bm[j]),
                                        float(bi[0, j]),
                                        float(bi[1, j]),
                                    ],
                                )
                            )
                        )
                        j += 1
                    writer.writerow(row)
            rec["restricted_group_table"] = {
                "basename": p.name,
                "sha256": sha(p),
                "rows": len(state["sizes"]),
            }
            records.append(rec)
        print(
            json.dumps(
                {
                    "phase": "control_B_complete",
                    "dataset": dataset,
                    "elapsed_seconds": time.perf_counter() - start,
                }
            ),
            flush=True,
        )
    if case is None:
        raise ValueError("archived fixed 275 member set not found; do not select a replacement")
    if case["search_observations"] != 514 or case["rec_observations"] != 1413:
        raise ValueError("fixed-case conservation failed")
    adjusted = bh([r["primary_control_B_two_sided_p"] for r in records])
    harmonic_six = sum(1 / k for k in range(1, 7))
    for rec, q in zip(records, adjusted):
        rec["primary_B_BH_adjusted_p_across_six"] = q
        rec["primary_B_BY_adjusted_p_dependency_sensitivity"] = min(1.0, q * harmonic_six)
    for asset in assets:
        if sha(asset["path"]) != asset["sha256"]:
            raise ValueError("input changed during analysis")
    if (
        sha(__file__) != script_hash
        or sha(args.inputs) != manifest_hash
        or sha(args.contract) != contract_hash
    ):
        raise ValueError("analysis code or declarations changed during execution")
    for extra in extras:
        if sha(extra["path"]) != extra["sha256"]:
            raise ValueError("admission metadata changed during analysis")
    result = {
        "schema": "sr_sid_rolemap.population_allocation_extension.v1",
        "status": "COMPLETE_VALIDITY_CHECKS_PASSED",
        "profile_id": PROFILE,
        "reps": REPS,
        "datasets": list(DATASETS),
        "mapping_families": list(FAMILIES),
        "jsd_definition": (
            "base2 JSD between normalized search/rec observation allocations over members of the "
            "same SID group; distinct from provider-label divergence"
        ),
        "primary_aggregation": "equal weight per collision group; singleton groups excluded",
        "support_stratum_definition": "min(group search total, group recommendation total)/group size; [1,1], (1,5], (5,20], (20,100], >100",
        "inference": (
            "six two-sided empirical comparisons of equal-group mean JSD against Control B; BH "
            "adjusted values across exactly six, without arbitrary-dependence FDR guarantee; "
            "BY(H6) reported as fixed dependency-conservative sensitivity; min attainable "
            "two-sided p 0.01"
        ),
        "control_A_boundary": "conditional allocation independence given exact member totals and group S/R marginals; not iid causal or real-event model",
        "control_B_boundary": (
            "paired count regrouping within floor(log2(total item support)) bands; no "
            "preservation of exact group S/R totals; not semantic quality or heldout utility"
        ),
        "case": case,
        "results": records,
        "inputs": assets,
        "inputs_rehashed_after": True,
        "admission_metadata_rehashed_after": True,
        "command_argv": sys.argv,
        "contract_sha256": contract_hash,
        "code_sha256": script_hash,
        "inputs_manifest_sha256": manifest_hash,
        "execution_receipt_policy": (
            "Independent local CPU analysis with dedicated command, actor, "
            "input/code/contract/output hashes and runtime receipt; axiomdesk_run training "
            "launcher not used because no training launcher/model/backend is invoked."
        ),
        "runtime_actor": "local installed CPython + NumPy process, no external API or paid compute",
        "provenance_receipt_sha256": sha(args.provenance_receipt)
        if args.provenance_receipt
        else None,
        "python": sys.version,
        "numpy": np.__version__,
        "platform": platform.platform(),
        "elapsed_seconds": time.perf_counter() - start,
        "maxrss_native": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "maxrss_unit": "bytes on macOS; KiB on Linux",
        "no_training_or_model_calls": True,
        "public_safety": "aggregate-only summary; full group/SID tables remain restricted",
    }
    emit(out / "POPULATION_RESULTS.json", result)
    emit(out / "NULL_AGGREGATE_DRAWS.json", null_draws)
    output_files = [out / "POPULATION_RESULTS.json", out / "NULL_AGGREGATE_DRAWS.json"] + sorted(
        restricted.glob("*.csv")
    )
    emit(
        out / "EXECUTION_RECEIPT.json",
        {
            "status": "COMPLETE_VALIDITY_CHECKS_PASSED",
            "command_argv": sys.argv,
            "runtime_actor": result["runtime_actor"],
            "launcher_policy": result["execution_receipt_policy"],
            "elapsed_seconds": time.perf_counter() - start,
            "code_sha256": script_hash,
            "contract_sha256": contract_hash,
            "inputs_manifest_sha256": manifest_hash,
            "inputs_verified_before_and_after": assets,
            "additional_admission_metadata": extras,
            "output_files": [
                {"path": str(p), "bytes": p.stat().st_size, "sha256": sha(p)} for p in output_files
            ],
            "python": sys.version,
            "numpy": np.__version__,
            "platform": platform.platform(),
            "blas_thread_env": {
                k: os.environ.get(k)
                for k in ["OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"]
            },
            "maxrss_native": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "no_training_or_model_calls": True,
        },
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "elapsed_seconds": result["elapsed_seconds"],
                "summary_sha256": sha(out / "POPULATION_RESULTS.json"),
            }
        ),
        flush=True,
    )


def independent_js(s, r):
    p = [x / sum(s) for x in s]
    q = [x / sum(r) for x in r]
    ans = 0
    for a, b in zip(p, q):
        mid = (a + b) / 2
        if a:
            ans += a * math.log2(a / mid) / 2
        if b:
            ans += b * math.log2(b / mid) / 2
    return ans


def tests(args):
    checks = []

    def ok(name, condition):
        if not bool(condition):
            raise AssertionError(name)
        checks.append(name)

    for s, r in [([1, 2], [2, 4]), ([9, 1], [1, 9]), ([0, 5], [5, 0]), ([4, 6, 2], [1, 8, 0])]:
        v = float(jsd_rows(np.array([s]), np.array([r]))[0])
        ok("independent_JSD_" + str(len(checks)), abs(v - independent_js(s, r)) < 1e-14)
        ok(
            "symmetry_" + str(len(checks)),
            abs(v - float(jsd_rows(np.array([r]), np.array([s]))[0])) < 1e-14,
        )
    ok("proportional_exact_zero", jsd_rows([[2, 4]], [[5, 10]])[0] == 0)
    ok("disjoint_unit_JS", jsd_rows([[0, 4]], [[3, 0]])[0] == 1)
    s = np.array([1, 1, 9, 1, 4])
    r = np.array([1, 1, 1, 9, 7])
    group = np.array([0, 0, 1, 1, 2])
    sizes = np.array([2, 2, 1])
    obs = group_stats(s, r, group, sizes)
    masks = strata(sizes, obs)
    ok("all_tied_argmax_overlap", not obs["disjoint"][0] and obs["argmax_overlap_count"][0] == 2)
    ok("opposite_leaders_disjoint", obs["disjoint"][1])
    ok("singletons_excluded", masks["all_collision_groups"].tolist() == [True, True, False])
    ok("singleton_JS_zero", obs["jsd"][2] == 0)
    order = np.array([4, 2, 0, 3, 1])
    reordered = group_stats(s[order], r[order], group[order], sizes)
    ok(
        "input_ID_reordering_observed_invariant",
        all(np.array_equal(obs[k], reordered[k]) for k in obs),
    )
    anull, ajs, mcheck = hypergeom_control(s, r, group, sizes, masks, 778)
    ok("A_all_exact_marginal_checks", mcheck == 2 * REPS)
    ok("A_same_group_denominators", len(anull["all_collision_groups"]["equal_group_jsd"]) == REPS)
    ok("A_positive_excess_constructed", obs["jsd"][1] > ajs[:, 1].mean())
    ok("A_negative_excess_proportional_constructed", obs["jsd"][0] < ajs[:, 0].mean())
    rng = np.random.Generator(np.random.PCG64(223))
    sample = rng.multivariate_hypergeometric([4, 6], 5, size=100000, method="marginals")
    expectation = 0
    for a in range(0, 5):
        if 0 <= 5 - a <= 6:
            probability = math.comb(4, a) * math.comb(6, 5 - a) / math.comb(10, 5)
            expectation += probability * independent_js([a, 5 - a], [4 - a, 1 + a])
    sim = jsd_rows(sample, np.array([4, 6]) - sample)
    ok(
        "small_exact_contingency_enumeration",
        abs(sim.mean() - expectation) < 6 * sim.std() / math.sqrt(len(sim)),
    )
    s2 = np.array([9, 8, 1, 2, 1, 2, 9, 8])
    r2 = np.array([1, 2, 9, 8, 9, 8, 1, 2])
    band = support_bands(s2, r2)
    ok(
        "floor_log2_exact_boundaries",
        support_bands(np.array([1, 1, 1, 1]), np.array([1, 2, 3, 7])).tolist() == [1, 1, 2, 3],
    )
    rng = np.random.Generator(np.random.PCG64(4))
    perm = paired_permutation_indices(band, rng)
    ok("B_global_paired_multiset", sorted(zip(s2, r2)) == sorted(zip(s2[perm], r2[perm])))
    ok("B_band_preservation", np.array_equal(band, band[perm]))
    gp = np.arange(8) // 2
    sz = np.full(4, 2)
    negative = group_stats(s2, r2, gp, sz)["jsd"].mean()
    positive = group_stats(s2, r2, np.tile(np.arange(4), 2), sz)["jsd"].mean()
    values = []
    for _ in range(REPS):
        perm = paired_permutation_indices(band, rng)
        values.append(group_stats(s2[perm], r2[perm], gp, sz)["jsd"].mean())
    ok("B_controlled_negative_direction", negative < np.mean(values))
    ok("B_controlled_positive_direction", positive > np.mean(values))
    ok("two_sided_empirical_tail_formula", empirical_p(100, list(range(199))) == 1)
    ok("two_sided_empirical_extreme_floor", empirical_p(200, list(range(199))) == 0.01)
    ok(
        "BH_six_only_monotonic",
        np.allclose(bh([0.01, 0.02, 0.04, 0.5, 0.7, 0.9]), [0.06, 0.06, 0.08, 0.75, 0.84, 0.9]),
    )
    ok(
        "empty_strata_JSON_null",
        all(
            v is None
            for v in means(
                obs["jsd"], obs["disjoint"], sizes, obs["events"], np.zeros(3, dtype=bool)
            ).values()
        ),
    )
    caught = False
    try:
        hypergeom_control(
            np.array([1, 1]),
            np.array([500000000, 500000000]),
            np.array([0, 0]),
            np.array([2]),
            {"all": np.array([True])},
            0,
        )
    except ValueError:
        caught = True
    ok("hypergeometric_large_count_refusal", caught)
    if args.out:
        emit(
            Path(args.out) / "TESTS.json",
            {
                "status": "PASS",
                "checks": checks,
                "count": len(checks),
                "exact_small_table_expected_jsd": expectation,
                "MC_small_table_mean_jsd": float(sim.mean()),
                "code_sha256": sha(__file__),
                "numpy": np.__version__,
                "python": sys.version,
                "fabricated_data_only": True,
            },
        )
    print(json.dumps({"status": "PASS", "test_count": len(checks)}))


def benchmark(args):
    start = time.perf_counter()
    rng = np.random.Generator(np.random.PCG64(4242))
    n = args.items
    s = rng.integers(1, 100, size=n)
    r = rng.integers(1, 100, size=n)
    sizes = np.full(n // 10, 10, dtype=np.int64)
    group = np.arange(n) // 10
    stats = group_stats(s, r, group, sizes)
    masks = strata(sizes, stats)
    ast = time.perf_counter()
    hypergeom_control(s, r, group, sizes, masks, 4244)
    asec = time.perf_counter() - ast
    bst = time.perf_counter()
    bands = support_bands(s, r)
    for _ in range(REPS):
        perm = paired_permutation_indices(bands, rng)
        for _family in range(3):
            group_stats(s[perm], r[perm], group, sizes)
    bsec = time.perf_counter() - bst
    rec = {
        "fabricated_data_only": True,
        "items": n,
        "collision_groups": len(sizes),
        "draws": REPS,
        "A_one_mapping_seconds": asec,
        "B_three_mapping_seconds": bsec,
        "approx_118269_item_six_strata_seconds": (6 * asec + bsec * 2) * 118269 / n / 2,
        "elapsed_seconds": time.perf_counter() - start,
        "code_sha256": sha(__file__),
        "maxrss_native": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "python": sys.version,
        "numpy": np.__version__,
        "boundary": "runtime estimate depends on actual group sizes/counts; no scientific real data computed",
    }
    if args.out:
        emit(Path(args.out) / "BENCHMARK.json", rec)
    print(json.dumps(rec))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    p = sub.add_parser("test")
    p.add_argument("--out", type=Path)
    p = sub.add_parser("benchmark")
    p.add_argument("--out", type=Path)
    p.add_argument("--items", type=int, default=100000)
    p = sub.add_parser("run")
    for name in ["inputs", "contract", "admissions", "out", "restricted-out"]:
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument(
        "--provenance-receipt",
        "--acceptance-receipt",
        dest="provenance_receipt",
        type=Path,
        help="Optional local provenance receipt",
    )
    args = parser.parse_args()
    if args.mode == "test":
        tests(args)
    elif args.mode == "benchmark":
        if args.items < 10 or args.items % 10:
            parser.error("benchmark items must be positive multiple of ten")
        benchmark(args)
    else:
        try:
            run(args)
        except Exception as exc:
            if args.out.is_dir() and not (args.out / "FAILURE_RECEIPT.json").exists():
                emit(
                    args.out / "FAILURE_RECEIPT.json",
                    {
                        "status": "FAILED_STOP_NO_FALLBACK",
                        "exception_type": type(exc).__name__,
                        "message": str(exc),
                        "command_argv": sys.argv,
                        "code_sha256": sha(__file__),
                        "python": sys.version,
                        "numpy": np.__version__,
                        "no_training_or_model_calls": True,
                    },
                )
            raise


if __name__ == "__main__":
    main()
