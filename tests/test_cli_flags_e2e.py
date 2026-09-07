"""Flags and entry points that had only an argparse test: each drives a real
Manager and checks the effect on disk or on the emitted text."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from genesispy import cache
from genesispy.cli import parse_args
from genesispy.manager import Manager
from genesispy.reporting import GenesisPyError, ParameterError
from genesispy.unique_module import UniqueModule
from tests._stubs import StubManager

LEAF = "//; N = parameter('N', 1)\nmodule `mname` (input clk);\n// N=`N`\nendmodule\n"
TOP = (
    "//; a = unique_inst('leaf', 'a', N=4)\n"
    "//; b = unique_inst('leaf', 'b', N=4)\n"
    "module `mname` (input clk);\n"
    "`a.instantiate(clk='clk')`;\n"
    "`b.instantiate()` (.clk(clk));\n"
    "endmodule\n"
)


def _design(tmp_path: Path) -> list[str]:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "leaf.vpy").write_text(LEAF)
    (tmp_path / "src" / "top.vpy").write_text(TOP)
    return ["--input", "top.vpy", "--input", "leaf.vpy", "--top", "top", "--src-path", "src"]


def _run(tmp_path: Path, argv: list[str], monkeypatch) -> Manager:
    monkeypatch.chdir(tmp_path)
    m = Manager(parse_args(argv))
    assert m.execute() == 0
    return m


def _files(d: Path) -> set[str]:
    return {p.name for p in d.iterdir()} if d.is_dir() else set()


def test_phases_can_be_driven_one_at_a_time(tmp_path: Path, monkeypatch) -> None:
    argv = _design(tmp_path)
    monkeypatch.chdir(tmp_path)
    m = Manager(parse_args([*argv, "--out-dir", "out"]))
    m.parse_files()
    assert {"top.py", "leaf.py"} <= _files(tmp_path / "genesis_raw")
    m.gen_verilog()  # calls flush_outputs itself
    assert "top.v" in _files(tmp_path / "out")
    # flush_outputs is idempotent: a second call rewrites nothing new.
    before = sorted(_files(tmp_path / "out"))
    m.flush_outputs()
    assert sorted(_files(tmp_path / "out")) == before


def test_instantiate_fragment_content(tmp_path: Path, monkeypatch) -> None:
    _run(tmp_path, [*_design(tmp_path), "--out-dir", "out"], monkeypatch)
    top = (tmp_path / "out" / "top.v").read_text()
    assert "leaf_unq1 a (\n  .clk(clk)\n);" in top
    assert "leaf_unq1 b (.clk(clk));" in top


def test_depend_flag_names_the_file(tmp_path: Path, monkeypatch) -> None:
    _run(tmp_path, [*_design(tmp_path), "--out-dir", "out", "--depend", "deps.mk"], monkeypatch)
    text = (tmp_path / "deps.mk").read_text()
    assert "src/top.vpy" in text and "src/leaf.vpy" in text
    assert not (tmp_path / "out" / "top.depend").exists()


def test_synth_and_verif_dirs_split_by_synth_top(tmp_path: Path, monkeypatch) -> None:
    _run(tmp_path, [*_design(tmp_path), "--synth-top", "top.a",
                    "--synth-dir", "s", "--verif-dir", "v"], monkeypatch)
    assert "leaf_unq1.v" in _files(tmp_path / "s")
    assert "top.v" in _files(tmp_path / "v")


@pytest.mark.parametrize("out_type,expected", [
    ("synth", {"leaf_unq1.v"}),
    ("verif", {"leaf_unq2.v", "top.v"}),
    ("both", {"leaf_unq1.v", "leaf_unq2.v", "top.v"}),
])
def test_out_type_filters_the_flavour(
    tmp_path: Path, monkeypatch, out_type: str, expected: set
) -> None:
    """a (synth cone) and b (verif cone) get distinct modules, so each is
    tagged with one flavour only."""
    argv = _design(tmp_path)
    (tmp_path / "src" / "top.vpy").write_text(TOP.replace("'b', N=4", "'b', N=5"))
    _run(tmp_path, [*argv, "--synth-top", "top.a", "--out-dir", "out",
                    "--out-type", out_type], monkeypatch)
    names = {n for n in _files(tmp_path / "out") if n.endswith(".v")}
    assert names == expected


def test_no_module_cache_elaborates_every_instance(tmp_path: Path, monkeypatch) -> None:
    _run(tmp_path, [*_design(tmp_path), "--out-dir", "out", "--no-module-cache"], monkeypatch)
    assert {"leaf_unq1.v", "leaf_unq2.v"} <= _files(tmp_path / "out")


def test_gen_raw_writes_raw_verilog_beside_the_py(tmp_path: Path, monkeypatch) -> None:
    _run(tmp_path, [*_design(tmp_path), "--out-dir", "out", "--gen-raw"], monkeypatch)
    assert {"top.py", "top.v", "leaf_unq1.v"} <= _files(tmp_path / "genesis_raw")


def test_unq_style_param_names_modules_by_parameters(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "leaf.vpy").write_text(LEAF)
    (tmp_path / "src" / "top.vpy").write_text("//; a = generate('leaf', 'a', N=8)\n")
    _run(tmp_path, ["--input", "top.vpy", "--input", "leaf.vpy", "--top", "top",
                    "--src-path", "src", "--out-dir", "out", "--unq-style", "param"], monkeypatch)
    assert "leaf_N_8.v" in _files(tmp_path / "out")


def test_cfg_path_resolves_a_bare_cfg_name(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "cfgs").mkdir()
    (tmp_path / "cfgs" / "w.cfg").write_text("configure('top.a.N', 6)\n")
    _run(tmp_path, [*_design(tmp_path), "--out-dir", "out", "--cfg-path", "cfgs",
                    "--cfg", "w.cfg"], monkeypatch)
    # The parent kwarg N=4 outranks the .cfg for a and b; the cfg value is
    # still consumed (no unused-override warning) by the lookup. Check the
    # file was found at all: a missing cfg is a ConfigError.
    assert (tmp_path / "out" / "top.v").exists()


def test_missing_cfg_is_a_config_error(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    argv = _design(tmp_path)
    rc = Manager(parse_args([*argv, "--cfg", "nope.cfg"])).execute()
    assert rc == 1
    assert "nope.cfg" in capsys.readouterr().err


def test_debug_reports_written_files(tmp_path: Path, monkeypatch, capsys) -> None:
    _run(tmp_path, [*_design(tmp_path), "--out-dir", "out", "--debug", "1"], monkeypatch)
    err = capsys.readouterr().err
    assert "output_writer: wrote" in err and "top.v" in err


def test_log_flag_tees_warnings_to_the_file(tmp_path: Path, monkeypatch) -> None:
    _run(tmp_path, [*_design(tmp_path), "--out-dir", "out", "-p", "NOSUCH=1",
                    "--log", "run.log"], monkeypatch)
    assert "override NOSUCH was never used" in (tmp_path / "run.log").read_text()


def test_path_flag_lists_touched_directories(tmp_path: Path, monkeypatch) -> None:
    _run(tmp_path, [*_design(tmp_path), "--out-dir", "out", "--path", "dirs.txt"], monkeypatch)
    lines = (tmp_path / "dirs.txt").read_text().splitlines()
    assert "src" in lines, lines


def test_use_tmp_and_keep_tmp(tmp_path: Path, monkeypatch) -> None:
    m = _run(tmp_path, [*_design(tmp_path), "--out-dir", "out", "--keep-tmp"], monkeypatch)
    assert not (tmp_path / "genesis_raw").exists()
    assert m.raw_dir.startswith(tempfile_root()) and os.path.isdir(m.raw_dir)
    assert "top.py" in _files(Path(m.raw_dir))


def tempfile_root() -> str:
    import tempfile

    return tempfile.gettempdir()


def test_py_import_loads_a_helper_module(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "helpers").mkdir()
    (tmp_path / "helpers" / "myhelp.py").write_text("WIDTH = 12\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "top.vpy").write_text("//; import myhelp\n// W=`myhelp.WIDTH`\n")
    monkeypatch.setattr(sys, "path", list(sys.path))
    _run(tmp_path, ["--input", "top.vpy", "--top", "top", "--src-path", "src", "--out-dir", "out",
                    "--py-path", "helpers", "--py-import", "myhelp"], monkeypatch)
    assert "// W=12" in (tmp_path / "out" / "top.v").read_text()
    assert "myhelp" in sys.modules


def test_py_import_failure_is_one_line(tmp_path: Path, monkeypatch, capsys) -> None:
    from genesispy.cli import main

    monkeypatch.chdir(tmp_path)
    argv = _design(tmp_path)
    assert main([*argv, "--py-import", "no_such_module_xyz"]) == 1
    err = capsys.readouterr().err
    assert "no_such_module_xyz" in err and "Traceback" not in err


def test_gen_only_without_the_class_is_a_genesispy_error(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    (tmp_path / "genesis_raw").mkdir()
    (tmp_path / "genesis_raw" / "top.py").write_text("x = 1\n")
    monkeypatch.chdir(tmp_path)
    rc = Manager(parse_args(["--gen-only", "--top", "top"])).execute()
    assert rc == 1
    assert "does not define class 'top'" in capsys.readouterr().err


def test_json_out_write_failure_is_reported(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    argv = _design(tmp_path)
    args = parse_args([*argv, "--out-dir", "out", "--json-out", "no/such/dir/h.json"])
    rc = Manager(args).execute()
    assert rc == 1
    assert "write_json failed" in capsys.readouterr().err


def test_json_out_tiny_and_full_from_the_cli(tmp_path: Path, monkeypatch) -> None:
    _run(tmp_path, [*_design(tmp_path), "--out-dir", "out", "--json-out", "h.json"], monkeypatch)
    full = json.loads((tmp_path / "h.json").read_text())
    tiny = json.loads((tmp_path / "h-tiny.json").read_text())
    subs = {s["InstanceName"]: s for s in full["HierarchyTop"]["SubInstances"]}
    assert {p["Name"]: p["Val"] for p in subs["a"]["Parameters"]} == {"N": 4}
    assert "CloneOf" in subs["b"]
    assert tiny["HierarchyTop"]["InstanceName"] == "top"


class _Mod(UniqueModule):
    pass


def test_get_param_unknown_raises() -> None:
    with pytest.raises(ParameterError, match="Unknown parameter"):
        _Mod(StubManager()).get_param("NOPE")


def test_extension_conflict_is_a_genesispy_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(GenesisPyError):
        Manager(parse_args(["--input", "a.vpy", "--top", "a",
                            "--extension", ".vpy=.a", "--extension", ".vpy=.b"]))


def test_stdout_mode_removes_the_raw_dir(tmp_path: Path, monkeypatch, capsys) -> None:
    _run(tmp_path, [*_design(tmp_path), "--stdout"], monkeypatch)
    out = capsys.readouterr().out
    assert "// genesispy: top.v" in out and "module top" in out
    assert not (tmp_path / "genesis_raw").exists()
    cache.clear_all()


def test_py_import_can_extend_user_mixin(tmp_path: Path, monkeypatch) -> None:
    """The guide's section 11.5 recipe: a --py-import module adds methods to UserMixin."""
    (tmp_path / "helpers").mkdir()
    (tmp_path / "helpers" / "mymix.py").write_text(
        "from genesispy.user_lib import UserMixin\n"
        "def hello(self):\n    return f'// {self.mname} says hello'\n"
        "UserMixin.hello = hello\n"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "top.vpy").write_text("`self.hello()`\n")
    monkeypatch.setattr(sys, "path", list(sys.path))
    # Absolute: a relative entry would hit the importer cached for an earlier test's cwd.
    _run(tmp_path, ["--input", "top.vpy", "--top", "top", "--src-path", "src", "--out-dir", "out",
                    "--py-path", str(tmp_path / "helpers"), "--py-import", "mymix"], monkeypatch)
    assert "// top says hello" in (tmp_path / "out" / "top.v").read_text()
    from genesispy.user_lib import UserMixin

    del UserMixin.hello
