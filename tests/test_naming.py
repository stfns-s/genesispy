"""Names genesispy derives: sanitised module stems, parameter names, synonym
targets, instance paths, and the translator's name-method map."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from genesispy.cli import parse_args
from genesispy.manager import Manager
from genesispy.reporting import ParameterError
from genesispy.tools import vp2vpy_map as M
from genesispy.unique_module import UniqueModule
from tests._stubs import StubManager



def _run(tmp_path: Path, argv: list[str]) -> int:
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        return Manager(parse_args(argv)).execute()
    finally:
        os.chdir(cwd)


# --- B28: stem sanitisation -----------------------------------------------------------

def test_two_inputs_with_one_sanitised_stem_are_rejected(tmp_path: Path, capsys) -> None:
    (tmp_path / "a-b.vpy").write_text("// from a-b\n")
    (tmp_path / "a_b.vpy").write_text("// from a_b\n")
    rc = _run(tmp_path, ["--input", "a-b.vpy", "--input", "a_b.vpy", "--top", "a_b"])
    assert rc != 0
    err = capsys.readouterr().err
    assert "a-b.vpy" in err and "a_b.vpy" in err, err


def test_keyword_stem_is_rejected(tmp_path: Path, capsys) -> None:
    (tmp_path / "if.vpy").write_text("// body\n")
    rc = _run(tmp_path, ["--input", "if.vpy", "--top", "if"])
    assert rc != 0
    assert "keyword" in capsys.readouterr().err


# --- F10: parameter names -------------------------------------------------------------

class _Mod(UniqueModule):
    pass


@pytest.mark.parametrize("name", ["my param", "a.x", "", "n-1"])
def test_parameter_name_must_be_a_word(name: str) -> None:
    m = _Mod(StubManager())
    with pytest.raises(ParameterError):
        m.parameter(name, 1)


def test_word_parameter_names_are_accepted() -> None:
    m = _Mod(StubManager())
    assert m.parameter("W_1", 3) == 3


# --- F11: synonym targets -------------------------------------------------------------

def _synonym_design(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "leaf.vpy").write_text("//; N = parameter('N', 1)\n")
    (tmp_path / "src" / "top.vpy").write_text(
        "//; synonym('leaf', 'leaf2')\n//; u = unique_inst('leaf2', 'u0', N=2)\n"
    )


def test_synonym_target_naming_an_input_template_is_refused(tmp_path: Path, capsys) -> None:
    _synonym_design(tmp_path)
    (tmp_path / "src" / "leaf2.vpy").write_text("//; N = parameter('N', 9)\n")
    rc = _run(tmp_path, ["--input", "top.vpy", "--input", "leaf.vpy", "--input", "leaf2.vpy",
                         "--top", "top", "--src-path", "src"])
    assert rc != 0
    assert "already exists" in capsys.readouterr().err


def test_synonym_target_naming_a_template_on_the_search_path_is_refused(
    tmp_path: Path, capsys
) -> None:
    _synonym_design(tmp_path)
    (tmp_path / "src" / "leaf2.vpy").write_text("//; N = parameter('N', 9)\n")
    rc = _run(tmp_path, ["--input", "top.vpy", "--input", "leaf.vpy", "--top", "top",
                         "--src-path", "src"])
    assert rc != 0
    assert "already exists" in capsys.readouterr().err


def test_synonym_target_without_a_template_works(tmp_path: Path) -> None:
    _synonym_design(tmp_path)
    rc = _run(tmp_path, ["--input", "top.vpy", "--input", "leaf.vpy", "--top", "top",
                         "--src-path", "src", "--out-dir", "out"])
    assert rc == 0
    assert (tmp_path / "out" / "leaf2_unq1.v").exists()


# --- B13: instance paths --------------------------------------------------------------

class _Top(UniqueModule):
    pass


class _Leaf(UniqueModule):
    pass


def test_instance_path_is_dotted_and_composes_with_get_instance_obj() -> None:
    """UniqueModule.pm:1057-1081: dot-joined, starting with the top's name."""
    top = _Top(StubManager())
    u0 = top.unique_inst(_Leaf, "u0")
    assert u0.get_instance_path() == "_Top.u0"
    assert top.search_subinst(path_regex=r"^_Top\.u0$") == [u0]
    assert top.get_instance_obj(u0.get_instance_path()) is u0


def test_get_module_name_is_the_unique_name() -> None:
    """UniqueModule.pm:363-372: get_module_name is the emitted name,
    get_base_name the template's."""
    top = _Top(StubManager())
    u0 = top.unique_inst(_Leaf, "u0")
    assert u0.get_module_name() == u0.get_unique_module_name() == str(u0.mname)
    assert u0.get_base_name() == "_Leaf"


# --- F1: Perl's name methods keep their names in the translation --------------------

@pytest.mark.parametrize("perl,py", [
    ("get_module_name", "get_module_name"),
    ("GetModuleName", "get_module_name"),
    ("get_base_name", "get_base_name"),
    ("get_unique_module_name", "get_unique_module_name"),
])
def test_vp2vpy_name_method_map(perl: str, py: str) -> None:
    assert M.METHOD_TABLE[perl] == py
