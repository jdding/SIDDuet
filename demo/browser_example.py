"""Run SIDDuet's three diagnostic workflows in pure Python (browser or local)."""

from __future__ import annotations

import contextlib
import csv
import io
import json
import math
from pathlib import Path
import random
import runpy
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def _jsd_base2(search_counts: list[int], rec_counts: list[int]) -> float:
    total_s = sum(search_counts)
    total_r = sum(rec_counts)
    if total_s <= 0 or total_r <= 0:
        return 0.0
    div = 0.0
    for s_val, r_val in zip(search_counts, rec_counts):
        p_i = s_val / total_s
        q_i = r_val / total_r
        m_i = 0.5 * (p_i + q_i)
        if p_i > 0:
            div += 0.5 * p_i * math.log2(p_i / m_i)
        if q_i > 0:
            div += 0.5 * q_i * math.log2(q_i / m_i)
    return div


def _leaders(items: list[str], counts: list[int]) -> set[str]:
    top = max(counts)
    return {item for item, value in zip(items, counts) if value == top}


def _compute_workflow1(counts_path: Path, sid_map_path: Path, draws: int = 199, seed: int = 20261104) -> dict:
    paired: dict[str, list[int]] = {}
    with counts_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            pair = paired.setdefault(row["item_id"], [0, 0])
            idx = 1 if row["role"] == "rec" else 0
            pair[idx] += int(row["count"])

    item_to_sid: dict[str, str] = {}
    with sid_map_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            item_to_sid[row["item_id"]] = row["sid"]

    common_items = sorted(i for i, (s, r) in paired.items() if s > 0 and r > 0)
    covered = sum(i in item_to_sid for i in common_items)
    if covered != len(common_items):
        raise ValueError(f"synthetic map coverage: {covered}/{len(common_items)} covered, "
                         f"{len(common_items) - covered} missing")
    by_sid: dict[str, list[str]] = {}
    for item in common_items:
        by_sid.setdefault(item_to_sid[item], []).append(item)

    collision_sids = sorted(sid for sid, members in by_sid.items() if len(members) >= 2)
    groups = []
    for sid in collision_sids:
        members = sorted(by_sid[sid])
        s_list = [paired[m][0] for m in members]
        r_list = [paired[m][1] for m in members]
        sum_s = sum(s_list)
        sum_r = sum(r_list)
        jsd = _jsd_base2(s_list, r_list)
        s_leaders = sorted(_leaders(members, s_list))
        r_leaders = sorted(_leaders(members, r_list))
        disjoint = not bool(set(s_leaders) & set(r_leaders))
        member_rows = [
            {
                "item": m,
                "search_count": s_val,
                "rec_count": r_val,
                "search_share": s_val / sum_s,
                "rec_share": r_val / sum_r,
                "is_search_leader": m in s_leaders,
                "is_rec_leader": m in r_leaders,
            }
            for m, s_val, r_val in zip(members, s_list, r_list)
        ]
        groups.append(
            {
                "sid": sid,
                "size": len(members),
                "search_total": sum_s,
                "rec_total": sum_r,
                "allocation_jsd": jsd,
                "search_leader": ", ".join(s_leaders),
                "search_leader_share": max(s_list) / sum_s,
                "rec_leader": ", ".join(r_leaders),
                "rec_leader_share": max(r_list) / sum_r,
                "disjoint_leaders": disjoint,
                "members": member_rows,
            }
        )

    rank_groups = runpy.run_path(str(ROOT / "scripts/inspect_groups.py"))["rank_groups"]
    by_code = {g["sid"]: g for g in groups}
    scores = {sid: g["allocation_jsd"] for sid, g in by_code.items()}
    groups = []
    for sid, rank, percentile in rank_groups(scores):
        g = by_code[sid]
        g.update(rank=rank, percentile=percentile)
        for role in ("search", "rec"):
            leaders = [m for m in g["members"] if m[f"is_{role}_leader"]]
            g[f"{role}_leader_traffic"] = " / ".join(
                f"{m['item']} · S {m['search_count']} ({m['search_share']:.2%}), "
                f"R {m['rec_count']} ({m['rec_share']:.2%})" for m in leaders
            )
        groups.append(g)

    observed_mean_jsd = sum(g["allocation_jsd"] for g in groups) / len(groups)
    disjoint_rate = sum(1 for g in groups if g["disjoint_leaders"]) / len(groups)

    # Pure-Python count-matched regrouping references (band-matched & exact-total)
    pairs = [tuple(paired[i]) for i in common_items]
    group_indices = [[common_items.index(m) for m in by_sid[sid]] for sid in collision_sids]

    def run_reference(strata_fn) -> dict:
        rng = random.Random(seed)
        strata: dict[int, list[int]] = {}
        for idx, (s_val, r_val) in enumerate(pairs):
            strata.setdefault(strata_fn(s_val, r_val), []).append(idx)
        draw_jsds = []
        draw_disjoint = []
        for _ in range(draws):
            perm = list(pairs)
            for indices in strata.values():
                if len(indices) > 1:
                    shuffled = [pairs[k] for k in indices]
                    rng.shuffle(shuffled)
                    for slot, val in zip(indices, shuffled):
                        perm[slot] = val
            jsd_vals = []
            disjoint_hits = 0
            for idxs in group_indices:
                s_g = [perm[k][0] for k in idxs]
                r_g = [perm[k][1] for k in idxs]
                jsd_vals.append(_jsd_base2(s_g, r_g))
                s_top = max(s_g)
                r_top = max(r_g)
                s_set = {pos for pos, v in enumerate(s_g) if v == s_top}
                r_set = {pos for pos, v in enumerate(r_g) if v == r_top}
                if not (s_set & r_set):
                    disjoint_hits += 1
            draw_jsds.append(sum(jsd_vals) / len(jsd_vals))
            draw_disjoint.append(disjoint_hits / len(group_indices))
        return {
            "draws": draws,
            "mean_jsd": sum(draw_jsds) / len(draw_jsds),
            "mean_disjoint_rate": sum(draw_disjoint) / len(draw_disjoint),
            "strata": len(strata),
        }

    band_ref = run_reference(lambda s, r: int(math.floor(math.log2(s + r))))
    exact_ref = run_reference(lambda s, r: s + r)

    return {
        "common_items": len(common_items),
        "covered_common_items": covered,
        "collision_groups": len(groups),
        "observed_mean_jsd": observed_mean_jsd,
        "observed_disjoint_rate": disjoint_rate,
        "band_reference": band_ref,
        "exact_reference": exact_ref,
        "groups": groups,
    }


