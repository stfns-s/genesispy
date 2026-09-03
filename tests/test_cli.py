"""Tests for genesispy.cli."""

from __future__ import annotations

import os

import pytest

from genesispy.cli import _reset_deprecation_warnings, parse_args


@pytest.fixture(autouse=True)
def _reset_warnings():
    """Each test starts with the deprecation-warning guard cleared."""
    _reset_deprecation_warnings()
    yield
    _reset_deprecation_warnings()


def test_defaults():
    ns = parse_args([])
    assert ns.input == []
    assert ns.input_list == []
    assert ns.top is None
    assert ns.synth_top is None
    assert ns.parameter == []
    assert ns.cfg == []
    assert ns.cfg_path == []
    assert ns.src_path == []
    assert ns.inc_path == []
    assert ns.py_path == []
    assert ns.py_import == []
    assert ns.out_type == "both"
    assert ns.product is None
    assert ns.vf_out is None
    assert ns.depend is None
    assert ns.path is None
    # Cluster J1: --log defaults to genesispy.log (lazy-opened; matches Perl).
    assert ns.log == "genesispy.log"
    assert ns.parse_only is False
    assert ns.gen_only is False
    assert ns.no_module_cache is False
    assert ns.gen_raw is False
    assert ns.raw_dir is None
    assert ns.use_tmp is False
    assert ns.keep_tmp is False
    assert ns.clean is False
    assert ns.debug == 0
    assert ns.out_dir is None
    assert ns.synth_dir is None
    assert ns.verif_dir is None
    assert ns.stdout is False
    assert ns.j2 is False


def test_stdout_flag():
    ns = parse_args(["--stdout"])
    assert ns.stdout is True


def test_j2_flag():
    ns = parse_args(["--j2"])
    assert ns.j2 is True


def test_j2_short_flag():
    ns = parse_args(["-j2"])
    assert ns.j2 is True


def test_input_multi():
    ns = parse_args(["--input", "a.vpy", "--input", "b.vpy"])
    assert ns.input == ["a.vpy", "b.vpy"]


def test_input_short_flag():
    ns = parse_args(["-i", "a.vpy", "-i", "b.vpy"])
    assert ns.input == ["a.vpy", "b.vpy"]


def test_short_flag_json_cfg():
    ns = parse_args(["-t", "my_top", "-j", "in.json"])
    assert ns.top == "my_top"
    assert ns.json_cfg == "in.json"


def test_xml_flag_rejected():
    """--xml / --xmlout were removed; legacy XML must be converted via
    genesispy-xml2json before being passed in."""
    with pytest.raises(SystemExit):
        parse_args(["--xml", "in.xml"])
    with pytest.raises(SystemExit):
        parse_args(["--xmlout", "out.xml"])


def test_parameter_accumulates():
    ns = parse_args(
        ["--parameter", "WIDTH=8", "--parameter", "DEPTH=16", "-p", "X=1"]
    )
    assert ns.parameter == ["WIDTH=8", "DEPTH=16", "X=1"]


def test_cfg_multi():
    ns = parse_args(["--cfg", "x.cfg", "--cfg", "y.cfg"])
    assert ns.cfg == ["x.cfg", "y.cfg"]


def test_cfg_alias_py_cfg():
    # --py-cfg is a peer spelling of --cfg; no deprecation warning, same dest.
    ns = parse_args(["--py-cfg", "x.cfg", "--cfg", "y.cfg"])
    assert ns.cfg == ["x.cfg", "y.cfg"]


def test_paths():
    ns = parse_args(
        ["--src-path", "src1", "--src-path", "src2", "--inc-path", "inc1"]
    )
    assert ns.src_path == ["src1", "src2"]
    assert ns.inc_path == ["inc1"]


def test_clean_flag():
    ns = parse_args(["--clean"])
    assert ns.clean is True


def test_debug_int():
    ns = parse_args(["--debug", "3"])
    assert ns.debug == 3


def test_debug_short_flag():
    ns = parse_args(["-d", "5"])
    assert ns.debug == 5


def test_out_dir():
    ns = parse_args(["--out-dir", "build/foo"])
    assert ns.out_dir == "build/foo"


