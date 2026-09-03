"""Unit + integration tests for ``genesispy.gvpy_cli``.

Exercises every flag of the ``gvpy`` console script through ``main()``,
plus the small pure helpers (``_flatten_csv``, ``_stem``).
"""

from __future__ import annotations

import re
import sys

import pytest

from genesispy import gvpy_cli
from genesispy.gvpy_cli import _flatten_csv, _stem, main


# --------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------
def test_flatten_csv_splits_commas():
    assert _flatten_csv(["a,b,c"]) == ["a", "b", "c"]


def test_flatten_csv_concatenates_repeats():
    assert _flatten_csv(["a", "b,c", "d"]) == ["a", "b", "c", "d"]


def test_flatten_csv_drops_empty():
    assert _flatten_csv(["a,,b", ""]) == ["a", "b"]


def test_flatten_csv_empty():
    assert _flatten_csv([]) == []


@pytest.mark.parametrize(
    "path, expected",
    [
        ("foo.vpy", "foo"),
        ("foo.gvpy", "foo"),
        ("foo.vp", "foo"),
        ("foo.gvp", "foo"),
        ("foo.svpy", "foo"),
        ("foo.svp", "foo"),
        ("/abs/path/bar.vpy", "bar"),
        ("noext", "noext"),
        ("name.unknown", "name.unknown"),
    ],
)
def test_stem(path, expected):
    assert _stem(path) == expected


# --------------------------------------------------------------------------
# main(): error paths
# --------------------------------------------------------------------------
def test_main_no_files_errors(capsys):
    rc = main([])
    assert rc == 2
    err = capsys.readouterr().err
    assert "no input files" in err


def test_main_malformed_defparam(tmp_path, capsys):
    """--defparam is a hidden alias for --parameter; malformed value still errors."""
    src = tmp_path / "x.vpy"
    src.write_text("module x; endmodule\n")
    rc = main(["--defparam", "BROKEN_NO_EQUALS", str(src)])
    assert rc == 2
    assert "alformed -parameter" in capsys.readouterr().err


def test_main_malformed_parameter(tmp_path, capsys):
    src = tmp_path / "x.vpy"
    src.write_text("module x; endmodule\n")
    rc = main(["--parameter", "BROKEN_NO_EQUALS", str(src)])
    assert rc == 2
    assert "alformed -parameter" in capsys.readouterr().err


def test_main_missing_input_returns_error(capsys):
    rc = main(["does_not_exist.vpy"])
    assert rc == 1
    assert "error processing" in capsys.readouterr().err


