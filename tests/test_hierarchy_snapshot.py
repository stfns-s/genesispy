"""Tests for ``config_handler.extract_stats`` and ``write_json``."""

from __future__ import annotations

import json

import pytest

from genesispy import cache
from genesispy.config_handler import (
    ConfigHandler,
    Priority,
    extract_stats,
)
from genesispy.errors import GenesisPyError
from genesispy.unique_module import UniqueModule

from ._stubs import StubManager


def setup_function(_fn) -> None:
    cache.clear_all()


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
    # DEPTH dropped (NeverUsed); DEBUG (INHERITANCE) goes in Parameters, not Immutable.
    assert a_params == {"WIDTH": 8, "DEBUG": True}
    assert "ImmutableParameters" not in a

    # Clone: only CloneOf, no params/subinstances. Path uses dot separator.
    b = by_name["u_b"]
    assert b["CloneOf"] == {"InstancePath": "_Top.u_a"}
    assert "Parameters" not in b
    assert "SubInstances" not in b


def test_small_drops_immutable_keeps_subtree() -> None:
    top = _make_tree()
    snap = extract_stats(top, variant="small")
    children = snap["HierarchyTop"]["SubInstances"]
    a = next(c for c in children if c["InstanceName"] == "u_a")
    assert "ImmutableParameters" not in a
    assert {p["Name"] for p in a["Parameters"]} == {"WIDTH", "DEBUG"}


def test_tiny_keeps_only_user_overrides() -> None:
    top = _make_tree()
    snap = extract_stats(top, variant="tiny")
    children = snap["HierarchyTop"]["SubInstances"]
    by_name = {c["InstanceName"]: c for c in children}

    # u_a: WIDTH (CMD_LINE) and DEBUG (INHERITANCE) both >= EXTERNAL_PARAM_FILE.
    # Pre-#81 fix DEBUG was dropped via the immut bucket.
    assert {p["Name"] for p in by_name["u_a"]["Parameters"]} == {"WIDTH", "DEBUG"}
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
    # ImmutableParameters always empty post-#81 (no recursion tracking).
    assert "ImmutableParameters" not in full_a

    small_a = next(
        c for c in small["HierarchyTop"]["SubInstances"]
        if c["InstanceName"] == "u_a"
    )
    assert "ImmutableParameters" not in small_a

    tiny_children = tiny["HierarchyTop"]["SubInstances"]
    assert {c["InstanceName"] for c in tiny_children} == {"u_a", "u_b"}
