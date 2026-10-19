#!/usr/bin/env python3
"""Validate the dependency-free invariants of a SearchRec RoleMap record."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "sr_sid_rolemap.rolemap_record.v1"
LEVELS = ("L0", "L1", "L2", "L3")
LEVEL_STATUS = {"observed", "null", "not_evaluated", "blocked"}
PERMISSION_STATUS = {"supported", "blocked", "not_evaluated"}
REQUIRED_TOP_LEVEL = {
    "schema_version",
    "record_id",
    "dataset",
    "item_bridge",
    "role_evidence",
    "topology",
    "sid_artifact",
    "observations",
    "decision",
    "provenance",
    "release",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def object_fields(value: Any, fields: set[str], name: str) -> None:
    require(isinstance(value, dict) and set(value) == fields, f"{name} fields do not match the v1 contract")


def string_fields(value: dict[str, Any], fields: tuple[str, ...], name: str) -> None:
    for field in fields:
        require(nonempty_string(value[field]), f"{name}.{field} must be non-empty")


def finite_number(value: Any) -> bool:
    return type(value) in {int, float} and math.isfinite(value)


def validate(record: dict[str, Any]) -> None:
    object_fields(record, REQUIRED_TOP_LEVEL, "top-level")
    require(record["schema_version"] == SCHEMA_VERSION, "unexpected schema_version")
    require(nonempty_string(record["record_id"]), "record_id must be non-empty")

    dataset = record["dataset"]
    object_fields(dataset, {"dataset_id", "split", "profile_id"}, "dataset")
    string_fields(dataset, ("dataset_id", "split", "profile_id"), "dataset")
    bridge = record["item_bridge"]
    object_fields(bridge, {"item_key", "key_type", "roles"}, "item_bridge")
    require(bridge.get("roles") == ["search", "recommendation"], "roles must be search then recommendation")
    require(nonempty_string(bridge.get("item_key")), "item_bridge.item_key must be non-empty")
    require(bridge["key_type"] in {"raw_restricted", "hashed_public", "synthetic"}, "invalid item key_type")

    role_evidence = record["role_evidence"]
    object_fields(role_evidence, {"source_protocol", "search", "recommendation"}, "role_evidence")
    string_fields(role_evidence, ("source_protocol",), "role_evidence")
    for role in ("search", "recommendation"):
        summary = role_evidence.get(role, {})
        object_fields(summary, {"support_bucket", "top_label", "entropy"}, role)
        require(nonempty_string(summary.get("support_bucket")), f"{role} support_bucket is required")
        require(nonempty_string(summary.get("top_label")), f"{role} top_label is required")
        require(finite_number(summary.get("entropy")) and summary["entropy"] >= 0, f"{role} entropy is invalid")

    topology = record["topology"]
    object_fields(topology, {"level", "status", "rsd", "rsi", "topology_cell", "builder_version"}, "topology")
    require(finite_number(topology["rsd"]), "topology.rsd must be finite")
    require(finite_number(topology["rsi"]) and -1 <= topology["rsi"] <= 1, "topology.rsi must be finite and within [-1, 1]")
    string_fields(topology, ("builder_version",), "topology")
    require(topology.get("level") == "L0", "topology must be the L0 record")
    require(topology.get("status") in {"observed", "null"}, "L0 must be observed or null")
    require(topology.get("topology_cell") in {
        "low_rsd|low_rsi",
        "low_rsd|high_rsi",
        "high_rsd|low_rsi",
        "high_rsd|high_rsi",
    }, "invalid topology cell")

    artifact = record["sid_artifact"]
    object_fields(artifact, {"artifact_id", "family", "map_version", "join_status", "provenance_uri"}, "sid_artifact")
    string_fields(artifact, ("artifact_id", "family", "map_version", "provenance_uri"), "sid_artifact")
    require(artifact["join_status"] in {"joined", "not_joined", "partial"}, "invalid SID join_status")

    observations = record["observations"]
    object_fields(observations, {"L1", "L2", "L3"}, "observations")
    for level in ("L1", "L2", "L3"):
        evidence = observations[level]
        object_fields(evidence, {"status", "surfaces"}, level)
        status = evidence.get("status")
        surfaces = evidence.get("surfaces")
        require(status in LEVEL_STATUS, f"invalid {level} status")
        require(isinstance(surfaces, list), f"{level}.surfaces must be a list")
        if status in {"observed", "null"}:
            require(bool(surfaces), f"{level} {status} requires at least one surface")
        if status in {"not_evaluated", "blocked"}:
            require(not surfaces, f"{level} {status} cannot contain observed surfaces")
        for surface in surfaces:
            object_fields(surface, {"surface_type", "status", "candidate_universe", "summary"}, f"{level} surface")
            require(surface.get("status") in {"observed", "null"}, f"invalid {level} surface status")
            require(nonempty_string(surface.get("surface_type")), f"{level} surface_type is required")
            require(nonempty_string(surface.get("candidate_universe")), f"{level} candidate_universe is required")
            require(isinstance(surface.get("summary"), dict), f"{level} summary must be an object")
        if status == "observed":
            require(any(surface["status"] == "observed" for surface in surfaces), f"{level} observed requires an observed surface")
        if status == "null":
            require(all(surface["status"] == "null" for surface in surfaces), f"{level} null cannot contain an observed surface")

    object_fields(record["decision"], {"claim_permissions", "next_required_checks"}, "decision")
    permissions = record["decision"].get("claim_permissions")
    require(isinstance(permissions, list) and permissions, "at least one claim permission is required")
    claim_ids: set[str] = set()
    for permission in permissions:
        object_fields(permission, {"claim_id", "status", "evidence_level", "reason"}, "claim permission")
        claim_id = permission.get("claim_id")
        require(nonempty_string(claim_id), "claim_id must be non-empty")
        require(claim_id not in claim_ids, f"duplicate claim_id: {claim_id}")
        claim_ids.add(claim_id)
        require(permission.get("status") in PERMISSION_STATUS, f"invalid permission status for {claim_id}")
        require(permission.get("evidence_level") in LEVELS, f"invalid evidence level for {claim_id}")
        require(nonempty_string(permission.get("reason")), f"reason is required for {claim_id}")
        if permission["status"] == "supported" and permission["evidence_level"] != "L0":
            evidence = observations[permission["evidence_level"]]
            require(evidence["status"] == "observed", f"supported {claim_id} lacks observed evidence")

    unresolved = any(row["status"] != "supported" for row in permissions)
    next_checks = record["decision"].get("next_required_checks")
    require(isinstance(next_checks, list), "next_required_checks must be a list")
    require(all(nonempty_string(check) for check in next_checks), "next_required_checks must contain non-empty strings")
    if unresolved:
        require(bool(next_checks), "blocked or unevaluated claims require a next check")

    provenance = record["provenance"]
    object_fields(provenance, {"builders", "source_checksums", "protocol_versions"}, "provenance")
    for field in ("builders", "source_checksums", "protocol_versions"):
        require(isinstance(provenance.get(field), list) and provenance[field], f"provenance.{field} is required")
        require(all(nonempty_string(value) for value in provenance[field]), f"provenance.{field} must contain non-empty strings")
    release = record["release"]
    object_fields(release, {"access_level", "restricted_fields"}, "release")
    require(release["access_level"] in {"public_synthetic", "public_hashed", "aggregate_only", "builder_only", "restricted"}, "invalid release access_level")
    require(isinstance(release["restricted_fields"], list) and all(nonempty_string(value) for value in release["restricted_fields"]), "restricted_fields must be a string list")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", required=True, type=Path)
    parser.add_argument("--schema", type=Path)
    args = parser.parse_args()

    record = json.loads(args.record.read_text(encoding="utf-8"))
    validate(record)
    if args.schema is not None:
        schema = json.loads(args.schema.read_text(encoding="utf-8"))
        require(schema.get("title") == "SearchRec RoleMap Record", "unexpected JSON Schema title")
        require(schema.get("properties", {}).get("schema_version", {}).get("const") == SCHEMA_VERSION, "JSON Schema version mismatch")
    print("PASS_ROLEMAP_RECORD_VALIDATION")


if __name__ == "__main__":
    main()
