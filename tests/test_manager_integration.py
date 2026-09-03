"""End-to-end integration tests: .vpy -> Verilog text in the cache."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from genesispy import cache
from genesispy.cli import parse_args
from genesispy.manager import Manager


FIXTURES = Path(__file__).parent / "fixtures" / "integration"


@pytest.fixture(autouse=True)
def _reset_cache():
    cache.clear_all()
    yield
    cache.clear_all()


def _run(
    tmp_path: Path, vpy_path: Path, top: str, extra_args: tuple = ()
) -> Manager:
    """Construct a Manager rooted at ``tmp_path`` and run execute()."""
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        args = parse_args(
            ["--input", str(vpy_path), "--top", top, *extra_args]
        )
        m = Manager(args)
        rc = m.execute()
        assert rc == 0, "Manager.execute() should succeed"
        return m
    finally:
        os.chdir(cwd)


def test_regfile_min_end_to_end(tmp_path: Path) -> None:
    vpy = FIXTURES / "regfile_min" / "regfile_min.vpy"
    assert vpy.is_file(), f"fixture missing: {vpy}"

    m = _run(tmp_path, vpy, "regfile_min")

    # Generated .py was emitted into raw_dir.
    raw_files = list((tmp_path / m.raw_dir).glob("*.py"))
    assert any(p.name == "regfile_min.py" for p in raw_files)

    # The Verilog cache contains either the bare or unq-suffixed key.
    keys = list(cache.OUTFILE_CONTENT_CACHE.keys())
    target = next(
        (
            k for k in keys
            if k == "regfile_min.v" or k.startswith("regfile_min_unq")
        ),
        None,
    )
    assert target is not None, f"no regfile_min entry in cache; saw {keys}"

    text = cache.OUTFILE_CONTENT_CACHE[target]
    assert "module regfile_min" in text
    assert "reg [3:0] r_3;" in text


def test_clean_removes_raw_dir(tmp_path: Path) -> None:
    vpy = FIXTURES / "regfile_min" / "regfile_min.vpy"
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        # First, do a real run so raw_dir gets created.
        args = parse_args(["--input", str(vpy), "--top", "regfile_min"])
        rc = Manager(args).execute()
        assert rc == 0
        raw = tmp_path / "genesis_raw"
        assert raw.is_dir()

        # Now run with --clean.
        args2 = parse_args(["--clean"])
        rc2 = Manager(args2).execute()
        assert rc2 == 0
        assert not raw.exists()
    finally:
        os.chdir(cwd)


def test_no_synthtop_tags_files_verif(tmp_path: Path) -> None:
    """Default (no --synthtop) -> every emitted file goes to genesis_verif/.

    Mirrors Perl SynthTop=undef behaviour (Manager.pm:89, 1339).
    """
    vpy = FIXTURES / "regfile_min" / "regfile_min.vpy"
    _run(tmp_path, vpy, "regfile_min")

    verif = tmp_path / "genesis_verif"
    synth = tmp_path / "genesis_synth"
    verif_v_files = list(verif.glob("*.v")) if verif.is_dir() else []
    synth_v_files = list(synth.glob("*.v")) if synth.is_dir() else []
    assert verif_v_files, f"expected .v files in {verif}, got verif={verif_v_files} synth={synth_v_files}"
    assert not synth_v_files, f"unexpected .v in synth_dir: {synth_v_files}"
    # Every cache filename should be tagged 'verif'.
    assert all(t == "verif" for t in cache.OUTFILE_TAGS.values())


def test_synthtop_root_tags_files_synth(tmp_path: Path) -> None:
    """--synthtop=<top> -> every file is tagged 'synth' and lands in
    genesis_synth/."""
    vpy = FIXTURES / "regfile_min" / "regfile_min.vpy"
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        args = parse_args([
            "--input", str(vpy), "--top", "regfile_min",
            "--synthtop", "regfile_min",
        ])
        rc = Manager(args).execute()
        assert rc == 0
    finally:
        os.chdir(cwd)

    synth = tmp_path / "genesis_synth"
    synth_v_files = list(synth.glob("*.v"))
    assert synth_v_files, f"expected .v in {synth}"
    assert all(t == "synth" for t in cache.OUTFILE_TAGS.values())


def test_missing_top_returns_error_code(tmp_path: Path) -> None:
    vpy = FIXTURES / "regfile_min" / "regfile_min.vpy"
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        args = parse_args(["--input", str(vpy), "--top", "nonexistent_top"])
        rc = Manager(args).execute()
        assert rc == 1
    finally:
        os.chdir(cwd)


def test_gen_only_two_phase(tmp_path: Path) -> None:
    """--gen-only with a pre-parsed raw dir produces Verilog without --input."""
    vpy = FIXTURES / "regfile_min" / "regfile_min.vpy"

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        # Phase 1: parse only.
        args1 = parse_args(["--input", str(vpy), "--top", "regfile_min", "--parse-only"])
        rc1 = Manager(args1).execute()
        assert rc1 == 0, "parse-only phase should succeed"
        raw = tmp_path / "genesis_raw"
        assert raw.is_dir(), "raw_dir should exist after --parse-only"

        cache.clear_all()

        # Phase 2: gen only — no --input.
        args2 = parse_args(["--gen-only", "--top", "regfile_min"])
        rc2 = Manager(args2).execute()
        assert rc2 == 0, "gen-only phase should succeed"
    finally:
        os.chdir(cwd)

    keys = list(cache.OUTFILE_CONTENT_CACHE.keys())
    target = next(
        (k for k in keys if k == "regfile_min.v" or k.startswith("regfile_min_unq")),
        None,
    )
    assert target is not None, f"no regfile_min entry in cache after gen-only; saw {keys}"
    assert "module regfile_min" in cache.OUTFILE_CONTENT_CACHE[target]

    # Confirm the file also landed on disk (no --synthtop => genesis_verif/).
    verif = tmp_path / "genesis_verif"
    disk_files = list(verif.glob("*.v")) if verif.is_dir() else []
    assert any("regfile_min" in p.name for p in disk_files), (
        f"expected regfile_min*.v in {verif}; found {disk_files}"
    )
    disk_text = next(p for p in disk_files if "regfile_min" in p.name).read_text()
    assert "module regfile_min" in disk_text


def test_gen_only_missing_raw_dir(tmp_path: Path, capsys) -> None:
    """--gen-only with no raw dir exits 1 and reports the raw_dir problem."""
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        args = parse_args(["--gen-only", "--top", "regfile_min"])
        rc = Manager(args).execute()
    finally:
        os.chdir(cwd)
    assert rc == 1
    err = capsys.readouterr().err
    assert "raw" in err and "does not exist" in err, (
        f"expected raw/does-not-exist message in stderr; got: {err!r}"
    )


def test_gen_only_missing_top(tmp_path: Path, capsys) -> None:
    """--gen-only with raw dir present but no --top exits 1 at execute time.

    --top is not argparse-required (default=None), so parse_args succeeds;
    the error is raised by Manager.load_top_module during execute().
    """
    vpy = FIXTURES / "regfile_min" / "regfile_min.vpy"

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        # Parse first so raw_dir exists.
        args1 = parse_args(["--input", str(vpy), "--top", "regfile_min", "--parse-only"])
        Manager(args1).execute()
        cache.clear_all()

        args2 = parse_args(["--gen-only"])
        rc = Manager(args2).execute()
    finally:
        os.chdir(cwd)
    assert rc == 1
    err = capsys.readouterr().err
    assert "No --top module specified" in err, (
        f"expected 'No --top module specified' in stderr; got: {err!r}"
    )


def test_bare_include_in_vpy_body(tmp_path: Path) -> None:
    """Genesis2-style ``//;include("frag.vpy")`` resolves bare from the body."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "frag.vpy").write_text(
        "//; emit('// fragment-line')\n"
    )
    top_vpy = src_dir / "top.vpy"
    top_vpy.write_text(
        "//; include('frag.vpy')\n"
        "//; emit('// after-include')\n"
    )
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        args = parse_args([
            "--input", str(top_vpy),
            "--top", "top",
            "--includepath", str(src_dir),
        ])
        rc = Manager(args).execute()
        assert rc == 0
    finally:
        os.chdir(cwd)
    keys = list(cache.OUTFILE_CONTENT_CACHE.keys())
    target = next(k for k in keys if k.startswith("top"))
    text = cache.OUTFILE_CONTENT_CACHE[target]
    assert "// fragment-line" in text
    assert "// after-include" in text


