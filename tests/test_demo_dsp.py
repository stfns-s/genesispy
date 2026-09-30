"""Verify the dsp demo's Makefile drives genesispy end-to-end.

dsp carries its own Makefile and build layout (``build/<top>/default/``)
instead of the shared ``genesispy.mk``, so it cannot join the parametrised
demos in ``test_demos_make.py``, whose assertions all assume
``genesis_synth/`` and ``genesis_vlog.vf``.

``make test`` and ``make test-smoke`` are deliberately not run here: they
sweep every configuration in ``verif/sweeps.mk`` (a few hundred) through a
simulator. That is the demo's own gate, run by hand from ``demos/dsp``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from tests._stale import ignore_stale


REPO = Path(__file__).resolve().parents[1]
DEMO = REPO / "demos" / "dsp"
TOPS = ("iir", "intg", "spec_mux")

# Build artefacts that must not reach the staging copy: a copied product is
# newer than the sources, so make skips the recipe and the assertions then
# check the copy rather than a fresh build.
pytestmark = pytest.mark.skipif(
    shutil.which("make") is None, reason="`make` not in PATH"
)


@pytest.fixture
def demo(tmp_path: Path) -> Path:
    dst = tmp_path / "dsp"
    shutil.copytree(DEMO, dst, ignore=ignore_stale)
    return dst


def _make(demo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run make in the demo copy against the in-tree genesispy launcher.

    The demo's Makefile defaults to ``GENESISPY ?= genesispy`` on PATH;
    pointing it at ``bin/genesispy`` removes the need for an installed
    console script.
    """
    env = {**os.environ, "GENESISPY": str(REPO / "bin" / "genesispy")}
    return subprocess.run(
        ["make", *args], cwd=demo, env=env,
        capture_output=True, text=True, timeout=600,
    )


def test_make_gen(demo: Path) -> None:
    r = _make(demo, "gen")
    assert r.returncode == 0, f"make gen failed:\n{r.stdout}\n{r.stderr}"
    # make echoes the recipe, so this proves the generator ran rather than
    # make finding a copied product already up to date.
    assert "genesispy" in r.stdout, (
        f"genesispy recipe did not run:\n{r.stdout}"
    )
    for top in TOPS:
        out = demo / "build" / top / "default"
        assert (out / f"{top}.vf").exists()
        assert (out / f"{top}.depend").exists()
        # The demo's sources are .vpy and both its generator call sites
        # pass -sv, so this is the cover for that shorthand redirecting
        # .vpy output to .sv.
        assert (out / "synth" / f"{top}.sv").exists()
        assert not (out / "synth" / f"{top}.v").exists()


def test_make_pylint(demo: Path) -> None:
    """pylint depends on gen and py_compiles the generated modules."""
    r = _make(demo, "pylint")
    assert r.returncode == 0, f"make pylint failed:\n{r.stdout}\n{r.stderr}"


def test_make_pytest(demo: Path) -> None:
    """The demo's own Q-format library tests, which need no simulator.

    They are not collected directly: pyproject's ``norecursedirs`` keeps
    ``demos`` out of this run, so this is the one place they execute.
    """
    r = _make(demo, "pytest")
    assert r.returncode == 0, f"make pytest failed:\n{r.stdout}\n{r.stderr}"


@pytest.mark.skipif(
    shutil.which("verilator") is None, reason="verilator not in PATH"
)
def test_make_vlint(demo: Path) -> None:
    r = _make(demo, "vlint", "VERILINT=verilator")
    assert r.returncode == 0, f"make vlint failed:\n{r.stdout}\n{r.stderr}"


def test_make_clean(demo: Path) -> None:
    assert _make(demo, "gen").returncode == 0
    r = _make(demo, "clean")
    assert r.returncode == 0, f"make clean failed:\n{r.stdout}\n{r.stderr}"
    assert not (demo / "build").exists()


def test_flag_change_rebuilds_a_product_newer_than_the_stamp(demo: Path) -> None:
    """make reads the product's mtime before any recipe runs. A future mtime
    forces the tie that coarse timestamps give by chance, so a stamp written
    by a recipe would leave the product up to date."""
    r = _make(demo, "intg")
    assert r.returncode == 0, f"make intg failed:\n{r.stdout}\n{r.stderr}"
    vf = demo / "build" / "intg" / "default" / "intg.vf"
    future = time.time() + 3600
    os.utime(vf, (future, future))
    r = _make(demo, "intg", "EXTRA_FLAGS_intg=--debug 1")
    assert r.returncode == 0, f"make intg failed:\n{r.stdout}\n{r.stderr}"
    assert "genesispy" in r.stdout, r.stdout
    assert vf.exists()


@pytest.mark.parametrize("args", [("help",), ("-n", "intg"), ("cleansim",)])
def test_a_non_building_run_leaves_stamp_and_product(demo: Path, args) -> None:
    assert _make(demo, "intg").returncode == 0
    top = demo / "build" / "intg" / "default"
    stamp = (top / "intg.flags").read_text()
    assert _make(demo, *args, "EXTRA_FLAGS_intg=--debug 1").returncode == 0
    assert (top / "intg.vf").exists()
    assert (top / "intg.flags").read_text() == stamp