def test_main_help_exits():
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_main_version_exits(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "gvpy" in out


# --------------------------------------------------------------------------
# main(): happy paths
# --------------------------------------------------------------------------
def _write_basic_module(tmp_path, name="example", body="  wire w;\n"):
    src = tmp_path / f"{name}.vpy"
    src.write_text(
        f"module {name};\n{body}endmodule\n"
    )
    return src


def test_main_emits_to_stdout(tmp_path, capsys):
    src = _write_basic_module(tmp_path)
    rc = main([str(src)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "module example" in out
    assert "wire w" in out
    assert "endmodule" in out


def test_main_comment_flag_rewrites_directive_and_banner(tmp_path, capsys):
    """--source-comment '#' makes the parser recognise '#;' directives and
    stamps '#' on the generated banner."""
    src = tmp_path / "c.vpy"
    src.write_text(
        "#; for i in range(2):\n"
        "    wire w_`i`;\n"
        "#; # endfor\n"
    )
    rc = main(["--source-comment", "#", str(src)])
    assert rc == 0
    out = capsys.readouterr().out
    # Loop body unrolled.
    assert "wire w_0;" in out
    assert "wire w_1;" in out
    # Banner uses the configured prefix.
    assert "# Genesis-Py generated module:" in out
    assert "// Genesis-Py" not in out
    # Directive lines themselves were consumed (not echoed).
    assert "#; for" not in out


def test_main_mname_overrides_stem(tmp_path, capsys):
    src = tmp_path / "input_file.vpy"
    src.write_text("module `mname`;\nendmodule\n")
    rc = main(["--mname", "renamed", str(src)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "module renamed" in out


def test_main_defparam_flows_through_parameter(tmp_path, capsys):
    """--defparam alias still routes into parameter() lookups."""
    src = tmp_path / "p.vpy"
    src.write_text(
        "module p;\n"
        "//; W = parameter('WIDTH', 1)\n"
        "  wire [`W-1`:0] x;\n"
        "endmodule\n"
    )
    rc = main(["--defparam", "WIDTH=8", str(src)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "wire [7:0] x" in captured.out
    assert "--defparam is deprecated" in captured.err


def test_main_defparam_warning_only_once(tmp_path, capsys):
    """Repeated --defparam emits the deprecation warning a single time."""
    src = tmp_path / "p.vpy"
    src.write_text(
        "module p;\n"
        "//; A = parameter('A', 0)\n"
        "//; B = parameter('B', 0)\n"
        "  // A=`A` B=`B`\n"
        "endmodule\n"
    )
    rc = main(["--defparam", "A=1", "--defparam", "B=2", str(src)])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.err.count("--defparam is deprecated") == 1


def test_main_parameter_no_deprecation_warning(tmp_path, capsys):
    """--parameter must not emit the --defparam deprecation."""
    src = tmp_path / "p.vpy"
    src.write_text(
        "module p;\n"
        "//; W = parameter('WIDTH', 1)\n"
        "  wire [`W-1`:0] x;\n"
        "endmodule\n"
    )
    rc = main(["--parameter", "WIDTH=8", str(src)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "--defparam is deprecated" not in captured.err


def test_main_parameter_flows_through_parameter(tmp_path, capsys):
    src = tmp_path / "p.vpy"
    src.write_text(
        "module p;\n"
        "//; W = parameter('WIDTH', 1)\n"
        "  wire [`W-1`:0] x;\n"
        "endmodule\n"
    )
    rc = main(["--parameter", "WIDTH=8", str(src)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "wire [7:0] x" in out


def test_main_parameter_short_flag(tmp_path, capsys):
    src = tmp_path / "p.vpy"
    src.write_text(
        "module p;\n"
        "//; W = parameter('WIDTH', 1)\n"
        "  wire [`W-1`:0] x;\n"
        "endmodule\n"
    )
    rc = main(["-p", "WIDTH=8", str(src)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "wire [7:0] x" in out


def test_main_defparam_default_when_absent(tmp_path, capsys):
    src = tmp_path / "p.vpy"
    src.write_text(
        "module p;\n"
        "//; W = parameter('WIDTH', 4)\n"
        "  wire [`W-1`:0] x;\n"
        "endmodule\n"
    )
    rc = main([str(src)])
    assert rc == 0
    assert "wire [3:0] x" in capsys.readouterr().out


def test_main_incdirs_resolves_pinclude(tmp_path, capsys):
    inc_dir = tmp_path / "inc"
    inc_dir.mkdir()
    (inc_dir / "snippet.py").write_text("emit('// helper-was-included\\n')\n")

    src = tmp_path / "top.vpy"
    src.write_text(
        "module top;\n"
        "//; self.pinclude('snippet.py')\n"
        "endmodule\n"
    )
    rc = main(["--incdirs", str(inc_dir), str(src)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "helper-was-included" in out


def test_main_incdirs_csv(tmp_path, capsys):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (b / "snippet.py").write_text("emit('// from-b\\n')\n")
    src = tmp_path / "top.vpy"
    src.write_text(
        "module top;\n//; self.pinclude('snippet.py')\nendmodule\n"
    )
    rc = main(["--incdirs", f"{a},{b}", str(src)])
    assert rc == 0
    assert "from-b" in capsys.readouterr().out


def test_main_libdirs_prepends_sys_path(tmp_path, capsys):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    src = _write_basic_module(tmp_path)
    before = list(sys.path)
    try:
        rc = main(["--libdirs", str(lib_dir), str(src)])
        assert rc == 0
        assert str(lib_dir) in sys.path
    finally:
        # Restore sys.path so other tests aren't affected.
        sys.path[:] = before


def test_main_comment_flag_accepted(tmp_path, capsys):
    """``--source-comment`` parses and is plumbed end-to-end (sentinel + banner)
    by ``test_main_comment_flag_rewrites_directive_and_banner`` above; this
    test just covers the rc==0 happy path with a non-default value.
    """
    src = _write_basic_module(tmp_path)
    rc = main(["--source-comment", "#", str(src)])
    assert rc == 0


def test_main_comment_empty_rejected(tmp_path):
    src = _write_basic_module(tmp_path)
    with pytest.raises(SystemExit):
        main(["--source-comment", "", str(src)])


def test_main_comment_whitespace_only_rejected(tmp_path):
    src = _write_basic_module(tmp_path)
    with pytest.raises(SystemExit):
        main(["--source-comment", "  ", str(src)])


def test_main_multiple_files(tmp_path, capsys):
    a = _write_basic_module(tmp_path, name="aaa")
    b = _write_basic_module(tmp_path, name="bbb")
    rc = main([str(a), str(b)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "module aaa" in out
    assert "module bbb" in out


def test_main_gvpy_strict_record_only_generate(tmp_path, capsys):
    """In ``--gvpy-strict``, ``generate`` is record-only; the body of the
    referenced module is NOT elaborated. The PARAMS comment lands in the
    output via ``instantiate``.
    """
    src = tmp_path / "top.vpy"
    src.write_text(
        "module top;\n"
        "//; sub = generate('submod', 'u_sub', WIDTH=8)\n"
        "//; instantiate(sub)\n"
        "endmodule\n"
    )
    rc = main(["--gvpy-strict", str(src)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "submod /*PARAMS: WIDTH=>8 */ u_sub" in out


def test_gvpy_synonym_class_is_idempotent(tmp_path):
    """`_GvpyManager.synonym_class(src, target)` returns the same class on repeats."""
    from genesispy.gvpy_cli import _GvpyManager
    import argparse

    src = tmp_path / "leaf.vpy"
    src.write_text("module leaf; endmodule\n")

    args = argparse.Namespace(mname=None, parameter=[])
    mgr = _GvpyManager(args, incdirs=[str(tmp_path)])
    a = mgr.synonym_class("leaf", "alias")
    b = mgr.synonym_class("leaf", "alias")
    assert a is b


def test_main_traceback_remapped_to_vpy_source(tmp_path, capsys):
    """A runtime error in a //; line yields a traceback mentioning the .vpy file."""
    src = tmp_path / "boom.vpy"
    src.write_text(
        "module boom;\n"
        "//; raise ValueError('detonated')\n"
        "endmodule\n"
    )
    rc = main([str(src)])
    err = capsys.readouterr().err
    assert rc == 1
    assert "boom.vpy" in err
    # Without the line-map registration, the frame's line number is the
    # generated-source line; with the fix it's remapped to .vpy line 2.
    assert 'line 2' in err


def test_main_gvpy_strict_parameter_honours_scoped_override(tmp_path, capsys):
    """Hierarchical ``--parameter top.X=val`` reaches strict-mode ``parameter()``."""
    src = tmp_path / "top.vpy"
    src.write_text(
        "module top;\n"
        "//; W = parameter('WIDTH', 8)\n"
        "//; sub = generate('submod', 'u_sub', WIDTH=W)\n"
        "//; instantiate(sub)\n"
        "endmodule\n"
    )
    rc = main(["--gvpy-strict", "--parameter", "top.WIDTH=16", str(src)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "WIDTH=>16" in out


def test_main_pinclude_runs_python(tmp_path, capsys):
    """``self.pinclude(path)`` execs raw Python in a namespace seeded
    with ``self``/``emit``/``parameter``.
    """
    inc_dir = tmp_path / "inc"
    inc_dir.mkdir()
    py = inc_dir / "snippet.py"
    py.write_text("emit('// hello-from-pinclude\\n')\n")

    src = tmp_path / "top.vpy"
    src.write_text(
        "module top;\n"
        "//; self.pinclude('snippet.py')\n"
        "endmodule\n"
    )
    rc = main(["--incdirs", str(inc_dir), str(src)])
    assert rc == 0
    assert "hello-from-pinclude" in capsys.readouterr().out


def test_main_pinclude_missing_file(tmp_path, capsys):
    src = tmp_path / "top.vpy"
    src.write_text(
        "module top;\n"
        "//; self.pinclude('nope.py')\n"
        "endmodule\n"
    )
    rc = main([str(src)])
    assert rc == 1
    assert "error processing" in capsys.readouterr().err


def test_output_comment_parses_block_pair(tmp_path, capsys):
    """``--output-comment '/*,*/'`` parses to ``("/*", "*/")`` and rc==0."""
    src = _write_basic_module(tmp_path)
    # Verify the flag is accepted (unknown flag would SystemExit with rc=2).
    rc = main(["--output-comment", "/*,*/", str(src)])
    assert rc == 0
    # Also verify the type converter produces the expected tuple.
    from genesispy.cli import _output_comment_arg
    assert _output_comment_arg("/*,*/") == ("/*", "*/")


def test_output_comment_inherits_source_comment(tmp_path, capsys):
    """Omitting ``--output-comment`` makes the emitted banner use ``--source-comment``."""
    src = tmp_path / "m.vpy"
    src.write_text("module m;\n  wire w;\nendmodule\n")
    rc = main(["--source-comment", "#", str(src)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "# Genesis-Py generated module:" in out
    assert "// Genesis-Py" not in out


# Review 11 #152 -- _build_class_from_vpy must reject names that aren't valid identifiers.
def test_build_class_from_vpy_rejects_unsafe_name(tmp_path):
    """A stem with `-` or a leading digit must surface as ValueError, not SyntaxError."""
    from genesispy.gvpy_cli import _build_class_from_vpy

    vpy = tmp_path / "src.vpy"
    vpy.write_text("")
    with pytest.raises(ValueError):
        _build_class_from_vpy("foo-bar", str(vpy))
    with pytest.raises(ValueError):
        _build_class_from_vpy("1leading", str(vpy))


# Review 15 #37 -- .gvpy input must follow .vpy's output extension.
def test_build_class_from_vpy_gvpy_inherits_vpy_suffix(tmp_path):
    """A ``.gvpy`` input file must emit using whatever ``.vpy`` is mapped
    to (e.g. ``.sv`` under ``--extension .vpy=.sv``), not the hardcoded
    ``.v`` fallback. Mixing ``.vpy`` and ``.gvpy`` inputs in one run
    should produce consistent output suffixes.
    """
    from genesispy.gvpy_cli import _build_class_from_vpy

    src = tmp_path / "foo.gvpy"
    src.write_text("")
    cls_default = _build_class_from_vpy(
        "foo", str(src), {".vpy": ".v", ".svpy": ".sv"}
    )
    assert cls_default._OUTPUT_SUFFIX == ".v"
    cls_sv = _build_class_from_vpy(
        "foo", str(src), {".vpy": ".sv", ".svpy": ".sv"}
    )
    assert cls_sv._OUTPUT_SUFFIX == ".sv"


def test_main_comment_deprecated_alias_names_gvpy(tmp_path, capsys, monkeypatch):
    """``--comment`` deprecation warning must name 'gvpy', not 'genesispy'."""
    from genesispy.cli import _reset_deprecation_warnings
    _reset_deprecation_warnings()
    monkeypatch.setattr(sys, "argv", ["gvpy"])
    src = tmp_path / "m.vpy"
    src.write_text("module m;\n  wire w;\nendmodule\n")
    rc = main(["--comment", "//", str(src)])
    assert rc == 0
    err = capsys.readouterr().err
    assert "--comment is deprecated" in err
    assert "gvpy" in err
    assert "genesispy" not in err


# Doc-review E3 -- bin/gvpy runs `python -m genesispy.gvpy_cli`, so deriving
# the program name from sys.argv[0] printed "gvpy_cli.py" in --help and in
# every deprecation/error message.
def test_help_uses_the_console_script_name(capsys, monkeypatch):
    """--help must name the program `gvpy`, whatever sys.argv[0] holds."""
    monkeypatch.setattr(sys, "argv", ["/some/path/gvpy_cli.py", "--help"])
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    assert out.startswith("usage: gvpy ")
    assert "gvpy_cli.py" not in out


# ---------------------------------------------------------------------------
# --param-footer (guards the second class factory against emitter drift)
# ---------------------------------------------------------------------------

def _write_param_module(tmp_path):
    src = tmp_path / "pm.vpy"
    src.write_text(
        "//; w = parameter('W', 8)\n"
        "module pm;\n"
        "  wire [`w-1`:0] bus;\n"
        "endmodule\n"
    )
    return src


def test_param_footer_appears_in_gvpy_stdout(tmp_path, capsys):
    """gvpy's own class factory must emit the footer too."""
    rc = main(["--param-footer", "-p", "W=16", str(_write_param_module(tmp_path))])
    assert rc == 0
    out = capsys.readouterr().out
    assert "// Genesis-Py resolved parameter provenance" in out
    assert re.search(r"^//\s+W\s+: 16\s+<- command line", out, re.M)


def test_param_footer_absent_by_default(tmp_path, capsys):
    rc = main(["-p", "W=16", str(_write_param_module(tmp_path))])
    assert rc == 0
    assert "resolved parameter provenance" not in capsys.readouterr().out
