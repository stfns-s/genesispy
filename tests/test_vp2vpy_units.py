"""Per-construct unit tests for the Perl -> Python translator.

Each case feeds a Perl snippet through the translator and checks the
emitted Python text contains the expected fragment. We don't assert
byte-for-byte; the translator's whitespace and parenthesization details
are intentionally flexible.

Skipped when ``perl`` + ``PPI`` aren't available
(``module load ramyx/perl/5.42.0/0.1.0`` on the workstations).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from genesispy.tools.vp2vpy import (
    DEFAULT_EXT_MAP,
    FileTranslator,
    Helper,
    WalkCtx,
    _dst_for,
    _resolve_inputs,
    translate_backtick_expr,
    translate_perl_snippet,
)


def _ppi_available() -> bool:
    try:
        r = subprocess.run(
            ["perl", "-MPPI", "-e", "1"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


pytestmark = pytest.mark.skipif(
    not _ppi_available(),
    reason="perl + PPI not on PATH (try `module load ramyx/perl/5.42.0/0.1.0`)",
)


@pytest.fixture(scope="module")
def helper():
    h = Helper()
    h.start()
    yield h
    h.close()


def _xlate_stmt(helper, perl: str) -> str:
    ctx = WalkCtx()
    return "\n".join(translate_perl_snippet(perl, helper, ctx))


def _xlate_expr(helper, perl: str) -> str:
    ctx = WalkCtx()
    return translate_backtick_expr(perl, helper, ctx)


def _xlate_file(helper, source: str) -> str:
    ft = FileTranslator(helper)
    return ft.translate(source).text


# ---------------------------------------------------------------------------
# Variables, scalars, arrays, hashes.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("perl,want", [
    ("my $x = 42;",                       "x = 42"),
    ("my $name = 'foo';",                 "name = 'foo'"),
    ('my $s = "hi $name";',               'f"hi {name}"'),
    ("my @arr = (1, 2, 3);",              "arr = [1, 2, 3]"),
    ("my $h = $obj->{key};",              'h = obj["key"]'),
    ("$x++;",                             "x += 1"),
    ("$x--;",                             "x -= 1"),
    ("$x += 5;",                          "x += 5"),
    ("push @arr, 4;",                     "arr.append(4)"),
    ("push @arr, 1, 2;",                  "arr.extend([1, 2])"),
    ("unshift @arr, 4;",                  "arr.insert(0, 4)"),
    ("unshift @arr, 1, 2;",               "arr[0:0] = [1, 2]"),
    ("pop @arr;",                         "arr.pop()"),
])
def test_assignments_and_array_ops(helper, perl, want):
    got = _xlate_stmt(helper, perl)
    assert want in got, f"want {want!r} in {got!r}"


# ---------------------------------------------------------------------------
# Operators.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("perl,want", [
    ("$x == $y",      "x == y"),
    ("$x eq $y",      "x == y"),
    ("$x ne $y",      "x != y"),
    ("$x && $y",      "x and y"),
    ("$x || $y",      "x or y"),
    ("$x . $y",       "x + y"),
    ("$x ** 2",       "x ** 2"),
])
def test_operators(helper, perl, want):
    got = _xlate_expr(helper, perl)
    assert want in got, f"want {want!r} in {got!r}"


# ---------------------------------------------------------------------------
# Control flow as full lines (using the file translator so block-stack
# tracking is exercised).
# ---------------------------------------------------------------------------

def test_c_style_for(helper):
    out = _xlate_file(helper, "//; for (my $i = 0; $i < 4; $i++) {\nbody\n//; }\n")
    assert "for i in range(0, 4):" in out
    assert "# endfor" in out


def test_c_style_for_with_le(helper):
    out = _xlate_file(helper, "//; for (my $i = 0; $i <= 3; $i++) {\nbody\n//; }\n")
    assert "for i in range(0, (3) + 1):" in out


def test_foreach(helper):
    out = _xlate_file(helper, "//; foreach my $x (@arr) {\nbody\n//; }\n")
    assert "for x in arr:" in out
    assert "# endfor" in out


def test_foreach_range_with_arithmetic_rhs(helper):
    # Perl `..` binds looser than arithmetic: `0..$N-1` means `0..($N-1)`.
    # Wrong (pre-fix): `range(0, (N) + 1) - 1`  (stray subtraction outside call)
    # Correct: the full `N - 1` expression is the upper bound inside range().
    out = _xlate_file(helper, "//; foreach my $i (0..$N-1) {\nbody\n//; }\n")
    assert "range(0, (N - 1) + 1)" in out


def test_foreach_range_simple_regression(helper):
    # `1..$N` — no arithmetic on rhs; must still work after the precedence fix.
    out = _xlate_file(helper, "//; foreach my $i (1..$N) {\nbody\n//; }\n")
    assert "range(1, (N) + 1)" in out


def test_foreach_range_with_arithmetic_rhs_add(helper):
    # `0..$N+2` — arithmetic on rhs, addition variant.
    out = _xlate_file(helper, "//; foreach my $i (0..$N+2) {\nbody\n//; }\n")
    assert "range(0, (N + 2) + 1)" in out


def test_while(helper):
    out = _xlate_file(helper, "//; while ($i < 10) {\nbody\n//; }\n")
    assert "while i < 10:" in out
    assert "# endwhile" in out


def test_if_elsif_else(helper):
    out = _xlate_file(helper,
        "//; if ($x > 0) {\nA\n//; } elsif ($x < 0) {\nB\n//; } else {\nC\n//; }\n")
    assert "if x > 0:" in out
    assert "elif x < 0:" in out
    assert "else:" in out
    assert "# endif" in out


def test_unless(helper):
    out = _xlate_file(helper, "//; unless ($x) {\nbody\n//; }\n")
    assert "if not (x):" in out


def test_postfix_if(helper):
    got = _xlate_stmt(helper, "print 'hi' if $debug;")
    assert "if debug:" in got


# ---------------------------------------------------------------------------
# Regex.
# ---------------------------------------------------------------------------

def test_regex_match(helper):
    got = _xlate_stmt(helper, 'if ($s =~ m/foo/i) { 1; }')
    assert "re.search('foo'" in got
    assert "re.I" in got


def test_regex_negative_match(helper):
    got = _xlate_stmt(helper, 'if ($s !~ /foo/) { 1; }')
    assert "re.search('foo'" in got
    assert "is None" in got


def test_regex_quote_in_pattern(helper):
    # Pattern containing a double-quote: /^"/ must yield compilable Python.
    got = _xlate_expr(helper, '$s =~ /^"/')
    assert "re.search" in got
    compile(got, "<t>", "eval")


def test_regex_digit_pattern_regression(helper):
    # \\d+ must survive repr and still match digits.
    got = _xlate_expr(helper, r'$s =~ /\d+/')
    assert "re.search" in got
    compile(got, "<t>", "eval")
    assert "\\d" in got


def test_regex_not_match_compiles(helper):
    # !~ branch must also yield compilable Python.
    got = _xlate_expr(helper, '$s !~ /^"/')
    assert "re.search" in got
    assert "is None" in got
    compile(got, "<t>", "eval")


# ---------------------------------------------------------------------------
# Builtins.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("perl,want", [
    ("scalar(@arr)",          "len(arr)"),
    ("length($s)",            "len(s)"),
    ("defined $x",            "(x is not None)"),
    ("sprintf('%02d', $i)",   "('%02d' % (i,))"),
    ('join(",", @items)',     ".join(["),  # both '(",")' and "(',')" acceptable
])
def test_builtins(helper, perl, want):
    got = _xlate_expr(helper, perl)
    assert want in got, f"want {want!r} in {got!r}"


# ---------------------------------------------------------------------------
# Genesis2 user API.
# ---------------------------------------------------------------------------

def test_parameter_call(helper):
    # Perl matches kwarg names case-insensitively, so both ``name`` and
    # ``NAME`` map to ``name=``; ``val`` -> ``default=``; ``doc`` -> ``doc=``.
    got = _xlate_stmt(helper,
        "my $n = parameter(name => 'N', val => 8, doc => 'width');")
    assert "parameter(" in got
    assert "name='N'" in got
    assert "default=8" in got, got


def test_generate_call(helper):
    got = _xlate_stmt(helper,
        "my $sub = generate('Foo', 'u_sub', WIDTH => $w);")
    assert "generate(" in got
    assert "WIDTH=w" in got


def test_parameter_uppercase_kwargs_normalised(helper):
    # Genesis2 idiom: NAME/VAL/DOC. The translator maps these to genesispy's
    # parameter() kwargs (name=, default=, doc=).
    got = _xlate_stmt(helper,
        "my $n = parameter(NAME => 'N', VAL => 8, DOC => 'width');")
    assert "name='N'" in got, got
    assert "default=8" in got, got
    assert "doc='width'" in got, got


def test_generate_base_arbitrary_kwargs_pass_through(helper):
    # Sub-instance overrides use user-defined param names (case-sensitive).
    # The kwarg map MUST NOT rewrite them.
    got = _xlate_stmt(helper,
        "my $c = generate_base('foo', 'u_foo', FOO_BAR => 8, NAME => 'x');")
    assert "FOO_BAR=8" in got, got
    # 'NAME' is not a genesispy kwarg of generate_base -- pass through verbatim.
    assert "NAME='x'" in got, got


def test_method_call_with_fat_comma(helper):
    # Genesis2 shortcut: define_param(NAME => VAL) -> positional (Name, Val).
    # genesispy's define_param signature is (name, default, ...).
    got = _xlate_stmt(helper,
        "my $c = $self->define_param('CFG_BUS_WIDTH' => 32);")
    # Perl define_param returns the value; the closest genesispy entry-point
    # is self.parameter() (self.define_param() returns None).
    assert "self.parameter(" in got, got
    assert "'CFG_BUS_WIDTH', 32" in got, got


def test_self_error(helper):
    got = _xlate_stmt(helper, '$self->error("nope");')
    assert "_vp2vpy_error(" in got


def test_arrow_chain(helper):
    got = _xlate_expr(helper, "$obj->{key}->[0]")
    assert 'obj["key"][0]' in got


# ---------------------------------------------------------------------------
# Additional Genesis2 API rewrites (clone/unique/emit/synonym).
# ---------------------------------------------------------------------------

def test_clone_inst_call(helper):
    got = _xlate_stmt(helper, "$self->clone_inst('u_src', 'u_dst');")
    assert "self.clone_inst('u_src', 'u_dst')" in got, got


def test_unique_inst_call_with_overrides(helper):
    got = _xlate_stmt(helper,
        "$self->unique_inst('Mod', 'u_inst', WIDTH => 8, DEPTH => 4);")
    assert "self.unique_inst(" in got
    assert "'Mod'" in got and "'u_inst'" in got
    assert "WIDTH=8" in got
    assert "DEPTH=4" in got


def test_emit_call(helper):
    got = _xlate_stmt(helper, "$self->emit('assign x = y;');")
    assert "self.emit(" in got
    assert "'assign x = y;'" in got


def test_synonym_call(helper):
    got = _xlate_stmt(helper, "$self->synonym('alias_name');")
    assert "self.synonym('alias_name')" in got, got


# ---------------------------------------------------------------------------
# POSIX math.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("perl,want", [
    ("POSIX::ceil($x)",  "math.ceil(x)"),
    ("POSIX::floor($x)", "math.floor(x)"),
    ("POSIX::log($x)",   "math.log(x)"),
    ("POSIX::sqrt($x)",  "math.sqrt(x)"),
])
def test_posix_math(helper, perl, want):
    got = _xlate_expr(helper, perl)
    assert want in got, f"want {want!r} in {got!r}"


# ---------------------------------------------------------------------------
# my-list unpacking and postfix unless.
# ---------------------------------------------------------------------------

def test_my_list_unpack(helper):
    got = _xlate_stmt(helper, "my ($a, $b) = (1, 2);")
    # Accept either tuple-LHS or bare-LHS forms.
    assert "a, b = (1, 2)" in got or "a, b = 1, 2" in got or "(a, b) = (1, 2)" in got, got


def test_postfix_unless(helper):
    got = _xlate_stmt(helper, "print 'hi' unless $debug;")
    assert "if not" in got and "debug" in got, got


# ---------------------------------------------------------------------------
# Backtick expressions.
# ---------------------------------------------------------------------------

def test_backtick_simple_var(helper):
    out = _xlate_file(helper, "wire w`$x`;\n")
    assert "wire w`x`;" in out


def test_backtick_arrow_method(helper):
    out = _xlate_file(helper, "`$csa->instantiate()` ();\n")
    assert "`csa.instantiate()`" in out


@pytest.mark.parametrize("verilog,want", [
    ("`timescale 1ns/1ps\n",      "\\`timescale 1ns/1ps"),
    ("`define FOO 1\n",           "\\`define FOO 1"),
    ("`include \"foo.vh\"\n",     "\\`include \"foo.vh\""),
    ("  `resetall\n",             "\\`resetall"),
])
def test_verilog_directive_escaped(helper, verilog, want):
    out = _xlate_file(helper, verilog)
    assert want in out, f"want {want!r} in {out!r}"


# ---------------------------------------------------------------------------
# F5: comment-prefixed compiler directives must have their backtick escaped.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("verilog,want", [
    ('// `include "foo.v"\n',   "\\`include"),
    ('wire w; // `FOO\n',       "\\`FOO"),
])
def test_comment_directive_escaped(helper, verilog, want):
    """Backtick-prefixed directives after a // comment must be escaped (F5)."""
    out = _xlate_file(helper, verilog)
    assert want in out, f"want {want!r} in {out!r}"


