"""Session-scoped pytest setup.

Prepends ``<repo>/bin`` to ``PATH`` so demo Makefiles that invoke
``genesispy`` / ``gvpy`` resolve to the in-tree launchers without
requiring ``pip install -e .``.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BIN_DIR = REPO_ROOT / "bin"

if BIN_DIR.is_dir():
    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    if str(BIN_DIR) not in path_parts:
        os.environ["PATH"] = str(BIN_DIR) + os.pathsep + os.environ.get("PATH", "")
