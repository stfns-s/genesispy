"""Tests for vexpr, the Verilog expression text helpers."""

import re

import pytest

import qfmt
import vexpr
from vexpr import VExprError, lit

WIDTHS = range(1, 9)


@pytest.mark.parametrize(
    "value, width, signed, expect",
    [
        (5, 8, True, "8'sd5"),
        (-5, 8, True, "-8'sd5"),
        (0, 8, True, "8'sd0"),
        (127, 8, True, "8'sd127"),
        (-128, 8, True, "-8'sd128"),
        (127, 10, True, "10'sd127"),
        (-128, 10, True, "-10'sd128"),
        (0, 1, True, "1'sd0"),
        (-1, 1, True, "-1'sd1"),
        (5, 8, False, "8'd5"),
        (255, 8, False, "8'd255"),
        (0, 1, False, "1'd0"),
        (1, 1, False, "1'd1"),
    ],
)
def test_lit_examples(value, width, signed, expect):
    assert lit(value, width, signed) == expect


@pytest.mark.parametrize("width", WIDTHS)
def test_lit_covers_every_signed_code(width):
    lo, hi = -(1 << (width - 1)), (1 << (width - 1)) - 1
    for v in range(lo, hi + 1):
        s = lit(v, width)
        assert s == (f"{width}'sd{v}" if v >= 0 else f"-{width}'sd{-v}")
        # the emitted text names the magnitude, and the sign sits outside it
        assert s.lstrip("-").startswith(f"{width}'sd")
        assert int(s.lstrip("-").split("'sd")[1]) == abs(v)
    with pytest.raises(VExprError):
        lit(lo - 1, width)
    with pytest.raises(VExprError):
        lit(hi + 1, width)


@pytest.mark.parametrize("width", WIDTHS)
def test_lit_covers_every_unsigned_code(width):
    for v in range(0, 1 << width):
        assert lit(v, width, signed=False) == f"{width}'d{v}"
    with pytest.raises(VExprError):
        lit(-1, width, signed=False)
    with pytest.raises(VExprError):
        lit(1 << width, width, signed=False)


def test_lit_rejects_zero_width():
    with pytest.raises(VExprError):
        lit(0, 0)


def test_lit_matches_the_lambda_it_replaces():
    """The eleven functions/ copies, byte for byte, over every value they can pass."""
    sdec = lambda v, w: f"{w}'sd{v}" if v >= 0 else f"-{w}'sd{-v}"  # noqa: E731
    for width in WIDTHS:
        for v in range(-(1 << (width - 1)), 1 << (width - 1)):
            assert lit(v, width) == sdec(v, width)


def test_error_type_is_a_value_error():
    assert issubclass(VExprError, ValueError)
    assert vexpr.VExprError is VExprError


# ---------------------------------------------------------------------- sext
@pytest.mark.parametrize(
    "args, kwargs, expect",
    [
        (("in", 8, 11), {}, "{ { 3 {in[7]} }, in }"),
        (("in", 8, 9), {}, "{ { 1 {in[7]} }, in }"),
        (("a", 4, 12), {}, "{ { 8 {a[3]} }, a }"),
        (("x", 8, 11), {"signed": False}, "{ { 3 {1'b0} }, x }"),
        (("x", 7, 10), {"msb": 0}, "{ { 3 {x[0]} }, x }"),
        (("x", 7, 10), {"msb": -2}, "{ { 3 {x[-2]} }, x }"),
    ],
)
def test_sext_examples(args, kwargs, expect):
    assert vexpr.sext(*args, **kwargs) == expect


def test_sext_reproduces_the_three_identical_template_sites():
    """functions/f_sh.vpy:19, f_shleft.vpy:18 and f_shright.vpy:20 are byte-identical."""
    for iwidth, isw in ((8, 11), (4, 7), (16, 19)):
        assert (
            vexpr.sext("in", iwidth, isw) == f"{{ {{ {isw - iwidth} {{in[{iwidth - 1}]}} }}, in }}"
        )


def test_sext_msb_defaults_to_the_top_bit():
    assert vexpr.sext("x", 8, 12) == vexpr.sext("x", 8, 12, msb=7)


def test_sext_rejects_a_non_widening_request():
    with pytest.raises(VExprError):
        vexpr.sext("x", 8, 8)
    with pytest.raises(VExprError):
        vexpr.sext("x", 8, 4)
    with pytest.raises(VExprError):
        vexpr.sext("x", 0, 4)


