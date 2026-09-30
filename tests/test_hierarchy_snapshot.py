"""Tests for ``config_handler.extract_stats`` and ``write_json``."""

from __future__ import annotations

import json

import pytest

from genesispy import cache
from genesispy.cli import parse_args
from genesispy.config_handler import (
    ConfigHandler,
    Priority,
    extract_stats,
)
from genesispy.manager import Manager
from genesispy.reporting import GenesisPyError
from genesispy.unique_module import UniqueModule

from ._stubs import StubManager



class _Top(UniqueModule):
    pass


class _Leaf(UniqueModule):
    pass


class _Leaf2(UniqueModule):
    pass


def _set_param(inst: UniqueModule, name: str, value, priority: int,
               state: str = "OVERRIDDEN", doc=None) -> None:
    inst._params[name] = {
        "value": value,
        "default": value,
        "state": state,
        "priority": priority,
        "doc": doc,
        "type": None,
    }


def _make_tree() -> _Top:
    """Top
       +-- u_a (_Leaf)        WIDTH=8 (CMD_LINE), DEPTH=4 (DECLARATION)
       |                      DEBUG=True (INHERITANCE)
       +-- u_b (clone of u_a)
       +-- u_c (_Leaf2)       WIDTH=16 (EXTERNAL_CONFIG)
    """
    top = _Top(StubManager())
    _set_param(top, "TOPNAME", "root", int(Priority.CMD_LINE))

    a = top.unique_inst(_Leaf, "u_a")
    _set_param(a, "WIDTH", 8, int(Priority.CMD_LINE))
    _set_param(a, "DEPTH", 4, int(Priority.DECLARATION), state="DEFINED")
    _set_param(a, "DEBUG", True, int(Priority.INHERITANCE))
    _set_param(a, "PIN", 3, int(Priority.IMMUTABLE), state="FORCED")

    top.clone_inst(a, "u_b")

    c = top.unique_inst(_Leaf2, "u_c")
    _set_param(c, "WIDTH", 16, int(Priority.EXTERNAL_CONFIG))

    return top


# ---------------------------------------------------------------------- #
# Shape: full / small / tiny                                             #
# ---------------------------------------------------------------------- #

def test_full_snapshot_shape() -> None:
    top = _make_tree()
    snap = extract_stats(top, variant="full")

    root = snap["HierarchyTop"]
    assert root["InstanceName"] == "_Top"
    assert root["BaseModuleName"] == "_Top"
    assert {p["Name"]: p["Val"] for p in root["Parameters"]} == {
        "TOPNAME": "root",
    }

    children = root["SubInstances"]
    by_name = {c["InstanceName"]: c for c in children}

    a = by_name["u_a"]
    a_params = {p["Name"]: p["Val"] for p in a["Parameters"]}
    # DEPTH is a declared default and stays; as in Perl, the parent-set DEBUG
    # (INHERITANCE) and the force-pinned PIN land under ImmutableParameters.
    assert a_params == {"WIDTH": 8, "DEPTH": 4}
    assert {p["Name"]: p["Val"] for p in a["ImmutableParameters"]} == {"DEBUG": True, "PIN": 3}

    # Clone: only CloneOf, no params/subinstances. Path uses dot separator.
    b = by_name["u_b"]
    assert b["CloneOf"] == {"InstancePath": "_Top.u_a"}
    assert b["TemplateName"] == "_Leaf"
    assert "Parameters" not in b
    assert "SubInstances" not in b


def test_small_drops_immutable_keeps_subtree() -> None:
    top = _make_tree()
    snap = extract_stats(top, variant="small")
    children = snap["HierarchyTop"]["SubInstances"]
    a = next(c for c in children if c["InstanceName"] == "u_a")
    assert "ImmutableParameters" not in a
    assert {p["Name"] for p in a["Parameters"]} == {"WIDTH", "DEPTH"}


def test_tiny_keeps_only_user_overrides() -> None:
    top = _make_tree()
    snap = extract_stats(top, variant="tiny")
    children = snap["HierarchyTop"]["SubInstances"]
    by_name = {c["InstanceName"]: c for c in children}

    # u_a: only WIDTH (CMD_LINE) is in [EXTERNAL_PARAM_FILE, INHERITANCE), as
    # in Perl; DEBUG (INHERITANCE) and PIN (IMMUTABLE) are tied, not configured.
    assert {p["Name"] for p in by_name["u_a"]["Parameters"]} == {"WIDTH"}
    assert "ImmutableParameters" not in by_name["u_a"]

    # u_c: WIDTH at EXTERNAL_CONFIG (< EXTERNAL_PARAM_FILE) -> empty -> pruned.
    assert "u_c" not in by_name


