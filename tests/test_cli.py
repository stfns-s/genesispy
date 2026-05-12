"""Tests for genesispy.cli."""

from __future__ import annotations

import os

import pytest

from genesispy.cli import parse_args


def test_defaults():
    ns = parse_args([])
    assert ns.input == []
    assert ns.inputlist == []
    assert ns.top is None
    assert ns.synthtop is None
    assert ns.parameter == []
    assert ns.cfg == []
    assert ns.cfgpath == []
    assert ns.srcpath == []
    assert ns.includepath == []
    assert ns.pythonpath == []
    assert ns.pymodule == []
    assert ns.flavor == "both"
    assert ns.product is None
    assert ns.depend is None
    assert ns.pathfile is None
    assert ns.log is None
    assert ns.parse_only is False
    assert ns.generate_only is False
    assert ns.no_module_cache is False
    assert ns.gen_raw is False
    assert ns.raw_dir is None
    assert ns.use_tmp is False
    assert ns.keep_tmp is False
    assert ns.clean is False
    assert ns.debug == 0
    assert ns.outputdir is None
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


def test_short_flag_json():
    ns = parse_args(["-t", "my_top", "-j", "in.json"])
    assert ns.top == "my_top"
    assert ns.json == "in.json"


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


def test_paths():
    ns = parse_args(
        ["--srcpath", "src1", "--srcpath", "src2", "--includepath", "inc1"]
    )
    assert ns.srcpath == ["src1", "src2"]
    assert ns.includepath == ["inc1"]


def test_clean_flag():
    ns = parse_args(["--clean"])
    assert ns.clean is True


def test_debug_int():
    ns = parse_args(["--debug", "3"])
    assert ns.debug == 3


def test_debug_short_flag():
    ns = parse_args(["-d", "5"])
    assert ns.debug == 5


def test_outputdir():
    ns = parse_args(["--outputdir", "build/foo"])
    assert ns.outputdir == "build/foo"


@pytest.mark.parametrize("p", ["synth", "verif", "both"])
def test_flavor_choices(p):
    ns = parse_args(["--flavor", p])
    assert ns.flavor == p


def test_flavor_invalid():
    with pytest.raises(SystemExit):
        parse_args(["--flavor", "nope"])


def test_product_takes_filename():
    ns = parse_args(["--product", "build/manifest"])
    assert ns.product == "build/manifest"


def test_keep_tmp_implies_use_tmp():
    ns = parse_args(["--keep-tmp"])
    assert ns.use_tmp is True
    assert ns.keep_tmp is True


def test_parse_generate_mutually_exclusive():
    with pytest.raises(SystemExit):
        parse_args(["--parse-only", "--generate-only"])


def test_phase_flags():
    ns = parse_args(["--parse-only"])
    assert ns.parse_only is True
    assert ns.generate_only is False


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


def test_synthtop():
    ns = parse_args(["--synthtop", "des_top"])
    assert ns.synthtop == "des_top"


def test_depend_pathfile_log():
    ns = parse_args(["--depend", "d.dep", "--pathfile", "p.list", "--log", "l.log"])
    assert ns.depend == "d.dep"
    assert ns.pathfile == "p.list"
    assert ns.log == "l.log"


def test_cfgpath_multi():
    ns = parse_args(["--cfgpath", "cfg1", "--cfgpath", "cfg2"])
    assert ns.cfgpath == ["cfg1", "cfg2"]


def test_pythonpath_pymodule():
    ns = parse_args(["--pythonpath", "lib", "--pymodule", "myhelper"])
    assert ns.pythonpath == ["lib"]
    assert ns.pymodule == ["myhelper"]


def test_unqstyle_default():
    ns = parse_args([])
    assert ns.unqstyle == "numeric"


@pytest.mark.parametrize("style", ["numeric", "param"])
def test_unqstyle_choices(style):
    ns = parse_args(["--unqstyle", style])
    assert ns.unqstyle == style


def test_unqstyle_invalid():
    with pytest.raises(SystemExit):
        parse_args(["--unqstyle", "bogus"])


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
    ns = parse_args(["--inputlist", str(lf)])
    assert ns.input == ["a.vpy", "b.vpy"]


def test_inputlist_short_flag(tmp_path):
    lf = tmp_path / "x.list"
    lf.write_text("a.vpy\n")
    ns = parse_args(["-l", str(lf)])
    assert ns.input == ["a.vpy"]


def test_inputlist_interleave_with_input(tmp_path):
    lf = tmp_path / "x.list"
    lf.write_text("c.vpy\n")
    ns = parse_args(["-i", "a.vpy", "--inputlist", str(lf), "-i", "b.vpy"])
    # -i entries first (in argparse order), then listfile contents.
    assert ns.input == ["a.vpy", "b.vpy", "c.vpy"]


def test_inputlist_inline_comment(tmp_path):
    lf = tmp_path / "x.list"
    lf.write_text("a.vpy  # a comment\n# full line\n\nb.vpy\n")
    ns = parse_args(["--inputlist", str(lf)])
    assert ns.input == ["a.vpy", "b.vpy"]


def test_inputlist_hash_in_filename(tmp_path):
    # `#` only counts as a comment marker when at column 0 or preceded
    # by whitespace. `foo#bar` is a literal filename.
    lf = tmp_path / "x.list"
    lf.write_text("foo#bar.vpy\nbaz.vpy #comment\n  #indented full-line\n")
    ns = parse_args(["--inputlist", str(lf)])
    assert ns.input == ["foo#bar.vpy", "baz.vpy"]


