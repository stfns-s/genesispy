"""End-to-end test for the bin/gvpy.py demo.

Shells out to ``make gen`` in ``demos/gvpy/``; skipped if ``make``
is not on PATH (mirrors :mod:`tests.test_demos_make`).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tests._stale import ignore_stale

DEMO_SRC = Path(__file__).resolve().parents[1] / "demos" / "gvpy"


pytestmark = pytest.mark.skipif(
    shutil.which("make") is None, reason="make not available on PATH"
)


@pytest.fixture
def demo(tmp_path: Path) -> Path:
    """A scratch copy of the demo, so the checked-in tree is never touched."""
    dst = tmp_path / "gvpy"
    shutil.copytree(DEMO_SRC, dst, ignore=ignore_stale)
    return dst


def _run(demo: Path, target: str, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["make", target, *extra],
        cwd=demo,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_make_clean(demo: Path) -> None:
    r = _run(demo, "clean")
    assert r.returncode == 0, r.stderr


def test_make_gen_produces_expected_verilog(demo: Path) -> None:
    r = _run(demo, "gen")
    assert r.returncode == 0, f"make gen failed: {r.stderr}"

    out = (demo / "example.out.v").read_text()

    # Module header from --mname.
    assert "module example" in out, out

    # parameter() default value flowed through (--parameter WIDTH=8).
    assert "parameter WIDTH = 8" in out

    # pp(3, "%02d") zero-padded to "03".
    assert "stage_03" in out

    # pp(0xa0 + 0, "%02x") -> "a0".
    assert "8'ha0" in out

    # generate + instantiate banner: kwargs flow through.
    assert "submod /*PARAMS: WIDTH=>8 STAGE=>0 MODE=>fast */ u_sub_0" in out
    assert "submod /*PARAMS: WIDTH=>8 STAGE=>3 MODE=>slow */ u_sub_3" in out

    # Manual attribute access on the _Inst wrapper.
    assert "submod /*WIDTH=8 MODE=fast*/ u_sub_manual" in out

    # Escaped backtick passthrough (literal backtick in output).
    assert "`not_an_expr`" in out


def _verilint() -> str | None:
    for tool in ("slang", "verilator"):
        if shutil.which(tool) is not None:
            return tool
    return None


def test_make_vlint(demo: Path) -> None:
    tool = _verilint()
    if tool is None:
        pytest.skip("neither slang nor verilator on PATH")
    r = _run(demo, "vlint", f"VERILINT={tool}")
    assert r.returncode == 0, f"make vlint ({tool}) failed:\n{r.stdout}\n{r.stderr}"


def test_make_lint(demo: Path) -> None:
    tool = _verilint()
    if tool is None:
        pytest.skip("neither slang nor verilator on PATH")
    r = _run(demo, "lint", f"VERILINT={tool}")
    assert r.returncode == 0, f"make lint ({tool}) failed:\n{r.stdout}\n{r.stderr}"


def test_make_gen_reruns_on_width_change(demo: Path) -> None:
    """make gen WIDTH=16 must re-run even when the output file is already present."""
    r1 = _run(demo, "gen")
    assert r1.returncode == 0, f"make gen failed: {r1.stderr}"

    out_default = (demo / "example.out.v").read_text()
    assert "parameter WIDTH = 8" in out_default, "default WIDTH=8 not found"

    # Re-run with a different width; without the flag stamp this says "up to date".
    r2 = _run(demo, "gen", "WIDTH=16")
    assert r2.returncode == 0, f"make gen WIDTH=16 failed: {r2.stderr}"
    out_w16 = (demo / "example.out.v").read_text()
    assert "parameter WIDTH = 16" in out_w16, (
        f"WIDTH=16 not reflected in output (stale build?): {out_w16[:500]}"
    )
