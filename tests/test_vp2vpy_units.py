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
import pytest

from genesispy.tools.vp2vpy import (
    FileTranslator, Helper, translate_perl_snippet, translate_backtick_expr,
    WalkCtx,
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
    assert 're.search(r"foo"' in got
    assert "re.I" in got


def test_regex_negative_match(helper):
    got = _xlate_stmt(helper, 'if ($s !~ /foo/) { 1; }')
    assert 're.search(r"foo"' in got
    assert "is None" in got


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
