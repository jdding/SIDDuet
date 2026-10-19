#!/usr/bin/env python3
"""Validate the public resource staging package."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "public_resource_smoke_result.json"
def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def checksum_rows() -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in (ROOT / "CHECKSUMS.sha256").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, rel = line.split("  ", 1)
        rows[rel] = digest
    return rows

def read_csv(rel: str) -> list[dict[str, str]]:
    with (ROOT / rel).open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))

def run_public_builder() -> list[str]:
    issues: list[str] = []
    outputs = ROOT / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)

    def run(name: str, command: list[str], marker: str, expected: list[Path]) -> None:
        proc = subprocess.run(command, text=True, capture_output=True, check=False)
        if proc.returncode != 0:
            issues.append(f"{name}_returncode")
        if marker not in proc.stdout:
            issues.append(f"{name}_missing_pass_output")
        for path in expected:
            if not path.exists() or path.stat().st_size == 0:
                issues.append(f"{name}_missing_{path.name}")

    summary_csv = outputs / "synthetic_public_summary.csv"
    summary_json = outputs / "synthetic_public_summary.json"
    run(
        "public_summary_builder",
        [sys.executable, str(ROOT / "scripts" / "build_public_summaries.py"), "--sample", str(ROOT / "samples" / "synthetic_sid_topology_sample.csv"), "--out-csv", str(summary_csv), "--out-json", str(summary_json)],
        "PASS_PUBLIC_SUMMARY_BUILDER",
        [summary_csv, summary_json],
    )

    materialized_csv = outputs / "synthetic_materialized_role_label_counts.csv"
    materialized_json = outputs / "synthetic_role_label_materialization.json"
    run(
        "role_label_materializer",
        [sys.executable, str(ROOT / "scripts" / "materialize_role_label_counts.py"), "--events", str(ROOT / "samples" / "synthetic_role_events.csv"), "--out-csv", str(materialized_csv), "--out-json", str(materialized_json)],
        "PASS_ROLE_LABEL_MATERIALIZER",
        [materialized_csv, materialized_json],
    )
    if materialized_csv.exists() and read_csv("outputs/synthetic_materialized_role_label_counts.csv") != read_csv("samples/synthetic_role_label_counts.csv"):
        issues.append("role_label_materializer_fixture_mismatch")

    topology_csv = outputs / "synthetic_role_topology.csv"
    topology_json = outputs / "synthetic_role_topology.json"
    with tempfile.TemporaryDirectory(prefix="rolemap-initial-topology-") as initial_dir:
        initial_csv = Path(initial_dir) / "synthetic_role_topology.csv"
        initial_json = Path(initial_dir) / "synthetic_role_topology.json"
        run(
            "role_topology_builder",
            [sys.executable, str(ROOT / "scripts" / "build_role_topology.py"), "--role-counts", str(materialized_csv), "--out-csv", str(initial_csv), "--out-json", str(initial_json)],
            "PASS_ROLE_TOPOLOGY_BUILDER", [initial_csv, initial_json],
        )
        for source, target in [(initial_csv, topology_csv), (initial_json, topology_json)]:
            if source.exists():
                shutil.copy2(source, target)
    if topology_csv.exists():
        topology_rows = read_csv("outputs/synthetic_role_topology.csv")
        if any(row.get("profile_id") != "sr_sid_rolemap.topology.value_median.v2" for row in topology_rows):
            issues.append("synthetic_profile_identity_mismatch")
        if any(int(row["rsi_split_key"]) == 0 and row["rsi_mag_bucket"] == "high_rsi" for row in topology_rows):
            issues.append("synthetic_zero_imbalance_in_high")
        if len(topology_rows) != 8:
            issues.append("role_topology_builder_item_count")
        if {row.get("topology_cell") for row in topology_rows} != {"low_rsd|low_rsi", "low_rsd|high_rsi", "high_rsd|low_rsi", "high_rsd|high_rsi"}:
            issues.append("role_topology_builder_cell_coverage")
    with tempfile.TemporaryDirectory() as repeat_dir:
        repeat_csv = Path(repeat_dir) / "synthetic_role_topology.csv"
        repeat_json = Path(repeat_dir) / "synthetic_role_topology.json"
        run(
            "role_topology_builder_repeat",
            [sys.executable, str(ROOT / "scripts" / "build_role_topology.py"), "--role-counts", str(materialized_csv), "--out-csv", str(repeat_csv), "--out-json", str(repeat_json)],
            "PASS_ROLE_TOPOLOGY_BUILDER",
            [repeat_csv, repeat_json],
        )
        if topology_csv.exists() and repeat_csv.exists() and topology_csv.read_bytes() != repeat_csv.read_bytes():
            issues.append("role_topology_builder_nondeterministic_csv")
        if topology_json.exists() and repeat_json.exists() and topology_json.read_bytes() != repeat_json.read_bytes():
            issues.append("role_topology_builder_nondeterministic_json")

    admission_csv = outputs / "synthetic_admission_cells.csv"
    admission_json = outputs / "synthetic_admission.json"
    run(
        "sid_family_admission",
        [sys.executable, str(ROOT / "scripts" / "admit_sid_family.py"), "--topology", str(topology_csv), "--sid-map", str(ROOT / "samples" / "synthetic_sid_map.csv"), "--family", "synthetic_demo", "--out-csv", str(admission_csv), "--out-json", str(admission_json)],
        "PASS_SID_FAMILY_ADMISSION",
        [admission_csv, admission_json],
    )
    if admission_json.exists():
        admission = json.loads(admission_json.read_text(encoding="utf-8"))
        summaries = admission.get("dataset_summaries", [])
        if not summaries or float(summaries[0].get("join_coverage", 0.0)) != 1.0:
            issues.append("sid_family_admission_join_coverage")
        if not summaries or int(summaries[0].get("max_topology_cells_per_sid", 0)) != 4:
            issues.append("sid_family_admission_cell_mixing")

    collision_csv = outputs / "synthetic_collision_metrics.csv"
    collision_json = outputs / "synthetic_collision_metrics.json"
    run(
        "collision_diagnostic",
        [sys.executable, str(ROOT / "scripts" / "evaluate_collision_diagnostic.py"), "--topology", str(topology_csv), "--sid-map", str(ROOT / "samples" / "synthetic_sid_map.csv"), "--out-csv", str(collision_csv), "--out-json", str(collision_json)],
        "PASS_COLLISION_DIAGNOSTIC",
        [collision_csv, collision_json],
    )
    if collision_json.exists() and int(json.loads(collision_json.read_text(encoding="utf-8")).get("evaluation_units", 0)) != 16:
        issues.append("collision_diagnostic_unit_count")

    fixed_csv = outputs / "synthetic_fixed_candidate_metrics.csv"
    fixed_json = outputs / "synthetic_fixed_candidate_metrics.json"
    adapted_csv = outputs / "synthetic_adapted_candidates.csv"
    run(
        "method_score_adapter",
        [sys.executable, str(ROOT / "scripts" / "adapt_method_scores.py"), "--scores", str(ROOT / "samples" / "synthetic_method_scores.csv"), "--topology", str(topology_csv), "--method-id", "synthetic_discriminative_ranker", "--method-paradigm", "discriminative", "--score-direction", "higher_is_better", "--out-csv", str(adapted_csv)],
        "PASS_METHOD_SCORE_ADAPTER",
        [adapted_csv],
    )
    run(
        "fixed_candidate_evaluation",
        [sys.executable, str(ROOT / "scripts" / "evaluate_fixed_candidates.py"), "--candidates", str(adapted_csv), "--out-csv", str(fixed_csv), "--out-json", str(fixed_json)],
        "PASS_FIXED_CANDIDATE_EVALUATION",
        [fixed_csv, fixed_json],
    )
    if fixed_json.exists() and int(json.loads(fixed_json.read_text(encoding="utf-8")).get("evaluation_units", 0)) != 8:
        issues.append("fixed_candidate_evaluation_unit_count")
    run(
        "interface_contracts",
        [sys.executable, str(ROOT / "scripts" / "validate_interface_contracts.py")],
        "PASS_INTERFACE_CONTRACTS",
        [outputs / "interface_contract_checks.json"],
    )
    return issues

def current_profile_issues() -> list[str]:
    issues = []
    profile = "sr_sid_rolemap.topology.value_median.v2"
    registry = json.loads((ROOT / "docs/TOPOLOGY_PROFILE_REGISTRY.json").read_text())
    state = json.loads((ROOT / "RELEASE_STATUS.json").read_text())
    if registry["current_profile_id"] != profile or state["topology_profile_id"] != profile:
        issues.append("current_profile_id_mismatch")
    if sha256(ROOT / registry["builder"]) != registry["builder_sha256"]:
        issues.append("current_builder_identity_mismatch")
    if sha256(ROOT / registry["contract"]) != registry["contract_sha256"]:
        issues.append("current_contract_identity_mismatch")
    proof = json.loads((ROOT / registry["reconstruction_verification"]).read_text())
    if proof["status"] != "PASS_REFERENCE_AND_INTERNAL_RECEIVER" or proof["topology_profile_id"] != profile:
        issues.append("current_reconstruction_receipt_mismatch")
    total = 0
    for dataset, relative in registry["current_references"].items():
        reference = json.loads((ROOT / relative).read_text())
        if (reference["profile_id"] != profile or reference["builder_sha256"] != registry["builder_sha256"]
                or reference["profile_contract_sha256"] != registry["contract_sha256"]):
            issues.append("reference_identity_mismatch:" + dataset)
        cells = reference["cell_counts"]
        if len(cells) != 4 or sum(cells.values()) != reference["items"]:
            issues.append("reference_cell_totals_mismatch:" + dataset)
        total += reference["items"]
        for axis, diagnostic in reference["median_diagnostics"][dataset].items():
            if diagnostic["low_items"] != diagnostic["below_median_items"] + diagnostic["at_median_items"]:
                issues.append("ties_not_kept_low:" + dataset + ":" + axis)
            if diagnostic["high_items"] != diagnostic["above_median_items"] or diagnostic["items"] != reference["items"]:
                issues.append("reference_median_totals_mismatch:" + dataset + ":" + axis)
        for field, source_field in [("topology_csv_sha256", "output_csv_sha256"), ("decision_sha256", "semantic_key_rank_partition_sha256")]:
            if proof["datasets"][dataset][field] != reference[source_field]:
                issues.append("receiver_output_binding_mismatch:" + dataset)
    if total != registry["reconstructed_common_items"] or registry["jdsearch_full_v2_rebuilt"]:
        issues.append("current_scope_mismatch")
    case = json.loads((ROOT / "reports/v2/fixed_275_case.json").read_text())
    if case["topology_profile_id"] != profile or sum(case["cell_counts"].values()) != case["group_size"]:
        issues.append("current_case_profile_mismatch")
    if case["topology_sha256"] != proof["datasets"]["kuaisar"]["topology_csv_sha256"]:
        issues.append("current_case_output_binding_mismatch")
    index = json.loads((ROOT / "reports/PROFILE_EVIDENCE_INDEX.json").read_text())
    return issues

def inventory_issues() -> list[str]:
    manifest = json.loads((ROOT / "PACKAGE_MANIFEST.json").read_text())
    rows = manifest["files"]
    expected = {row["path"] for row in rows}
    parts = json.loads((ROOT / "weights/unisar_kuaisar_v1/CHECKPOINT.json").read_text())["parts"]
    optional = {"weights/unisar_kuaisar_v1/" + row["path"] for row in parts}
    files = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*")
             if p.is_file() and not set(p.relative_to(ROOT).parts) & {".git", "outputs", "__pycache__"}}
    files -= {"CHECKSUMS.sha256", "PACKAGE_MANIFEST.json"} | optional
    checksums = checksum_rows()
    issues = []
    if len(rows) != len(expected) or expected != files or expected != set(checksums):
        issues.append("inventory_mismatch")
    for row in rows:
        path = ROOT / row["path"]
        if not path.is_file() or row["sha256"] != checksums.get(row["path"]) or path.stat().st_size != row["bytes"] or sha256(path) != row["sha256"]:
            issues.append("integrity_mismatch:" + row["path"])
    if manifest["counts"] != {"files": len(rows), "bytes": sum(row["bytes"] for row in rows)}:
        issues.append("manifest_counts_mismatch")
    release = json.loads((ROOT / "RELEASE_STATUS.json").read_text())
    if manifest["release_version"] != release["version"] or manifest["release_tag"] != release["release_tag"]:
        issues.append("release_identity_mismatch")
    return issues


def checkpoint_issues() -> tuple[list[str], str]:
    root = ROOT / "weights/unisar_kuaisar_v1"
    spec = json.loads((root / "CHECKPOINT.json").read_text())
    if spec["schema"] != "sr_sid_rolemap.checkpoint_parts.v1" or spec["license"] != "CC-BY-NC-SA-4.0":
        return ["checkpoint_manifest_mismatch"], "invalid"
    paths = [(root / row["path"]).resolve() for row in spec["parts"]]
    if any(not path.is_relative_to(root.resolve()) for path in paths):
        return ["checkpoint_path_escape"], "invalid"
    if not any(path.exists() for path in paths):
        return [], "optional_release_download_not_present"
    whole = hashlib.sha256()
    total = 0
    for row, path in zip(spec["parts"], paths):
        if not path.is_file() or path.stat().st_size != row["bytes"] or sha256(path) != row["sha256"]:
            return ["checkpoint_part_mismatch"], "invalid"
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                total += len(block)
                whole.update(block)
    if total != spec["bytes"] or whole.hexdigest() != spec["sha256"]:
        return ["checkpoint_whole_mismatch"], "invalid"
    return [], "all_parts_verified"


def main() -> None:
    integrity = inventory_issues()
    profile = current_profile_issues()
    checkpoint, checkpoint_status = checkpoint_issues()
    builder = run_public_builder()
    groups = {"inventory_issues": integrity, "current_profile_issues": profile,
              "checkpoint_issues": checkpoint, "public_builder_issues": builder}
    payload = {"status": "fail" if any(groups.values()) else "pass", **groups,
               "current_profile_id": "sr_sid_rolemap.topology.value_median.v2",
               "checkpoint_status": checkpoint_status,
               "verification_scope": "Synthetic interfaces, complete source inventory, bound current aggregate references and optional checkpoint integrity; real model replay is separate."}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    if payload["status"] != "pass":
        raise SystemExit(json.dumps(payload, indent=2))
    print("PASS_PUBLIC_RESOURCE_SMOKE")
    print("wrote outputs/public_resource_smoke_result.json")


if __name__ == "__main__":
    main()
