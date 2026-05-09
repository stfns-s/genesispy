"""Tests for the configurable input/output extension map (--extension)."""

from __future__ import annotations

import os

import pytest

from genesispy import cache
from genesispy.cli import parse_args
from genesispy.extensions import (
    DEFAULT_EXTENSION_MAP,
    build_extension_map,
    parse_extension_spec,
)
from genesispy.output_writer import _canonical_filename, flush_to_disk
from genesispy.unique_module import UniqueModule

from ._stubs import StubManager


def setup_function(_fn) -> None:
    cache.clear_all()


class Top(UniqueModule):
    pass


class Leaf(UniqueModule):
    pass


# ---------- _canonical_filename --------------------------------------- #


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


# ---------- parse_extension_spec -------------------------------------- #


def test_parse_extension_spec_basic() -> None:
    assert parse_extension_spec(".vpy=.v") == (".vpy", ".v")
    assert parse_extension_spec(".tvpy=.tv") == (".tvpy", ".tv")


def test_parse_extension_spec_adds_leading_dot() -> None:
    assert parse_extension_spec("vpy=v") == (".vpy", ".v")


def test_parse_extension_spec_lowercases() -> None:
    assert parse_extension_spec(".VPY=.SV") == (".vpy", ".sv")


def test_parse_extension_spec_missing_eq_rejected() -> None:
    import argparse as _ap
    with pytest.raises(_ap.ArgumentTypeError):
        parse_extension_spec(".vpy")


def test_parse_extension_spec_empty_side_rejected() -> None:
    import argparse as _ap
    with pytest.raises(_ap.ArgumentTypeError):
        parse_extension_spec(".vpy=")
    with pytest.raises(_ap.ArgumentTypeError):
        parse_extension_spec("=.v")


# ---------- build_extension_map --------------------------------------- #


def test_build_extension_map_defaults() -> None:
    assert build_extension_map([]) == DEFAULT_EXTENSION_MAP


def test_build_extension_map_user_adds_pair() -> None:
    m = build_extension_map([(".tvpy", ".tv")])
    assert m[".tvpy"] == ".tv"
    assert m[".vpy"] == ".v"


def test_build_extension_map_user_overrides_default() -> None:
    m = build_extension_map([(".vpy", ".sv")])
    assert m[".vpy"] == ".sv"


def test_build_extension_map_duplicate_user_keys_rejected() -> None:
    with pytest.raises(ValueError):
        build_extension_map([(".vpy", ".sv"), (".vpy", ".v")])


# ---------- CLI ------------------------------------------------------- #


def test_cli_default_extensions_empty() -> None:
    args = parse_args(["-i", "x.vpy", "-t", "X"])
    assert args.extensions == []


def test_cli_extension_repeatable() -> None:
    args = parse_args(
        ["-i", "x.vpy", "-t", "X",
         "--extension", ".tvpy=.tv",
         "--extension", "foo=bar"]
    )
    assert args.extensions == [(".tvpy", ".tv"), (".foo", ".bar")]


def test_cli_sv_appends_vpy_sv() -> None:
    args = parse_args(["-i", "x.vpy", "-t", "X", "-sv"])
    assert (".vpy", ".sv") in args.extensions


def test_cli_sv_redundant_with_explicit_match() -> None:
    args = parse_args(
        ["-i", "x.vpy", "-t", "X", "-sv", "--extension", ".vpy=.sv"]
    )
    # No duplicate — explicit entry left as-is, -sv finds it and skips.
    assert args.extensions.count((".vpy", ".sv")) == 1


def test_cli_sv_conflicts_with_explicit_vpy_v() -> None:
    with pytest.raises(SystemExit):
        parse_args(
            ["-i", "x.vpy", "-t", "X", "-sv", "--extension", ".vpy=.v"]
        )


def test_cli_extension_invalid_rejected() -> None:
    with pytest.raises(SystemExit):
        parse_args(["-i", "x.vpy", "-t", "X", "--extension", "no_eq"])
    with pytest.raises(SystemExit):
        parse_args(["-i", "x.vpy", "-t", "X", "--extension", ".vpy="])


def test_cli_suffix_removed() -> None:
    """``--suffix`` is gone -- argparse rejects it as an unrecognised flag."""
    with pytest.raises(SystemExit):
        parse_args(["-i", "x.vpy", "-t", "X", "--suffix", ".sv"])


def test_cli_suffix_eq_form_also_rejected() -> None:
    with pytest.raises(SystemExit):
        parse_args(["-i", "x.vpy", "-t", "X", "--suffix=.sv"])


# ---------- runtime: per-class _OUTPUT_SUFFIX ------------------------- #


def test_default_output_suffix_is_v() -> None:
    mgr = StubManager()
    top = Top(mgr)
    child = top.unique_inst(Leaf, "u_leaf", WIDTH=8)
    assert f"{child.get_unique_module_name()}.v" in cache.OUTFILE_CONTENT_CACHE


def test_per_class_output_suffix_overrides_default() -> None:
    class SVTop(UniqueModule):
        _OUTPUT_SUFFIX = ".sv"

    class SVLeaf(UniqueModule):
        _OUTPUT_SUFFIX = ".sv"

    mgr = StubManager()
    top = SVTop(mgr)
    child = top.unique_inst(SVLeaf, "u_leaf", WIDTH=8)
    expected = f"{child.get_unique_module_name()}.sv"
    assert expected in cache.OUTFILE_CONTENT_CACHE
    assert f"{child.get_unique_module_name()}.v" not in cache.OUTFILE_CONTENT_CACHE


def test_synonym_mirrors_under_class_suffix() -> None:
    class SVTop(UniqueModule):
        _OUTPUT_SUFFIX = ".sv"

    class SVLeaf(UniqueModule):
        _OUTPUT_SUFFIX = ".sv"

    mgr = StubManager()
    top = SVTop(mgr)
    child = top.unique_inst(SVLeaf, "u_leaf", WIDTH=8)
    child.synonym("LeafAlias")
    assert "LeafAlias.sv" in cache.OUTFILE_CONTENT_CACHE


def test_mixed_suffixes_in_one_run() -> None:
    """Two modules with different _OUTPUT_SUFFIX produce correctly-paired outputs."""

    class VTop(UniqueModule):
        _OUTPUT_SUFFIX = ".v"

    class SVLeaf(UniqueModule):
        _OUTPUT_SUFFIX = ".sv"

    mgr = StubManager()
    top = VTop(mgr)
    top.execute()
    child = top.unique_inst(SVLeaf, "u_leaf", WIDTH=8)
    assert f"{top.get_unique_module_name()}.v" in cache.OUTFILE_CONTENT_CACHE
    assert f"{child.get_unique_module_name()}.sv" in cache.OUTFILE_CONTENT_CACHE


def test_flush_to_disk_writes_pre_suffixed_keys(tmp_path) -> None:
    mgr = StubManager()
    mgr.synth_dir = str(tmp_path / "synth")
    mgr.verif_dir = str(tmp_path / "verif")
    mgr.output_dir = str(tmp_path)
    cache.OUTFILE_CONTENT_CACHE["alu.sv"] = "module alu; endmodule\n"
    cache.OUTFILE_TAGS["alu.sv"] = "synth"
    written = flush_to_disk(mgr)
    assert any(p.endswith("alu.sv") for p in written["synth"])
    assert os.path.isfile(os.path.join(mgr.synth_dir, "alu.sv"))