def test_comment_directive_zero_todos(helper):
    """Escaping a comment-prefixed directive must not produce any TODO markers."""
    result = FileTranslator(helper).translate('// `include "foo.v"\n')
    assert result.todos == [], f"unexpected todos: {result.todos!r}"


def test_comment_paired_backtick_not_escaped(helper):
    """A paired backtick span in a comment must NOT be escaped (regression)."""
    # endmodule // `mname` has an even backtick count: both must remain unescaped.
    out = _xlate_file(helper, "endmodule // `mname`\n")
    # The translated output keeps a backtick span (either `mname` or `mname()`).
    assert "\\`mname\\`" not in out, f"paired span was wrongly escaped:\n{out}"


def test_comment_directive_parse_vpy_roundtrip(helper):
    """Escaped comment directive must survive parse_vpy without ParseError."""
    import os
    import tempfile
    from genesispy.template.parser import parse_vpy
    ft = FileTranslator(helper)
    result = ft.translate('// `include "foo.v"\n')
    with tempfile.NamedTemporaryFile(suffix=".vpy", mode="w", delete=False) as f:
        f.write(result.text)
        fname = f.name
    try:
        py = parse_vpy(fname)
        compile(py, fname, "exec")
    finally:
        os.unlink(fname)


# ---------------------------------------------------------------------------
# Indent + sentinel placement (the parser's strict rule).
# ---------------------------------------------------------------------------

