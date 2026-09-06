"""Exhaustive cross-validation of qfmt against Fraction arithmetic over small formats."""

from fractions import Fraction
from itertools import combinations, product
from math import floor

import pytest

import qfmt
from qfmt import Bounds, Fmt, QError, badd, bmult

WIDTHS = range(1, 7)
FRACS = range(-2, 7)
FMTS = [Fmt(s, w, f) for s in (True, False) for w in WIDTHS for f in FRACS]

# Enumerating every code pair is only affordable on narrow words. The wider ones are
# checked at their corners, which is where products and sums take their extremes.
SMALL = [f for f in FMTS if f.width <= 4 and f.frac in (-1, 0, 3)]


def narrower(f: Fmt) -> Fmt | None:
    return Fmt(f.signed, f.width - 1, f.frac) if f.width > 1 else None


# -------------------------------------------------------------------- notation
@pytest.mark.parametrize("f", FMTS, ids=str)
def test_q_string_round_trips(f):
    assert qfmt.parse(f.to_q()) == f
    assert qfmt.parse((f.signed, f.width, f.frac)) == f
    assert qfmt.parse(f) is f


@pytest.mark.parametrize(
    "text, expect",
    [
        ("Q1.6", Fmt(True, 7, 6)),
        ("UQ8.8", Fmt(False, 16, 8)),
        ("Q-1.5", Fmt(True, 4, 5)),
        ("UQ-1.3", Fmt(False, 2, 3)),
        ("Q4.-1", Fmt(True, 3, -1)),
        (" Q0.1 ", Fmt(True, 1, 1)),
    ],
)
def test_parse_examples(text, expect):
    assert qfmt.parse(text) == expect


@pytest.mark.parametrize("text", ["X4.4", "Q1", "Q1.6junk", "", "Q0.0", "Q-1.1", "UQ-2.1", "q1.6"])
def test_parse_rejects(text):
    with pytest.raises(QError):
        qfmt.parse(text)


def test_width_below_one_rejected():
    with pytest.raises(QError):
        Fmt(True, 0, 0)


@pytest.mark.parametrize("n, expect", [(1, 0), (2, 1), (3, 2), (4, 2), (5, 3), (8, 3), (9, 4)])
def test_clog2(n, expect):
    assert qfmt.clog2(n) == expect


def test_clog2_rejects_zero():
    with pytest.raises(QError):
        qfmt.clog2(0)


# ------------------------------------------------------------------ code/value
@pytest.mark.parametrize("f", FMTS, ids=str)
def test_encode_decode_every_code(f):
    for c in f.codes():
        v = f.decode(c)
        assert f.encode(v) == c
        assert f.contains(v)
    assert not f.contains(f.max_val + f.lsb)
    assert not f.contains(f.min_val - f.lsb)
    assert not f.contains(f.max_val + f.lsb / 2)


@pytest.mark.parametrize("f", FMTS, ids=str)
def test_decode_and_encode_reject_out_of_range(f):
    with pytest.raises(QError):
        f.decode(f.max_code + 1)
    with pytest.raises(QError):
        f.encode(f.max_val + f.lsb)
    with pytest.raises(QError):
        f.encode(f.lsb / 2)


def test_from_range_infers_signedness_from_lo():
    assert qfmt.from_range(Fraction(-1), Fraction(1), 4).signed
    assert not qfmt.from_range(Fraction(0), Fraction(1), 4).signed
    assert qfmt.from_range(Fraction(0), Fraction(1), 4, signed=True).signed


@pytest.mark.parametrize(
    "lo, hi, frac, signed",
    [(1, 0, 0, None), (-1, 1, 0, False), (Fraction(1, 3), 1, 0, None)],
)
def test_from_range_rejects(lo, hi, frac, signed):
    with pytest.raises(QError):
        qfmt.from_range(Fraction(lo), Fraction(hi), frac, signed)


def test_align_rejects_no_terms():
    with pytest.raises(QError):
        qfmt.align([])


def test_image_of_explicit_bounds():
    rq = qfmt.requant("Q4.4", "Q2.2", "half_up")
    assert rq.image(Bounds(-8, 7, 4)) == Bounds(-2, 2, 2)


def test_with_frac_preserves_range():
    f = qfmt.parse("Q2.3")
    g = f.with_frac(5)
    assert g == Fmt(True, 7, 5)
    assert g.min_val == f.min_val
    assert all(g.contains(f.decode(c)) for c in f.codes())
    with pytest.raises(QError):
        f.with_frac(2)


