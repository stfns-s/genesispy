"""Translate every Genesis2 demo .vp/.vph and check the output parses.

The bar here is *syntactic*: each translated file must (1) be reachable
by genesispy's ``parse_vpy`` and (2) the resulting Python source must
``compile`` cleanly. Module-load (``exec``) is not a valid bar -- ``.vpy``
templates place ``//;`` directives at module level, but bare-name
aliases (``parameter``, ``emit``, ...) are bound only inside the
generated ``execute()`` method body. Runtime semantic correctness is
verified by the workspace ``test_parity/`` suite, which wires up a
``Manager`` per-demo.

Skipped when ``perl`` + ``PPI`` aren't available, or when the Genesis2
submodule isn't checked out.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tests._parity_run import ppi_available
from genesispy import cache
from genesispy.cli import parse_args
from genesispy.manager import Manager
from genesispy.template.parser import parse_vpy
from genesispy.tools.vp2vpy import FileTranslator, Helper


REPO_ROOT = Path(__file__).resolve().parents[3]
GENESIS2_DEMO_ROOT = REPO_ROOT / "Genesis2" / "demo"
GLCTEST_ROOT = (
    REPO_ROOT / "Genesis2" / "test" / "glctest"
    / "global_controller" / "rtl" / "genesis"
)



pytestmark = [
    pytest.mark.skipif(
        not ppi_available(),
        reason="perl + PPI not on PATH (try `module load ramyx/perl/5.42.0/0.1.0`)",
    ),
    pytest.mark.skipif(
        not GENESIS2_DEMO_ROOT.exists(),
        reason=f"Genesis2 submodule not present at {GENESIS2_DEMO_ROOT}",
    ),
]


def _all_inputs() -> list[Path]:
    inputs: list[Path] = []
    for ext in (".vp", ".vph"):
        inputs.extend(sorted(GENESIS2_DEMO_ROOT.rglob(f"*{ext}")))
    if GLCTEST_ROOT.is_dir():
        inputs.extend(sorted(GLCTEST_ROOT.rglob("*.svp")))
    return inputs


def _src_id(p: Path) -> str:
    try:
        return str(p.relative_to(GENESIS2_DEMO_ROOT))
    except ValueError:
        return str(p.relative_to(REPO_ROOT / "Genesis2"))


@pytest.fixture(scope="module")
def helper():
    h = Helper()
    h.start()
    yield h
    h.close()


@pytest.mark.parametrize(
    "src",
    _all_inputs(),
    ids=_src_id,
)
def test_translate_and_parse(src: Path, helper, tmp_path):
    ft = FileTranslator(helper)
    result = ft.translate(src.read_text(encoding="utf-8"))
    assert "# TODO vp2vpy:" not in result.text, (
        f"{src}: translator emitted unresolved TODOs:\n{result.text}"
    )
    assert not result.todos, (
        f"{src}: translator recorded unresolved todos: {result.todos}"
    )
    out_path = tmp_path / src.with_suffix(".vpy").name
    out_path.write_text(result.text, encoding="utf-8")
    py = parse_vpy(str(out_path))
    # Compile to surface any syntax errors in the rendered Python.
    compile(py, str(out_path), "exec")


# ---------------------------------------------------------------------------
# Every translated Genesis2 demo must also elaborate.
# ---------------------------------------------------------------------------

_BIN = Path(__file__).resolve().parents[1] / "bin"

_ELABORATE = [
    ("regfile", []),
    ("regfile", ["-p", "FLOP_TYPE=flop"]),
    ("iterative_wallace_tree", []),
    ("many_iterative_wallace_trees", []),
    ("random_logic", []),
]


@pytest.mark.parametrize(
    "demo,extra", _ELABORATE, ids=lambda x: x if isinstance(x, str) else " ".join(x)
)
def test_translated_demo_elaborates(demo: str, extra: list, helper, tmp_path):
    src_dir = GENESIS2_DEMO_ROOT / demo / "genesis-source"
    out_src = tmp_path / "src"
    out_src.mkdir()
    names = []
    for src in sorted(src_dir.glob("*.vp")):
        ft = FileTranslator(helper)
        result = ft.translate(src.read_text(encoding="utf-8"))
        assert not result.todos, f"{src}: {result.todos}"
        (out_src / src.with_suffix(".vpy").name).write_text(result.text, encoding="utf-8")
        names.append(src.with_suffix(".vpy").name)
    cfg = tmp_path / "config.json"
    r = subprocess.run(
        [str(_BIN / "genesispy-xml2json"), str(GENESIS2_DEMO_ROOT / demo / "config.xml"), str(cfg)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    argv = ["--top", "top", "--src-path", "src", "--json-cfg", "config.json", "--out-dir", "out",
            *extra]
    for n in names:
        argv += ["--input", n]
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        cache.clear_all()
        rc = Manager(parse_args(argv)).execute()
    finally:
        os.chdir(cwd)
        cache.clear_all()
    assert rc == 0
    assert (tmp_path / "out" / "top.v").exists()