# ------------------------------------------------------------------ pad_low
@pytest.mark.parametrize(
    "n, expect",
    [(0, "x"), (1, "{ x, { 1 {1'b0} } }"), (6, "{ x, { 6 {1'b0} } }")],
)
def test_pad_low_examples(n, expect):
    assert vexpr.pad_low("x", n) == expect


def test_pad_low_rejects_a_negative_count():
    with pytest.raises(VExprError):
        vexpr.pad_low("x", -1)


# --------------------------------------------------------------------- decl
@pytest.mark.parametrize(
    "what, kwargs, expect",
    [
        (8, {"signed": True}, "signed [7:0]"),
        (8, {"signed": False}, "       [7:0]"),
        (8, {"signed": False, "pad": False}, "[7:0]"),
        (1, {"signed": True}, "signed [0:0]"),
        (64, {"signed": False, "pad": False}, "[63:0]"),
    ],
)
def test_decl_from_a_width(what, kwargs, expect):
    assert vexpr.decl(what, **kwargs) == expect


@pytest.mark.parametrize(
    "q, expect",
    [
        ("Q4.6", "signed [3:-6]"),
        ("Q-1.5", "signed [-2:-5]"),
        ("UQ3.-1", "       [2:1]"),
        ("Q1.6", "signed [0:-6]"),
        ("UQ8.8", "       [7:-8]"),
    ],
)
def test_decl_from_a_format(q, expect):
    assert vexpr.decl(qfmt.parse(q)) == expect


def test_decl_padding_aligns_the_bracket():
    """The unsigned form blanks to the width of 'signed', so ranges line up."""
    s, u = vexpr.decl(8, signed=True), vexpr.decl(8, signed=False)
    assert len(s) == len(u)
    assert s.index("[") == u.index("[")
    assert u.strip() == "[7:0]"


def test_decl_signed_argument_overrides_the_format():
    f = qfmt.parse("Q4.6")
    assert vexpr.decl(f, signed=False) == "       [3:-6]"


def test_decl_rejects_a_width_with_no_signedness():
    with pytest.raises(VExprError):
        vexpr.decl(8)
    with pytest.raises(VExprError):
        vexpr.decl(0, signed=True)


@pytest.mark.parametrize(
    "q, expect",
    [
        ("Q4.6", "signed [3:-6]"),
        ("Q-1.5", "signed [-2:-5]"),
        ("UQ3.-1", "[2:1]"),
        ("Q1.6", "signed [0:-6]"),
        ("UQ8.8", "[7:-8]"),
        ("Q0.1", "signed [-1:-1]"),
    ],
)
def test_decl_unpadded_is_the_range_qfmt_used_to_emit(q, expect):
    """This replaces Fmt.decl(), which returned the range without the keyword."""
    assert vexpr.decl(qfmt.parse(q), pad=False) == expect


# ------------------------------------------------------------- parenthesize
def test_parenthesize_examples():
    assert vexpr.parenthesize(list("abcd")) == "(a + b) + (c + d)"
    assert vexpr.parenthesize(list("ab")) == "a + b"
    assert vexpr.parenthesize(["a"]) == "a"
    assert vexpr.parenthesize(list("abc")) == "(a + b) + (c)"
    assert vexpr.parenthesize(list("ab"), leaf=1) == "(a) + (b)"
    assert vexpr.parenthesize(list("abcd"), op=" * ") == "(a * b) * (c * d)"


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 7, 8, 16, 17, 20, 60])
@pytest.mark.parametrize("leaf", [1, 2, 3, 4, 5, 8])
def test_parenthesize_is_balanced_and_keeps_every_term(n, leaf):
    terms = [f"x{i}" for i in range(n)]
    s = vexpr.parenthesize(terms, leaf=leaf)
    depth = 0
    for c in s:
        depth += c == "("
        depth -= c == ")"
        assert depth >= 0
    assert depth == 0
    assert re.findall(r"x\d+", s) == terms


@pytest.mark.parametrize("n", [2, 3, 5, 8, 13, 21])
@pytest.mark.parametrize("leaf", [1, 2, 4])
def test_parenthesize_preserves_the_value(n, leaf):
    """Grouping is a hint to synthesis; it must never change what is computed."""
    values = [i * 7 - 11 for i in range(n)]
    expr = vexpr.parenthesize([str(v) for v in values], leaf=leaf)
    assert eval(expr) == sum(values)  # noqa: S307 -- expression is built above


def test_parenthesize_rejects_an_empty_list_or_a_zero_leaf():
    with pytest.raises(VExprError):
        vexpr.parenthesize([])
    with pytest.raises(VExprError):
        vexpr.parenthesize(list("ab"), leaf=0)
