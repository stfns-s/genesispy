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
def _reset_cli_deprecation_warnings():
    """Clear the one-time-per-flag deprecation guard before each test so
    deprecation warnings in tests don't leak across tests in the same
    process."""
    from genesispy.cli import _reset_deprecation_warnings

    _reset_deprecation_warnings()
    yield
    _reset_deprecation_warnings()


@pytest.fixture(autouse=True)
def _reset_error_log_state():
    """Suppress the process-global error log between tests so the
    Cluster J ``--log`` default (``genesispy.log`` lazy-open) doesn't
    create stray log files in the test working directory when other
    tests construct a Manager and then trigger error()/warning()."""
    from genesispy import reporting

    reporting.set_log_file(None)
    yield
    reporting.set_log_file(None)
