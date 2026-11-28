"""Unified command-line entry point for SIDDuet workflows."""

from __future__ import annotations

import argparse
from importlib.util import find_spec
from pathlib import Path
import subprocess
import sys

from sidduet import REPO_ROOT, __version__

COMMANDS: dict[str, tuple[str, str]] = {
    "verify-table2": (
        "scripts/verify_table2.py",
        "Verify the six main Table 2 rows from saved Monte Carlo draw means.",
    ),
    "validate": (
        "scripts/validate_release.py",
        "Check SHA-256 manifest integrity and run the standard-library smoke suite.",
    ),
    "calibrate": (
        "scripts/calibrate_task_allocation.py",
        "Calibrate paired task counts against band-matched and exact-total references.",
    ),
    "inspect-groups": (
        "scripts/inspect_groups.py",
        "Rank collision groups by allocation JSD for upper-tail human inspection.",
    ),
    "import-counts": (
        "scripts/import_role_counts.py",
        "Map local CSV columns into the canonical paired-count schema.",
    ),
    "replay-qilin": (
        "scripts/replay_qilin_calibration.py",
        "Replay Qilin GenSAR shared-prefix calibration from pinned provider Parquet files.",
    ),
    "demo": (
        "scripts/serve_demo.py",
        "Launch the local browser interface for the three SIDDuet workflows.",
    ),
}


COMMAND_EXTRAS = {
    "calibrate": ("calibration", ("numpy",)),
    "inspect-groups": ("calibration", ("numpy",)),
    "replay-qilin": ("provider", ("numpy", "pyarrow")),
}


def resolve_script(rel_path: str) -> Path:
    script = (REPO_ROOT / rel_path).resolve()
    if not script.is_file():
        raise FileNotFoundError(
            f"Cannot find {rel_path}. From a tagged SIDDuet checkout, "
            "use an editable install: python -m pip install -e ."
        )
    return script


def build_parser() -> argparse.ArgumentParser:
    epilog_lines = ["Available subcommands:"]
    for name, (_, desc) in COMMANDS.items():
        epilog_lines.append(f"  {name:<15s} {desc}")
    epilog_lines.append("")
    epilog_lines.append("Pass `-h` after a subcommand to see its options (e.g. `sidduet calibrate -h`).")
    parser = argparse.ArgumentParser(
        prog="sidduet",
        description="SIDDuet CLI: Semantic IDs across Search and Recommendation.",
        epilog="\n".join(epilog_lines),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"SIDDuet {__version__}",
    )
    parser.add_argument("command", choices=sorted(COMMANDS), help="Workflow subcommand to execute.")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments forwarded to the workflow script.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parsed = parser.parse_args(argv)
    rel_path, _ = COMMANDS[parsed.command]
    try:
        script = resolve_script(rel_path)
    except FileNotFoundError as error:
        parser.error(str(error))
    extra, modules = COMMAND_EXTRAS.get(parsed.command, ("", ()))
    missing = [module for module in modules if find_spec(module) is None]
    if missing:
        parser.error(
            f"{parsed.command} needs {', '.join(missing)}. From the SIDDuet checkout, "
            f"run: python -m pip install -e '.[{extra}]'"
        )
    forwarded = list(parsed.args)
    if forwarded and forwarded[0] == "--":
        forwarded = forwarded[1:]
    proc = subprocess.run([sys.executable, "-B", str(script), *forwarded], check=False)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
