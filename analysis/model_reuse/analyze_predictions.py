#!/usr/bin/env python3
"""Describe real-score coverage and support-stratified label associations."""

from __future__ import annotations
import argparse, csv, hashlib, json, math
from collections import defaultdict
from pathlib import Path
import numpy as np


def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def ci(v):
    a = np.asarray(v)
    a = a[np.isfinite(a)]
    return {
        "ci95": np.quantile(a, [0.025, 0.975]).tolist() if len(a) else None,
        "valid_draws": len(a),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for n in ["units", "topology", "inference", "out"]:
        parser.add_argument("--" + n, type=Path, required=True)
    parser.add_argument("--draws", type=int, default=2000)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    with args.topology.open(newline="") as f:
        top = {r["item_id"]: r for r in csv.DictReader(f)}
    with args.units.open(newline="") as f:
        allrows = list(csv.DictReader(f))
    report = {
        "schema": "sr_sid_rolemap.actual_model_diagnostic.v1",
        "status": "PASS_DESCRIPTIVE_ANALYSIS",
        "method": "UniSAR",
        "dataset": "kuaisar_unisar_processed",
        "confirmatory": False,
        "bootstrap_draws": args.draws,
        "roles": {},
        "inputs_sha256": {p.name: sha(p) for p in [args.units, args.topology, args.inference]},
        "boundary": (
            "A descriptive full-test expansion after the initial sample. Cohort differences and "
            "label associations are not causal effects, ranking gains or prospective prediction "
            "validation."
        ),
    }
    for role in ["search", "rec"]:
        rows = [r for r in allrows if r["role"] == role]
        users = sorted({r["user_id"] for r in rows})
        um = {u: i for i, u in enumerate(users)}
        u = len(users)
        data = np.zeros((u, 4))
        covered = []
        for r in rows:
            v = float(r["ndcg10"])
            i = um[r["user_id"]]
            data[i, 0] += 1
            data[i, 1] += v
            if int(r["covered"]):
                data[i, 2] += 1
                data[i, 3] += v
                covered.append(r)
        rng = np.random.default_rng(20261019)
        weights = rng.multinomial(u, np.full(u, 1 / u), size=args.draws)
        b = weights @ data
        valid = b[:, 2] > 0
        delta = b[valid, 3] / b[valid, 2] - b[valid, 1] / b[valid, 0]
        sums = data.sum(axis=0)
        out = {
            "requests": len(rows),
            "users": u,
            "covered_requests": len(covered),
            "covered_users": int(np.sum(data[:, 2] > 0)),
            "coverage_percent": 100 * len(covered) / len(rows),
            "all_ndcg10": sums[1] / sums[0],
            "covered_ndcg10": sums[3] / sums[2] if sums[2] else None,
            "covered_minus_all_ndcg10": sums[3] / sums[2] - sums[1] / sums[0] if sums[2] else None,
            "cohort_difference_bootstrap": ci(delta),
            "target_tied_requests": sum(int(r["target_ties"]) > 1 for r in rows),
            "all_equal_requests": sum(int(r["target_ties"]) == 100 for r in rows),
        }
        strata = defaultdict(lambda: defaultdict(list))
        raw = defaultdict(list)
        for r in covered:
            t = top[r["item_id"]]
            sc = int(t["search_support"])
            rc = int(t["rec_support"])
            k = (math.floor(math.log2(sc + rc)), math.floor(abs(math.log2((sc + 1) / (rc + 1)))))
            group = int(abs(float(t["js_divergence"]) - 1.0) <= 1e-12)
            strata[k][group].append(r)
            raw["maximal_JSD" if group else "nonmaximal_JSD"].append(float(r["ndcg10"]))
        eligible = [k for k, v in sorted(strata.items()) if len(v[0]) >= 5 and len(v[1]) >= 5]
        used = [r for k in eligible for g in [0, 1] for r in strata[k][g]]
        nusers = len({r["user_id"] for r in used})
        assoc = {
            "group_definition": "label JSD=1 versus JSD<1; fixed tolerance 1e-12",
            "raw_groups": {
                k: {"requests": len(v), "ndcg10": float(np.mean(v))} for k, v in raw.items()
            },
            "eligible_strata": len(eligible),
            "eligible_requests": len(used),
            "eligible_users": nusers,
            "status": "INSUFFICIENT_SUPPORT",
            "difference_maximal_minus_nonmaximal": None,
            "bootstrap": None,
        }
        if len(eligible) >= 3 and nusers >= 20:
            s = np.zeros((u, len(eligible), 4))
            for j, k in enumerate(eligible):
                for g in [0, 1]:
                    for r in strata[k][g]:
                        i = um[r["user_id"]]
                        s[i, j, 2 * g] += 1
                        s[i, j, 2 * g + 1] += float(r["ndcg10"])
            point = s.sum(axis=0)
            w = np.minimum(point[:, 0], point[:, 2])
            d = point[:, 3] / point[:, 2] - point[:, 1] / point[:, 0]
            boots = (weights @ s.reshape(u, -1)).reshape(args.draws, len(eligible), 4)
            valid = (boots[:, :, 0] > 0).all(axis=1) & (boots[:, :, 2] > 0).all(axis=1)
            b = boots[valid]
            bw = np.minimum(b[:, :, 0], b[:, :, 2])
            bd = b[:, :, 3] / b[:, :, 2] - b[:, :, 1] / b[:, :, 0]
            v = (bw * bd).sum(axis=1) / bw.sum(axis=1)
            assoc.update(
                status="DESCRIPTIVE_ASSOCIATION",
                difference_maximal_minus_nonmaximal=float(np.dot(w, d) / w.sum()),
                bootstrap=ci(v),
            )
        out["support_stratified_label_association"] = assoc
        report["roles"][role] = out
    with (args.out / "coverage.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "role",
                "requests",
                "covered_requests",
                "coverage_percent",
                "all_ndcg10",
                "covered_ndcg10",
                "difference",
                "ci95_low",
                "ci95_high",
            ]
        )
        for role, r in report["roles"].items():
            w.writerow(
                [
                    role,
                    r["requests"],
                    r["covered_requests"],
                    r["coverage_percent"],
                    r["all_ndcg10"],
                    r["covered_ndcg10"],
                    r["covered_minus_all_ndcg10"],
                    *(r["cohort_difference_bootstrap"]["ci95"] or [None, None]),
                ]
            )
    (args.out / "RESULTS.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["roles"]), flush=True)


if __name__ == "__main__":
    main()