def test_directive_indent_format(helper):
    out = _xlate_file(helper,
        "//; for (my $i = 0; $i < 4; $i++) {\n"
        "//;   $j = $i;\n"
        "//; }\n")
    # Body line must have exactly 4 leading spaces inside the directive
    # (depth=1 in genesispy's parser).
    assert "//;     j = i" in out  # 1 space after //; + 4 spaces of indent
    assert "//; # endfor" in out


# ---------------------------------------------------------------------------
# Helper pipe framing (review B4): non-ASCII payloads must not deadlock.
# ---------------------------------------------------------------------------

def test_non_ascii_payload_roundtrip():
    """Perl helper framed in characters while Python framed in bytes; any
    multi-byte character wedged both processes. Guarded by a worker-thread
    timeout so a regression fails instead of hanging pytest.
    """
    import concurrent.futures

    h = Helper()
    h.start()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_xlate_stmt, h, 'my $x = "µm — dash";')
            try:
                got = fut.result(timeout=30)
            except concurrent.futures.TimeoutError:
                h.close()  # kills perl -> unblocks the worker thread
                pytest.fail("helper deadlocked on non-ASCII payload (B4)")
    finally:
        h.close()
    assert "µm" in got, f"non-ASCII lost: {got!r}"
    assert "dash" in got
    assert "Âµ" not in got, f"double-encoded response: {got!r}"