def _compute_synthetic_pooling(groups: list[dict]) -> dict:
    """Compare fixed smoothing rules on a held-out share of synthetic counts."""
    # Keep smoothing fixed so the held-out counts only score the rules.
    alpha = beta = 10.0
    train_s: dict[str, dict[str, float]] = {}
    train_r: dict[str, dict[str, float]] = {}
    eval_s: dict[str, dict[str, float]] = {}
    eval_r: dict[str, dict[str, float]] = {}
    for g in groups:
        sid = g["sid"]
        train_s[sid], train_r[sid] = {}, {}
        eval_s[sid], eval_r[sid] = {}, {}
        for m in g["members"]:
            item = m["item"]
            s_tot, r_tot = m["search_count"], m["rec_count"]
            s_ev = max(1, round(0.2 * s_tot))
            r_ev = max(1, round(0.2 * r_tot))
            train_s[sid][item] = float(max(0, s_tot - s_ev))
            train_r[sid][item] = float(max(0, r_tot - r_ev))
            eval_s[sid][item] = float(s_ev)
            eval_r[sid][item] = float(r_ev)

    def macro_loss(probs_by_task: dict[str, dict[str, dict[str, float]]]) -> tuple[float, float, float]:
        role_losses = {}
        for role, ev_map in (("search", eval_s), ("rec", eval_r)):
            total_w = 0.0
            weighted_loss = 0.0
            for sid, items_ev in ev_map.items():
                for item, cnt in items_ev.items():
                    if cnt > 0:
                        weighted_loss += -cnt * math.log(probs_by_task[role][sid][item])
                        total_w += cnt
            role_losses[role] = weighted_loss / total_w
        macro = 0.5 * (role_losses["search"] + role_losses["rec"])
        return macro, role_losses["search"], role_losses["rec"]

    pooled_probs = {"search": {}, "rec": {}}
    separate_probs = {"search": {}, "rec": {}}
    shrinkage_probs = {"search": {}, "rec": {}}
    for group in groups:
        sid = group["sid"]
        members = [member["item"] for member in group["members"]]
        prior = 1.0 / len(members)
        pooled_counts = {item: train_s[sid][item] + train_r[sid][item] for item in members}
        pooled_total = sum(pooled_counts.values())
        pooled = {
            item: (count + alpha * prior) / (pooled_total + alpha)
            for item, count in pooled_counts.items()
        }
        for task, train in (("search", train_s), ("rec", train_r)):
            counts = train[sid]
            total = sum(counts.values())
            pooled_probs[task][sid] = pooled
            separate_probs[task][sid] = {
                item: (count + alpha * prior) / (total + alpha)
                for item, count in counts.items()
            }
            shrinkage_probs[task][sid] = {
                item: (count + beta * pooled[item]) / (total + beta)
                for item, count in counts.items()
            }

    def scored(rule, probabilities, **smoothing):
        macro, search, rec = macro_loss(probabilities)
        return {
            "rule": rule,
            **smoothing,
            "macro_loss": macro,
            "search_loss": search,
            "rec_loss": rec,
        }

    pooled = scored("pooled", pooled_probs, alpha=alpha)
    separate = scored("separate", separate_probs, alpha=alpha)
    return {
        "pooled": pooled,
        "task_conditioned": separate,
        "shrinkage": scored("shrinkage", shrinkage_probs, beta=beta),
        "delta_nats": pooled["macro_loss"] - separate["macro_loss"],
    }


