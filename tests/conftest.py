"""Session-scoped pytest setup.

Prepends ``<repo>/bin`` to ``PATH`` so demo Makefiles that invoke
``genesispy`` / ``gvpy`` resolve to the in-tree launchers without
requiring ``pip install -e .``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BIN_DIR = REPO_ROOT / "bin"

if BIN_DIR.is_dir():
    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    if str(BIN_DIR) not in path_parts:
        os.environ["PATH"] = str(BIN_DIR) + os.pathsep + os.environ.get("PATH", "")


@pytest.fixture(autouse=True)
def _reset_caches():
    """Every process-global (module cache, outfile cache, counters, the log
    tee) starts clean for each test; a module left over from an earlier test
    would otherwise appear in a later ``--stdout`` dump, and a Manager's
    ``--log`` default would leave stray log files."""
    from genesispy import cache

    cache.clear_all()
    yield
    cache.clear_all()


@pytest.fixture(autouse=True)
def _reset_cli_deprecation_warnings():
    """Clear the one-time-per-flag deprecation guard before each test so
    deprecation warnings in tests don't leak across tests in the same
    process."""
    from genesispy.cli import _reset_deprecation_warnings

    _reset_deprecation_warnings()
    yield
    _reset_deprecation_warnings()

