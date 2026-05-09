"""Tests for the Manager skeleton."""

from __future__ import annotations

import os

import pytest

from genesispy.cli import parse_args
from genesispy.errors import ParseError
from genesispy.manager import Manager


def _make_manager(argv):
    return Manager(parse_args(argv))


def test_init_from_namespace_defaults():
    m = _make_manager([])
    assert m.top is None
    assert m.debug == 0
    assert m.sources_path == []
    assert m.includes_path == []
    assert m.output_dir == "genesis_synth"
    assert m.raw_dir == "genesis_raw"
    assert m.synth_dir == "genesis_synth"
    assert m.verif_dir == "genesis_verif"
    assert m.cfg_handler is None
    assert m.syntax == "genesis"


def test_jinja2_flag_sets_syntax():
    m = _make_manager(["--jinja2"])
    assert m.syntax == "jinja2"


def test_init_propagates_cli_values():
    m = _make_manager(
        [
            "--top", "core",
            "--debug", "2",
            "--srcpath", "src",
            "--includepath", "inc",
            "--outputdir", "out",
        ]
    )
    assert m.top == "core"
    assert m.debug == 2
    assert m.sources_path == ["src"]
    assert m.includes_path == ["inc"]
    assert m.output_dir == "out"


def test_find_file_in_sources_path(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    f = src / "hello.vpy"
    f.write_text("x")
    m = _make_manager(["--srcpath", str(src)])
    found = m.find_file("hello.vpy")
    assert os.path.abspath(found) == os.path.abspath(str(f))


def test_find_file_in_includes_path(tmp_path):
    inc = tmp_path / "inc"
    inc.mkdir()
    f = inc / "h.vh"
    f.write_text("x")
    m = _make_manager(["--includepath", str(inc)])
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


def test_execute_returns_zero(capsys):
    m = _make_manager([])
    rc = m.execute()
    assert rc == 0
    captured = capsys.readouterr()
    assert "stub" in captured.err