# ------------------------------------------------------------------------ mult
@pytest.mark.parametrize("a", SMALL, ids=str)
def test_mult_holds_every_product(a):
    for b in SMALL:
        p = qfmt.mult(a, b)
        assert p.frac == a.frac + b.frac
        for ca, cb in product(a.codes(), b.codes()):
            assert p.contains(a.decode(ca) * b.decode(cb))


@pytest.mark.parametrize("a", FMTS, ids=str)
def test_mult_is_narrowest_at_corners(a):
    for b in FMTS:
        p = qfmt.mult(a, b)
        corners = [x * y for x in (a.min_val, a.max_val) for y in (b.min_val, b.max_val)]
        assert all(p.contains(c) for c in corners)
        n = narrower(p)
        assert n is None or not all(n.contains(c) for c in corners)
        assert p.signed == (a.signed or b.signed)


@pytest.mark.parametrize("a", FMTS, ids=str)
def test_mult_width_is_sum_of_widths(a):
    for b in FMTS:
        w = qfmt.mult(a, b).width
        if a.signed and b.signed:
            assert w == a.width + b.width
        elif not a.signed and not b.signed:
            # a one-bit unsigned factor is an AND gate and adds no width
            assert w == (max(a.width, b.width) if min(a.width, b.width) == 1 else a.width + b.width)
        else:
            # a one-bit unsigned factor gates the signed one and adds no width
            s, u = (a, b) if a.signed else (b, a)
            assert w == (s.width if u.width == 1 else a.width + b.width)


@pytest.mark.parametrize("a", [f for f in SMALL if f.signed], ids=str)
def test_mult_sym_holds_all_but_the_excluded_corner(a):
    for b in SMALL:
        p = qfmt.mult(a, b, sym=True)
        assert p.width <= qfmt.mult(a, b).width
        for ca, cb in product(a.codes(), b.codes()):
            if ca != a.min_code:
                assert p.contains(a.decode(ca) * b.decode(cb))
        if p.width < qfmt.mult(a, b).width:
            assert any(not p.contains(a.decode(a.min_code) * b.decode(cb)) for cb in b.codes())


def test_mult_sym_saves_one_bit_for_signed_operands():
    for a, b in product(FMTS, FMTS):
        if a.signed and b.signed and a.width >= 2:
            assert qfmt.mult(a, b, sym=True).width == a.width + b.width - 1


def test_mult_sym_needs_signed_first_operand():
    with pytest.raises(QError):
        qfmt.mult("UQ4.4", "Q4.4", sym=True)
    assert qfmt.mult("UQ4.4", "Q4.4") == qfmt.mult("Q4.4", "UQ4.4")


@pytest.mark.parametrize("a", [f for f in SMALL if f.signed], ids=str)
def test_mult_bsym_mirrors_sym_on_the_other_operand(a):
    for b in SMALL:
        if b.signed:
            assert qfmt.mult(a, b, bsym=True) == qfmt.mult(b, a, sym=True)


@pytest.mark.parametrize("a", [f for f in SMALL if f.signed], ids=str)
def test_mult_both_sym_holds_all_but_the_two_excluded_corners(a):
    for b in SMALL:
        if not b.signed:
            continue
        p = qfmt.mult(a, b, sym=True, bsym=True)
        assert p.width <= qfmt.mult(a, b, sym=True).width
        assert p.width <= qfmt.mult(a, b, bsym=True).width
        for ca, cb in product(a.codes(), b.codes()):
            if ca != a.min_code and cb != b.min_code:
                assert p.contains(a.decode(ca) * b.decode(cb))


def test_mult_both_sym_can_beat_either_flag_alone():
    assert qfmt.mult("Q2.0", "Q2.0").width == 4
    assert qfmt.mult("Q2.0", "Q2.0", sym=True).width == 3
    assert qfmt.mult("Q2.0", "Q2.0", bsym=True).width == 3
    assert qfmt.mult("Q2.0", "Q2.0", sym=True, bsym=True).width == 2


def test_mult_bsym_needs_signed_second_operand():
    with pytest.raises(QError):
        qfmt.mult("Q4.4", "UQ4.4", bsym=True)


# ------------------------------------------------------------------- sum/align
@pytest.mark.parametrize("a", SMALL, ids=str)
def test_add_holds_every_pair_sum(a):
    for b in SMALL:
        if b.frac != a.frac:
            continue
        s = qfmt.add([a, b])
        for ca, cb in product(a.codes(), b.codes()):
            assert s.contains(a.decode(ca) + b.decode(cb))


