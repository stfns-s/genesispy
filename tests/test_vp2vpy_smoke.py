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

import subprocess
from pathlib import Path

import pytest

from genesispy.template.parser import parse_vpy
from genesispy.tools.vp2vpy import FileTranslator, Helper


REPO_ROOT = Path(__file__).resolve().parents[3]
GENESIS2_DEMO_ROOT = REPO_ROOT / "Genesis2" / "demo"
GLCTEST_ROOT = (
    REPO_ROOT / "Genesis2" / "test" / "glctest"
    / "global_controller" / "rtl" / "genesis"
)


def _ppi_available() -> bool:
    try:
        return subprocess.run(
            ["perl", "-MPPI", "-e", "1"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
        ).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


pytestmark = [
    pytest.mark.skipif(
        not _ppi_available(),
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
