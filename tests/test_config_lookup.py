"""Configuration lookup contracts: path-scoped JSON, scoped .cfg overrides in the
dedup key, JSON schema validation, the ``Val`` value key, explicit null, unused
override reporting, and declared defaults in ``--json-out``."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from genesispy import cache
from genesispy.cli import parse_args
from genesispy.config_handler import ConfigHandler
from genesispy.manager import Manager
from genesispy.reporting import ConfigError
from tests._stubs import args_namespace

CHILD = (
    "//; W = parameter('W', 1)\n"
    "module `mname` ();\n"
    "// W=`W`\n"
    "endmodule\n"
)
TOP = (
    "//; a = unique_inst('child', 'a')\n"
    "//; b = unique_inst('child', 'b')\n"
    "module `mname` ();\n"
    "`a.instantiate()` ();\n"
    "`b.instantiate()` ();\n"
    "endmodule\n"
)
ARGV = ["--input", "top.vpy", "--input", "child.vpy", "--top", "top", "--src-path", "src",
        "--out-dir", "out"]



def _design(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "child.vpy").write_text(CHILD)
    (tmp_path / "src" / "top.vpy").write_text(TOP)


def _run(tmp_path: Path, argv: list[str]) -> int:
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        return Manager(parse_args(argv)).execute()
    finally:
        os.chdir(cwd)


def _emitted(tmp_path: Path) -> dict[str, str]:
    return {p.name: p.read_text() for p in (tmp_path / "out").glob("*.v")}


def _w_of(files: dict[str, str], top_text: str, inst: str) -> str:
    """Return the W= line of the module instantiated as ``inst`` in top."""
    mod = next(line.split()[0] for line in top_text.splitlines() if f" {inst} " in line)
    return next(line for line in files[f"{mod}.v"].splitlines() if line.startswith("// W="))


def _cfg_handler(tmp_path: Path, tree: object) -> ConfigHandler:
    p = tmp_path / "c.json"
    p.write_text(json.dumps(tree))
    ch = ConfigHandler(args_namespace())
    ch.read_json(str(p))
    return ch


# --- B1: JSON parameters resolve by instance path ---------------------------------

def test_json_params_are_scoped_by_instance_path(tmp_path: Path) -> None:
    _design(tmp_path)
    (tmp_path / "c.json").write_text(json.dumps({"HierarchyTop": {
        "InstanceName": "top",
        "Parameters": [{"Name": "W", "__Val__": 7}],
        "SubInstances": [
            {"InstanceName": "a", "Parameters": [{"Name": "W", "__Val__": 3}]},
            {"InstanceName": "b", "Parameters": [{"Name": "W", "__Val__": 4}]},
        ],
    }}))
    assert _run(tmp_path, [*ARGV, "--json-cfg", "c.json"]) == 0
    files = _emitted(tmp_path)
    assert _w_of(files, files["top.v"], "a") == "// W=3"
    assert _w_of(files, files["top.v"], "b") == "// W=4"


def test_json_param_on_one_node_does_not_leak_to_children(tmp_path: Path) -> None:
    _design(tmp_path)
    (tmp_path / "c.json").write_text(json.dumps({"HierarchyTop": {
        "InstanceName": "top",
        "Parameters": [{"Name": "W", "__Val__": 7}],
    }}))
    assert _run(tmp_path, [*ARGV, "--json-cfg", "c.json"]) == 0
    files = _emitted(tmp_path)
    assert _w_of(files, files["top.v"], "a") == "// W=1"


def test_json_top_instance_name_mismatch_is_an_error(tmp_path: Path, capsys) -> None:
    _design(tmp_path)
    (tmp_path / "c.json").write_text(json.dumps({"HierarchyTop": {
        "InstanceName": "nottop",
        "SubInstances": [{"InstanceName": "a", "Parameters": [{"Name": "W", "__Val__": 3}]}],
    }}))
    assert _run(tmp_path, [*ARGV, "--json-cfg", "c.json"]) != 0
    assert "nottop" in capsys.readouterr().err


def test_config_handler_lookup_by_path() -> None:
    ch = ConfigHandler(args_namespace())
    ch._param_db = {"HierarchyTop": {
        "InstanceName": "top",
        "SubInstances": [
            {"InstanceName": "a", "Parameters": [{"Name": "W", "__Val__": 3}]},
            {"InstanceName": "b", "Parameters": [{"Name": "W", "__Val__": 4}]},
        ],
    }}
    assert ch.get_configuration("W", instance_path=("top", "a")) == 3
    assert ch.get_configuration("W", instance_path=("top", "b")) == 4
    assert not ch.exists_configuration("W", instance_path=("top",))
    assert not ch.exists_configuration("W", instance_path=("top", "c"))


# --- B2: scoped .cfg overrides enter the dedup key ----------------------------------

def test_cfg_scoped_overrides_produce_distinct_unique_modules(tmp_path: Path) -> None:
    _design(tmp_path)
    (tmp_path / "scoped.cfg").write_text(
        "configure('top.a.W', 3)\nconfigure('top.b.W', 4)\n"
    )
    assert _run(tmp_path, [*ARGV, "--cfg", "scoped.cfg"]) == 0
    files = _emitted(tmp_path)
    assert _w_of(files, files["top.v"], "a") == "// W=3"
    assert _w_of(files, files["top.v"], "b") == "// W=4"


# --- B3: the writer's ``Val`` key is accepted on input ------------------------------

def test_val_key_is_accepted(tmp_path: Path) -> None:
    ch = _cfg_handler(tmp_path, {"HierarchyTop": {"Parameters": [{"Name": "W", "Val": 9}]}})
    assert ch.get_param_val("W") == 9


def test_json_out_round_trips_into_json_cfg(tmp_path: Path) -> None:
    _design(tmp_path)
    assert _run(tmp_path, [*ARGV, "-p", "W=9", "--json-out", "out.json"]) == 0
    cache.clear_all()
    assert _run(tmp_path, [*ARGV, "--json-cfg", "out.json"]) == 0
    files = _emitted(tmp_path)
    assert _w_of(files, files["top.v"], "a") == "// W=9"
    # b was written as a CloneOf a (dedup) and so carries no parameters of
    # its own; a snapshot records values only on the elaborated instance.
    assert _w_of(files, files["top.v"], "b") == "// W=1"


# --- B4: malformed JSON shapes are rejected -----------------------------------------

@pytest.mark.parametrize("tree", [
    {"Parameters": [{"Name": "W", "__Val__": 7}]},
    {"HierarchyTop": {"Parameters": [{"Name": "W", "Value": 7}]}},
    {"HierarchyTop": {"Parameters": {"W": 5}}},
    {"HierarchyTop": {"Parameters": [{"__Val__": 7}]}},
    {"HierarchyTop": {"Parameters": [{"Name": "W", "__Val__": 7, "Val": 7}]}},
    {"HierarchyTop": {"Parameters": [{"Name": "W", "__Val__": 7}, {"Name": "W", "__Val__": 8}]}},
    {"HierarchyTop": {"SubInstances": [{"Parameters": []}]}},
    {"HierarchyTop": {"SubInstances": {"a": {}}}},
], ids=["no-root", "no-value-key", "dict-params", "no-name", "two-value-keys",
        "duplicate-name", "subinst-no-name", "dict-subinstances"])
def test_malformed_json_config_is_rejected(tmp_path: Path, tree: object) -> None:
    with pytest.raises(ConfigError):
        _cfg_handler(tmp_path, tree)


def test_empty_string_containers_are_accepted(tmp_path: Path) -> None:
    """xml2json emits ``""`` for an empty element."""
    ch = _cfg_handler(tmp_path, {"HierarchyTop": {
        "InstanceName": "top", "Parameters": "", "ImmutableParameters": "", "SubInstances": "",
    }})
    assert not ch.exists_configuration("W", instance_path=("top",))


# --- B5: unused command-line and .cfg overrides are reported -----------------------

def test_unused_overrides_are_reported(tmp_path: Path, capsys) -> None:
    _design(tmp_path)
    (tmp_path / "u.cfg").write_text("configure('top.WIDTH', 6)\n")
    (tmp_path / "u.json").write_text(json.dumps({"HierarchyTop": {
        "InstanceName": "top", "Parameters": [{"Name": "DEPTH", "__Val__": 2}],
    }}))
    rc = _run(tmp_path, [*ARGV, "-p", "WIDTH=5", "-p", "top.nosuch.W=3",
                         "--cfg", "u.cfg", "--json-cfg", "u.json"])
    assert rc == 0
    err = capsys.readouterr().err
    for spec in ("WIDTH", "top.nosuch.W", "top.WIDTH"):
        assert f"override {spec} was never used" in err, err
    # JSON parameters are not checked (Perl's Finalize covers -parameter and .cfg only).
    assert "DEPTH" not in err


def test_used_overrides_are_not_reported(tmp_path: Path, capsys) -> None:
    _design(tmp_path)
    (tmp_path / "u.cfg").write_text("configure('top.b.W', 6)\n")
    assert _run(tmp_path, [*ARGV, "-p", "W=9", "-p", "top.a.W=3", "--cfg", "u.cfg"]) == 0
    assert "never used" not in capsys.readouterr().err


# --- B12: --json-out full carries declared defaults ---------------------------------

def test_json_out_full_includes_declared_defaults(tmp_path: Path) -> None:
    _design(tmp_path)
    assert _run(tmp_path, [*ARGV, "--json-out", "h.json"]) == 0
    full = json.loads((tmp_path / "h.json").read_text())
    a = next(s for s in full["HierarchyTop"]["SubInstances"] if s["InstanceName"] == "a")
    assert {p["Name"]: p["Val"] for p in a["Parameters"]} == {"W": 1}
    tiny = json.loads((tmp_path / "h-tiny.json").read_text())
    assert "Parameters" not in tiny["HierarchyTop"]


# --- B19: explicit JSON null overrides to None --------------------------------------

def test_json_null_overrides_to_none(tmp_path: Path) -> None:
    _design(tmp_path)
    (tmp_path / "c.json").write_text(json.dumps({"HierarchyTop": {
        "InstanceName": "top",
        "SubInstances": [{"InstanceName": "a", "Parameters": [{"Name": "W", "__Val__": None}]}],
    }}))
    assert _run(tmp_path, [*ARGV, "--json-cfg", "c.json"]) == 0
    files = _emitted(tmp_path)
    assert _w_of(files, files["top.v"], "a") == "// W=None"
