#!/usr/bin/env python3
"""Export UniSAR candidate scores in the RoleMap input format."""

from __future__ import annotations
import argparse, csv, hashlib, importlib, json, math, sys, time
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
import torch

DATASET = "kuaisar_unisar_processed"


def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def metrics(s):
    greater = int(np.sum(s > s[0]))
    tied = int(np.sum(s == s[0]))
    ranks = range(greater + 1, greater + tied + 1)
    return (
        sum(1 / math.log2(k + 1) for k in ranks if k <= 10) / tied,
        sum(k <= 10 for k in ranks) / tied,
        tied,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for n in ["official-root", "processed-root", "checkpoint", "users", "topology", "out"]:
        parser.add_argument("--" + n, type=Path, required=True)
    parser.add_argument("--per-role", type=int, default=1024)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--seed", default="rolemap-external-20261019-v1")
    parser.add_argument("--expected-checkpoint", default="")
    parser.add_argument("--pilot", action="store_true")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    t0 = time.monotonic()
    torch.set_num_threads(4)
    cksha = sha(args.checkpoint)
    if args.expected_checkpoint and cksha != args.expected_checkpoint:
        raise ValueError("checkpoint identity mismatch")
    source_hashes = {
        str(p.relative_to(args.official_root)): sha(p) for p in args.official_root.rglob("*.py")
    }
    if (
        source_hashes.get("models/UniSAR.py")
        != "bd2711f26da727d261749d771ceee89cfc01c5c1d23c31946f52bc9471b6f0df"
    ):
        raise ValueError("unexpected upstream model implementation")
    sys.path.insert(0, str(args.official_root.resolve()))
    const = importlib.import_module("utils.const")
    const.init_setting_KuaiSAR()
    for field, rel in {
        "user_vocab": "vocab/user_vocab.pkl",
        "query_vocab": "vocab/query_vocab.pkl",
        "user_map_vocab": "vocab/user_vocab_np.pkl",
        "item_map_vocab": "vocab/item_vocab_np.pkl",
        "session_map_vocab": "vocab/src_session_vocab_np.pkl",
        "rec_test": "dataset/rec_test.pkl",
        "src_test": "dataset/src_test.pkl",
    }.items():
        setattr(const, field, str((args.processed_root / rel).resolve()))
    utils = importlib.import_module("utils.utils")
    datasets = importlib.import_module("utils.dataset")
    mod = importlib.import_module("models.UniSAR")
    uv = utils.load_pickle(const.user_vocab)
    ma = SimpleNamespace(
        device=torch.device("cpu"),
        model_path=str(args.out / "not_saved"),
        dropout=0.0,
        batch_size=1024,
        num_layers=1,
        num_heads=2,
        q_i_cl_temp=0.5,
        q_i_cl_weight=0.0,
        his_cl_temp=0.1,
        his_cl_weight=0.0,
        pred_hid_units=[200, 80, 1],
    )
    model = mod.UniSAR(ma)
    state = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    loaded = model.load_state_dict(state, strict=False)
    allowed = ("feature_alignment.infoNCE_loss.", "rec_his_cl.", "src_his_cl.")
    assert not loaded.missing_keys and all(k.startswith(allowed) for k in loaded.unexpected_keys), (
        loaded.missing_keys,
        loaded.unexpected_keys,
    )
    for layer in model.modules():
        if isinstance(layer, torch.nn.TransformerEncoder):
            layer.enable_nested_tensor = False
            layer.use_nested_tensor = False
    if hasattr(torch.backends, "mha"):
        torch.backends.mha.set_fastpath_enabled(False)
    model.eval()
    del state
    selected_users = set(json.loads(args.users.read_text()))
    with args.topology.open(newline="") as f:
        topology = {row["item_id"] for row in csv.DictReader(f)}
    report = {
        "status": "RUNNING",
        "model": "UniSAR",
        "dataset": DATASET,
        "checkpoint_sha256": cksha,
        "upstream_commit": "1a14a246066cd1aa6ee789c57ff2c7499f3d7379",
        "source_sha256": source_hashes,
        "load": {
            "missing_keys": loaded.missing_keys,
            "ignored_training_only_keys": loaded.unexpected_keys,
        },
        "device": "cpu",
        "threads": 4,
        "new_training": False,
        "pilot": args.pilot,
        "runtime_changes": [
            "dropout disabled in eval",
            "contrastive training-only buffers omitted, all prediction weights required",
            "nested-tensor and MHA fastpath disabled",
        ],
        "setup_seconds": time.monotonic() - t0,
        "roles": {},
        "input_sha256": {},
    }
    fieldnames = ["dataset", "unit_id", "role", "candidate_id", "is_target", "score"]
    outall = (args.out / "all_scores.csv").open("w", newline="")
    outcov = (args.out / "covered_scores.csv").open("w", newline="")
    outunit = (args.out / "units.csv").open("w", newline="")
    wa, wc = (
        csv.DictWriter(outall, fieldnames=fieldnames),
        csv.DictWriter(outcov, fieldnames=fieldnames),
    )
    uf = ["unit_id", "user_id", "role", "item_id", "covered", "ndcg10", "hit10", "target_ties"]
    wu = csv.DictWriter(outunit, fieldnames=uf)
    for w in [wa, wc, wu]:
        w.writeheader()
    for role, dsclass, fn, predict in [
        ("search", datasets.SrcDataSet, "src_test.pkl", model.src_predict),
        ("rec", datasets.RecDataSet, "rec_test.pkl", model.rec_predict),
    ]:
        ds = dsclass("test", uv)
        frame = ds.sampler.data
        indices = [int(i) for i in frame.index if int(frame.loc[i, "user_id"]) in selected_users]
        indices.sort(
            key=lambda i: hashlib.sha256(
                (args.seed + ":" + role + ":" + str(i)).encode()
            ).hexdigest()
        )
        indices = indices[: args.per_role]
        pdig = sha(args.processed_root / "dataset" / fn)
        report["input_sha256"][fn] = pdig
        (args.out / (role + "_selected_rows.json")).write_text(json.dumps(indices) + "\n")
        summary = {
            "provider_test_rows": len(frame),
            "selected_requests": len(indices),
            "scored_requests": 0,
            "duplicate_candidate_requests": 0,
            "topology_covered": 0,
            "ndcg_sum": 0.0,
            "hit_sum": 0.0,
            "covered_ndcg_sum": 0.0,
            "covered_hit_sum": 0.0,
            "target_tied_requests": 0,
            "all_equal_requests": 0,
            "max_target_ties": 0,
            "batch_single_max_abs": None,
            "inference_seconds": 0.0,
        }
        ti = time.monotonic()
        for start in range(0, len(indices), args.batch_size):
            ids = indices[start : start + args.batch_size]
            feed = []
            valid = []
            for i in ids:
                d = ds[i]
                cand = [int(d["item"][0])] + [int(x) for x in d["neg_items"][0]]
                if len(set(cand)) != len(cand):
                    summary["duplicate_candidate_requests"] += 1
                    continue
                valid.append((i, cand))
                feed.append(d)
            if not feed:
                continue
            batch = ds.collate_batch(feed)
            with torch.inference_mode():
                s = predict(batch).detach().cpu().numpy()
            assert s.shape == (len(valid), 100) and np.isfinite(s).all(), s.shape
            if start == 0:
                with torch.inference_mode():
                    single = predict(ds.collate_batch([feed[0]])).detach().cpu().numpy()[0]
                diff = float(np.max(np.abs(single - s[0])))
                summary["batch_single_max_abs"] = diff
                assert np.allclose(single, s[0], rtol=1e-4, atol=1e-6), diff
            for (i, cand), values in zip(valid, s):
                uid = hashlib.sha256((args.seed + ":" + role + ":" + str(i)).encode()).hexdigest()[
                    :24
                ]
                covered = str(cand[0]) in topology
                n, h, ties = metrics(values)
                summary["scored_requests"] += 1
                summary["ndcg_sum"] += n
                summary["hit_sum"] += h
                summary["topology_covered"] += covered
                summary["target_tied_requests"] += ties > 1
                summary["all_equal_requests"] += ties == 100
                summary["max_target_ties"] = max(summary["max_target_ties"], ties)
                if covered:
                    summary["covered_ndcg_sum"] += n
                    summary["covered_hit_sum"] += h
                for j, (item, v) in enumerate(zip(cand, values)):
                    row = {
                        "dataset": DATASET,
                        "unit_id": uid,
                        "role": role,
                        "candidate_id": item,
                        "is_target": int(j == 0),
                        "score": repr(float(v)),
                    }
                    wa.writerow(row)
                    if covered:
                        wc.writerow(row)
                wu.writerow(
                    dict(
                        zip(
                            uf,
                            [
                                uid,
                                int(frame.loc[i, "user_id"]),
                                role,
                                cand[0],
                                int(covered),
                                repr(n),
                                repr(h),
                                ties,
                            ],
                        )
                    )
                )
            print(
                json.dumps(
                    {"role": role, "scored": summary["scored_requests"], "planned": len(indices)}
                ),
                flush=True,
            )
        summary["inference_seconds"] = time.monotonic() - ti
        for src, dst, den in [
            ("ndcg_sum", "ndcg10", "scored_requests"),
            ("hit_sum", "hit10", "scored_requests"),
            ("covered_ndcg_sum", "covered_ndcg10", "topology_covered"),
            ("covered_hit_sum", "covered_hit10", "topology_covered"),
        ]:
            summary[dst] = summary[src] / summary[den] if summary[den] else None
        report["roles"][role] = summary
    for f in [outall, outcov, outunit]:
        f.close()
    report["status"] = "PASS_REAL_CHECKPOINT_INFERENCE"
    report["seconds"] = time.monotonic() - t0
    report["output_sha256"] = {f.name: sha(f) for f in args.out.glob("*.csv")}
    (args.out / "INFERENCE.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {"status": report["status"], "seconds": report["seconds"], "roles": report["roles"]}
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