def _check_add(fs):
    s = qfmt.add(fs)
    lo = sum(f.min_val for f in fs)
    hi = sum(f.max_val for f in fs)
    assert s.contains(lo) and s.contains(hi)
    n = narrower(s)
    assert n is None or not (n.contains(lo) and n.contains(hi))
    assert s.signed == any(f.signed for f in fs)


def test_add_is_narrowest_for_pairs():
    for a, b in product(FMTS, FMTS):
        if a.frac == b.frac:
            _check_add([a, b])


def test_add_is_narrowest_for_three_and_four_terms():
    pool = [Fmt(s, w, 0) for s in (True, False) for w in WIDTHS]
    for k in (3, 4):
        for fs in combinations(pool, k):
            _check_add(list(fs))


def test_add_rejects_misaligned_terms():
    with pytest.raises(QError):
        qfmt.add(["Q4.4", "Q4.5"])
    with pytest.raises(QError):
        qfmt.add([])


def test_align_preserves_ranges_and_reports_shifts():
    fs = [qfmt.parse(q) for q in ("Q1.6", "Q-1.5", "Q5.2")]
    aligned, shifts = qfmt.align(fs)
    assert shifts == [0, 1, 4]
    assert {f.frac for f in aligned} == {6}
    for f, g in zip(fs, aligned):
        assert g.min_val == f.min_val
        assert all(g.contains(f.decode(c)) for c in f.codes())
    assert qfmt.add(aligned).width == 12


def test_envelope_covers_every_input():
    for a, b in product(FMTS, FMTS):
        h = qfmt.envelope([a, b])
        for f in (a, b):
            assert h.contains(f.min_val) and h.contains(f.max_val)
            assert h.contains(f.min_val + f.lsb) or f.width == 1
        n = narrower(h)
        vals = [a.min_val, a.max_val, b.min_val, b.max_val]
        assert n is None or not all(n.contains(v) for v in vals)


# ---------------------------------------------------------------------- bounds
@pytest.mark.parametrize("f", FMTS, ids=str)
def test_bounds_of_names_the_format_and_round_trips(f):
    b = Bounds.of(f)
    assert (b.lo, b.hi, b.frac, b.signed) == (f.min_code, f.max_code, f.frac, f.signed)
    assert (b.lo_val, b.hi_val) == (f.min_val, f.max_val)
    assert b.fmt() == f
    if f.signed:
        assert Bounds.of(f, sym=True) == Bounds(-f.max_code, f.max_code, f.frac, True)
    else:
        with pytest.raises(QError):
            Bounds.of(f, sym=True)


def test_bounds_rejects_empty_range_and_negative_unsigned():
    with pytest.raises(QError):
        Bounds(3, 2, 0)
    with pytest.raises(QError):
        Bounds(-1, 2, 0, signed=False)


@pytest.mark.parametrize("a", SMALL, ids=str)
def test_bmult_ends_are_attained(a):
    for b in SMALL:
        for sa, sb in product((False, True), repeat=2):
            if (sa and not a.signed) or (sb and not b.signed):
                continue
            ba, bb = Bounds.of(a, sa), Bounds.of(b, sb)
            p = bmult(ba, bb)
            prods = [x * y for x in range(ba.lo, ba.hi + 1) for y in range(bb.lo, bb.hi + 1)]
            assert (p.lo, p.hi, p.frac, p.signed) == (
                min(prods),
                max(prods),
                a.frac + b.frac,
                a.signed or b.signed,
            )


def test_badd_sums_the_ends_and_beats_add_on_partial_ranges():
    terms = [Bounds(-31, 32, 6)] * 3
    s = badd(terms)
    assert (s.lo, s.hi, s.frac) == (-93, 96, 6)
    assert s.fmt() == qfmt.parse("Q2.6")
    assert qfmt.add([t.fmt() for t in terms]) == qfmt.parse("Q3.6")


def test_badd_rejects_misaligned_and_empty():
    with pytest.raises(QError):
        badd([Bounds(0, 1, 2), Bounds(0, 1, 3)])
    with pytest.raises(QError):
        badd([])


