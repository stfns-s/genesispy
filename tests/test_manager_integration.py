"""End-to-end integration tests: .vpy -> Verilog text in the cache."""

from __future__ import annotations

import os
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


def _run(tmp_path: Path, vpy_path: Path, top: str) -> Manager:
    """Construct a Manager rooted at ``tmp_path`` and run execute()."""
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        args = parse_args(["--input", str(vpy_path), "--top", top])
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
