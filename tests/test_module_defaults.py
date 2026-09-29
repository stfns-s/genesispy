"""--defaults: per-module parameter defaults from a BLOCK_PARAMS tree, the lowest config tier."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from genesispy.cli import parse_args
from genesispy.manager import Manager

LEAF = (
    "//; N = parameter('N', 1)\n"
    "//; M = parameter('M', 2)\n"
    "module `mname` (input clk);\n"
    "// N=`N` M=`M`\n"
    "endmodule\n"
)


def _top(inst: str = "//; u = unique_inst('leaf', 'u')\n") -> str:
    return inst + "module `mname` (input clk);\n`u.instantiate()` (.clk(clk));\nendmodule\n"


def _write_defaults(tmp_path: Path, tree: dict, name: str = "d.py") -> str:
    path = tmp_path / name
    if name.endswith(".json"):
        path.write_text(json.dumps(tree))
    else:
        path.write_text(f"BLOCK_PARAMS = {tree!r}\n")
    return name


def _design(tmp_path: Path, top: str | None = None, leaf: str = LEAF) -> list[str]:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "leaf.vpy").write_text(leaf)
    (tmp_path / "src" / "top.vpy").write_text(_top() if top is None else top)
    return ["--input", "top.vpy", "--input", "leaf.vpy", "--top", "top", "--src-path", "src",
            "--out-dir", "out"]


def _run(tmp_path: Path, argv: list[str], monkeypatch) -> int:
    monkeypatch.chdir(tmp_path)
    return Manager(parse_args(argv)).execute()


def _leaf_text(tmp_path: Path, name: str = "leaf") -> str:
    files = sorted((tmp_path / "out").glob(f"{name}*.v"))
    assert files, sorted(p.name for p in (tmp_path / "out").iterdir())
    return files[0].read_text()


@pytest.mark.parametrize("fname", ["d.py", "d.json"])
def test_entry_value_replaces_the_declared_default(tmp_path, monkeypatch, fname):
    argv = _design(tmp_path)
    d = _write_defaults(tmp_path, {"leaf": {"N": 5}}, fname)
    assert _run(tmp_path, [*argv, "--defaults", d], monkeypatch) == 0
    assert "// N=5 M=2" in _leaf_text(tmp_path)


def test_python_values_keep_their_type(tmp_path, monkeypatch):
    argv = _design(tmp_path)
    d = _write_defaults(tmp_path, {"leaf": {"N": [3, 4], "M": "fast"}})
    assert _run(tmp_path, [*argv, "--defaults", d], monkeypatch) == 0
    assert "// N=[3, 4] M=fast" in _leaf_text(tmp_path)


def test_no_entry_keeps_the_declared_default(tmp_path, monkeypatch):
    argv = _design(tmp_path)
    d = _write_defaults(tmp_path, {"leaf": {"M": 7}})
    assert _run(tmp_path, [*argv, "--defaults", d], monkeypatch) == 0
    assert "// N=1 M=7" in _leaf_text(tmp_path)


FORCED_LEAF = LEAF.replace("parameter('N', 1)", "parameter('N', 9, force=True)")
JSON_CFG = {"HierarchyTop": {"InstanceName": "top", "SubInstances": [
    {"InstanceName": "u", "Parameters": [{"Name": "N", "__Val__": 9}]}]}}


@pytest.mark.parametrize("source", ["cfg", "json", "p_bare", "p_scoped", "parent", "force"])
def test_every_other_source_outranks_a_default(tmp_path, monkeypatch, source):
    top = _top("//; u = unique_inst('leaf', 'u', N=9)\n") if source == "parent" else None
    argv = _design(tmp_path, top, FORCED_LEAF if source == "force" else LEAF)
    extra = {
        "cfg": ["--cfg", "w.cfg"],
        "json": ["--json-cfg", "c.json"],
        "p_bare": ["-p", "N=9", "--params-global"],
        "p_scoped": ["-p", "top.u.N=9"],
    }.get(source, [])
    (tmp_path / "w.cfg").write_text("configure('top.u.N', 9)\n")
    (tmp_path / "c.json").write_text(json.dumps(JSON_CFG))
    d = _write_defaults(tmp_path, {"leaf": {"N": 5}})
    assert _run(tmp_path, [*argv, *extra, "--defaults", d], monkeypatch) == 0
    assert "// N=9 M=2" in _leaf_text(tmp_path)


def test_generated_name_falls_back_to_the_template_entry_per_key(tmp_path, monkeypatch):
    argv = _design(tmp_path, _top("//; u = generate_w_name('leaf', 'leaf_fast', 'u')\n"))
    d = _write_defaults(tmp_path, {"leaf": {"N": 5, "M": 6}, "leaf_fast": {"N": 8}})
    assert _run(tmp_path, [*argv, "--defaults", d], monkeypatch) == 0
    assert "// N=8 M=6" in _leaf_text(tmp_path, "leaf_fast")


def test_nested_entry_is_found_and_dict_values_are_not_parameters(tmp_path, monkeypatch):
    argv = _design(tmp_path)
    d = _write_defaults(tmp_path, {"top": {"leaf": {"N": 5, "sub": {"M": 3}}}})
    assert _run(tmp_path, [*argv, "--defaults", d], monkeypatch) == 0
    # sub is a child entry of leaf, not leaf's M
    assert "// N=5 M=2" in _leaf_text(tmp_path)


def test_several_files_combine(tmp_path, monkeypatch):
    argv = _design(tmp_path)
    a = _write_defaults(tmp_path, {"leaf": {"N": 5}}, "a.py")
    b = _write_defaults(tmp_path, {"top": {}}, "b.json")
    assert _run(tmp_path, [*argv, "--defaults", a, "--defaults", b], monkeypatch) == 0
    assert "// N=5 M=2" in _leaf_text(tmp_path)


@pytest.mark.parametrize(
    "files, message",
    [
        ({"d.py": {"grp": {"leaf": {"N": 5}}, "leaf": {"N": 6}}}, "leaf at grp.leaf and leaf"),
        ({"d.py": {"leaf": 5}}, "entry 'leaf' is not a dict"),
        ({"a.py": {"leaf": {"N": 5}}, "b.json": {"leaf": {"N": 6}}}, "leaf at"),
        ({"d.txt": {"leaf": {"N": 5}}}, "not a .py or .json file"),
    ],
)
def test_a_bad_tree_is_a_config_error(tmp_path, monkeypatch, capsys, files, message):
    argv = _design(tmp_path)
    for name, tree in files.items():
        (tmp_path / name).write_text(json.dumps(tree) if not name.endswith(".py")
                                     else f"BLOCK_PARAMS = {tree!r}\n")
    flags = [x for name in files for x in ("--defaults", name)]
    assert _run(tmp_path, [*argv, *flags], monkeypatch) != 0
    assert message in capsys.readouterr().err


def test_a_python_file_without_block_params_is_a_config_error(tmp_path, monkeypatch, capsys):
    argv = _design(tmp_path)
    (tmp_path / "d.py").write_text("PARAMS = {}\n")
    assert _run(tmp_path, [*argv, "--defaults", "d.py"], monkeypatch) != 0
    assert "no BLOCK_PARAMS dict" in capsys.readouterr().err


def test_a_missing_file_is_a_config_error(tmp_path, monkeypatch, capsys):
    argv = _design(tmp_path)
    assert _run(tmp_path, [*argv, "--defaults", "nope.py"], monkeypatch) != 0
    assert "nope.py" in capsys.readouterr().err


def test_unused_entries_and_keys_warn_but_pass(tmp_path, monkeypatch, capsys):
    argv = _design(tmp_path)
    d = _write_defaults(tmp_path, {"leaf": {"N": 5, "TYPO": 1}, "ghost": {"N": 1}})
    assert _run(tmp_path, [*argv, "--defaults", d], monkeypatch) == 0
    err = capsys.readouterr().err
    assert "default leaf.TYPO was never used (--defaults d.py)" in err
    assert "default ghost was never used (--defaults d.py)" in err
    assert "default leaf was never used" not in err


def test_param_footer_names_the_defaults_tier(tmp_path, monkeypatch):
    argv = _design(tmp_path)
    d = _write_defaults(tmp_path, {"leaf": {"N": 5}})
    assert _run(tmp_path, [*argv, "--defaults", d, "--param-footer"], monkeypatch) == 0
    assert re.search(r"^//\s+N\s+: 5\s+<- module defaults \(--defaults\)$",
                     _leaf_text(tmp_path), re.M)


def test_identical_instances_still_share_one_module(tmp_path, monkeypatch):
    top = (
        "//; u = unique_inst('leaf', 'u')\n"
        "//; v = unique_inst('leaf', 'v')\n"
        "module `mname` (input clk);\n`u.instantiate()` (.clk(clk));\n"
        "`v.instantiate()` (.clk(clk));\nendmodule\n"
    )
    argv = _design(tmp_path, top)
    d = _write_defaults(tmp_path, {"leaf": {"N": 5}})
    assert _run(tmp_path, [*argv, "--defaults", d], monkeypatch) == 0
    assert len(list((tmp_path / "out").glob("leaf*.v"))) == 1