# --------------------------------------------------------------------- requant
def ref_requant(v: Fraction, dst: Fmt, mode: str, osym: bool) -> int:
    q = v / dst.lsb
    if mode == "trunc":
        c = floor(q)
    elif mode == "half_up":
        c = floor(q + Fraction(1, 2))
    elif mode == "half_away":
        c = floor(abs(q) + Fraction(1, 2))
        if q < 0:
            c = -c
    elif mode == "to_zero":
        c = int(q)  # Fraction.__trunc__ rounds toward zero
    elif mode == "half_even":
        c = round(q)  # Fraction.__round__ is half-to-even
    else:
        raise AssertionError(f"ref_requant does not model {mode!r}")
    lo = -dst.max_code if (dst.signed and osym) else dst.min_code
    return max(lo, min(dst.max_code, c))


REQ_SRC = [f for f in FMTS if f.width <= 5]
REQ_DST = [f for f in FMTS if f.frac in (-2, 0, 3, 6)]


@pytest.mark.parametrize("osym", [False, True])
@pytest.mark.parametrize("mode", qfmt.ROUND_MODES)
def test_requant_matches_fraction_reference(mode, osym):
    for src, dst in product(REQ_SRC, REQ_DST):
        rq = qfmt.requant(src, dst, mode, osym)
        for c in src.codes():
            assert rq.apply(c) == ref_requant(src.decode(c), dst, mode, osym), (src, dst, c)


@pytest.mark.parametrize("osym", [False, True])
@pytest.mark.parametrize("mode", qfmt.ROUND_MODES)
def test_image_is_the_range_of_apply_over_the_bounds(mode, osym):
    for src, dst in product(REQ_SRC, REQ_DST):
        for sym in (False, True):
            if sym and not src.signed:
                continue
            b = Bounds.of(src, sym)
            rq = qfmt.requant(b, dst, mode, osym)
            assert rq.src_bounds == b
            codes = range(b.lo, b.hi + 1)
            seen = [rq.apply(c) for c in codes]
            img = rq.image()
            assert (img.lo, img.hi, img.frac, img.signed) == (
                min(seen),
                max(seen),
                dst.frac,
                dst.signed,
            )
            clamped = any(rq.apply(c, clamp=False) != rq.apply(c) for c in codes)
            assert rq.sat_reachable == clamped, (src, dst, sym)


def test_requant_from_bounds_judges_the_clamp_over_the_bounds():
    # Q1.5 x Q1.6, both symmetric, requantized half_up to six fractional bits: the bounds
    # fit Q1.6, the mult format (their container) does not.
    p = bmult(Bounds.of("Q1.5", sym=True), Bounds.of("Q1.6", sym=True))
    assert (p.lo, p.hi, p.frac) == (-1953, 1953, 11)
    rq = qfmt.requant(p, "Q1.6", "half_up", saturate=False)
    assert rq.image() == Bounds(-61, 61, 6)
    assert rq.src == p.fmt()
    with pytest.raises(QError):
        qfmt.requant(p.fmt(), "Q1.6", "half_up", saturate=False)


def test_image_rejects_bounds_at_another_frac():
    with pytest.raises(QError):
        qfmt.requant("Q4.4", "Q2.2").image(Bounds(0, 1, 3))


def test_requant_reports_loss():
    assert qfmt.requant("Q4.4", "Q6.6").lossless
    assert not qfmt.requant("Q4.4", "Q4.2").lossless
    assert not qfmt.requant("Q4.4", "Q4.2").sat_reachable
    assert qfmt.requant("Q4.4", "Q4.2", "half_up").sat_reachable
    assert qfmt.requant("Q4.4", "Q4.2", "half_away").sat_reachable
    assert not qfmt.requant("Q4.4", "Q4.2", "to_zero").sat_reachable
    assert qfmt.requant("Q4.4", "Q2.4").sat_reachable
    assert qfmt.requant("Q4.4", "Q4.4", osym=True).sat_reachable


def test_requant_reports_which_clamp_end_is_reachable():
    top = qfmt.requant("Q4.4", "Q4.2", "half_up")
    assert (top.sat_lo, top.sat_hi) == (False, True)
    low = qfmt.requant("Q4.4", "Q4.4", osym=True)
    assert (low.sat_lo, low.sat_hi) == (True, False)
    both = qfmt.requant("Q4.4", "Q2.4")
    assert (both.sat_lo, both.sat_hi) == (True, True)
    none = qfmt.requant("Q4.4", "Q4.2")
    assert (none.sat_lo, none.sat_hi) == (False, False)


def test_requant_can_refuse_saturation():
    with pytest.raises(QError):
        qfmt.requant("Q4.4", "Q2.4", saturate=False)
    assert qfmt.requant("Q4.4", "Q4.2", saturate=False).shift == 2


def test_requant_rejects_bad_mode():
    with pytest.raises(QError):
        qfmt.requant("Q4.4", "Q2.2", "nearest")