def test_inputlist_directives(tmp_path):
    lf = tmp_path / "x.list"
    lf.write_text(
        "--srcpath src1\n"
        "--includepath inc1\n"
        "--input a.vpy b.vpy\n"
    )
    ns = parse_args(["--inputlist", str(lf)])
    assert ns.input == ["a.vpy", "b.vpy"]
    assert ns.srcpath == ["src1"]
    assert ns.includepath == ["inc1"]


def test_inputlist_recursive(tmp_path):
    inner = tmp_path / "inner.list"
    inner.write_text("inner.vpy\n")
    outer = tmp_path / "outer.list"
    outer.write_text(f"--inputlist {inner}\nouter.vpy\n")
    ns = parse_args(["--inputlist", str(outer)])
    assert ns.input == ["inner.vpy", "outer.vpy"]


def test_inputlist_cycle(tmp_path):
    a = tmp_path / "a.list"
    b = tmp_path / "b.list"
    a.write_text(f"--inputlist {b}\n")
    b.write_text(f"--inputlist {a}\n")
    with pytest.raises(SystemExit):
        parse_args(["--inputlist", str(a)])


def test_inputlist_symlink_cycle(tmp_path):
    # Cycle detection must use realpath; abspath bypasses symlink loops.
    real = tmp_path / "real.list"
    link = tmp_path / "link.list"
    real.write_text(f"--inputlist {link}\n")
    os.symlink(real, link)
    with pytest.raises(SystemExit):
        parse_args(["--inputlist", str(link)])


def test_inputlist_missing_file(tmp_path):
    with pytest.raises(SystemExit):
        parse_args(["--inputlist", str(tmp_path / "does_not_exist.list")])


def test_inputlist_empty_warns(tmp_path, capsys):
    lf = tmp_path / "empty.list"
    lf.write_text("# only a comment\n\n")
    parse_args(["--inputlist", str(lf)])
    captured = capsys.readouterr()
    assert "contributed no inputs" in captured.err


def test_inputlist_duplicate_warns(tmp_path, capsys):
    lf = tmp_path / "dup.list"
    lf.write_text("a.vpy\na.vpy\n")
    ns = parse_args(["--inputlist", str(lf)])
    assert ns.input == ["a.vpy", "a.vpy"]  # kept
    captured = capsys.readouterr()
    assert "duplicate path" in captured.err


def test_inputlist_multiple(tmp_path):
    a = tmp_path / "a.list"
    b = tmp_path / "b.list"
    a.write_text("from_a.vpy\n")
    b.write_text("from_b.vpy\n")
    ns = parse_args(["--inputlist", str(a), "--inputlist", str(b)])
    assert ns.input == ["from_a.vpy", "from_b.vpy"]


def test_inputlist_absolute_path(tmp_path):
    lf = tmp_path / "abs.list"
    lf.write_text("/tmp/abs.vpy\nrel.vpy\n")
    ns = parse_args(["--inputlist", str(lf)])
    assert ns.input == ["/tmp/abs.vpy", "rel.vpy"]


@pytest.mark.parametrize(
    "rejected",
    # Flags whose first letter is NOT a short-flag (so argparse can't
    # silently re-parse them as `-X est`, e.g. `-clean` -> `-c lean`).
    ["-clean", "-version", "-help", "-cfg", "-srcpath", "-includepath",
     "-outputdir", "-unqstyle", "-flavor", "-xmlout", "-jsonout"],
)
def test_single_dash_long_flags_rejected(rejected):
    """Genesis2-style single-dash long flags must no longer parse."""
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


# Review 11 #190 -- --jsonout help must not reference a nonexistent --gen flag.
def test_jsonout_help_does_not_reference_nonexistent_gen_flag():
    """`--jsonout`'s help string cites a `--gen` flag that does not exist.

    The actual mutually-exclusive switches are `--parse-only` and
    `--generate-only`; the bare `--gen` is leftover prose. This is
    user-visible drift on `genesispy --help`.
    """
    from genesispy.cli import _build_parser

    parser = _build_parser()
    actions = {a.dest: a for a in parser._actions}
    help_text = (actions["jsonout"].help or "")
    assert "--gen" not in help_text, (
        f"--jsonout help references nonexistent flag --gen: {help_text!r}"
    )
    # Positive: should reference the real switch it errors against.
    assert "parse-only" in help_text.lower(), (
        f"--jsonout help should reference --parse-only: {help_text!r}"
    )


# ---------------------------------------------------------------------------
# --comment validation
# ---------------------------------------------------------------------------

def test_comment_default_is_double_slash():
    ns = parse_args([])
    assert ns.comment == "//"


def test_comment_custom_accepted():
    ns = parse_args(["--comment", "#"])
    assert ns.comment == "#"


def test_comment_empty_rejected():
    # Empty prefix would collapse the directive sentinel to bare ';' and
    # emit banner lines without any comment marker.
    with pytest.raises(SystemExit):
        parse_args(["--comment", ""])


def test_comment_whitespace_only_rejected():
    with pytest.raises(SystemExit):
        parse_args(["--comment", "   "])


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
        "-i", str(src), "-t", "c", "--comment", "#", "--stdout",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "wire w_0;" in out
    assert "wire w_1;" in out
    assert "# Genesis-Py generated module:" in out
    assert "// Genesis-Py" not in out
    assert "#; for" not in out
