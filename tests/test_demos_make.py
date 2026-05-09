"""Verify each demo's Makefile drives the genesispy CLI end-to-end.

Shells out to `make gen` in a tmp copy of each demo dir, then `make pylint`
to ensure the generated .py modules compile. `make clean` is checked to leave
the dir free of build artifacts. `make vlint` / `make lint` are exercised
when slang or verilator is available on PATH.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


DEMOS = Path(__file__).resolve().parents[1] / "demos"
DEMO_NAMES = [
    "random_logic",
    "iterative_wallace_tree",
    "many_iterative_wallace_trees",
    "regfile",
]


def _have_make() -> bool:
    return shutil.which("make") is not None


def _verilint() -> str | None:
    for tool in ("slang", "verilator"):
        if shutil.which(tool) is not None:
            return tool
    return None


pytestmark = pytest.mark.skipif(not _have_make(), reason="`make` not in PATH")


@pytest.fixture
def demo_copy(tmp_path: Path, request) -> Path:
    name = request.param
    src = DEMOS / name
    dst = tmp_path / name
    shutil.copytree(src, dst)
    shutil.copy(DEMOS / "genesispy.mk", tmp_path / "genesispy.mk")
    return dst


@pytest.mark.parametrize("demo_copy", DEMO_NAMES, indirect=True)
def test_make_gen(demo_copy: Path) -> None:
    r = subprocess.run(
        ["make", "gen"], cwd=demo_copy, capture_output=True, text=True,
        timeout=300,
    )
    assert r.returncode == 0, f"make gen failed:\n{r.stdout}\n{r.stderr}"
    # Demos don't pass --synthtop; under Perl-default semantics every
    # emitted .v is verif-tagged.  The Makefile passes --outputdir
    # genesis_synth, which (per --outputdir cascade) also supplies the
    # default for --verif-dir, so the .v lands under genesis_synth/
    # alongside the .vlist and the genesis_vlog.vf product list.
    assert (demo_copy / "genesis_synth" / "top.v").exists()
    assert (demo_copy / "genesis_synth" / "top.vlist").exists()
    assert (demo_copy / "genesis_vlog.vf").exists()


@pytest.mark.parametrize("demo_copy", DEMO_NAMES, indirect=True)
def test_make_gen_j2(demo_copy: Path) -> None:
    """The jinja2 twin sources elaborate via ``make gen-j2``; outputs land
    in a parallel ``genesis_synth.j2/`` tree."""
    r = subprocess.run(
        ["make", "gen-j2"], cwd=demo_copy, capture_output=True, text=True,
        timeout=300,
    )
    assert r.returncode == 0, f"make gen-j2 failed:\n{r.stdout}\n{r.stderr}"
    assert (demo_copy / "genesis_synth.j2" / "top.v").exists()
    assert (demo_copy / "genesis_synth.j2" / "top.vlist").exists()
    assert (demo_copy / "genesis_vlog.j2.vf").exists()


@pytest.mark.parametrize("demo_copy", DEMO_NAMES, indirect=True)
def test_make_pylint(demo_copy: Path) -> None:
    r = subprocess.run(
        ["make", "pylint"], cwd=demo_copy, capture_output=True, text=True
    )
    assert r.returncode == 0, f"make pylint failed:\n{r.stdout}\n{r.stderr}"


@pytest.mark.parametrize("demo_copy", DEMO_NAMES, indirect=True)
def test_make_vlint(demo_copy: Path) -> None:
    tool = _verilint()
    if tool is None:
        pytest.skip("neither slang nor verilator on PATH")
    r = subprocess.run(
        ["make", "vlint", f"VERILINT={tool}"],
        cwd=demo_copy, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"make vlint ({tool}) failed:\n{r.stdout}\n{r.stderr}"


@pytest.mark.parametrize("demo_copy", DEMO_NAMES, indirect=True)
def test_make_lint(demo_copy: Path) -> None:
    tool = _verilint()
    if tool is None:
        pytest.skip("neither slang nor verilator on PATH")
    r = subprocess.run(
        ["make", "lint", f"VERILINT={tool}"],
        cwd=demo_copy, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"make lint ({tool}) failed:\n{r.stdout}\n{r.stderr}"


@pytest.mark.parametrize("demo_copy", DEMO_NAMES, indirect=True)
def test_make_clean(demo_copy: Path) -> None:
    subprocess.run(["make", "gen"], cwd=demo_copy, check=True, capture_output=True)
    r = subprocess.run(
        ["make", "clean"], cwd=demo_copy, capture_output=True, text=True
    )
    assert r.returncode == 0, f"make clean failed:\n{r.stdout}\n{r.stderr}"
    assert not (demo_copy / "genesis_raw").exists()
    assert not (demo_copy / "genesis_synth").exists()
    assert not (demo_copy / "genesis_verif").exists()
    assert not (demo_copy / "genesis_vlog.vf").exists()