# ---------------------------------------------------------------------------
# Ternary ?: (review B5): structural translation to Python conditionals.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("perl,want", [
    ("$c ? $a : $b",             "(a if c else b)"),
    ("$x > 0 ? 'pos' : 'neg'",   "('pos' if x > 0 else 'neg')"),
    # Right-associative chain.
    ("$a ? $b : $c ? $d : $e",   "(b if a else (d if c else e))"),
    # Nesting in the true branch.
    ("$a ? $b ? $c : $d : $e",   "((c if b else d) if a else e)"),
])
def test_ternary_expr(helper, perl, want):
    got = _xlate_expr(helper, perl)
    assert want in got, f"want {want!r} in {got!r}"


@pytest.mark.parametrize("perl,want", [
    ("my $x = $c ? 1 : 2;",                "x = (1 if c else 2)"),
    ("$x = $w ? $w : 0;",                  "x = (w if w else 0)"),
    ("foo($c ? $a : $b, 3);",              "(a if c else b)"),
])
def test_ternary_stmt(helper, perl, want):
    got = _xlate_stmt(helper, perl)
    assert want in got, f"want {want!r} in {got!r}"


def test_ternary_unmatched_falls_back_to_todo(helper):
    # '?' with no ':' -> Unmappable -> TODO passthrough via FileTranslator.
    out = _xlate_file(helper, "//; my $x = $a ? $b;\n")
    assert "TODO vp2vpy" in out


