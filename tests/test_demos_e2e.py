"""End-to-end demo regression tests.

For each ported demo, run the full genesispy pipeline (parse → emit → load →
elaborate → write) and assert the expected Verilog files are produced.

This is logical-equivalence verification, not byte-equality against the Perl
gold output. Unique-name SHA suffixes (Foo_unq1, Foo_unq2, ...) are allowed
to differ; we only check that the expected number of distinct modules are
generated and each contains the demo's signature Verilog content.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from genesispy import cache
from genesispy.cli import parse_args
from genesispy.manager import Manager


DEMOS = Path(__file__).resolve().parents[1] / "demos"


@pytest.fixture(autouse=True)
def _reset_cache():
    cache.clear_all()
    yield
    cache.clear_all()


SYNTAXES = ("genesis", "j2")


def _run_demo(
    tmp_path: Path,
    demo_dir: Path,
    top: str,
    *inputs: str,
    config_flag: str | None = None,
    config_file: str | None = None,
    extra_argv: list[str] | None = None,
    syntax: str = "genesis",
    extra_dirs: tuple[str, ...] = (),
) -> Path:
    """Copy demo files into tmp_path, run genesispy on them, return synth dir.

    ``syntax`` selects the template flavour: ``"genesis"`` uses
    ``genesis_src/`` (default ``//;`` / backtick directives); ``"j2"``
    uses ``genesis_src.j2/`` and passes ``--j2``. ``extra_dirs`` names further
    subdirectories to copy, for demos whose sources are not all under
    ``genesis_src/`` (e.g. a ``lib/`` reached by ``--py-path``).
    """
    src_subdir = "genesis_src" if syntax == "genesis" else "genesis_src.j2"
    tmp_path.mkdir(parents=True, exist_ok=True)
    for src in demo_dir.iterdir():
        if src.is_file():
            shutil.copy(src, tmp_path / src.name)
        elif src.is_dir() and src.name in (src_subdir, *extra_dirs):
            shutil.copytree(src, tmp_path / src.name, dirs_exist_ok=True)

    cache.clear_all()

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        argv = []
        for f in inputs:
            argv.extend(["--input", f])
        argv.extend(["--top", top, "--srcpath", src_subdir])
        if syntax == "j2":
            argv.append("--j2")
        if config_flag and config_file:
            argv.extend([config_flag, config_file])
        if extra_argv:
            argv.extend(extra_argv)
        rc = Manager(parse_args(argv)).execute()
        assert rc == 0, f"genesispy returned {rc} for {demo_dir.name}"
    finally:
        os.chdir(cwd)

    # Without --synthtop, every file is tagged 'verif' (Perl SynthTop=undef
    # default).  Demos in this suite intentionally don't pass --synthtop;
    # check verif_dir first, then fall back to synth_dir for any test that
    # opts in via extra_argv.
    verif = tmp_path / "genesis_verif"
    if verif.is_dir() and any(verif.iterdir()):
        return verif
    return tmp_path / "genesis_synth"


@pytest.mark.parametrize("syntax", SYNTAXES)
def test_random_logic(tmp_path: Path, syntax: str) -> None:
    synth = _run_demo(
        tmp_path, DEMOS / "random_logic", "top",
        "top.vpy", "OneHotMux.vpy",
        syntax=syntax,
    )
    files = sorted(p.name for p in synth.iterdir())
    assert "top.v" in files
    onehot_files = [f for f in files if f.startswith("OneHotMux_")]
    assert len(onehot_files) == 6, f"expected 6 OneHotMux variants, got {onehot_files}"

    top_v = (synth / "top.v").read_text()
    assert "module top" in top_v
    assert "OneHotMux_" in top_v


@pytest.mark.parametrize("syntax", SYNTAXES)
def test_iterative_wallace_tree(tmp_path: Path, syntax: str) -> None:
    synth = _run_demo(
        tmp_path, DEMOS / "iterative_wallace_tree", "top",
        "top.vpy", "wallace.vpy", "CSA.vpy",
        syntax=syntax,
    )
    files = sorted(p.name for p in synth.iterdir())
    assert "top.v" in files
    assert any(f.startswith("wallace_") for f in files)
    assert any(f.startswith("CSA_") for f in files)


@pytest.mark.parametrize("syntax", SYNTAXES)
def test_many_iterative_wallace_trees_default(tmp_path: Path, syntax: str) -> None:
    """No-config mode uses the in-source WALLACES_WIDTHS default of [4, 8]."""
    synth = _run_demo(
        tmp_path, DEMOS / "many_iterative_wallace_trees", "top",
        "top.vpy", "wallace.vpy", "CSA.vpy",
        syntax=syntax,
    )
    files = sorted(p.name for p in synth.iterdir())
    wallace_files = [f for f in files if f.startswith("wallace_unq")]
    clone_files = [f for f in files if f.startswith("clone_of_wallce_")]
    assert len(wallace_files) == 2, (
        f"expected 2 distinct wallace widths (default [4,8]), got {wallace_files}"
    )
    # Perl parity: clones emit no per-clone file (UniqueModule.pm:1480).
    assert clone_files == [], (
        f"expected no per-clone files, got {clone_files}"
    )
    # Defaults: COND=True, ParamHash={}
    body = (synth / "wallace_unq1.v").read_text()
    assert "COND      = True" in body
    assert "ParamHash = {}" in body


@pytest.mark.parametrize("syntax", SYNTAXES)
def test_many_iterative_wallace_trees_via_json(tmp_path: Path, syntax: str) -> None:
    """JSON config overrides the defaults: widths -> [2,5,16,32,64], COND=False,
    ParamHash populated. Same source tree as the default test."""
    synth = _run_demo(
        tmp_path, DEMOS / "many_iterative_wallace_trees", "top",
        "top.vpy", "wallace.vpy", "CSA.vpy",
        config_flag="--json", config_file="config.json",
        syntax=syntax,
    )
    files = sorted(p.name for p in synth.iterdir())
    wallace_files = [f for f in files if f.startswith("wallace_unq")]
    clone_files = [f for f in files if f.startswith("clone_of_wallce_")]
    assert len(wallace_files) == 5, (
        f"expected 5 distinct wallace widths, got {wallace_files}"
    )
    assert clone_files == [], (
        f"expected no per-clone files, got {clone_files}"
    )
    # Config-driven values flow into RTL.
    body = (synth / "wallace_unq1.v").read_text()
    assert "COND      = False" in body
    assert "'Assoc': 4" in body  # ParamHash from config
    # Confirm the JSON-driven run picked up the WALLACES_WIDTHS array
    # (top-level Parameters / __ArrayType__ native list).
    top_v = (synth / "top.v").read_text()
    for w in (2, 5, 16, 32, 64):
        assert f"wallace_{w}" in top_v, f"width {w} not instantiated"


@pytest.mark.parametrize("syntax", SYNTAXES)
def test_many_iterative_wallace_trees_via_cfg(tmp_path: Path, syntax: str) -> None:
    """`.cfg` Python config overrides the in-source defaults with its own
    widths/COND/ParamHash when no higher-priority source is supplied."""
    synth = _run_demo(
        tmp_path, DEMOS / "many_iterative_wallace_trees", "top",
        "top.vpy", "wallace.vpy", "CSA.vpy",
        extra_argv=["--cfg", "config.py"],
        syntax=syntax,
    )
    wallace_files = [p.name for p in synth.iterdir() if p.name.startswith("wallace_unq")]
    clone_files = [p.name for p in synth.iterdir() if p.name.startswith("clone_of_wallce_")]
    assert len(wallace_files) == 3, wallace_files
    assert clone_files == [], clone_files
    body = (synth / "wallace_unq1.v").read_text()
    assert "COND      = True" in body                      # cfg sets True
    assert "'tag': 'cfg-driven'" in body                   # cfg's ParamHash payload


@pytest.mark.parametrize("syntax", SYNTAXES)
def test_many_iterative_wallace_trees_json_beats_cfg(tmp_path: Path, syntax: str) -> None:
    """When both --json and --cfg are supplied, JSON outranks .cfg for any
    key it sets (matches Perl Genesis2 ordering)."""
    synth = _run_demo(
        tmp_path, DEMOS / "many_iterative_wallace_trees", "top",
        "top.vpy", "wallace.vpy", "CSA.vpy",
        config_flag="--json", config_file="config.json",
        extra_argv=["--cfg", "config.py"],
        syntax=syntax,
    )
    wallace_files = [p.name for p in synth.iterdir() if p.name.startswith("wallace_unq")]
    assert len(wallace_files) == 5, (
        f"expected JSON widths [2,5,16,32,64] to win over cfg [3,7,11], got {wallace_files}"
    )
    body = (synth / "wallace_unq1.v").read_text()
    assert "COND      = False" in body                     # JSON False beats cfg True
    assert "'Assoc': 4" in body                            # JSON ParamHash beats cfg's


@pytest.mark.parametrize("syntax", SYNTAXES)
def test_regfile(tmp_path: Path, syntax: str) -> None:
    synth = _run_demo(
        tmp_path, DEMOS / "regfile", "top",
        "top.vpy", "reg_file.vpy", "flop.vpy", "cfg_ifc.vpy", "top_flop_only.vpy",
        syntax=syntax,
    )
    files = sorted(p.name for p in synth.iterdir())
    v_files = [f for f in files if f.endswith(".v")]
    assert "top.v" in files
    flop_files = [f for f in v_files if f.startswith("flop_")]
    reg_file_files = [f for f in v_files if f.startswith("reg_file_") or f == "reg_file.v"]
    cfg_ifc_files = [f for f in v_files if f.startswith("cfg_ifc")]
    assert len(flop_files) >= 1, flop_files
    assert len(reg_file_files) >= 1, reg_file_files
    assert len(cfg_ifc_files) >= 1, cfg_ifc_files
    body = (synth / "top.v").read_text()
    assert "module top()" in body
    assert "DataOut1" in body
    assert "DataOut2" in body


def test_include_examples(tmp_path: Path) -> None:
    """include_examples is wrapperless: include()-d leaves, single emitted
    top.v, no config file.  top.vpy includes codec.vpy, which includes
    gray.vpy twice, so the emitted functions come from two nesting levels
    and carry names derived at each of them."""
    synth = _run_demo(
        tmp_path, DEMOS / "include_examples", "top",
        "top.vpy",
        extra_argv=["--inc-path", "genesis_src"],
    )
    files = [p.name for p in synth.iterdir()]
    assert files == ["top.v"], f"expected exactly top.v, got {files}"
    body = (synth / "top.v").read_text()
    assert "module top" in body
    # Named by top.vpy, one per width in its set.
    assert "function static [2:0] gray_codec_w3;" in body
    assert "function static [4:0] gray_codec_w5;" in body
    # Named by codec.vpy, which included gray.vpy for each half.
    assert "function static [4:0] gray_codec_w5_enc;" in body
    assert "function static [4:0] gray_codec_w5_dec;" in body
    # gray.vpy included straight from top.vpy as well.
    assert "function static [3:0] gray_enc_w4;" in body


def test_pyinclude_examples(tmp_path: Path) -> None:
    """pyinclude_examples proves the namespace rule three ways: each module
    sees only what it pyinclude'd itself, and a pyinclude inside an
    include()'d snippet does not reach the caller."""
    synth = _run_demo(
        tmp_path, DEMOS / "pyinclude_examples", "top",
        "top.vpy",
        extra_argv=["--inc-path", "genesis_src", "--py-path", "lib"],
        extra_dirs=("lib",),
    )
    files = sorted(p.name for p in synth.iterdir())
    assert files == ["leaf_unq1.v", "top.v"], files

    top = (synth / "top.v").read_text()
    leaf = (synth / "leaf_unq1.v").read_text()
    # top pyincluded emitters.py only; leaf pyincluded fixed.py only.
    assert "pyinclude'd names visible here: decl_signed, check_eq" in top
    assert "pyinclude'd names visible here: acc_width, sat_bounds" in leaf
    # frag.vpy's own pyinclude stays inside the include()'d snippet.
    assert "leaked into top from frag.vpy's pyinclude: (none)" in top
    # decl_signed built these, taking the module as its first argument.
    assert "reg signed [11:0] exp_hi;" in top
    assert "wire signed [11:0] acc;" in top
    # Widths came from fixed.py: acc_width(8, 16) == 12, so headroom is 4.
    assert "leaf_unq1: 16 x 8-bit terms -> 12-bit acc" in leaf
    assert "headroom = 4;" in top


def test_generation_examples(tmp_path: Path) -> None:
    """Five tops sharing one pll.vpy, each via a different generation
    primitive. No j2 twin in this demo, so only the default flavour runs.
    """
    demo_dir = DEMOS / "generation_examples"
    src_dst = tmp_path / "genesis_src"
    shutil.copytree(demo_dir / "genesis_src", src_dst)

    cases = [
        ("ex1_unique",   {"ex1_unique.v",   "pll_unq1.v", "pll_unq2.v", "pll_unq3.v"}),
        ("ex2_ununique", {"ex2_ununique.v", "pll.v"}),
        ("ex3_genwname", {"ex3_genwname.v", "my_pll.v"}),
        ("ex4_synonym",  {"ex4_synonym.v",  "my_pll.v"}),
        ("ex5_clone",    {"ex5_clone.v",    "pll_unq1.v"}),
    ]

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        for top, want in cases:
            cache.clear_all()
            out_dir = f"genesis_synth_{top.split('_')[0]}"
            argv = [
                "--input", f"{top}.vpy",
                "--input", "pll.vpy",
                "--top", top,
                "--srcpath", "genesis_src",
                "--out-dir", out_dir,
            ]
            rc = Manager(parse_args(argv)).execute()
            assert rc == 0, f"{top}: genesispy returned {rc}"
            got = {p.name for p in (tmp_path / out_dir).iterdir() if p.suffix == ".v"}
            assert want <= got, f"{top}: expected {want}, got {got}"
    finally:
        os.chdir(cwd)
