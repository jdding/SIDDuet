"""SIDDuet: cross-task diagnostics for Semantic IDs across search and recommendation."""

from __future__ import annotations

from pathlib import Path

__version__ = "0.4.1"
REPO_ROOT = Path(__file__).resolve().parents[1]

__all__ = ["REPO_ROOT", "__version__"]
