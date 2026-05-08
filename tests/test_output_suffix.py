"""Tests for the configurable output suffix (--suffix CLI flag)."""

from __future__ import annotations

import os

import pytest

from genesispy import cache
from genesispy.cli import parse_args
from genesispy.output_writer import _canonical_filename, flush_to_disk
from genesispy.unique_module import UniqueModule

from ._stubs import StubManager


def setup_function(_fn) -> None:
    cache.clear_all()


class Top(UniqueModule):
    pass


class Leaf(UniqueModule):
    pass


def test_canonical_filename_default_suffix() -> None:
    assert _canonical_filename("foo") == "foo.v"
    assert _canonical_filename("foo.v") == "foo.v"


def test_canonical_filename_custom_suffix() -> None:
    assert _canonical_filename("foo", ".sv") == "foo.sv"
    assert _canonical_filename("foo.v", ".sv") == "foo.v"


def test_canonical_filename_dotted_basename_gets_suffix() -> None:
    """Non-Verilog dot in a basename (e.g. 'foo.bar') must not suppress suffix-append."""
    assert _canonical_filename("foo.bar") == "foo.bar.v"
    assert _canonical_filename("foo.bar", ".sv") == "foo.bar.sv"


def test_cli_suffix_default() -> None:
    args = parse_args(["-i", "x.vpy", "-t", "X"])
    assert args.suffix == ".v"


def test_cli_suffix_explicit() -> None:
    args = parse_args(["-i", "x.vpy", "-t", "X", "--suffix", ".sv"])
    assert args.suffix == ".sv"


def test_cli_suffix_normalises_leading_dot() -> None:
    args = parse_args(["-i", "x.vpy", "-t", "X", "--suffix", "sv"])
    assert args.suffix == ".sv"


def test_cli_systemverilog_long() -> None:
    args = parse_args(["-i", "x.vpy", "-t", "X", "--systemverilog"])
    assert args.suffix == ".sv"


def test_cli_systemverilog_short() -> None:
    args = parse_args(["-i", "x.vpy", "-t", "X", "-sv"])
    assert args.suffix == ".sv"


def test_cli_systemverilog_conflicts_with_suffix() -> None:
    with pytest.raises(SystemExit):
        parse_args(["-i", "x.vpy", "-t", "X", "-sv", "--suffix", "v"])


def test_cli_suffix_empty_rejected() -> None:
    """Bug #2 (review12 batch C #4): --suffix '' would yield 'foo.' files."""
    with pytest.raises(SystemExit):
        parse_args(["-i", "x.vpy", "-t", "X", "--suffix", ""])


def test_execute_uses_manager_suffix() -> None:
    mgr = StubManager(output_suffix=".sv")
    top = Top(mgr)
    child = top.unique_inst(Leaf, "u_leaf", WIDTH=8)
    expected = f"{child.get_unique_module_name()}.sv"
    assert expected in cache.OUTFILE_CONTENT_CACHE
    assert f"{child.get_unique_module_name()}.v" not in cache.OUTFILE_CONTENT_CACHE


def test_synonym_mirrors_under_custom_suffix() -> None:
    mgr = StubManager(output_suffix=".sv")
    top = Top(mgr)
    child = top.unique_inst(Leaf, "u_leaf", WIDTH=8)
    child.synonym("LeafAlias")
    assert f"LeafAlias.sv" in cache.OUTFILE_CONTENT_CACHE


def test_flush_to_disk_emits_custom_suffix(tmp_path) -> None:
    mgr = StubManager(output_suffix=".sv")
    mgr.synth_dir = str(tmp_path / "synth")
    mgr.verif_dir = str(tmp_path / "verif")
    mgr.output_dir = str(tmp_path)
    cache.OUTFILE_CONTENT_CACHE["alu"] = "module alu; endmodule\n"
    cache.OUTFILE_TAGS["alu"] = "synth"
    written = flush_to_disk(mgr)
    assert any(p.endswith("alu.sv") for p in written["synth"])
    assert os.path.isfile(os.path.join(mgr.synth_dir, "alu.sv"))
