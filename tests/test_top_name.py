"""--top-name: the top template emitted under another name, as generate_w_name does."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from genesispy import cache
from genesispy.cli import parse_args
from genesispy.manager import Manager

LEAF = (
    "//; N = parameter('N', 1)\n"
    "//; s = unique_inst('sub', 's', TAG=str(mname))\n"
    "module `mname` (input clk);\n"
    "wire [`N`-1:0] `self.get_base_name()`_w;\n"
    "`s.instantiate()` (.clk(clk));\n"
    "endmodule\n"
)
SUB = (
    "//; TAG = parameter('TAG', 'none')\n"
    "module `mname` (input clk);\n"
    "wire `TAG`_tag;\n"
    "endmodule\n"
)
PARENT = (
    "//; u = generate_w_name('leaf', 'leaf_fast', 'u', N=4)\n"
    "module `mname` (input clk);\n"
    "`u.instantiate()` (.clk(clk));\n"
    "endmodule\n"
)


def _design(tmp_path: Path, top: str = PARENT) -> None:
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    (src / "leaf.vpy").write_text(LEAF)
    (src / "sub.vpy").write_text(SUB)
    (src / "top.vpy").write_text(top)


def _run(tmp_path: Path, argv: list[str], monkeypatch, out: str = "out") -> int:
    monkeypatch.chdir(tmp_path)
    base = ["--input", "top.vpy", "--input", "leaf.vpy", "--input", "sub.vpy",
            "--src-path", "src", "--out-dir", out]
    return Manager(parse_args([*base, *argv])).execute()


def _alone(extra: list[str] = ()) -> list[str]:
    return ["--top", "leaf", "--top-name", "leaf_fast", *extra]


def _body(path: Path) -> str:
    """The Verilog without comments or blank lines."""
    text = re.sub(r"/\*.*?\*/", "", path.read_text(), flags=re.S)
    lines = (re.sub(r"//.*", "", line).rstrip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def test_the_top_is_emitted_under_the_name(tmp_path, monkeypatch):
    _design(tmp_path)
    assert _run(tmp_path, _alone(["--json-out", "h.json"]), monkeypatch) == 0
    out = tmp_path / "out"
    assert not (out / "leaf.v").exists()
    body = _body(out / "leaf_fast.v")
    assert "module leaf_fast" in body
    assert "leaf_fast_w;" in body
    assert (out / "leaf_fast.vlist").exists()
    root = json.loads((tmp_path / "h.json").read_text())["HierarchyTop"]
    assert root["InstanceName"] == "leaf_fast"
    assert root["UniqueModuleName"] == "leaf_fast"
    assert root["TemplateName"] == "leaf"


def test_same_rtl_as_a_parent_generate_w_name(tmp_path, monkeypatch):
    _design(tmp_path)
    assert _run(tmp_path, ["--top", "top"], monkeypatch, out="parent") == 0
    cache.clear_all()
    assert _run(tmp_path, _alone(["-p", "leaf_fast.N=4"]), monkeypatch, out="alone") == 0
    parent = {p.name for p in (tmp_path / "parent").glob("*.v")} - {"top.v"}
    alone = {p.name for p in (tmp_path / "alone").glob("*.v")}
    assert parent == alone
    for name in sorted(alone):
        assert _body(tmp_path / "alone" / name) == _body(tmp_path / "parent" / name), name


def test_defaults_read_the_name_then_the_template(tmp_path, monkeypatch, capsys):
    _design(tmp_path)
    (tmp_path / "d.py").write_text(
        "BLOCK_PARAMS = {'leaf_fast': {'N': 6}, 'leaf': {'N': 3}, 'alt': {'N': 8}}\n")
    assert _run(tmp_path, _alone(["--defaults", "d.py"]), monkeypatch) == 0
    assert "wire [6-1:0]" in _body(tmp_path / "out" / "leaf_fast.v")
    err = capsys.readouterr().err
    assert "default leaf_fast.N" not in err and "default leaf.N" not in err
    cache.clear_all()
    flags = ["--defaults", "d.py", "--defaults-entry", "alt"]
    assert _run(tmp_path, _alone(flags), monkeypatch, out="out2") == 0
    assert "wire [8-1:0]" in _body(tmp_path / "out2" / "leaf_fast.v")


def test_a_dotted_parameter_is_rooted_at_the_name(tmp_path, monkeypatch, capsys):
    _design(tmp_path)
    assert _run(tmp_path, _alone(["-p", "leaf_fast.N=5"]), monkeypatch) == 0
    assert "wire [5-1:0]" in _body(tmp_path / "out" / "leaf_fast.v")
    cache.clear_all()
    assert _run(tmp_path, _alone(["-p", "leaf.N=5"]), monkeypatch, out="out2") == 0
    assert "wire [1-1:0]" in _body(tmp_path / "out2" / "leaf_fast.v")
    assert "override leaf.N was never used" in capsys.readouterr().err


@pytest.mark.parametrize("name", ["9leaf", "leaf-fast", "class"])
def test_an_illegal_name_is_a_usage_error(name):
    with pytest.raises(SystemExit) as exc:
        parse_args(["--top", "leaf", "--top-name", name])
    assert exc.value.code == 2


def test_a_name_that_is_a_template_is_an_error(tmp_path, monkeypatch, capsys):
    _design(tmp_path)
    assert _run(tmp_path, ["--top", "leaf", "--top-name", "sub"], monkeypatch) == 1
    assert "sub" in capsys.readouterr().err
    assert not list(tmp_path.glob("out/*.v"))


# A child's generate_w_name, or its unique name (the first sub is sub_unq1).
@pytest.mark.parametrize("top, name", [("top", "leaf_fast"), ("leaf", "sub_unq1")])
def test_a_child_emitted_under_the_name_is_an_error(tmp_path, monkeypatch, capsys, top, name):
    _design(tmp_path)
    assert _run(tmp_path, ["--top", top, "--top-name", name], monkeypatch) == 1
    assert name in capsys.readouterr().err
    assert not list(tmp_path.glob("out/*.v"))
