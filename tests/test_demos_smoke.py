"""Smoke test for hand-ported Genesis2 demos.

Per-file checks (NOT a gold diff -- Phase G owns gold diffs):

* Each demo directory exists.
* Every ``.vpy``/``.svpy`` file parses cleanly via
  :func:`genesispy.template.parser.parse_vpy` and the resulting Python
  source ``compile()`` succeeds.
* Every ``config.py`` / ``*.cfg.py`` file ``compile()`` succeeds (no exec).
* Every ``.json`` config file loads via :func:`genesispy.json_io.read_json`.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from genesispy.template.parser import parse_vpy
from genesispy.json_io import read_json


_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEMOS_ROOT = _REPO_ROOT / "demos"

_DEMOS = ["regfile", "iterative_wallace_tree",
          "many_iterative_wallace_trees", "random_logic",
          "generation_examples", "logmult"]


def _collect(demo: str, suffixes):
    """Return a sorted list of files under demos/<demo> matching ``suffixes``."""
    base = _DEMOS_ROOT / demo
    if not base.exists():
        return []
    out = []
    for root, _dirs, files in os.walk(base):
        for f in files:
            if any(f.endswith(s) for s in suffixes):
                out.append(os.path.join(root, f))
    return sorted(out)


def _all(suffixes):
    out = []
    for d in _DEMOS:
        out.extend(_collect(d, suffixes))
    return out


@pytest.mark.parametrize("demo", _DEMOS)
def test_demo_dir_exists(demo: str) -> None:
    assert (_DEMOS_ROOT / demo).is_dir(), (
        f"Expected demo directory {_DEMOS_ROOT / demo} to exist"
    )


_VPY_FILES = _all((".vpy", ".svpy"))
_CFG_FILES = _all((".cfg.py", "config.py"))
_JSON_FILES = _all((".json",))


@pytest.mark.parametrize("path", _VPY_FILES, ids=lambda p: os.path.relpath(p, _DEMOS_ROOT))
def test_vpy_parses_and_compiles(path: str) -> None:
    # Files under a demo's genesis_src.j2/ subtree are j2-flavour twins.
    syntax = "j2" if "genesis_src.j2" in path.split(os.sep) else "genesis"
    src = parse_vpy(path, syntax=syntax)
    # The parser output is the body of an ``execute()`` method.  Wrap in a
    # ``def`` so that ``return`` / indentation are valid.
    wrapped = "def _exec(self):\n" + ("\n".join(
        ("    " + line) if line else "" for line in src.splitlines()
    )) + "\n"
    compile(wrapped, path, "exec")


@pytest.mark.parametrize("path", _CFG_FILES, ids=lambda p: os.path.relpath(p, _DEMOS_ROOT))
def test_cfg_compiles(path: str) -> None:
    with open(path, "r", encoding="utf-8") as fh:
        compile(fh.read(), path, "exec")


@pytest.mark.parametrize("path", _JSON_FILES, ids=lambda p: os.path.relpath(p, _DEMOS_ROOT))
def test_json_loads(path: str) -> None:
    tree = read_json(path)
    assert tree is not None