@pytest.mark.parametrize("p", ["synth", "verif", "both"])
def test_out_type_choices(p):
    ns = parse_args(["--out-type", p])
    assert ns.out_type == p


def test_out_type_invalid():
    with pytest.raises(SystemExit):
        parse_args(["--out-type", "nope"])


def test_product_takes_filename():
    ns = parse_args(["--product", "build/manifest"])
    assert ns.product == "build/manifest"


def test_vf_out_takes_filename():
    ns = parse_args(["--vf-out", "build/manifest"])
    assert ns.vf_out == "build/manifest"


def test_keep_tmp_implies_use_tmp():
    ns = parse_args(["--keep-tmp"])
    assert ns.use_tmp is True
    assert ns.keep_tmp is True


def test_parse_gen_mutually_exclusive():
    with pytest.raises(SystemExit):
        parse_args(["--parse-only", "--gen-only"])


def test_phase_flags():
    ns = parse_args(["--parse-only"])
    assert ns.parse_only is True
    assert ns.gen_only is False


def test_no_module_cache_flag():
    ns = parse_args(["--no-module-cache"])
    assert ns.no_module_cache is True


def test_gen_raw_flag():
    ns = parse_args(["--gen-raw"])
    assert ns.gen_raw is True


def test_raw_dir_override():
    ns = parse_args(["--raw-dir", "/tmp/some_raw"])
    assert ns.raw_dir == "/tmp/some_raw"


def test_raw_dir_mutex_use_tmp():
    with pytest.raises(SystemExit):
        parse_args(["--raw-dir", "/tmp/x", "--use-tmp"])


def test_raw_dir_mutex_keep_tmp():
    with pytest.raises(SystemExit):
        parse_args(["--raw-dir", "/tmp/x", "--keep-tmp"])


def test_synth_top():
    ns = parse_args(["--synth-top", "des_top"])
    assert ns.synth_top == "des_top"


def test_depend_path_log():
    ns = parse_args(["--depend", "d.dep", "--path", "p.list", "--log", "l.log"])
    assert ns.depend == "d.dep"
    assert ns.path == "p.list"
    assert ns.log == "l.log"


def test_cfg_path_multi():
    ns = parse_args(["--cfg-path", "cfg1", "--cfg-path", "cfg2"])
    assert ns.cfg_path == ["cfg1", "cfg2"]


def test_py_path_py_import():
    ns = parse_args(["--py-path", "lib", "--py-import", "myhelper"])
    assert ns.py_path == ["lib"]
    assert ns.py_import == ["myhelper"]


def test_unq_style_default():
    ns = parse_args([])
    assert ns.unq_style == "numeric"


@pytest.mark.parametrize("style", ["numeric", "param"])
def test_unq_style_choices(style):
    ns = parse_args(["--unq-style", style])
    assert ns.unq_style == style


def test_unq_style_invalid():
    with pytest.raises(SystemExit):
        parse_args(["--unq-style", "bogus"])


def test_help_exits():
    with pytest.raises(SystemExit) as exc:
        parse_args(["-h"])
    assert exc.value.code == 0


def test_help_long_exits():
    with pytest.raises(SystemExit) as exc:
        parse_args(["--help"])
    assert exc.value.code == 0


def test_version_exits():
    with pytest.raises(SystemExit) as exc:
        parse_args(["--version"])
    assert exc.value.code == 0


def test_inputlist_basic(tmp_path):
    lf = tmp_path / "files.list"
    lf.write_text("a.vpy\nb.vpy\n")
    ns = parse_args(["--input-list", str(lf)])
    assert ns.input == ["a.vpy", "b.vpy"]


def test_inputlist_short_flag(tmp_path):
    lf = tmp_path / "x.list"
    lf.write_text("a.vpy\n")
    ns = parse_args(["-f", str(lf)])
    assert ns.input == ["a.vpy"]


