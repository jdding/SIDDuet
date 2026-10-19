#!/usr/bin/env python3
"""Exercise the shipped record, registry, and scored-prediction CLI contracts."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOPOLOGY_PROFILE_ID = "sr_sid_rolemap.topology.value_median.v2"


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    checks: list[dict[str, object]] = []

    def run(name: str, script: str, arguments: list[str], marker: str = "", error: str = "") -> None:
        proc = subprocess.run(
            [sys.executable, "-I", str(ROOT / "scripts" / script), *arguments],
            text=True, capture_output=True, check=False,
        )
        passed = proc.returncode != 0 and error in proc.stderr if error else proc.returncode == 0 and marker in proc.stdout
        checks.append({"check": name, "passed": passed, "returncode": proc.returncode})
        if not passed:
            raise ValueError(f"{name}: {proc.stdout}\n{proc.stderr}")

    with tempfile.TemporaryDirectory(prefix="rolemap-contract-") as temporary:
        scratch = Path(temporary)
        for script in ("materialize_qilin_role_counts.py", "audit_shared_time_boundary.py", "normalize_sid_export.py"):
            run(f"{script}_cli_available", script, ["--help"], "usage:")
        record_path = ROOT / "samples" / "synthetic_rolemap_record.json"
        schema_args = ["--schema", str(ROOT / "schemas" / "rolemap_record.schema.json")]
        run("record_valid", "validate_rolemap_record.py", ["--record", str(record_path), *schema_args], "PASS_ROLEMAP_RECORD_VALIDATION")
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["observations"]["L2"]["status"] = "blocked"
        invalid_record = scratch / "blocked_record_with_observation.json"
        invalid_record.write_text(json.dumps(record), encoding="utf-8")
        run("record_blocked_observation_rejected", "validate_rolemap_record.py", ["--record", str(invalid_record), *schema_args], error="blocked cannot contain observed surfaces")

        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["decision"]["claim_permissions"][1]["status"] = "supported"
        invalid_record.write_text(json.dumps(record), encoding="utf-8")
        run("record_null_support_rejected", "validate_rolemap_record.py", ["--record", str(invalid_record), *schema_args], error="lacks observed evidence")
        for field in ("dataset", "sid_artifact", "release"):
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record[field] = {}
            invalid_record.write_text(json.dumps(record), encoding="utf-8")
            run(f"record_empty_{field}_rejected", "validate_rolemap_record.py", ["--record", str(invalid_record), *schema_args], error=f"{field} fields do not match")
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["observations"]["L2"]["status"] = "observed"
        record["decision"]["claim_permissions"][1]["status"] = "supported"
        invalid_record.write_text(json.dumps(record), encoding="utf-8")
        run("record_null_surface_cannot_support_observed", "validate_rolemap_record.py", ["--record", str(invalid_record), *schema_args], error="observed requires an observed surface")

        for kind, filename, marker in [
            ("method", "METHOD_ADMISSION_REGISTRY.json", "PASS_METHOD_ADMISSION_REGISTRY"),
            ("dataset", "DATASET_ADMISSION_REGISTRY.json", "PASS_DATASET_ADMISSION_REGISTRY"),
        ]:
            registry_path = ROOT / "docs" / filename
            run(f"{kind}_registry_valid", f"validate_{kind}_registry.py", ["--registry", str(registry_path)], marker)
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            rows = registry["methods" if kind == "method" else "datasets"]
            rows.append(rows[0].copy())
            invalid_registry = scratch / filename
            invalid_registry.write_text(json.dumps(registry), encoding="utf-8")
            run(f"{kind}_duplicate_rejected", f"validate_{kind}_registry.py", ["--registry", str(invalid_registry)], error=f"duplicate {kind}_id")

        topology = ROOT / "outputs" / "synthetic_role_topology.csv"
        scores_path = ROOT / "samples" / "synthetic_method_scores.csv"
        adapter_args = ["--topology", str(topology), "--method-id", "synthetic_contract_probe", "--method-paradigm", "discriminative"]
        with topology.open(encoding="utf-8", newline="") as handle:
            topology_rows = list(csv.DictReader(handle))
        topology_sha256 = hashlib.sha256(topology.read_bytes()).hexdigest()
        invalid_topology = scratch / "invalid_topology.csv"
        topology_consumers = [
            ("admission", "admit_sid_family.py", ["--sid-map", str(ROOT / "samples" / "synthetic_sid_map.csv"), "--family", "synthetic_contract_probe", "--out-csv", str(scratch / "admission.csv"), "--out-json", str(scratch / "admission.json")], "PASS_SID_FAMILY_ADMISSION"),
            ("collision", "evaluate_collision_diagnostic.py", ["--sid-map", str(ROOT / "samples" / "synthetic_sid_map.csv"), "--out-csv", str(scratch / "collision.csv"), "--out-json", str(scratch / "collision.json")], "PASS_COLLISION_DIAGNOSTIC"),
            ("adapter", "adapt_method_scores.py", ["--scores", str(scores_path), "--method-id", "synthetic_contract_probe", "--method-paradigm", "discriminative", "--score-direction", "higher_is_better", "--out-csv", str(scratch / "identity_adapted.csv")], "PASS_METHOD_SCORE_ADAPTER"),
        ]
        for name, script, arguments, marker in topology_consumers:
            run(f"{name}_v2_topology_valid", script, ["--topology", str(topology), *arguments], marker)
            for kind in ("missing", "old", "mixed", "duplicate"):
                probe_topology = [row.copy() for row in topology_rows]
                if kind == "missing":
                    for row in probe_topology:
                        row.pop("profile_id", None)
                elif kind == "old":
                    for row in probe_topology:
                        row["profile_id"] = "MAIN_B2_B3_REGISTERED_V1"
                elif kind == "mixed":
                    probe_topology[0]["profile_id"] = "MAIN_B2_B3_REGISTERED_V1"
                else:
                    probe_topology.append(probe_topology[0].copy())
                write_csv(invalid_topology, probe_topology)
                error = "duplicate topology item" if kind == "duplicate" else "topology profile_id must be"
                run(f"{name}_topology_{kind}_rejected", script, ["--topology", str(invalid_topology), *arguments], error=error)
        for name in ("admission", "collision"):
            payload = json.loads((scratch / f"{name}.json").read_text(encoding="utf-8"))
            if payload.get("topology_profile_id") != TOPOLOGY_PROFILE_ID or payload.get("topology_sha256") != topology_sha256:
                raise ValueError(f"{name} must bind the exact topology identity")
        partial_topology = scratch / "partial_dataset_topology.csv"
        partial_rows = topology_rows + [dict(row, dataset="unmapped_dataset") for row in topology_rows]
        write_csv(partial_topology, partial_rows)
        partial_json = scratch / "partial_admission.json"
        partial_csv = scratch / "partial_admission.csv"
        partial_args = ["--topology", str(partial_topology), "--sid-map", str(ROOT / "samples" / "synthetic_sid_map.csv"), "--family", "synthetic_contract_probe", "--out-csv", str(partial_csv), "--out-json", str(partial_json)]
        run("admission_partial_dataset_map_valid", "admit_sid_family.py", partial_args, "PASS_SID_FAMILY_ADMISSION")
        partial_payload = json.loads(partial_json.read_text(encoding="utf-8"))
        partial_summaries = {row["dataset"]: row for row in partial_payload["dataset_summaries"]}
        uncovered = partial_summaries.pop("unmapped_dataset")
        if uncovered["topology_items"] != len(topology_rows) or any(uncovered[field] != 0 for field in ("joined_items", "join_coverage", "unique_sid_count", "mixed_cell_sid_count", "max_topology_cells_per_sid")):
            raise ValueError("unmapped dataset must retain its universe and zero coverage/counts")
        if any(uncovered[field] is not None for field in ("unique_sid_ratio", "collision_rate", "cell_collision_rate_spread")):
            raise ValueError("unmapped dataset collision ratios must be null, not zero")
        baseline = json.loads((scratch / "admission.json").read_text(encoding="utf-8"))
        for row in baseline["dataset_summaries"]:
            if {key: value for key, value in row.items() if key != "topology_sha256"} != {key: value for key, value in partial_summaries[row["dataset"]].items() if key != "topology_sha256"}:
                raise ValueError("partially covered input must preserve covered-dataset statistics")
        with partial_csv.open(encoding="utf-8", newline="") as handle:
            if any(row["dataset"] == "unmapped_dataset" for row in csv.DictReader(handle)):
                raise ValueError("unmapped dataset must not emit fabricated collision-cell metrics")
        partial_sha256 = hashlib.sha256(partial_topology.read_bytes()).hexdigest()
        if partial_payload["topology_sha256"] != partial_sha256 or uncovered["topology_sha256"] != partial_sha256:
            raise ValueError("partial admission must bind the complete topology input")
        with (ROOT / "samples" / "synthetic_sid_map.csv").open(encoding="utf-8", newline="") as handle:
            absent_map = [dict(row, dataset="absent_everywhere") for row in csv.DictReader(handle)]
        absent_map_path = scratch / "absent_map.csv"
        write_csv(absent_map_path, absent_map)
        run("admission_no_global_overlap_rejected", "admit_sid_family.py", ["--topology", str(partial_topology), "--sid-map", str(absent_map_path), "--family", "synthetic_contract_probe", "--out-csv", str(scratch / "absent.csv"), "--out-json", str(scratch / "absent.json")], error="SID map has no overlap with topology")

        adapted = scratch / "adapted.csv"
        run("score_adapter_valid", "adapt_method_scores.py", ["--scores", str(scores_path), *adapter_args, "--score-direction", "higher_is_better", "--out-csv", str(adapted)], "PASS_METHOD_SCORE_ADAPTER")
        evaluation_json = scratch / "evaluation.json"

        def evaluate(name: str, input_path: Path, error: str = "") -> dict[str, object]:
            run(name, "evaluate_fixed_candidates.py", ["--candidates", str(input_path), "--out-csv", str(scratch / "metrics.csv"), "--out-json", str(evaluation_json)], "PASS_FIXED_CANDIDATE_EVALUATION", error)
            return {} if error else json.loads(evaluation_json.read_text(encoding="utf-8"))

        evaluation = evaluate("adapted_scores_evaluated", adapted)
        if evaluation["evaluation_units"] != 8:
            raise ValueError("adapter fixture must retain eight evaluation units")
        if evaluation.get("topology_profile_id") != TOPOLOGY_PROFILE_ID or evaluation.get("topology_sha256") != topology_sha256:
            raise ValueError("fixed evaluator must retain the exact topology identity")
        with adapted.open(encoding="utf-8", newline="") as handle:
            identity_rows = list(csv.DictReader(handle))
        if any(row.get("topology_profile_id") != TOPOLOGY_PROFILE_ID or row.get("topology_sha256") != topology_sha256 for row in identity_rows):
            raise ValueError("score adapter must bind the exact topology identity on every row")
        for kind in ("missing_profile", "missing_sha", "empty_profile", "old", "mixed", "mixed_sha", "invalid_sha"):
            probe_candidates = [row.copy() for row in identity_rows]
            if kind in {"missing_profile", "missing_sha"}:
                field = "topology_profile_id" if kind == "missing_profile" else "topology_sha256"
                for row in probe_candidates:
                    row.pop(field)
                error = "candidate input missing fields"
            elif kind == "empty_profile":
                probe_candidates[0]["topology_profile_id"] = ""
                error = "candidate topology_profile_id must be"
            elif kind == "old":
                for row in probe_candidates:
                    row["topology_profile_id"] = "MAIN_B2_B3_REGISTERED_V1"
                error = "candidate topology_profile_id must be"
            elif kind == "mixed":
                probe_candidates[0]["topology_profile_id"] = "MAIN_B2_B3_REGISTERED_V1"
                error = "candidate topology_profile_id must be"
            elif kind == "mixed_sha":
                probe_candidates[0]["topology_sha256"] = "0" * 64
                error = "candidate topology_sha256 must be constant"
            else:
                for row in probe_candidates:
                    row["topology_sha256"] = "not_a_sha256"
                error = "candidate topology_sha256 must be a lowercase SHA256"
            invalid_candidates = scratch / "invalid_identity_candidates.csv"
            write_csv(invalid_candidates, probe_candidates)
            evaluate(f"evaluator_identity_{kind}_rejected", invalid_candidates, error=error)
        with scores_path.open(encoding="utf-8", newline="") as handle:
            scores = list(csv.DictReader(handle))
        probe = [row.copy() for row in scores[:2]]
        probe[0]["score"], probe[1]["score"] = "1.0", "2.0"
        probe_path = scratch / "scores.csv"
        write_csv(probe_path, probe)
        adapted_by_direction: list[dict[str, str]] = []
        for direction, expected in [("lower_is_better", 1.0), ("higher_is_better", 1.0 / math.log2(3))]:
            run(f"adapter_{direction}", "adapt_method_scores.py", ["--scores", str(probe_path), *adapter_args, "--score-direction", direction, "--out-csv", str(adapted)], "PASS_METHOD_SCORE_ADAPTER")
            evaluation = evaluate(f"evaluator_{direction}", adapted)
            overall = next(row for row in evaluation["aggregates"] if row["slice_type"] == "all")
            if abs(float(overall["ndcg10"]) - expected) > 1e-6:
                raise ValueError(f"incorrect ordering for {direction}")
            with adapted.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            for row in rows:
                row["method_id"] = direction
            adapted_by_direction.extend(rows)
        write_csv(adapted, adapted_by_direction)
        evaluation = evaluate("methods_not_pooled", adapted)
        if evaluation["evaluation_units"] != 2 or len(evaluation["methods"]) != 2:
            raise ValueError("distinct methods sharing unit IDs must remain separate")

        invalid_scores = [row.copy() for row in probe]
        invalid_scores[0]["candidate_id"] = "missing_topology_target"
        write_csv(probe_path, invalid_scores)
        run("missing_topology_target_rejected", "adapt_method_scores.py", ["--scores", str(probe_path), *adapter_args, "--score-direction", "higher_is_better", "--out-csv", str(adapted)], error="target item is absent from topology")
        for target_flags in [("0", "0"), ("1", "1")]:
            invalid_scores = [row.copy() for row in probe]
            for row, flag in zip(invalid_scores, target_flags):
                row["is_target"] = flag
            write_csv(probe_path, invalid_scores)
            run(f"target_count_{sum(int(flag) for flag in target_flags)}_rejected", "adapt_method_scores.py", ["--scores", str(probe_path), *adapter_args, "--score-direction", "higher_is_better", "--out-csv", str(adapted)], error="exactly one target")
        invalid_rows = [row.copy() for row in adapted_by_direction[:2]]
        invalid_rows[0]["score_direction"] = "higher_is_better"
        write_csv(adapted, invalid_rows)
        evaluate("mixed_direction_rejected", adapted, error="method metadata must be constant")
        for value in ("nan", "inf"):
            invalid_scores = [row.copy() for row in probe]
            invalid_scores[0]["score"] = value
            write_csv(probe_path, invalid_scores)
            run(f"adapter_{value}_rejected", "adapt_method_scores.py", ["--scores", str(probe_path), *adapter_args, "--score-direction", "higher_is_better", "--out-csv", str(adapted)], error="scores must be finite")
            invalid_rows = [row.copy() for row in adapted_by_direction[:2]]
            invalid_rows[0]["score"] = value
            write_csv(adapted, invalid_rows)
            evaluate(f"evaluator_{value}_rejected", adapted, error="scores must be finite")
        invalid_scores = [row.copy() for row in probe]
        invalid_scores[1]["candidate_id"] = invalid_scores[0]["candidate_id"]
        write_csv(probe_path, invalid_scores)
        run("adapter_duplicate_candidate_rejected", "adapt_method_scores.py", ["--scores", str(probe_path), *adapter_args, "--score-direction", "higher_is_better", "--out-csv", str(adapted)], error="duplicate candidate_id")
        invalid_rows = [row.copy() for row in adapted_by_direction[:2]]
        invalid_rows[1]["candidate_id"] = invalid_rows[0]["candidate_id"]
        write_csv(adapted, invalid_rows)
        evaluate("evaluator_duplicate_candidate_rejected", adapted, error="duplicate candidate_id")

    output = ROOT / "outputs" / "interface_contract_checks.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"status": "pass", "checks": checks}, indent=2) + "\n", encoding="utf-8")
    print("PASS_INTERFACE_CONTRACTS")


if __name__ == "__main__":
    main()
