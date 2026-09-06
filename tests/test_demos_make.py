"""Verify each demo's Makefile drives the genesispy CLI end-to-end.

Shells out to `make gen` in a tmp copy of each demo dir, then `make pylint`
to ensure the generated .py modules compile. `make clean` is checked to leave
the dir free of build artifacts. `make vlint` / `make lint` are exercised
when slang or verilator is available on PATH.
"""

from __future__ import annotations

import os
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
    "include_examples",
    "pyinclude_examples",
]

# Build artefacts that must not be copied into the staging directory.
# A copied stale product is newer than the sources, causing make to skip
# regeneration and assert against the copied (not freshly built) files.
# *.flags are the flag-stamp files written by genesispy.mk (C1); glob
# patterns are accepted by shutil.ignore_patterns.
_STALE_PATTERNS = (
    "genesis_synth", "genesis_verif", "genesis_raw", "genesis_work",
    "obj_dir", "xcelium.d", "xrun.history", "xrun.log",
    "genesis_vlog.vf", "genesis_vlog.j2.vf", "*.flags",
    "depend.list", "genesis.log", "genesis_clean.cmd",
)


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
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*_STALE_PATTERNS))
    shutil.copy(DEMOS / "genesispy.mk", tmp_path / "genesispy.mk")
    return dst


@pytest.mark.parametrize("demo_copy", DEMO_NAMES, indirect=True)
def test_make_gen(demo_copy: Path) -> None:
    r = subprocess.run(
        ["make", "gen"], cwd=demo_copy, capture_output=True, text=True,
        timeout=300,
    )
    assert r.returncode == 0, f"make gen failed:\n{r.stdout}\n{r.stderr}"
    # The genesispy recipe must have actually run (not been skipped due to a
    # stale copied product).  make echoes the recipe command on stdout.
    assert "genesispy" in r.stdout, (
        f"genesispy recipe did not run (make may have used stale artefacts):\n{r.stdout}"
    )
    # Demos don't pass --synthtop; under Genesis2-default semantics every
    # emitted .v is verif-tagged.  The Makefile passes --outputdir
    # genesis_synth, so .v files land there; the file list itself is
    # written to the demo root via --vf-out, and the default
    # <top>.vlist is suppressed.
    assert (demo_copy / "genesis_synth" / "top.v").exists()
    assert (demo_copy / "genesis_vlog.vf").exists()
    assert not (demo_copy / "genesis_synth" / "top.vlist").exists()


@pytest.mark.parametrize("demo_copy", DEMO_NAMES, indirect=True)
def test_make_gen_j2(demo_copy: Path) -> None:
    """The j2 twin sources elaborate via ``make gen-j2``; outputs land
    in a parallel ``genesis_synth.j2/`` tree."""
    if not (demo_copy / "genesis_src.j2").is_dir():
        pytest.skip(f"no genesis_src.j2/ in {demo_copy.name}")
    r = subprocess.run(
        ["make", "gen-j2"], cwd=demo_copy, capture_output=True, text=True,
        timeout=300,
    )
    assert r.returncode == 0, f"make gen-j2 failed:\n{r.stdout}\n{r.stderr}"
    assert (demo_copy / "genesis_synth.j2" / "top.v").exists()
    assert (demo_copy / "genesis_vlog.j2.vf").exists()
    assert not (demo_copy / "genesis_synth.j2" / "top.vlist").exists()


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


# generation_examples doesn't fit the single-TOP, single-output-dir
# parametrization above: its Makefile recurses into five sub-makes, one per
# example, each writing to its own genesis_synth_ex<N>/ output dir.
_GEN_EX_EXPECTED = {
    "ex1": {"ex1_unique.v", "pll_unq1.v", "pll_unq2.v", "pll_unq3.v"},
    "ex2": {"ex2_ununique.v", "pll.v"},
    "ex3": {"ex3_genwname.v", "my_pll.v"},
    "ex4": {"ex4_synonym.v", "my_pll.v"},
    "ex5": {"ex5_clone.v", "pll_unq1.v"},
}


def _copy_generation_examples(tmp_path: Path) -> Path:
    src = DEMOS / "generation_examples"
    dst = tmp_path / "generation_examples"
    shutil.copytree(src, dst)
    shutil.copy(DEMOS / "genesispy.mk", tmp_path / "genesispy.mk")
    return dst


def test_generation_examples_make(tmp_path: Path) -> None:
    dst = _copy_generation_examples(tmp_path)
    r = subprocess.run(
        ["make", "gen"], cwd=dst, capture_output=True, text=True, timeout=300,
    )
    assert r.returncode == 0, f"make gen failed:\n{r.stdout}\n{r.stderr}"
    for ex, want in _GEN_EX_EXPECTED.items():
        d = dst / f"genesis_synth_{ex}"
        assert d.is_dir(), f"missing output dir {d}"
        got = {p.name for p in d.iterdir() if p.suffix == ".v"}
        assert want <= got, f"{ex}: expected {want}, got {got}"

    r = subprocess.run(
        ["make", "clean"], cwd=dst, capture_output=True, text=True
    )
    assert r.returncode == 0, f"make clean failed:\n{r.stdout}\n{r.stderr}"
    for ex in _GEN_EX_EXPECTED:
        assert not (dst / f"genesis_synth_{ex}").exists()
    assert not list(dst.glob("genesis_vlog_*.vf"))


