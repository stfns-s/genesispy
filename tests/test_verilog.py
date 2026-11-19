"""Tests for genesispy.lib.verilog, the Verilog text helpers."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from genesispy.lib import verilog
from genesispy.lib.verilog import VerilogError, limit, lit

WIDTHS = range(1, 9)


@dataclass(frozen=True)
class _Fmt:
    """A fixed-point format as decl sees it: only int_bits, frac and signed."""

    signed: bool
    int_bits: int
    frac: int


def _q(text: str) -> _Fmt:
    """_Fmt from Qm.n / UQm.n, m counting the sign bit."""
    m = re.fullmatch(r"(U?)Q(-?\d+)\.(-?\d+)", text)
    assert m, text
    return _Fmt(m.group(1) == "", int(m.group(2)), int(m.group(3)))


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
    with pytest.raises(VerilogError):
        lit(lo - 1, width)
    with pytest.raises(VerilogError):
        lit(hi + 1, width)


@pytest.mark.parametrize("width", WIDTHS)
def test_lit_covers_every_unsigned_code(width):
    for v in range(0, 1 << width):
        assert lit(v, width, signed=False) == f"{width}'d{v}"
    with pytest.raises(VerilogError):
        lit(-1, width, signed=False)
    with pytest.raises(VerilogError):
        lit(1 << width, width, signed=False)


@pytest.mark.parametrize(
    "value, width, signed, fmt, expect",
    [
        (5, 8, True, "bin", "8'sb00000101"),
        (-5, 8, True, "bin", "8'sb11111011"),
        (-128, 8, True, "bin", "8'sb10000000"),
        (5, 8, False, "bin", "8'b00000101"),
        (-1, 1, True, "bin", "1'sb1"),
        (0, 1, False, "bin", "1'b0"),
        (-5, 8, True, "hex", "8'shfb"),
        (-128, 8, True, "hex", "8'sh80"),
        (255, 8, False, "hex", "8'hff"),
        (-1, 6, True, "hex", "6'sh3f"),
        (5, 12, True, "hex", "12'sh005"),
        (-5, 8, True, "dec", "-8'sd5"),
        (5, 8, False, "dec", "8'd5"),
    ],
)
def test_lit_format_examples(value, width, signed, fmt, expect):
    assert lit(value, width, signed, fmt=fmt) == expect


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("signed", (True, False))
@pytest.mark.parametrize("fmt, base, letter", [("bin", 2, "b"), ("hex", 16, "h")])
def test_lit_format_decodes_to_every_code(width, signed, fmt, base, letter):
    lo, hi = (-(1 << (width - 1)), (1 << (width - 1)) - 1) if signed else (0, (1 << width) - 1)
    prefix = f"{width}'{'s' if signed else ''}{letter}"
    ndig = width if base == 2 else -(-width // 4)
    for v in range(lo, hi + 1):
        s = lit(v, width, signed, fmt=fmt)
        assert s.startswith(prefix)
        digits = s[len(prefix):]
        assert len(digits) == ndig
        code = int(digits, base)
        assert code < (1 << width)
        assert (code - (1 << width) if signed and code >> (width - 1) else code) == v
    with pytest.raises(VerilogError):
        lit(lo - 1, width, signed, fmt=fmt)
    with pytest.raises(VerilogError):
        lit(hi + 1, width, signed, fmt=fmt)


@pytest.mark.parametrize("value, signed", [(-5, True), (200, False)])
def test_lit_format_none_and_dec_are_the_decimal_text(value, signed):
    assert lit(value, 8, signed, fmt=None) == lit(value, 8, signed, fmt="dec") \
        == lit(value, 8, signed)


def test_lit_rejects_an_unknown_format():
    with pytest.raises(VerilogError):
        lit(5, 8, fmt="oct")


def test_lit_rejects_zero_width():
    with pytest.raises(VerilogError):
        lit(0, 0)


@pytest.mark.parametrize(
    "args, kw, expect",
    [
        (("max", 8), {}, "8'sb01111111"),
        (("min", 8), {}, "8'sb10000000"),
        (("min", 8), {"symm": True}, "8'sb10000001"),
        (("max", 8), {"symm": True}, "8'sb01111111"),
        (("max", 8), {"signed": False}, "8'b11111111"),
        (("min", 8), {"signed": False}, "8'b00000000"),
        (("max", 8), {"fmt": "hex"}, "8'sh7f"),
        (("min", 8), {"symm": True, "fmt": "hex"}, "8'sh81"),
        (("max", 12), {"fmt": "hex"}, "12'sh7ff"),
        (("min", 8), {"fmt": "dec"}, "-8'sd128"),
        (("min", 8), {"symm": True, "fmt": "dec"}, "-8'sd127"),
        (("max", 1), {}, "1'sb0"),
        (("min", 1), {}, "1'sb1"),
        (("min", 1), {"symm": True}, "1'sb0"),
        ((), {"bound": "min", "width": 8, "symm": True}, "8'sb10000001"),
    ],
)
def test_limit_examples(args, kw, expect):
    assert limit(*args, **kw) == expect


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("signed, symm", [(True, False), (True, True), (False, False)])
def test_limit_is_the_format_end(width, signed, symm):
    if signed:
        lo, hi = -(1 << (width - 1)) + symm, (1 << (width - 1)) - 1
    else:
        lo, hi = 0, (1 << width) - 1
    for fmt in ("bin", "hex", "dec"):
        assert limit("min", width, signed, symm, fmt) == lit(lo, width, signed, fmt)
        assert limit("max", width, signed, symm, fmt) == lit(hi, width, signed, fmt)


def test_limit_defaults_to_binary():
    assert limit("max", 8) == lit(127, 8, fmt="bin")


@pytest.mark.parametrize("bound", ["Max", "mid", True])
def test_limit_rejects_an_unknown_bound(bound):
    with pytest.raises(VerilogError, match="^limit: bound"):
        limit(bound, 8)


@pytest.mark.parametrize("fmt", [None, "oct"])
def test_limit_rejects_an_unknown_format(fmt):
    with pytest.raises(VerilogError, match="^limit: fmt"):
        limit("max", 8, fmt=fmt)


def test_limit_rejects_symm_when_unsigned():
    with pytest.raises(VerilogError, match="^limit: symm"):
        limit("min", 8, signed=False, symm=True)


def test_limit_rejects_zero_width():
    with pytest.raises(VerilogError, match="^lit:"):
        limit("max", 0)


def test_error_type_is_a_value_error():
    assert issubclass(VerilogError, ValueError)


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
    assert verilog.sext(*args, **kwargs) == expect


def test_sext_reproduces_the_three_identical_template_sites():
    """functions/f_sh.vpy:25, f_shleft.vpy:21 and f_shright.vpy:23 are byte-identical."""
    assert verilog.sext("in", 8, 11) == "{ { 3 {in[7]} }, in }"
    assert verilog.sext("in", 4, 7) == "{ { 3 {in[3]} }, in }"
    assert verilog.sext("in", 16, 19) == "{ { 3 {in[15]} }, in }"


def test_sext_msb_defaults_to_the_top_bit():
    assert verilog.sext("x", 8, 12) == verilog.sext("x", 8, 12, msb=7)


def test_sext_rejects_a_non_widening_request():
    with pytest.raises(VerilogError):
        verilog.sext("x", 8, 8)
    with pytest.raises(VerilogError):
        verilog.sext("x", 8, 4)
    with pytest.raises(VerilogError):
        verilog.sext("x", 0, 4)


@pytest.mark.parametrize(
    "n, expect",
    [(0, "x"), (1, "{ x, { 1 {1'b0} } }"), (6, "{ x, { 6 {1'b0} } }")],
)
def test_pad_low_examples(n, expect):
    assert verilog.pad_low("x", n) == expect


def test_pad_low_rejects_a_negative_count():
    with pytest.raises(VerilogError):
        verilog.pad_low("x", -1)


_CONCAT_0_6_3 = json.loads(
    (Path(__file__).parent / "fixtures" / "verilog_concat_0_6_3.json").read_text()
)


@pytest.mark.parametrize("term, from_w, to_w, msb, signed, text", _CONCAT_0_6_3["sext"])
def test_sext_concat_text_matches_0_6_3(term, from_w, to_w, msb, signed, text):
    assert verilog.sext(term, from_w, to_w, msb=msb, signed=signed) == text
    assert verilog.sext(term, from_w, to_w, msb=msb, signed=signed, form="concat") == text


@pytest.mark.parametrize("term, n, text", _CONCAT_0_6_3["pad_low"])
def test_pad_low_concat_text_matches_0_6_3(term, n, text):
    assert verilog.pad_low(term, n) == text
    assert verilog.pad_low(term, n, from_w=6, form="concat") == text


@pytest.mark.parametrize(
    "args, kwargs, expect",
    [
        (("x", 3, 15), {}, "15'(signed'(x))"),
        (("x", 3, 15), {"signed": False}, "15'(unsigned'(x))"),
        (("acc", 8, 12), {"msb": 3}, "12'(signed'(acc))"),
        (("acc[3:0]", 4, 8), {}, "8'(signed'(acc[3:0]))"),
        (("acc[k +: 4]", 4, 8), {}, "8'(signed'(acc[k +: 4]))"),
        (("{a, b}", 4, 8), {}, "8'(signed'({a, b}))"),
        (("x[3]", 1, 4), {}, "4'(signed'(x[3]))"),
    ],
)
def test_sext_cast(args, kwargs, expect):
    assert verilog.sext(*args, form="cast", **kwargs) == expect


def test_pad_low_cast():
    assert verilog.pad_low("x", 4, from_w=6, form="cast") == "(10'(x) << 4)"
    assert verilog.pad_low("x", 0, form="cast") == "x"


def test_unknown_form_is_rejected():
    with pytest.raises(VerilogError):
        verilog.sext("x", 3, 15, form="legacy")
    with pytest.raises(VerilogError):
        verilog.pad_low("x", 4, from_w=6, form="legacy")
    with pytest.raises(VerilogError):
        verilog.set_widen_form("legacy")
    assert verilog.get_widen_form() == "concat"


def test_pad_low_cast_needs_from_w():
    with pytest.raises(VerilogError):
        verilog.pad_low("x", 4, form="cast")
    with pytest.raises(VerilogError):
        verilog.pad_low("x", 4, from_w=0, form="cast")


def test_cast_keeps_the_width_checks():
    with pytest.raises(VerilogError):
        verilog.sext("x", 4, 4, form="cast")
    with pytest.raises(VerilogError):
        verilog.sext("x", 0, 4, form="cast")
    with pytest.raises(VerilogError):
        verilog.pad_low("x", -1, from_w=6, form="cast")


def test_default_is_concat():
    assert verilog.get_widen_form() == "concat"
    assert verilog.sext("x", 8, 11) == "{ { 3 {x[7]} }, x }"


def test_set_widen_form_changes_the_default():
    verilog.set_widen_form("cast")
    assert verilog.get_widen_form() == "cast"
    assert verilog.sext("x", 8, 11) == "11'(signed'(x))"
    assert verilog.pad_low("x", 3, from_w=8) == "(11'(x) << 3)"


def test_call_form_overrides_the_default():
    verilog.set_widen_form("cast")
    assert verilog.sext("x", 8, 11, form="concat") == "{ { 3 {x[7]} }, x }"


def test_clear_all_resets_the_default():
    from genesispy import cache

    verilog.set_widen_form("cast")
    cache.clear_all()
    assert verilog.get_widen_form() == "concat"


def test_set_widen_form_warns_during_elaboration(capsys):
    from genesispy import cache

    cache.ELABORATING = True
    verilog.set_widen_form("cast")
    assert (
        "set_widen_form('cast') called during elaboration; templates elaborated earlier "
        "keep the previous form"
    ) in capsys.readouterr().err
    assert verilog.get_widen_form() == "cast"


def test_set_widen_form_is_silent_outside_elaboration(capsys):
    verilog.set_widen_form("cast")
    assert "set_widen_form" not in capsys.readouterr().err


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
    assert verilog.decl(what, **kwargs) == expect


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
    assert verilog.decl(_q(q)) == expect


def test_decl_padding_aligns_the_bracket():
    """The unsigned form blanks to the width of 'signed', so ranges line up."""
    s, u = verilog.decl(8, signed=True), verilog.decl(8, signed=False)
    assert len(s) == len(u)
    assert s.index("[") == u.index("[")
    assert u.strip() == "[7:0]"


def test_decl_signed_argument_overrides_the_format():
    f = _q("Q4.6")
    assert verilog.decl(f, signed=False) == "       [3:-6]"


def test_decl_rejects_a_width_with_no_signedness():
    with pytest.raises(VerilogError):
        verilog.decl(8)
    with pytest.raises(VerilogError):
        verilog.decl(0, signed=True)


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
def test_decl_unpadded_is_the_bare_range(q, expect):
    assert verilog.decl(_q(q), pad=False) == expect


def test_decl_col_right_justifies_both_bounds():
    col = [_q("Q4.12"), 16]
    assert verilog.decl(col[0], col=col) == "signed [ 3:-12]"
    assert verilog.decl(16, signed=False, col=col) == "       [15:  0]"


def test_decl_col_gives_every_member_one_length():
    col = [_q(q) for q in ("Q4.6", "UQ12.0", "Q1.15", "Q-1.5")]
    lengths = {len(verilog.decl(f, col=col)) for f in col}
    assert len(lengths) == 1


def test_decl_empty_col_is_the_plain_form():
    f = _q("Q4.6")
    assert verilog.decl(f, col=()) == verilog.decl(f)
    assert verilog.decl(8, signed=False, col=[]) == "       [7:0]"


def test_decl_col_need_not_contain_what():
    assert verilog.decl(4, signed=True, col=[_q("Q10.2")]) == "signed [3: 0]"


def test_decl_col_member_width_needs_no_signedness():
    assert verilog.decl(4, signed=False, pad=False, col=[100]) == "[ 3:0]"


def test_parenthesize_examples():
    assert verilog.parenthesize(list("abcd")) == "(a + b) + (c + d)"
    assert verilog.parenthesize(list("ab")) == "a + b"
    assert verilog.parenthesize(["a"]) == "a"
    assert verilog.parenthesize(list("abc")) == "(a + b) + (c)"
    assert verilog.parenthesize(list("ab"), leaf=1) == "(a) + (b)"
    assert verilog.parenthesize(list("abcd"), op=" * ") == "(a * b) * (c * d)"


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 7, 8, 16, 17, 20, 60])
@pytest.mark.parametrize("leaf", [1, 2, 3, 4, 5, 8])
def test_parenthesize_is_balanced_and_keeps_every_term(n, leaf):
    terms = [f"x{i}" for i in range(n)]
    s = verilog.parenthesize(terms, leaf=leaf)
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
    expr = verilog.parenthesize([str(v) for v in values], leaf=leaf)
    assert eval(expr) == sum(values)  # noqa: S307 -- expression is built above


def test_parenthesize_rejects_an_empty_list_or_a_zero_leaf():
    with pytest.raises(VerilogError):
        verilog.parenthesize([])
    with pytest.raises(VerilogError):
        verilog.parenthesize(list("ab"), leaf=0)


@pytest.mark.parametrize(
    "n, expect",
    [
        (1, "coef0"),
        (4, "coef3"),
        (10, "coef9"),
        (11, "coef10"),
        (100, "coef99"),
        (101, "coef100"),
    ],
)
def test_idx_pads_to_the_width_of_the_last_member(n, expect):
    assert verilog.idx("coef", n - 1, n) == expect


@pytest.mark.parametrize("n", [1, 4, 10, 11, 100, 101])
def test_idx_gives_every_member_the_same_width(n):
    names = [verilog.idx("s", i, n) for i in range(n)]
    assert len({len(s) for s in names}) == 1
    assert names == sorted(names)


@pytest.mark.parametrize(
    "n,min_width,expect",
    [
        (4, 1, "coef3"),
        (4, 2, "coef03"),
        (4, 4, "coef0003"),
        (12, 2, "coef03"),
        (101, 2, "coef003"),
    ],
)
def test_idx_min_width_is_a_floor_not_a_width(n, min_width, expect):
    assert verilog.idx("coef", 3, n, min_width) == expect


def test_idx_rejects_a_min_width_below_one():
    with pytest.raises(VerilogError):
        verilog.idx("s", 0, 4, 0)


def test_idx_rejects_an_index_outside_the_family():
    with pytest.raises(VerilogError):
        verilog.idx("s", 4, 4)
    with pytest.raises(VerilogError):
        verilog.idx("s", -1, 4)
    with pytest.raises(VerilogError):
        verilog.idx("s", 0, 0)


def test_wrap_sum_keeps_a_short_sum_on_one_line():
    assert verilog.wrap_sum("  assign s = ", "a + b + c") == ["  assign s = a + b + c"]


def test_wrap_sum_breaks_after_a_plus_under_the_first_term():
    head = "assign s = "
    lines = verilog.wrap_sum(head, "aaaa + bbbb + cccc + dddd", width=len(head) + 15)
    assert lines == ["assign s = aaaa + bbbb +", "           cccc + dddd"]


def test_wrap_sum_never_splits_a_term():
    long = "a" * 50
    assert verilog.wrap_sum("x = ", f"{long} + b", width=10) == [f"x = {long} +", "    b"]


@pytest.mark.parametrize("term_w", [1, 2, 3, 5, 8])
@pytest.mark.parametrize("width", range(20, 41))
def test_wrap_sum_no_line_exceeds_width(term_w, width):
    head = "    s = "
    terms = [f"t{i:0{term_w}d}" for i in range(30)]
    lines = verilog.wrap_sum(head, " + ".join(terms), width)
    assert max(len(line) for line in lines) <= width


@pytest.mark.parametrize("n", [1, 2, 7, 40])
@pytest.mark.parametrize("width", [20, 60, 100])
def test_wrap_sum_keeps_every_term_in_order(n, width):
    terms = [f"t{i}" for i in range(n)]
    lines = verilog.wrap_sum("    wire [3:0] s = ", " + ".join(terms), width)
    assert " ".join(line.strip() for line in lines) == "wire [3:0] s = " + " + ".join(terms)


def test_port_map_aligns_the_open_parens():
    text = verilog.port_map([("grad00", "gf_00"), ("eq_err", "eq_err"), ("adapt_clk", "adapt_clk")])
    assert text == (
        "        .grad00    (gf_00),\n"
        "        .eq_err    (eq_err),\n"
        "        .adapt_clk (adapt_clk)"
    )


def test_port_map_indent_and_one_port():
    assert verilog.port_map([("clk", "clk")], indent=4) == "    .clk (clk)"


def test_port_map_keeps_the_order_and_every_net():
    ports = [(f"p{i}", f"n[{i}]") for i in range(12)]
    lines = verilog.port_map(ports).split("\n")
    assert [re.match(r"\s+\.(\w+)", line).group(1) for line in lines] == [p for p, _ in ports]
    assert len({line.index("(") for line in lines}) == 1
    assert all(line.endswith(",") for line in lines[:-1])
    assert lines[-1].endswith(")")


@pytest.mark.parametrize("ports", [[], [("a", "x"), ("a", "y")]])
def test_port_map_rejects_an_empty_list_or_a_repeated_port(ports):
    with pytest.raises(VerilogError):
        verilog.port_map(ports)


_WIDEN_TOP = (
    "module `mname` (input [7:0] x, output [10:0] y);\n"
    "assign y = `verilog.sext('x', 8, 11)`;\n"
    "endmodule\n"
)


def _widen_run(tmp_path, monkeypatch, argv=(), top=_WIDEN_TOP, cfg=None):
    from genesispy.cli import parse_args
    from genesispy.manager import Manager

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "top.vpy").write_text(top)
    args = ["--input", "top.vpy", "--top", "top", "--src-path", "src", "--out-dir", "out",
            *argv]
    if cfg is not None:
        (tmp_path / "w.cfg").write_text(cfg)
        args += ["--cfg", "w.cfg"]
    monkeypatch.chdir(tmp_path)
    rc = Manager(parse_args(args)).execute()
    files = sorted((tmp_path / "out").glob("top*.v"))
    return rc, files[0].read_text() if files else ""


def test_flag_sets_the_run_default(tmp_path, monkeypatch):
    rc, text = _widen_run(tmp_path, monkeypatch, ["--verilog-default-widen-form", "cast"])
    assert rc == 0
    assert "assign y = 11'(signed'(x));" in text


def test_cfg_setter_overrides_the_flag(tmp_path, monkeypatch, capsys):
    cfg = "from genesispy.lib import verilog\nverilog.set_widen_form('concat')\n"
    rc, text = _widen_run(tmp_path, monkeypatch, ["--verilog-default-widen-form", "cast"],
                          cfg=cfg)
    assert rc == 0
    assert "assign y = { { 3 {x[7]} }, x };" in text
    assert "set_widen_form" not in capsys.readouterr().err


def test_template_setter_warns(tmp_path, monkeypatch, capsys):
    top = "//; verilog.set_widen_form('cast')\n" + _WIDEN_TOP
    rc, text = _widen_run(tmp_path, monkeypatch, top=top)
    assert rc == 0
    assert "assign y = 11'(signed'(x));" in text
    assert "set_widen_form('cast') called during elaboration" in capsys.readouterr().err


def test_elaboration_flag_clears_after_an_error(tmp_path, monkeypatch):
    from genesispy import cache

    top = "//; raise ValueError('boom')\n" + _WIDEN_TOP
    rc, _ = _widen_run(tmp_path, monkeypatch, top=top)
    assert rc != 0
    assert cache.ELABORATING is False
