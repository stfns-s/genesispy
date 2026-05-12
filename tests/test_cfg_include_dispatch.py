"""Tests for the .cfg include() extension dispatcher."""

from __future__ import annotations

import json
import os

import pytest

from genesispy import config_handler


class _Args:
    parameter = []
    unqstyle = None


class _Mgr:
    args = _Args()

    def _resolve_cfg_path(self, name):
        return None


class _MgrWithCfgPath:
    """Minimal manager exposing _resolve_cfg_path against a list of dirs."""

    def __init__(self, cfg_path):
        self.args = _Args()
        self.cfg_path = list(cfg_path)
        self.touched_dirs: list[str] = []

    def _resolve_cfg_path(self, name: str) -> str:
        if os.path.isabs(name) or os.path.exists(name):
            return os.path.abspath(name)
        for d in self.cfg_path:
            cand = os.path.join(d, name)
            if os.path.exists(cand):
                return os.path.abspath(cand)
        return name


def _ch():
    return config_handler.ConfigHandler(_Mgr())


def _ch_with_cfg_path(cfg_path):
    return config_handler.ConfigHandler(_MgrWithCfgPath(cfg_path))


def test_include_xml_rejected(tmp_path):
    """XML configs are no longer accepted; convert via genesispy-xml2json."""
    from genesispy.errors import ConfigError, GenesisPyError

    xml_p = tmp_path / "data.xml"
    xml_p.write_text("<HierarchyTop/>")
    cfg_p = tmp_path / "main.cfg"
    cfg_p.write_text(f"include({str(xml_p)!r})\n")

    ch = _ch()
    with pytest.raises((ConfigError, GenesisPyError)):
        ch.read_cfg(str(cfg_p))


def test_include_dispatches_json(tmp_path):
    json_p = tmp_path / "data.json"
    json_p.write_text(json.dumps({
        "HierarchyTop": {"Parameters": [{"Name": "BAR", "__Val__": 22}]}
    }))
    cfg_p = tmp_path / "main.cfg"
    cfg_p.write_text(f"include({str(json_p)!r})\n")

    ch = _ch()
    ch.read_cfg(str(cfg_p))
    assert ch.get_param_val("BAR") == 22


def test_include_dispatches_uppercase_extension(tmp_path):
    json_p = tmp_path / "data.JSON"
    json_p.write_text(json.dumps({
        "HierarchyTop": {"Parameters": [{"Name": "BAZ", "__Val__": 33}]}
    }))
    cfg_p = tmp_path / "main.cfg"
    cfg_p.write_text(f"include({str(json_p)!r})\n")

    ch = _ch()
    ch.read_cfg(str(cfg_p))
    assert ch.get_param_val("BAZ") == 33


def test_include_dispatches_cfg(tmp_path):
    inner_cfg = tmp_path / "inner.cfg"
    inner_cfg.write_text("configure('QUX', 44)\n")
    outer_cfg = tmp_path / "outer.cfg"
    outer_cfg.write_text(f"include({str(inner_cfg)!r})\n")

    ch = _ch()
    ch.read_cfg(str(outer_cfg))
    assert ch.get_configuration("QUX") == 44


def test_include_json_then_json_merges(tmp_path):
    """Repeated JSON includes deep-merge into the same `_param_db`."""
    json_a = tmp_path / "a.json"
    json_a.write_text(json.dumps({
        "HierarchyTop": {"Parameters": [{"Name": "FROM_A", "__Val__": 1}]}
    }))
    json_b = tmp_path / "b.json"
    json_b.write_text(json.dumps({
        "HierarchyTop": {"Parameters": [{"Name": "FROM_B", "__Val__": 2}]}
    }))
    cfg_p = tmp_path / "main.cfg"
    cfg_p.write_text(
        f"include({str(json_a)!r})\n"
        f"include({str(json_b)!r})\n"
    )

    ch = _ch()
    ch.read_cfg(str(cfg_p))
    assert ch.get_param_val("FROM_A") == 1
    assert ch.get_param_val("FROM_B") == 2


# --------------------------------------------------------------------------
# include() resolves relative paths via --cfgpath (Genesis2 parity).
# --------------------------------------------------------------------------
def test_include_relative_cfg_resolves_via_cfgpath(tmp_path):
    cfgs = tmp_path / "cfgs"
    cfgs.mkdir()
    (cfgs / "inner.cfg").write_text("configure('Q', 7)\n")
    outer = tmp_path / "outer.cfg"
    outer.write_text("include('inner.cfg')\n")

    ch = _ch_with_cfg_path([str(cfgs)])
    ch.read_cfg(str(outer))
    assert ch.get_configuration("Q") == 7


def test_include_relative_json_resolves_via_cfgpath(tmp_path):
    cfgs = tmp_path / "cfgs"
    cfgs.mkdir()
    (cfgs / "data.json").write_text(json.dumps({
        "HierarchyTop": {"Parameters": [{"Name": "S", "__Val__": 5}]}
    }))
    outer = tmp_path / "outer.cfg"
    outer.write_text("include('data.json')\n")

    ch = _ch_with_cfg_path([str(cfgs)])
    ch.read_cfg(str(outer))
    assert ch.get_param_val("S") == 5