# ---------------------------------------------------------------------------
# B13: backtick-span Unmappable in Verilog body lines (chokepoint tests).
# ---------------------------------------------------------------------------

# "assign x = `m/foo/`;" — m/foo/ reliably raises Unmappable (bare m//).

_BACKTICK_UNMAPPABLE_LINE = "assign x = `m/foo/`;\n"
_BACKTICK_UNMAPPABLE_SOURCE = _BACKTICK_UNMAPPABLE_LINE


def test_verilog_backtick_unmappable_strict_raises(helper):
    """strict=True: translate() raises Unmappable for a backtick-span that cannot be mapped."""
    from genesispy.tools.vp2vpy import Unmappable
    ft = FileTranslator(helper, strict=True)
    with pytest.raises(Unmappable):
        ft.translate(_BACKTICK_UNMAPPABLE_SOURCE)


def test_verilog_backtick_unmappable_non_strict_marker(helper):
    """strict=False: output contains TODO marker, todos list is non-empty."""
    ft = FileTranslator(helper, strict=False)
    result = ft.translate(_BACKTICK_UNMAPPABLE_SOURCE)
    assert "# TODO vp2vpy:" in result.text, (
        f"expected TODO marker in output:\n{result.text}"
    )
    assert result.todos, f"expected todos to be non-empty, got {result.todos!r}"


def test_verilog_backtick_unmappable_non_strict_escaped(helper):
    """strict=False: failed backtick span is escaped so parse_vpy accepts the output."""
    import os
    import tempfile

    from genesispy.template.parser import parse_vpy
    ft = FileTranslator(helper, strict=False)
    result = ft.translate(_BACKTICK_UNMAPPABLE_SOURCE)
    # No unescaped backtick span of the unmappable body survives.
    assert "`m/foo/`" not in result.text, (
        f"unescaped backtick span still in output:\n{result.text}"
    )
    with tempfile.NamedTemporaryFile(suffix=".vpy", mode="w", delete=False) as f:
        f.write(result.text)
        fname = f.name
    try:
        py = parse_vpy(fname)
        compile(py, fname, "exec")
    finally:
        os.unlink(fname)


# ---------------------------------------------------------------------------
# B11: hash-literal fat-comma lists emit dict literals.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("perl,want", [
    ("my %h = (a => 1, b => 2);",   "h = {'a': 1, 'b': 2}"),
    ("my %h = ($k => $v);",         "h = {k: v}"),
])
def test_hash_fat_comma_dict_literal(helper, perl, want):
    got = _xlate_stmt(helper, perl)
    assert want in got, f"want {want!r} in {got!r}"


def test_hash_empty_preserved(helper):
    # Empty hash: keep current output (dict([])).
    got = _xlate_stmt(helper, "my %h = ();")
    assert "h = dict([])" in got, f"unexpected output: {got!r}"


def test_hash_flat_no_fat_comma_preserved(helper):
    # Flat k,v list with no fat-comma: existing dict([...]) path preserved.
    got = _xlate_stmt(helper, "my %h = (a, 1, b, 2);")
    assert "dict([" in got, f"unexpected output: {got!r}"


def test_hash_mixed_list_emits_todo(helper):
    # Mixed: some items with fat-comma, some without -> Unmappable -> TODO marker.
    out = _xlate_file(helper, "//; my %h = (a => 1, 2);\n")
    assert "# TODO vp2vpy:" in out, f"expected TODO marker in:\n{out}"


def test_chokepoint_invariant_directive(helper):
    """Directive-level Unmappable: strict raises ⟺ non-strict emits marker ⟺ todo recorded."""
    from genesispy.tools.vp2vpy import Unmappable
    source = "//; my $x = $a ? $b;\n"   # ternary with no ':' -> Unmappable
    ft_strict = FileTranslator(helper, strict=True)
    with pytest.raises(Unmappable):
        ft_strict.translate(source)
    ft_lax = FileTranslator(helper, strict=False)
    result = ft_lax.translate(source)
    assert "# TODO vp2vpy:" in result.text
    assert result.todos


def test_chokepoint_invariant_verilog_backtick(helper):
    """Verilog-backtick Unmappable: strict raises ⟺ non-strict emits marker ⟺ todo recorded."""
    from genesispy.tools.vp2vpy import Unmappable
    ft_strict = FileTranslator(helper, strict=True)
    with pytest.raises(Unmappable):
        ft_strict.translate(_BACKTICK_UNMAPPABLE_SOURCE)
    ft_lax = FileTranslator(helper, strict=False)
    result = ft_lax.translate(_BACKTICK_UNMAPPABLE_SOURCE)
    assert "# TODO vp2vpy:" in result.text
    assert result.todos