def test_inputlist_interleave_with_input(tmp_path):
    lf = tmp_path / "x.list"
    lf.write_text("c.vpy\n")
    ns = parse_args(["-i", "a.vpy", "--input-list", str(lf), "-i", "b.vpy"])
    # -i entries first (in argparse order), then listfile contents.
    assert ns.input == ["a.vpy", "b.vpy", "c.vpy"]


def test_inputlist_inline_comment(tmp_path):
    lf = tmp_path / "x.list"
    lf.write_text("a.vpy  # a comment\n# full line\n\nb.vpy\n")
    ns = parse_args(["--input-list", str(lf)])
    assert ns.input == ["a.vpy", "b.vpy"]


def test_inputlist_hash_in_filename(tmp_path):
    # `#` only counts as a comment marker when at column 0 or preceded
    # by whitespace. `foo#bar` is a literal filename.
    lf = tmp_path / "x.list"
    lf.write_text("foo#bar.vpy\nbaz.vpy #comment\n  #indented full-line\n")
    ns = parse_args(["--input-list", str(lf)])
    assert ns.input == ["foo#bar.vpy", "baz.vpy"]


def test_inputlist_directives(tmp_path):
    lf = tmp_path / "x.list"
    lf.write_text(
        "--src-path src1\n"
        "--inc-path inc1\n"
        "--input a.vpy b.vpy\n"
    )
    ns = parse_args(["--input-list", str(lf)])
    assert ns.input == ["a.vpy", "b.vpy"]
    assert ns.src_path == ["src1"]
    assert ns.inc_path == ["inc1"]


def test_inputlist_recursive(tmp_path):
    inner = tmp_path / "inner.list"
    inner.write_text("inner.vpy\n")
    outer = tmp_path / "outer.list"
    outer.write_text(f"--input-list {inner}\nouter.vpy\n")
    ns = parse_args(["--input-list", str(outer)])
    assert ns.input == ["inner.vpy", "outer.vpy"]


def test_inputlist_cycle(tmp_path):
    a = tmp_path / "a.list"
    b = tmp_path / "b.list"
    a.write_text(f"--input-list {b}\n")
    b.write_text(f"--input-list {a}\n")
    with pytest.raises(SystemExit):
        parse_args(["--input-list", str(a)])


def test_inputlist_symlink_cycle(tmp_path):
    # Cycle detection must use realpath; abspath bypasses symlink loops.
    real = tmp_path / "real.list"
    link = tmp_path / "link.list"
    real.write_text(f"--input-list {link}\n")
    os.symlink(real, link)
    with pytest.raises(SystemExit):
        parse_args(["--input-list", str(link)])


def test_inputlist_diamond(tmp_path):
    # A includes B and C; B and C both include D; D lists d.vpy.
    # This is a diamond, not a cycle — must succeed with d.vpy exactly once.
    d_vpy = tmp_path / "d.vpy"
    d_vpy.write_text("")
    d = tmp_path / "d.list"
    d.write_text(f"{d_vpy}\n")
    b = tmp_path / "b.list"
    b.write_text(f"--input-list {d}\n")
    c = tmp_path / "c.list"
    c.write_text(f"--input-list {d}\n")
    a = tmp_path / "a.list"
    a.write_text(f"--input-list {b}\n--input-list {c}\n")
    ns = parse_args(["--input-list", str(a)])
    assert ns.input.count(str(d_vpy)) == 1


def test_inputlist_repeated_sibling(tmp_path):
    # The same sub-list referenced twice from one listfile is skipped silently.
    d_vpy = tmp_path / "d.vpy"
    d_vpy.write_text("")
    d = tmp_path / "d.list"
    d.write_text(f"{d_vpy}\n")
    a = tmp_path / "a.list"
    a.write_text(f"--input-list {d}\n--input-list {d}\n")
    ns = parse_args(["--input-list", str(a)])
    assert ns.input.count(str(d_vpy)) == 1


def test_inputlist_missing_file(tmp_path):
    with pytest.raises(SystemExit):
        parse_args(["--input-list", str(tmp_path / "does_not_exist.list")])


def test_inputlist_empty_warns(tmp_path, capsys):
    lf = tmp_path / "empty.list"
    lf.write_text("# only a comment\n\n")
    parse_args(["--input-list", str(lf)])
    captured = capsys.readouterr()
    assert "contributed no inputs" in captured.err