# ---------------------------------------------------------------------------
# --param-footer
# ---------------------------------------------------------------------------

PF = FIXTURES / "param_footer"


def _pf_leaf_text() -> str:
    """Return the generated Verilog for the pf_leaf unique module."""
    key = next(k for k in cache.OUTFILE_CONTENT_CACHE if k.startswith("pf_leaf"))
    return cache.OUTFILE_CONTENT_CACHE[key]


def test_param_footer_end_to_end(tmp_path: Path) -> None:
    """The footer reports parameters the banner cannot see, with provenance.

    WIDTH arrives as a parent unique_inst kwarg, DEPTH from --parameter, and
    both are resolved by parameter() calls in the leaf's own body -- i.e.
    after to_verilog() has already written the banner.
    """
    _run(
        tmp_path, PF / "pf_top.vpy", "pf_top",
        ("--input", str(PF / "pf_leaf.vpy"), "-p", "DEPTH=32", "--param-footer"),
    )
    text = _pf_leaf_text()

    assert "Genesis-Py resolved parameter provenance" in text
    # The block sits past the end of the module, not in the banner.
    assert text.index("resolved parameter provenance") > text.rindex("endmodule")

    footer = text[text.index("// Genesis-Py resolved parameter provenance"):]
    assert re.search(r"^//\s+DEPTH\s+: 32\s+<- command line", footer, re.M)
    assert re.search(r"^//\s+WIDTH\s+: 16\s+<- parent instantiation", footer, re.M)


def test_param_footer_absent_by_default(tmp_path: Path) -> None:
    """Without the flag the generated Verilog is unchanged."""
    _run(
        tmp_path, PF / "pf_top.vpy", "pf_top",
        ("--input", str(PF / "pf_leaf.vpy"), "-p", "DEPTH=32"),
    )
    assert "resolved parameter provenance" not in _pf_leaf_text()