# ---------------------------------------------------------------------------
# exists / delete / chomp (B10, B14).
# ---------------------------------------------------------------------------

def test_exists_bareword_key(helper):
    """exists $h{k} -> ('k' in h), not exists(...)."""
    got = _xlate_expr(helper, "exists $h{k}")
    assert "('k' in h)" in got, f"got: {got!r}"


def test_exists_variable_key(helper):
    """exists $h{$key} -> (key in h)."""
    got = _xlate_expr(helper, "exists $h{$key}")
    assert "(key in h)" in got, f"got: {got!r}"


def test_exists_nontrivial_routes_to_todo(helper):
    """Non-subscript exists arg -> TODO marker, no bare exists( call."""
    # exists($x) is a proxy for any non-subscript argument: it hits
    # Unmappable -> _handle_unmappable -> marker.
    source = "//; my $r = exists($x);\n"
    ft = FileTranslator(helper, strict=False)
    result = ft.translate(source)
    assert "# TODO vp2vpy:" in result.text, f"no marker in:\n{result.text}"
    # No uncommented Python exists( call should survive.
    # Filter out TODO marker lines and the commented-out Perl echo.
    live_lines = [
        ln for ln in result.text.splitlines()
        if "# TODO vp2vpy:" not in ln and "# my $r" not in ln
    ]
    assert not any("exists(" in ln for ln in live_lines), (
        f"bare exists( survived in live output:\n{result.text}"
    )


def test_delete_bareword_key(helper):
    """delete $h{k} -> h.pop('k', None)."""
    got = _xlate_stmt(helper, "delete $h{k};")
    assert "h.pop('k', None)" in got, f"got: {got!r}"


def test_chomp_stmt(helper):
    """chomp $line; -> line = (line).rstrip('\\n')."""
    got = _xlate_stmt(helper, "chomp $line;")
    assert got.startswith("line ="), f"got: {got!r}"
    assert ".rstrip(" in got, f"got: {got!r}"


# ---------------------------------------------------------------------------
# F6: .svp / .svph extension map (pure-path tests; no helper required).
# Note: pytestmark on this module skips without perl+PPI, so these tests
# are also gated by that mark. They exercise no Perl logic.
# ---------------------------------------------------------------------------

def test_default_ext_map_svp():
    """DEFAULT_EXT_MAP includes .svp -> .svpy and .svph -> .svpy."""
    assert DEFAULT_EXT_MAP[".svp"] == ".svpy"
    assert DEFAULT_EXT_MAP[".svph"] == ".svpy"


def test_dst_for_svp_direct():
    """.svp direct argument maps to .svpy output."""
    result = _dst_for(Path("a/foo.svp"), root=None, out=None)
    assert result == Path("a/foo.svpy"), f"got: {result}"


def test_dst_for_svph_direct():
    """.svph direct argument maps to .svpy output."""
    result = _dst_for(Path("a/foo.svph"), root=None, out=None)
    assert result == Path("a/foo.svpy"), f"got: {result}"


def test_dst_for_vp_unchanged():
    """.vp still maps to .vpy (regression guard)."""
    result = _dst_for(Path("a/foo.vp"), root=None, out=None)
    assert result == Path("a/foo.vpy"), f"got: {result}"


def test_resolve_inputs_directory_finds_svp(tmp_path):
    """Directory input resolver picks up .svp and .vp files."""
    (tmp_path / "x.vp").write_text("// vp\n")
    (tmp_path / "y.svp").write_text("// svp\n")
    found = _resolve_inputs([tmp_path])
    names = {p.name for p in found}
    assert "x.vp" in names, f"missing x.vp in {names}"
    assert "y.svp" in names, f"missing y.svp in {names}"


def test_resolve_inputs_directory_svp_dst_maps_to_svpy(tmp_path):
    """A .svp found via directory resolution produces a .svpy destination."""
    (tmp_path / "y.svp").write_text("// svp\n")
    found = _resolve_inputs([tmp_path])
    svp = next(p for p in found if p.suffix == ".svp")
    dst = _dst_for(svp, root=tmp_path, out=tmp_path / "out")
    assert dst.suffix == ".svpy", f"expected .svpy, got {dst.suffix}"