def test_requant_rejects_osym_with_a_frac_target():
    with pytest.raises(QError):
        qfmt.requant(qfmt.Bounds(-4, 3, 0), 0, osym=True)


def test_requant_reports_the_shape_f_qcvt_emits():
    """f_qcvt reads shift, the clamp bounds and src_bounds; the rounding itself it builds
    from mode and shift, so there is no constant here for it to pick up."""
    rq = qfmt.requant("Q4.12", "Q2.6", "half_even")
    assert (rq.shift, rq.mode) == (6, "half_even")
    assert (rq.min_code, rq.max_code) == (-128, 127)
    rq = qfmt.requant("Q4.4", "Q4.4", osym=True)
    assert (rq.min_code, rq.max_code) == (-127, 127)
    rq = qfmt.requant("Q3.5", "Q3.9")
    assert rq.shift == -4
    # whether a negative code can arrive is what lets the emitter drop the sign term
    assert qfmt.requant("UQ8.8", "UQ4.4", "half_away").src_bounds.lo == 0
    assert qfmt.requant(Bounds(0, 60, 4), "Q4.2", "to_zero").src_bounds.lo == 0
    assert qfmt.requant("Q4.12", "Q2.6", "half_away").src_bounds.lo < 0


# -------------------------------------------------------- reference design check
def test_ffe_slice_widths_from_ff_txt():
    """The partial-sum widths derived in ff.txt section 3, from formats alone."""
    sample = qfmt.parse("Q1.6")
    coef_w = [4, 6, 7, 8, 9, 10, 9, 9, 8, 8, 6, 6, 5, 5, 5, 5, 5, 5, 5, 5] + [5] * 40
    groups = [
        [4, 5, 6],
        [0, 1, 2, 3] + list(range(7, 20)),
        list(range(20, 40)),
        list(range(40, 60)),
    ]
    coefs = [Fmt(True, w, 5) for w in coef_w]
    assert [c.to_q() for c in coefs[:6]] == ["Q-1.5", "Q1.5", "Q2.5", "Q3.5", "Q4.5", "Q5.5"]
    pp = [qfmt.requant(qfmt.mult(c, sample, sym=True), Fmt(True, c.width + 4, 9)) for c in coefs]
    assert all(r.shift == 2 for r in pp)
    ps = [qfmt.add([pp[i].dst for i in g]) for g in groups]
    assert [p.width for p in ps] == [15, 15, 14, 14]
    out = qfmt.add(ps)
    assert (out.width, out.to_q()) == (17, "Q8.9")


# ---------------------------------------------------------- requant to a frac
BOUNDS = [
    Bounds(lo, hi, frac, signed)
    for signed in (True, False)
    for frac in (-1, 0, 2, 3)
    for lo in range(-9 if signed else 0, 9)
    for hi in range(lo, 9)
]


@pytest.mark.parametrize("mode", qfmt.ROUND_MODES)
def test_frac_target_is_the_unclamped_image_over_every_code(mode):
    for b in BOUNDS:
        for frac in range(-2, 5):
            rq = qfmt.requant(b, frac, mode)
            # a 16-bit target cannot clamp any of these codes, so apply() is the bare rounding
            wide = qfmt.requant(b, Fmt(b.signed, 16, frac), mode)
            imgs = [wide.apply(c, clamp=False) for c in range(b.lo, b.hi + 1)]
            got = rq.image()
            assert (got.lo, got.hi, got.frac, got.signed) == (min(imgs), max(imgs), frac, b.signed)
            assert rq.dst == got.fmt()
            assert not rq.sat_reachable


def test_frac_target_names_the_product_format_dotp_declares():
    p = bmult(Bounds.of("Q1.5", sym=True), Bounds.of("Q1.6", sym=True))
    assert qfmt.requant(p, 6, "half_up").image() == Bounds(-61, 61, 6)
    assert qfmt.requant(p, 6, "trunc").image() == Bounds(-62, 61, 6)
    assert qfmt.requant(p, 6, "half_up").dst == qfmt.parse("Q1.6")
    assert qfmt.requant(p, 13).image() == Bounds(p.lo << 2, p.hi << 2, 13)


def test_frac_target_needs_a_bounds_source():
    with pytest.raises(QError):
        qfmt.requant("Q4.4", 2)


def test_frac_target_rejects_a_bad_mode():
    with pytest.raises(QError):
        qfmt.requant(Bounds(0, 1, 0), 0, "nearest")