def test_generation_examples_make_vlint(tmp_path: Path) -> None:
    tool = _verilint()
    if tool is None:
        pytest.skip("neither slang nor verilator on PATH")
    dst = _copy_generation_examples(tmp_path)
    r = subprocess.run(
        ["make", "vlint", f"VERILINT={tool}"],
        cwd=dst, capture_output=True, text=True, timeout=300,
    )
    assert r.returncode == 0, f"make vlint ({tool}) failed:\n{r.stdout}\n{r.stderr}"


def _copy_many_wallace(tmp_path: Path) -> Path:
    src = DEMOS / "many_iterative_wallace_trees"
    dst = tmp_path / "many_iterative_wallace_trees"
    shutil.copytree(src, dst)
    shutil.copy(DEMOS / "genesispy.mk", tmp_path / "genesispy.mk")
    return dst


def test_make_gen_reruns_on_config_change(tmp_path: Path) -> None:
    """make gen with JSON_CONFIG must re-run even when the product is already up to date."""
    dst = _copy_many_wallace(tmp_path)

    # First run: no config — default widths [4, 8] → 2 unique wallace modules.
    r1 = subprocess.run(
        ["make", "gen"], cwd=dst, capture_output=True, text=True, timeout=300,
    )
    assert r1.returncode == 0, f"first make gen failed:\n{r1.stdout}\n{r1.stderr}"
    wallace_default = {p.name for p in (dst / "genesis_synth").iterdir()
                       if p.name.startswith("wallace_unq")}
    assert len(wallace_default) == 2, f"expected 2 wallace_unq*.v, got {wallace_default}"

    # Second run: with JSON_CONFIG → widths [2,5,16,32,64] → 5 unique wallace modules.
    # Without the flag-stamp fix this second make says "up to date" and keeps the 2-file result.
    r2 = subprocess.run(
        ["make", "gen", "JSON_CONFIG=config.json"],
        cwd=dst, capture_output=True, text=True, timeout=300,
    )
    assert r2.returncode == 0, f"second make gen failed:\n{r2.stdout}\n{r2.stderr}"
    wallace_json = {p.name for p in (dst / "genesis_synth").iterdir()
                   if p.name.startswith("wallace_unq")}
    assert len(wallace_json) == 5, (
        f"expected 5 wallace_unq*.v after JSON_CONFIG run, got {wallace_json}"
    )


@pytest.mark.parametrize(
    "demo_copy,leaf",
    [
        ("include_examples", "genesis_src/gray.vpy"),
        ("include_examples", "genesis_src/codec.vpy"),
    ],
    indirect=["demo_copy"],
)
def test_make_gen_rebuilds_on_included_leaf_edit(demo_copy: Path, leaf: str) -> None:
    """Editing an include()'d leaf must trigger a rebuild on the next make gen.

    include_examples sets INPUTS := top.vpy; its leaves enter via include()
    under --inc-path genesis_src so SRC_FILES only lists top.vpy.  The
    generated depfile lists the leaves as prerequisites; once -include'd by
    genesispy.mk the rebuild fires automatically.
    """
    r1 = subprocess.run(
        ["make", "gen"], cwd=demo_copy, capture_output=True, text=True, timeout=300,
    )
    assert r1.returncode == 0, f"first make gen failed:\n{r1.stdout}\n{r1.stderr}"

    vf = demo_copy / "genesis_vlog.vf"
    mtime_before = vf.stat().st_mtime

    # Advance the leaf mtime by at least 1 s so make sees it as newer.
    leaf_path = demo_copy / leaf
    new_mtime = mtime_before + 2.0
    os.utime(leaf_path, (new_mtime, new_mtime))

    r2 = subprocess.run(
        ["make", "gen"], cwd=demo_copy, capture_output=True, text=True, timeout=300,
    )
    assert r2.returncode == 0, f"second make gen failed:\n{r2.stdout}\n{r2.stderr}"

    # genesispy writes are idempotent (content unchanged -> mtime stable), so
    # detect rebuild via the recipe echo in make's stdout rather than mtime.
    assert "genesispy" in r2.stdout, (
        f"make gen did not rebuild after touching {leaf} "
        f"(genesispy recipe did not echo in stdout)\n"
        f"stdout:\n{r2.stdout}\nstderr:\n{r2.stderr}"
    )


def test_make_gen_no_spurious_rebuild(tmp_path: Path) -> None:
    """Identical consecutive make gen invocations must not re-run the genesispy recipe."""
    dst = _copy_many_wallace(tmp_path)

    r1 = subprocess.run(
        ["make", "gen"], cwd=dst, capture_output=True, text=True, timeout=300,
    )
    assert r1.returncode == 0, f"make gen failed:\n{r1.stdout}\n{r1.stderr}"
    vf_mtime = (dst / "genesis_vlog.vf").stat().st_mtime

    # A second identical make gen must not re-run the genesispy recipe: the
    # product file's mtime must not change (flag stamp content is unchanged,
    # so the stamp's mtime is also unchanged, so VLOG_VF stays up to date).
    r2 = subprocess.run(
        ["make", "gen"], cwd=dst, capture_output=True, text=True, timeout=300,
    )
    assert r2.returncode == 0, f"second make gen failed:\n{r2.stdout}\n{r2.stderr}"
    vf_mtime2 = (dst / "genesis_vlog.vf").stat().st_mtime
    assert vf_mtime2 == vf_mtime, (
        "genesispy recipe ran again on identical make gen (mtime changed)"
    )