def test_inputlist_empty_skipped_no_warn(tmp_path, capsys):
    # An empty listfile referenced a second time (already processed) must NOT
    # trigger the empty-list warning for the skipped occurrence.
    lf = tmp_path / "empty.list"
    lf.write_text("# only a comment\n\n")
    # Pass the same empty listfile twice via --input-list.
    parse_args(["--input-list", str(lf), "--input-list", str(lf)])
    captured = capsys.readouterr()
    # Warning fires exactly once for the first occurrence; the skip path
    # must not produce a second occurrence.
    assert captured.err.count("contributed no inputs") == 1


def test_inputlist_duplicate_warns(tmp_path, capsys):
    lf = tmp_path / "dup.list"
    lf.write_text("a.vpy\na.vpy\n")
    ns = parse_args(["--input-list", str(lf)])
    assert ns.input == ["a.vpy", "a.vpy"]  # kept
    captured = capsys.readouterr()
    assert "duplicate path" in captured.err


def test_inputlist_multiple(tmp_path):
    a = tmp_path / "a.list"
    b = tmp_path / "b.list"
    a.write_text("from_a.vpy\n")
    b.write_text("from_b.vpy\n")
    ns = parse_args(["--input-list", str(a), "--input-list", str(b)])
    assert ns.input == ["from_a.vpy", "from_b.vpy"]


def test_inputlist_absolute_path(tmp_path):
    lf = tmp_path / "abs.list"
    lf.write_text("/tmp/abs.vpy\nrel.vpy\n")
    ns = parse_args(["--input-list", str(lf)])
    assert ns.input == ["/tmp/abs.vpy", "rel.vpy"]


@pytest.mark.parametrize(
    "rejected",
    # Single-dash long flags must not parse (argparse-style; we use GNU long flags).
    ["-clean", "-version", "-help", "-cfg", "-src-path", "-inc-path",
     "-out-dir", "-unq-style", "-out-type", "-xmlout", "-json-out"],
)
def test_single_dash_long_flags_rejected(rejected):
    """Single-dash long flags must not parse."""
    with pytest.raises(SystemExit):
        parse_args([rejected, "x"])


# --------------------------------------------------------------------------
# Inline-comment stripping in listfile lines
# --------------------------------------------------------------------------
def test_strip_inline_comment_quote_aware():
    from genesispy.cli import _strip_inline_comment as strip

    # Bare-ish cases preserved from the prior implementation.
    assert strip("foo #bar") == "foo "
    assert strip("foo#bar") == "foo#bar"
    assert strip("# whole line") == ""
    assert strip("plain") == "plain"

    # Quote-aware: a '#' inside double or single quotes is not a comment.
    assert strip('"foo bar#baz"') == '"foo bar#baz"'
    assert strip("'foo bar#baz'") == "'foo bar#baz'"
    assert strip('--input "/path with #/file" # trailing') == (
        '--input "/path with #/file" '
    )


def test_json_out_help_does_not_reference_nonexistent_gen_flag():
    """``--json-out``'s help string must not cite a nonexistent ``--gen``."""
    from genesispy.cli import _build_parser

    parser = _build_parser()
    # Pick the primary action (the one whose help isn't suppressed).
    primary = next(
        a for a in parser._actions
        if a.dest == "json_out" and a.help and a.help != "==SUPPRESS=="
    )
    help_text = primary.help or ""
    assert "--gen" not in help_text, (
        f"--json-out help references nonexistent flag --gen: {help_text!r}"
    )
    # Positive: should reference the real switch it errors against.
    assert "parse-only" in help_text.lower(), (
        f"--json-out help should reference --parse-only: {help_text!r}"
    )


# ---------------------------------------------------------------------------
# --source-comment validation
# ---------------------------------------------------------------------------

def test_source_comment_default_is_double_slash():
    ns = parse_args([])
    assert ns.source_comment == "//"


def test_source_comment_custom_accepted():
    ns = parse_args(["--source-comment", "#"])
    assert ns.source_comment == "#"


