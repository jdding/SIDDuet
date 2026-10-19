#!/usr/bin/env python3
"""Run the fixed synthetic workflow through a small local HTTP interface."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def metadata():
    state = json.loads((ROOT / "RELEASE_STATUS.json").read_text(encoding="utf-8"))
    return {
        key: state[key]
        for key in ("version", "publication_status", "scientific_reproduction_status")
    }


def run_workflow():
    started = time.monotonic()
    manifest = json.loads((ROOT / "PACKAGE_MANIFEST.json").read_text(encoding="utf-8"))
    names = [row["path"] for row in manifest["files"]] + [
        "PACKAGE_MANIFEST.json",
        "CHECKSUMS.sha256",
    ]
    with tempfile.TemporaryDirectory(prefix="rolemap-synthetic-demo-") as folder:
        work = Path(folder)
        for name in names:
            relative = Path(name)
            source = (ROOT / relative).resolve()
            if relative.is_absolute() or ".." in relative.parts or not source.is_relative_to(ROOT):
                raise ValueError("invalid manifest member")
            target = work / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        proc = subprocess.Popen(
            [sys.executable, "-I", str(work / "scripts" / "validate_release.py")],
            cwd=work,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            raise RuntimeError("workflow timed out") from None
        if proc.returncode:
            raise RuntimeError("workflow failed")
        outputs = work / "outputs"
        load = lambda name: json.loads((outputs / name).read_text(encoding="utf-8"))
        summary = load("public_resource_smoke_result.json")
        checks = load("interface_contract_checks.json")["checks"]
        with (outputs / "synthetic_role_topology.csv").open(newline="", encoding="utf-8") as handle:
            topology = list(csv.DictReader(handle))
        if summary["status"] != "pass" or not all(row["passed"] for row in checks):
            raise RuntimeError("synthetic checks failed")
        if len(topology) != 8 or any(row["dataset"] != "demo" for row in topology):
            raise RuntimeError("unexpected synthetic topology")
        topology = [
            {
                "item": row["item_id"],
                "search_support": float(row["search_support"]),
                "rec_support": float(row["rec_support"]),
                "rsd": float(row["rsd_score"]),
                "rsi": float(row["rsi_signed"]),
                "cell": row["topology_cell"],
            }
            for row in topology
        ]
        admission = load("synthetic_admission.json")["dataset_summaries"][0]
        metrics = [
            row
            for row in load("synthetic_fixed_candidate_metrics.json")["aggregates"]
            if row["slice_type"] == "all"
        ]
        result = {
            "status": "pass",
            "synthetic": True,
            "isolated_run": True,
            "run_id": secrets.token_hex(6),
            "metadata": metadata(),
            "topology": topology,
            "coverage": {
                key: admission[key]
                for key in ("topology_items", "joined_items", "join_coverage", "unique_sid_count")
            },
            "metrics": [
                {key: row[key] for key in ("role", "units", "ndcg10", "hit10")} for row in metrics
            ],
            "checks": [{"name": row["check"], "passed": bool(row["passed"])} for row in checks],
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
    return result


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, value, content_type="application/json; charset=utf-8", nonce=None):
        body = (
            json.dumps(value, allow_nan=False).encode()
            if content_type.startswith("application/json")
            else value
        )
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            (
                "default-src 'none'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; "
                "frame-ancestors 'none'; form-action 'none'; script-src 'nonce-"
            )
            + (nonce or "")
            + "'",
        )
        self.end_headers()
        self.wfile.write(body)

    def allowed_host(self):
        try:
            host = urlsplit("//" + self.headers.get("Host", "")).hostname
        except ValueError:
            return False
        return self.server.bind_host != "127.0.0.1" or host in {"127.0.0.1", "localhost"}

    def do_GET(self):
        if not self.allowed_host():
            return self.reply(403, {"error": "Host is not allowed"})
        if self.path == "/health":
            return self.reply(200, {"status": "ready", "synthetic": True, **metadata()})
        if self.path == "/":
            nonce = secrets.token_urlsafe(18)
            body = (
                (ROOT / "demo" / "index.html")
                .read_text(encoding="utf-8")
                .replace("__SCRIPT_NONCE__", nonce)
                .encode()
            )
            return self.reply(200, body, "text/html; charset=utf-8", nonce)
        self.reply(404, {"error": "Route not found"})

    def do_POST(self):
        if not self.allowed_host():
            return self.reply(403, {"error": "Host is not allowed"})
        if self.path != "/api/run":
            return self.reply(404, {"error": "Route not found"})
        origin = self.headers.get("Origin")
        if origin and (
            urlsplit(origin).scheme not in {"http", "https"}
            or urlsplit(origin).netloc != self.headers.get("Host")
        ):
            return self.reply(403, {"error": "Origin is not allowed"})
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            return self.reply(415, {"error": "Use empty JSON object"})
        try:
            size = int(self.headers.get("Content-Length", "-1"))
            if not 0 < size <= 64:
                return self.reply(413, {"error": "Request body size is not allowed"})
            if json.loads(self.rfile.read(size)) != {}:
                return self.reply(400, {"error": "Only an empty JSON object is accepted"})
        except (ValueError, json.JSONDecodeError):
            return self.reply(400, {"error": "Invalid JSON request"})
        if not self.server.workflow_lock.acquire(blocking=False):
            return self.reply(429, {"error": "A synthetic run is already active"})
        try:
            result = run_workflow()
        except Exception:
            self.reply(500, {"error": "Synthetic workflow did not complete"})
        else:
            self.reply(200, result)
        finally:
            self.server.workflow_lock.release()

    def do_PUT(self):
        self.reply(405, {"error": "Method not allowed"})

    do_DELETE = do_PATCH = do_OPTIONS = do_PUT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Explicit bind address; defaults to loopback. Hosting is a separate user action.",
    )
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.bind_host = args.host
    server.workflow_lock = threading.Lock()
    print(f"DEMO_READY http://{args.host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
