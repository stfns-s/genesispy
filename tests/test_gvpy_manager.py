"""``_GvpyManager`` behaviour shared with ``Manager``: synonym registry, file
search errors, and the template stem list."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from genesispy.gvpy_cli import _GvpyManager, _stem, main
from genesispy.reporting import GenesisPyError, ParseError


def _mgr(tmp_path: Path) -> _GvpyManager:
    return _GvpyManager(argparse.Namespace(mname=None, parameter=[]), incdirs=[str(tmp_path)])


def test_synonym_resolves_for_generate(tmp_path: Path, capsys) -> None:
    """B11: a synonym registered in a body is found by a later string-named generate."""
    (tmp_path / "leaf.vpy").write_text("//; N = parameter('N', 1)\nmodule `mname`; endmodule\n")
    (tmp_path / "top.vpy").write_text(
        "//; synonym('leaf', 'leaf2')\n"
        "//; u = generate('leaf2', 'u2', N=8)\n"
        "`u.instantiate()` ();\n"
    )
    rc = main(["--inc-path", str(tmp_path), str(tmp_path / "top.vpy")])
    out = capsys.readouterr()
    assert rc == 0, out.err
    assert "leaf2_unq1 u2" in out.out


def test_synonym_rebind_to_a_different_source_is_refused(tmp_path: Path) -> None:
    (tmp_path / "leaf.vpy").write_text("module leaf; endmodule\n")
    (tmp_path / "other.vpy").write_text("module other; endmodule\n")
    mgr = _mgr(tmp_path)
    mgr.synonym_class("leaf", "alias")
    with pytest.raises(GenesisPyError, match="already registered"):
        mgr.synonym_class("other", "alias")


def test_synonym_target_shadowing_a_template_is_refused(tmp_path: Path) -> None:
    (tmp_path / "leaf.vpy").write_text("module leaf; endmodule\n")
    (tmp_path / "alias.vpy").write_text("module alias; endmodule\n")
    mgr = _mgr(tmp_path)
    with pytest.raises(GenesisPyError, match="already exists"):
        mgr.synonym_class("leaf", "alias")


def test_find_file_miss_names_the_search_paths(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    with pytest.raises(ParseError, match="not found in search paths"):
        mgr.find_file("nope.vpy")


def test_resolve_module_class_miss_is_a_genesispy_error(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    with pytest.raises(GenesisPyError, match="Cannot resolve module"):
        mgr.resolve_module_class("nope")


@pytest.mark.parametrize("path", ["foo.vp", "foo.gvp", "foo.svp"])
def test_stem_keeps_legacy_extensions_that_the_parser_rejects(path: str) -> None:
    assert _stem(path) == path
