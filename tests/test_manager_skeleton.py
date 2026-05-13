"""Tests for the Manager skeleton."""

from __future__ import annotations

import os

import pytest

from genesispy.cli import parse_args
from genesispy.reporting import ParseError
from genesispy.manager import Manager


def _make_manager(argv):
    return Manager(parse_args(argv))


def test_init_from_namespace_defaults():
    m = _make_manager([])
    assert m.top is None
    assert m.debug == 0
    assert m.src_path == []
    assert m.inc_path == []
    assert m.output_dir == "genesis_synth"
    assert m.raw_dir == "genesis_raw"
    assert m.synth_dir == "genesis_synth"
    assert m.verif_dir == "genesis_verif"
    assert m.cfg_handler is None
    assert m.syntax == "genesis"


def test_j2_flag_sets_syntax():
    m = _make_manager(["--j2"])
    assert m.syntax == "j2"


def test_init_propagates_cli_values():
    m = _make_manager(
        [
            "--top", "core",
            "--debug", "2",
            "--src-path", "src",
            "--inc-path", "inc",
            "--out-dir", "out",
        ]
    )
    assert m.top == "core"
    assert m.debug == 2
    assert m.src_path == ["src"]
    assert m.inc_path == ["inc"]
    assert m.output_dir == "out"


def test_find_file_in_src_path(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    f = src / "hello.vpy"
    f.write_text("x")
    m = _make_manager(["--src-path", str(src)])
    found = m.find_file("hello.vpy")
    assert os.path.abspath(found) == os.path.abspath(str(f))


def test_find_file_in_inc_path(tmp_path):
    inc = tmp_path / "inc"
    inc.mkdir()
    f = inc / "h.vh"
    f.write_text("x")
    m = _make_manager(["--inc-path", str(inc)])
    assert os.path.abspath(m.find_file("h.vh")) == os.path.abspath(str(f))


def test_find_file_paths_override(tmp_path):
    other = tmp_path / "o"
    other.mkdir()
    f = other / "z.txt"
    f.write_text("x")
    m = _make_manager([])
    assert os.path.abspath(m.find_file("z.txt", paths=[str(other)])) == os.path.abspath(str(f))


def test_find_file_absolute_existing(tmp_path):
    f = tmp_path / "abs.vpy"
    f.write_text("x")
    m = _make_manager([])
    assert m.find_file(str(f)) == str(f)


def test_find_file_missing_raises():
    m = _make_manager([])
    with pytest.raises(ParseError):
        m.find_file("definitely_not_there_xyz.vpy")


def test_find_file_missing_absolute_raises(tmp_path):
    m = _make_manager([])
    with pytest.raises(ParseError):
        m.find_file(str(tmp_path / "nope.vpy"))


def test_resolve_module_class_walks_inc_path(tmp_path):
    """resolve_module_class falls back to inc_path when input list misses.

    Mirrors Perl's @INC scan in load_base_module (UniqueModule.pm). Required
    so that bare-name `synonym(src, trgt)` (Cluster A) and `unique_inst` by
    string name can find `.vpy` sources that the user placed on `--inc-path`
    instead of `--input`.
    """
    inc = tmp_path / "inc"
    inc.mkdir()
    (inc / "lib_mod.vpy").write_text("module lib_mod;\nendmodule\n")
    raw = tmp_path / "raw"
    m = _make_manager(
        [
            "--inc-path", str(inc),
            "--raw-dir", str(raw),
        ]
    )
    cls = m.resolve_module_class("lib_mod")
    assert cls is not None
    assert cls.__name__ == "lib_mod"


def test_resolve_module_class_missing_raises(tmp_path):
    """Missing module (not on inputs, not on inc_path) still raises."""
    from genesispy.reporting import GenesisPyError
    m = _make_manager(["--raw-dir", str(tmp_path / "raw")])
    with pytest.raises(GenesisPyError, match="not found"):
        m.resolve_module_class("nonexistent_xyz")


def test_execute_returns_zero(capsys):
    m = _make_manager([])
    rc = m.execute()
    assert rc == 0
    captured = capsys.readouterr()
    assert "stub" in captured.err