def test_tiny_prunes_empty_branches() -> None:
    top = _Top(StubManager())
    a = top.unique_inst(_Leaf, "u_a")
    _set_param(a, "WIDTH", 8, int(Priority.EXTERNAL_CONFIG))  # below tiny cutoff
    snap = extract_stats(top, variant="tiny")
    root = snap["HierarchyTop"]
    assert "SubInstances" not in root


# ---------------------------------------------------------------------- #
# Synonyms                                                               #
# ---------------------------------------------------------------------- #

def test_synonym_emitted_as_sibling_stub() -> None:
    top = _Top(StubManager())
    a = top.unique_inst(_Leaf, "u_a")
    a.synonym("Alias")

    snap = extract_stats(top, variant="full")
    children = snap["HierarchyTop"]["SubInstances"]
    by_name = {c["InstanceName"]: c for c in children}

    assert "u_a" in by_name
    assert "Alias" in by_name
    stub = by_name["Alias"]
    assert stub["SynonymFor"] == "_Top.u_a"
    assert stub["TemplateName"] == "_Leaf"
    assert "Parameters" not in stub
    assert "SubInstances" not in stub


# ---------------------------------------------------------------------- #
# write_json contract                                                    #
# ---------------------------------------------------------------------- #

def test_write_json_requires_top_inst(tmp_path) -> None:
    import types
    args = types.SimpleNamespace(parameter=[], unq_style=None)
    ch = ConfigHandler(types.SimpleNamespace(args=args))
    with pytest.raises(GenesisPyError):
        ch.write_json(str(tmp_path / "out.json"), top_inst=None)


def test_write_json_emits_three_files(tmp_path) -> None:
    import types
    top = _make_tree()
    args = types.SimpleNamespace(parameter=[], unq_style=None)
    ch = ConfigHandler(types.SimpleNamespace(args=args))

    out = tmp_path / "hier.json"
    ch.write_json(str(out), top_inst=top)

    full = json.loads(out.read_text())
    small = json.loads((tmp_path / "hier-small.json").read_text())
    tiny = json.loads((tmp_path / "hier-tiny.json").read_text())

    full_a = next(
        c for c in full["HierarchyTop"]["SubInstances"]
        if c["InstanceName"] == "u_a"
    )
    assert {p["Name"] for p in full_a["ImmutableParameters"]} == {"DEBUG", "PIN"}

    small_a = next(
        c for c in small["HierarchyTop"]["SubInstances"]
        if c["InstanceName"] == "u_a"
    )
    assert "ImmutableParameters" not in small_a

    tiny_children = tiny["HierarchyTop"]["SubInstances"]
    assert {c["InstanceName"] for c in tiny_children} == {"u_a", "u_b"}


# ---------------------------------------------------------------------- #
# TemplateName through --json-out                                        #
# ---------------------------------------------------------------------- #

_GEN_TOP = (
    "//; u = generate_w_name('leaf', 'leaf_fast', 'u')\n"
    "module `mname` (input clk);\n`u.instantiate()` (.clk(clk));\nendmodule\n"
)
_GEN_LEAF = "//; N = parameter('N', 1)\nmodule `mname` (input clk);\n// N=`N`\nendmodule\n"


def _run_gen(tmp_path, monkeypatch, *extra: str) -> int:
    monkeypatch.chdir(tmp_path)
    cache.clear_all()
    argv = ["--input", "top.vpy", "--input", "leaf.vpy", "--top", "top", "--src-path", "src",
            "--out-dir", "out", *extra]
    return Manager(parse_args(argv)).execute()


def test_json_out_records_the_template_of_a_generated_name(tmp_path, monkeypatch) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "top.vpy").write_text(_GEN_TOP)
    (tmp_path / "src" / "leaf.vpy").write_text(_GEN_LEAF)
    assert _run_gen(tmp_path, monkeypatch, "--json-out", "hier.json") == 0
    root = json.loads((tmp_path / "hier.json").read_text())["HierarchyTop"]
    assert root["TemplateName"] == "top"
    (u,) = root["SubInstances"]
    assert u["TemplateName"] == "leaf"
    assert u["UniqueModuleName"] == "leaf_fast"

    # Fed back as --json-cfg, the snapshot loads and its values apply.
    for p in u["Parameters"]:
        if p["Name"] == "N":
            p["Val"] = 4
    (tmp_path / "cfg.json").write_text(json.dumps({"HierarchyTop": root}))
    assert _run_gen(tmp_path, monkeypatch, "--json-cfg", "cfg.json") == 0
    (leaf_v,) = (tmp_path / "out").glob("leaf_fast*.v")
    assert "// N=4" in leaf_v.read_text()
