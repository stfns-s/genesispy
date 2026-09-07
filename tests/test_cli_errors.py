"""Every command-line fault path reports one line, not a traceback; ``--clean``
covers every named product; listfile paths resolve against the listfile."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from genesispy import cache
from genesispy.cli import main, parse_args
from genesispy.unique_module import UniqueModule
from tests._stubs import StubManager

LEAF = "//; N = parameter('N', 1)\nmodule `mname`; endmodule\n"


def _run(tmp_path: Path, argv: list[str]) -> int:
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        return main(argv)
    finally:
        os.chdir(cwd)


def _design(tmp_path: Path, top_body: str = "module `mname`; endmodule\n") -> list[str]:
    (tmp_path / "top.vpy").write_text(top_body)
    return ["--input", "top.vpy", "--top", "top", "--out-dir", "out"]


# --- B20: a missing absolute path is a one-line error ---------------------------------

def test_missing_absolute_input_is_one_line(tmp_path: Path, capsys) -> None:
    rc = _run(tmp_path, ["--input", str(tmp_path / "nope.vpy"), "--top", "nope"])
    err = capsys.readouterr().err
    assert rc == 1 and "Traceback" not in err and "not found" in err, err


@pytest.mark.parametrize("call", ["include", "pyinclude"])
def test_missing_absolute_include_is_one_line(tmp_path: Path, capsys, call: str) -> None:
    target = tmp_path / ("nope.vpy" if call == "include" else "nope.py")
    argv = _design(tmp_path, f"//; {call}({str(target)!r})\n")
    rc = _run(tmp_path, argv)
    err = capsys.readouterr().err
    assert rc == 1 and "Traceback" not in err and "not found" in err, err


# --- B21: --clean removes every named product ------------------------------------------

def test_clean_removes_named_products(tmp_path: Path) -> None:
    argv = _design(tmp_path)
    extra = ["--vf-out", "prod", "--depend", "deps.mk", "--json-out", "h.json",
             "--path", "dirs.txt", "--log", "run.log"]
    assert _run(tmp_path, [*argv, *extra]) == 0
    for name in ("prod.vf", "deps.mk", "h.json", "h-small.json", "h-tiny.json", "dirs.txt"):
        assert (tmp_path / name).exists(), name
    (tmp_path / "run.log").write_text("x\n")
    cache.clear_all()
    assert _run(tmp_path, [*argv, *extra, "--clean"]) == 0
    for name in ("prod.vf", "deps.mk", "h.json", "h-small.json", "h-tiny.json", "dirs.txt",
                 "run.log", "out"):
        assert not (tmp_path / name).exists(), name


def test_clean_script_lists_named_products(tmp_path: Path) -> None:
    argv = _design(tmp_path)
    assert _run(tmp_path, [*argv, "--product", "lists.vf", "--json-out", "h.json"]) == 0
    script = (tmp_path / "out" / "genesispy_clean.sh").read_text()
    for name in ("lists.vf", "lists.synth.vf", "lists.verif.vf", "h.json", "h-tiny.json"):
        assert name in script, script


# --- B24: a .cfg runtime error names file and line ------------------------------------

def test_cfg_runtime_error_names_the_line(tmp_path: Path, capsys) -> None:
    (tmp_path / "bad.cfg").write_text("configure('top.W', 1)\nx = undefined_name\n")
    argv = _design(tmp_path)
    rc = _run(tmp_path, [*argv, "--cfg", "bad.cfg"])
    err = capsys.readouterr().err
    assert rc == 1 and "bad.cfg:2" in err and "undefined_name" in err, err


# --- B29: Manager construction errors are one line --------------------------------------

def test_conflicting_extensions_are_one_line(tmp_path: Path, capsys) -> None:
    argv = _design(tmp_path)
    rc = _run(tmp_path, [*argv, "--extension", ".vpy=.a", "--extension", ".vpy=.b"])
    err = capsys.readouterr().err
    assert rc == 1 and "Traceback" not in err and ".vpy" in err, err


# --- B30 / F4: listfiles -----------------------------------------------------------------

def test_listfile_unbalanced_quote_is_a_usage_error(tmp_path: Path, capsys) -> None:
    lf = tmp_path / "x.list"
    lf.write_text("foo's.vpy\n")
    with pytest.raises(SystemExit):
        parse_args(["--input-list", str(lf)])
    assert "x.list" in capsys.readouterr().err


def test_listfile_paths_resolve_against_the_listfile_dir(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    (tmp_path / "lst").mkdir()
    (tmp_path / "lst" / "a.vpy").write_text("// a\n")
    (tmp_path / "lst" / "inc").mkdir()
    (tmp_path / "lst" / "list.txt").write_text(
        "--input a.vpy\n--inc-path inc\n--input elsewhere.vpy\nbare.vpy\n"
    )
    monkeypatch.chdir(tmp_path)
    ns = parse_args(["--input-list", "lst/list.txt"])
    # Perl Manager.pm:637-650: a directive argument that resolves to nothing
    # is dropped with a warning; a bare path line is kept as written.
    assert ns.input == [str(tmp_path / "lst" / "a.vpy"), "bare.vpy"]
    assert ns.inc_path == [str(tmp_path / "lst" / "inc")]
    err = capsys.readouterr().err
    assert (
        f"ignoring path {tmp_path / 'lst' / 'elsewhere.vpy'} (derived from elsewhere.vpy):"
        f" non-existent path on {tmp_path / 'lst' / 'list.txt'}:3" in err
    )


def test_listfile_undefined_variable_drops_the_path(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    (tmp_path / "a.vpy").write_text("// a\n")
    lf = tmp_path / "list.txt"
    lf.write_text("--input $GPY_NO_SUCH_VAR/x.vpy a.vpy\n")
    monkeypatch.delenv("GPY_NO_SUCH_VAR", raising=False)
    ns = parse_args(["--input-list", str(lf)])
    assert ns.input == [str(tmp_path / "a.vpy")]
    assert (
        f"ignoring path $GPY_NO_SUCH_VAR/x.vpy: environment var GPY_NO_SUCH_VAR"
        f" is undefined at {lf}:1" in capsys.readouterr().err
    )


def test_listfile_expands_environment_variables(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "top.vpy").write_text("// top\n")
    lf = tmp_path / "list.txt"
    lf.write_text("--src-path $GPY_TEST_ROOT/src\n--input ${GPY_TEST_ROOT}/top.vpy\n")
    monkeypatch.setenv("GPY_TEST_ROOT", str(tmp_path))
    ns = parse_args(["--input-list", str(lf)])
    assert ns.src_path == [str(tmp_path / "src")]
    assert ns.input == [str(tmp_path / "top.vpy")]


# --- B31: nothing to do is an error -----------------------------------------------------

def test_top_without_inputs_is_an_error(tmp_path: Path, capsys) -> None:
    rc = _run(tmp_path, ["-t", "x"])
    assert rc == 1
    assert "no input" in capsys.readouterr().err


# --- F8: clone_inst accepts an instance path ------------------------------------------

class _Top(UniqueModule):
    pass


class _Leaf(UniqueModule):
    pass


def test_clone_inst_accepts_an_instance_path() -> None:
    top = _Top(StubManager())
    u0 = top.unique_inst(_Leaf, "u0")
    u1 = top.clone_inst("_Top.u0", "u1")
    assert u1.get_unique_module_name() == u0.get_unique_module_name()
    assert u1.get_instance_name() == "u1"