def _load_published_summaries() -> dict:
    # Workflow 2: Published UniSAR / KuaiSAR (Table 3)
    mr = json.loads((ROOT / "reports/model_reuse/RESULTS.json").read_text(encoding="utf-8"))
    table3 = []
    for role_key, label in (("search", "Search"), ("rec", "Recommendation")):
        r = mr["roles"][role_key]
        table3.append(
            {
                "task": label,
                "covered_requests": r["covered_requests"],
                "total_requests": r["requests"],
                "paired_coverage_pct": r["coverage_percent"],
                "full_ndcg10": r["all_ndcg10"],
                "covered_ndcg10": r["covered_ndcg10"],
                "diff_ci95": r["cohort_difference_bootstrap"]["ci95"],
            }
        )

    # Workflow 3: Published Qilin two-window pooling (Table 4)
    tw = json.loads(
        (
            ROOT
            / "analysis/reuse_validation/results/two_window_sensitivity/TWO_WINDOW_SENSITIVITY.json"
        ).read_text(encoding="utf-8")
    )
    view_labels = [
        ("gensar_shared2", "GenSAR · Shared prefix (2)*"),
        ("gensar_semantic_complete", "GenSAR · Semantic full"),
        ("gensar_collaborative_complete", "GenSAR · Collaborative full"),
        ("gaoq_depth1", "GAOQ · Prefix (1)"),
        ("gaoq_depth2", "GAOQ · Prefix (2)"),
    ]
    by_key = {(r["name"], r["window"]): r for r in tw["results"]}
    table4 = []
    for name, label in view_labels:
        w1 = by_key[(name, "original")]
        w2 = by_key[(name, "shared")]
        table4.append(
            {
                "view": label,
                "primary": bool(w1["primary"]),
                "first_delta_mnats": w1["delta_nats"]["macro"] * 1e3,
                "first_ci_mnats": [x * 1e3 for x in w1["two_window_family95_nats"]],
                "first_requests": w1["scored_requests"],
                "second_delta_mnats": w2["delta_nats"]["macro"] * 1e3,
                "second_ci_mnats": [x * 1e3 for x in w2["two_window_family95_nats"]],
                "second_requests": w2["scored_requests"],
            }
        )
    table4.append(
        {
            "view": "GAOQ · Full (3), control",
            "primary": False,
            "control": True,
        }
    )

    cs = json.loads((ROOT / "reports/cohort_sensitivity/RESULTS.json").read_text(encoding="utf-8"))
    cohort_sens = []
    for w in cs["windows"]:
        t = w["training_only"]
        delta_mnats = (t["loss"]["blind"]["macro"] - t["loss"]["aware"]["macro"]) * 1e3
        ci_mnats = [x * 1e3 for x in t["bootstrap"]["intervals"][0]["family95"]]
        aud = t["coverage"]["audit"]
        cohort_sens.append(
            {
                "window": "First (~91 min)" if w["window"] == "first" else "Additional (4 h)",
                "groups": t["collision_groups"],
                "scored_requests": aud["rec"]["scored_requests"] + aud["search"]["scored_requests"],
                "delta_mnats": delta_mnats,
                "ci_mnats": ci_mnats,
            }
        )

    return {"table3": table3, "table4": table4, "cohort_sensitivity": cohort_sens}


