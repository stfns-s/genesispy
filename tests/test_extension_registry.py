"""Tests for the extension registry and the --extension suffixes."""

import argparse

import pytest

from genesispy.extensions import (
    ExtensionRegistry,
    ExtensionSpec,
    parse_extension_spec,
)
from genesispy.cli import parse_args
from genesispy.manager import Manager
from genesispy.reporting import GenesisPyError


@pytest.mark.parametrize("raw, spec", [
    (".rdlpy=.rdl", ExtensionSpec(".rdlpy", ".rdl", True, None)),
    ("rdlpy=rdl:nolist", ExtensionSpec(".rdlpy", ".rdl", False, None)),
    (".vhdpy=.vhd:comment=--", ExtensionSpec(".vhdpy", ".vhd", True, "--")),
    (".sdcpy=.sdc:nolist:comment=#", ExtensionSpec(".sdcpy", ".sdc", False, "#")),
    (".x=.y:comment=a:b", ExtensionSpec(".x", ".y", True, "a:b")),
    (".x=.y:comment=#:nolist", ExtensionSpec(".x", ".y", True, "#:nolist")),
])
def test_parse_extension_spec(raw, spec):
    assert parse_extension_spec(raw) == spec


@pytest.mark.parametrize("raw", [".x=.y:comment=", ".x=.y:bogus", ".x=.y:nolist:nolist", ".x"])
def test_parse_extension_spec_rejects(raw):
    with pytest.raises(argparse.ArgumentTypeError):
        parse_extension_spec(raw)


def test_from_specs_conflict_raises():
    specs = [ExtensionSpec(".x", ".y"), ExtensionSpec(".x", ".y", listed=False, comment="#")]
    with pytest.raises(ValueError) as exc:
        ExtensionRegistry.from_specs(specs)
    assert str(exc.value) == (
        "--extension: conflicting settings for '.x': '.x=.y' vs '.x=.y:nolist:comment=#'"
    )


def test_from_specs_overrides_default():
    reg = ExtensionRegistry.from_specs([ExtensionSpec(".vpy", ".sv")])
    assert reg.map[".vpy"] == ".sv"


def test_register_adds_and_map_is_same_object():
    reg = ExtensionRegistry.from_specs([])
    m = reg.map
    reg.register(".sdcpy", ".sdc", listed=False, comment="#")
    assert m[".sdcpy"] == ".sdc" and reg.map is m
    assert reg.listed(".sdcpy") is False and reg.comment(".sdcpy") == "#"


def test_register_repeat_is_noop():
    reg = ExtensionRegistry.from_specs([])
    reg.register(".sdcpy", ".sdc", listed=False, comment="#")
    reg.register(".sdcpy", ".sdc", listed=False, comment="#")
    assert reg.map[".sdcpy"] == ".sdc"
    assert reg.listed(".sdcpy") is False and reg.comment(".sdcpy") == "#"


def test_register_normalises():
    reg = ExtensionRegistry.from_specs([])
    reg.register(".sdcpy", ".sdc")
    reg.register("SDCPY", "sdc")
    assert reg.map[".sdcpy"] == ".sdc"


def test_register_remap_default_raises():
    reg = ExtensionRegistry.from_specs([])
    with pytest.raises(ValueError):
        reg.register(".svpy", ".v")


def test_register_differs_from_cli_raises():
    reg = ExtensionRegistry.from_specs([ExtensionSpec(".rdlpy", ".rdl")])
    with pytest.raises(ValueError):
        reg.register(".rdlpy", ".rdl", listed=False)


def test_register_empty_comment_raises():
    reg = ExtensionRegistry.from_specs([])
    with pytest.raises(ValueError):
        reg.register(".sdcpy", ".sdc", comment="")


@pytest.mark.parametrize("in_ext, out_ext", [("", ".y"), (".", ".y"), (".x", "")])
def test_register_bad_extension_names_no_flag(in_ext, out_ext):
    reg = ExtensionRegistry.from_specs([])
    with pytest.raises(ValueError) as exc:
        reg.register(in_ext, out_ext)
    assert "--extension" not in str(exc.value)
    assert str(exc.value).startswith("extension ")


def test_unmapped_queries():
    reg = ExtensionRegistry.from_specs([])
    assert reg.listed(None) is True
    assert reg.listed(".nope") is True
    assert reg.comment(None) is None
    assert reg.comment(".nope") is None


def test_manager_exposes_registry(tmp_path):
    args = parse_args(["--extension", ".rdlpy=.rdl:nolist", "-i", "a.vpy",
                       "--out-dir", str(tmp_path)])
    mgr = Manager(args)
    assert mgr.extension_map is mgr.extensions.map
    assert mgr.extension_map[".rdlpy"] == ".rdl"
    assert mgr.extensions.listed(".rdlpy") is False


def test_manager_conflict_raises_genesispy_error(tmp_path):
    args = parse_args(["--extension", ".x=.y", "--extension", ".x=.y:nolist",
                       "-i", "a.vpy", "--out-dir", str(tmp_path)])
    with pytest.raises(GenesisPyError):
        Manager(args)


def test_sv_flag_still_maps_vpy_to_sv(tmp_path):
    args = parse_args(["-sv", "-i", "a.vpy", "--out-dir", str(tmp_path)])
    assert args.extensions == [ExtensionSpec(".vpy", ".sv")]
    assert Manager(args).extension_map[".vpy"] == ".sv"