def test_source_comment_empty_rejected():
    # Empty prefix would collapse the directive sentinel to bare ';' and
    # emit banner lines without any comment marker.
    with pytest.raises(SystemExit):
        parse_args(["--source-comment", ""])


def test_source_comment_whitespace_only_rejected():
    with pytest.raises(SystemExit):
        parse_args(["--source-comment", "   "])


def test_deprecated_comment_alias_works_and_warns(capsys):
    ns = parse_args(["--comment", "#"])
    captured = capsys.readouterr()
    assert ns.source_comment == "#"
    assert "--comment is deprecated" in captured.err
    assert "--source-comment" in captured.err


def test_main_comment_flag_rewrites_directive_and_banner(tmp_path, capsys):
    """End-to-end: --comment '#' makes the parser recognise '#;' directives
    and stamps '#' on the auto-generated banner. Mirror of the gvpy test
    test_gvpy_cli.test_main_comment_flag_rewrites_directive_and_banner.
    """
    from genesispy.cli import main

    src = tmp_path / "c.vpy"
    src.write_text(
        "module c;\n"
        "#; for i in range(2):\n"
        "    wire w_`i`;\n"
        "#; # endfor\n"
        "endmodule\n"
    )
    rc = main([
        "-i", str(src), "-t", "c", "--source-comment", "#", "--stdout",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "wire w_0;" in out
    assert "wire w_1;" in out
    assert "# Genesis-Py generated module:" in out
    assert "// Genesis-Py" not in out
    assert "#; for" not in out


# ---------------------------------------------------------------------------
# --output-comment
# ---------------------------------------------------------------------------

def test_output_comment_unset_defaults_to_none():
    ns = parse_args([])
    assert ns.output_comment is None


def test_output_comment_line_form():
    ns = parse_args(["--output-comment", "@"])
    assert ns.output_comment == "@"


def test_output_comment_block_form():
    ns = parse_args(["--output-comment", "/*,*/"])
    assert ns.output_comment == ("/*", "*/")


def test_output_comment_empty_rejected():
    with pytest.raises(SystemExit):
        parse_args(["--output-comment", ""])


def test_output_comment_empty_open_rejected():
    with pytest.raises(SystemExit):
        parse_args(["--output-comment", ",*/"])


def test_output_comment_empty_close_rejected():
    with pytest.raises(SystemExit):
        parse_args(["--output-comment", "/*,"])


def test_output_comment_manager_resolution_inherits_source_comment():
    from genesispy.manager import _resolve_output_comment
    ns = parse_args(["--source-comment", "#"])
    assert _resolve_output_comment(ns) == "#"


def test_output_comment_manager_resolution_uses_explicit_value():
    from genesispy.manager import _resolve_output_comment
    ns = parse_args(["--source-comment", "#", "--output-comment", "/*,*/"])
    assert _resolve_output_comment(ns) == ("/*", "*/")


# ---------------------------------------------------------------------------
# Deprecated-alias compatibility
# ---------------------------------------------------------------------------
# Each old long-form spelling is preserved as a hidden alias that emits a
# one-time deprecation warning to stderr and populates the same Namespace
# attribute as the new spelling. The aliases are absent from --help.

@pytest.mark.parametrize(
    "old, new, attr, value",
    [
        # --inputlist tested separately because it reads a real file.
        ("--synthtop", "--synth-top", "synth_top", "top.foo"),
        ("--json", "-j/--json-cfg", "json_cfg", "x.json"),
        ("--cfgpath", "--cfg-path", "cfg_path", "cfg1"),
        ("--srcpath", "--src-path", "src_path", "src1"),
        ("--includepath", "--inc-path", "inc_path", "inc1"),
        ("--pythonpath", "--py-path", "py_path", "lib"),
        ("--pymodule", "--py-import", "py_import", "myhelper"),
        ("--flavor", "--out-type", "out_type", "synth"),
        ("--jsonout", "--json-out", "json_out", "out.json"),
        ("--outputdir", "--out-dir", "out_dir", "build"),
        ("--pathfile", "--path", "path", "p.list"),
        ("--unqstyle", "--unq-style", "unq_style", "param"),
    ],
)
def test_deprecated_long_alias_works_and_warns(old, new, attr, value, capsys):
    ns = parse_args([old, value])
    captured = capsys.readouterr()
    # New attribute populated.
    assert getattr(ns, attr) == value or getattr(ns, attr) == [value]
    # Warning fired naming the new spelling.
    assert old in captured.err
    assert new in captured.err
    assert "deprecated" in captured.err


def test_deprecated_short_l_alias_works_and_warns(tmp_path, capsys):
    lf = tmp_path / "x.list"
    lf.write_text("a.vpy\n")
    ns = parse_args(["-l", str(lf)])
    captured = capsys.readouterr()
    assert ns.input == ["a.vpy"]
    assert "-l is deprecated" in captured.err
    assert "-f/--input-list" in captured.err


def test_deprecated_inputlist_alias_works_and_warns(tmp_path, capsys):
    lf = tmp_path / "x.list"
    lf.write_text("a.vpy\n")
    ns = parse_args(["--inputlist", str(lf)])
    captured = capsys.readouterr()
    assert ns.input == ["a.vpy"]
    assert "--inputlist is deprecated" in captured.err
    assert "-f/--input-list" in captured.err


def test_deprecated_generate_only_works_and_warns(capsys):
    ns = parse_args(["--generate-only"])
    captured = capsys.readouterr()
    assert ns.gen_only is True
    assert "--generate-only is deprecated" in captured.err
    assert "--gen-only" in captured.err


def test_deprecated_systemverilog_works_and_warns(capsys):
    ns = parse_args(["--systemverilog"])
    captured = capsys.readouterr()
    assert ns.system_verilog is True
    assert "--systemverilog is deprecated" in captured.err
    assert "-sv/--system-verilog" in captured.err


def test_deprecation_warns_once_per_flag(capsys):
    # Repeating the same deprecated flag must warn exactly once.
    parse_args(["--srcpath", "A", "--srcpath", "B"])
    captured = capsys.readouterr()
    assert captured.err.count("--srcpath is deprecated") == 1


def test_new_flag_no_warning(capsys):
    parse_args(["--src-path", "A"])
    captured = capsys.readouterr()
    assert "deprecated" not in captured.err


def test_listfile_deprecated_directives(tmp_path, capsys):
    """Deprecated directive spellings inside an --input-list file still work
    and emit a one-time stderr warning per spelling."""
    lf = tmp_path / "x.list"
    lf.write_text(
        "--srcpath src1\n"
        "--includepath inc1\n"
        "--input a.vpy\n"
    )
    ns = parse_args(["--input-list", str(lf)])
    captured = capsys.readouterr()
    assert ns.input == ["a.vpy"]
    assert ns.src_path == ["src1"]
    assert ns.inc_path == ["inc1"]
    assert "--srcpath is deprecated" in captured.err
    assert "--includepath is deprecated" in captured.err


def test_deprecated_aliases_hidden_from_help():
    """Deprecated aliases must not appear anywhere in --help output."""
    from genesispy.cli import _build_parser

    parser = _build_parser()
    help_text = parser.format_help()
    for hidden in (
        "--inputlist", "--synthtop", "--cfgpath", "--srcpath",
        "--includepath", "--pythonpath", "--pymodule", "--flavor",
        "--jsonout", "--outputdir", "--pathfile", "--unqstyle",
        "--systemverilog", "--generate-only",
    ):
        assert hidden not in help_text, (
            f"deprecated alias {hidden!r} leaked into --help output"
        )


# ---------------------------------------------------------------------------
# --param-footer
# ---------------------------------------------------------------------------

def test_param_footer_defaults_false():
    assert parse_args([]).param_footer is False


def test_param_footer_flag_sets_true():
    assert parse_args(["--param-footer"]).param_footer is True


def test_param_footer_reaches_manager(tmp_path):
    from genesispy.manager import Manager

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        assert Manager(parse_args(["--param-footer"])).param_footer is True
        assert Manager(parse_args([])).param_footer is False
    finally:
        os.chdir(cwd)