def run_example() -> dict:
    steps = []
    scripts = str(ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)

    with tempfile.TemporaryDirectory(prefix="sidduet-browser-") as folder:
        output = Path(folder)

        def run(script: str, arguments: list) -> str:
            previous = sys.argv
            capture = io.StringIO()
            sys.argv = [script, *map(str, arguments)]
            try:
                with contextlib.redirect_stdout(capture):
                    runpy.run_path(str(ROOT / "scripts" / script), run_name="__main__")
            finally:
                sys.argv = previous
            out = capture.getvalue().strip()
            steps.append({"script": script, "output": out.splitlines()[0] if out else "ok"})
            return out

        run(
            "materialize_role_label_counts.py",
            [
                "--events",
                ROOT / "samples/synthetic_role_events.csv",
                "--out-csv",
                output / "counts.csv",
                "--out-json",
                output / "counts.json",
            ],
        )
        run(
            "build_role_topology.py",
            [
                "--role-counts",
                output / "counts.csv",
                "--out-csv",
                output / "topology.csv",
                "--out-json",
                output / "topology.json",
            ],
        )
        run(
            "admit_sid_family.py",
            [
                "--topology",
                output / "topology.csv",
                "--sid-map",
                ROOT / "samples/synthetic_sid_map.csv",
                "--family",
                "synthetic_demo",
                "--out-csv",
                output / "admission.csv",
                "--out-json",
                output / "admission.json",
            ],
        )
        run(
            "evaluate_collision_diagnostic.py",
            [
                "--topology",
                output / "topology.csv",
                "--sid-map",
                ROOT / "samples/synthetic_sid_map.csv",
                "--out-csv",
                output / "collision.csv",
                "--out-json",
                output / "collision.json",
            ],
        )
        run(
            "adapt_method_scores.py",
            [
                "--scores",
                ROOT / "samples/synthetic_prediction_coverage_scores.csv",
                "--allow-unpaired-targets",
                "--topology",
                output / "topology.csv",
                "--method-id",
                "synthetic_demo",
                "--method-paradigm",
                "discriminative",
                "--score-direction",
                "higher_is_better",
                "--out-csv",
                output / "adapted.csv",
            ],
        )
        run(
            "evaluate_fixed_candidates.py",
            [
                "--candidates",
                output / "adapted.csv",
                "--paired-target-slices",
                "--out-csv",
                output / "metrics.csv",
                "--out-json",
                output / "metrics.json",
            ],
        )
        table2_csv = run("verify_table2.py", [])
        table2_rows = list(csv.DictReader(io.StringIO(table2_csv)))

        def load(name: str) -> dict:
            return json.loads((output / name).read_text(encoding="utf-8"))

        coverage = load("admission.json")["dataset_summaries"][0]
        score_rows = load("metrics.json")["aggregates"]
        covered_by_role = {
            row["role"]: row for row in score_rows
            if row["slice_type"] == "paired_target" and row["slice_value"] == "covered"
        }
        metrics = []
        for row in score_rows:
            if row["slice_type"] != "all":
                continue
            covered = covered_by_role.get(row["role"], {})
            metrics.append({
                "role": row["role"],
                "units": row["units"],
                "ndcg10": row["ndcg10"],
                "hit10": row["hit10"],
                "covered_units": covered.get("units", 0),
                "covered_ndcg10": covered.get("ndcg10"),
            })
        workflow1 = _compute_workflow1(output / "counts.csv", ROOT / "samples/synthetic_sid_map.csv")
        pooling_synth = _compute_synthetic_pooling(workflow1["groups"])
        published = _load_published_summaries()

        if workflow1["common_items"] != 8 or coverage["join_coverage"] != 1.0:
            raise ValueError("synthetic item or map coverage differs from the fixture")
        if {row["role"] for row in metrics} != {"search", "rec"} or len(table2_rows) != 6:
            raise ValueError("expected both task metrics and six verified Table 2 rows")

        return {
            "status": "pass",
            "version": "0.4.2",
            "synthetic": True,
            "workflow1": workflow1,
            "table2": table2_rows,
            "coverage": {
                key: coverage[key]
                for key in ("topology_items", "joined_items", "join_coverage", "unique_sid_count")
            },
            "metrics": metrics,
            "table3": published["table3"],
            "pooling_synthetic": pooling_synth,
            "table4": published["table4"],
            "cohort_sensitivity": published["cohort_sensitivity"],
            "steps": steps,
            "python": sys.version.split()[0],
        }


if __name__ == "__main__":
    print(json.dumps(run_example()))
