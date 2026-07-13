"""End-to-end test for the bin/gvpy.py demo.

Shells out to ``make gen`` in ``demos/gvpy/``; skipped if ``make``
is not on PATH (mirrors :mod:`tests.test_demos_make`).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


DEMO = Path(__file__).resolve().parents[1] / "demos" / "gvpy"


pytestmark = pytest.mark.skipif(
    shutil.which("make") is None, reason="make not available on PATH"
)


def _run(target: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["make", target],
        cwd=DEMO,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_make_clean() -> None:
    r = _run("clean")
    assert r.returncode == 0, r.stderr


def test_make_gen_produces_expected_verilog() -> None:
    # Always start clean.
    _run("clean")
    r = _run("gen")
    assert r.returncode == 0, f"make gen failed: {r.stderr}"

    out = (DEMO / "example.out.v").read_text()

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

    # Cleanup.
    _run("clean")


def _verilint() -> str | None:
    for tool in ("slang", "verilator"):
        if shutil.which(tool) is not None:
            return tool
    return None


def _run_with(target: str, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["make", target, *extra],
        cwd=DEMO,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_make_vlint() -> None:
    tool = _verilint()
    if tool is None:
        pytest.skip("neither slang nor verilator on PATH")
    _run("clean")
    r = _run_with("vlint", f"VERILINT={tool}")
    assert r.returncode == 0, f"make vlint ({tool}) failed:\n{r.stdout}\n{r.stderr}"
    _run("clean")


def test_make_lint() -> None:
    tool = _verilint()
    if tool is None:
        pytest.skip("neither slang nor verilator on PATH")
    _run("clean")
    r = _run_with("lint", f"VERILINT={tool}")
    assert r.returncode == 0, f"make lint ({tool}) failed:\n{r.stdout}\n{r.stderr}"
    _run("clean")


def test_make_gen_reruns_on_width_change() -> None:
    """make gen WIDTH=16 must re-run even when the output file is already present."""
    _run("clean")
    r1 = _run("gen")
    assert r1.returncode == 0, f"make gen failed: {r1.stderr}"

    # Verify default width.
    out_default = (DEMO / "example.out.v").read_text()
    assert "parameter WIDTH = 8" in out_default, "default WIDTH=8 not found"

    # Re-run with a different width; without the flag-stamp fix this says "up to date".
    r2 = _run_with("gen", "WIDTH=16")
    assert r2.returncode == 0, f"make gen WIDTH=16 failed: {r2.stderr}"
    out_w16 = (DEMO / "example.out.v").read_text()
    assert "parameter WIDTH = 16" in out_w16, (
        f"WIDTH=16 not reflected in output (stale build?): {out_w16[:500]}"
    )

    _run("clean")
