"""Fixed-point format algebra for generation-time width derivation.

A format is (signed, width, frac). A stored code c denotes c / 2**frac, read as two's
complement when signed. Integer bits are width - frac and may be zero or negative, so
Q-1.5 (a four-bit signed word with five fractional bits) is a valid format.

The Qm.n strings follow the ARM convention: m + n is the width and m includes the sign
bit, so a 16-bit signed integer is Q16.0 (Texas Instruments would write Q15.0).

Every range is exact: values are Fractions, never floats. Nothing here emits Verilog or
imports genesispy, so the module runs under pytest on its own.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from fractions import Fraction

_Q_RE = re.compile(r"(U?)Q(-?\d+)\.(-?\d+)")

ROUND_MODES = ("trunc", "half_up", "half_even", "half_away", "to_zero")


class QError(ValueError):
    """A format, conversion or combination that the algebra rejects."""


def _lsb(frac: int) -> Fraction:
    return Fraction(1, 1 << frac) if frac >= 0 else Fraction(1 << -frac)


def clog2(n: int) -> int:
    """Bits needed to count n distinct values: ceil(log2(n)), exact in integers."""
    if n < 1:
        raise QError(f"clog2: need n >= 1, got {n}")
    return (n - 1).bit_length()


@dataclass(frozen=True)
class Fmt:
    signed: bool
    width: int
    frac: int

    def __post_init__(self) -> None:
        if self.width < 1:
            raise QError(f"{self.to_q()}: a format needs at least one bit")

    # ----------------------------------------------------------------- shape
    @property
    def int_bits(self) -> int:
        return self.width - self.frac

    @property
    def lsb(self) -> Fraction:
        return _lsb(self.frac)

    @property
    def min_code(self) -> int:
        return -(1 << (self.width - 1)) if self.signed else 0

    @property
    def max_code(self) -> int:
        return (1 << (self.width - 1)) - 1 if self.signed else (1 << self.width) - 1

    @property
    def min_val(self) -> Fraction:
        return self.min_code * self.lsb

    @property
    def max_val(self) -> Fraction:
        return self.max_code * self.lsb

    # ------------------------------------------------------------- notation
    def to_q(self) -> str:
        return f"{'' if self.signed else 'U'}Q{self.width - self.frac}.{self.frac}"

    def __str__(self) -> str:
        return self.to_q()

    # ----------------------------------------------------------- code/value
    def decode(self, code: int) -> Fraction:
        if not self.min_code <= code <= self.max_code:
            raise QError(f"{self}: code {code} out of range")
        return code * self.lsb

    def encode(self, value: Fraction | int) -> int:
        """Exact code for value; raises unless value is representable and in range."""
        q = Fraction(value) / self.lsb
        if q.denominator != 1:
            raise QError(f"{self}: {value} is not a multiple of the lsb")
        code = int(q)
        if not self.min_code <= code <= self.max_code:
            raise QError(f"{self}: {value} out of range")
        return code

    def contains(self, value: Fraction | int) -> bool:
        q = Fraction(value) / self.lsb
        return q.denominator == 1 and self.min_code <= q <= self.max_code

    def codes(self) -> range:
        return range(self.min_code, self.max_code + 1)

    def with_frac(self, frac: int) -> Fmt:
        """Same range at more fractional bits: a value-preserving left shift."""
        if frac < self.frac:
            raise QError(f"{self}: with_frac({frac}) would drop bits; use requant")
        return Fmt(self.signed, self.width + frac - self.frac, frac)


FmtLike = Fmt | str | Sequence[object]


def parse(x: FmtLike) -> Fmt:
    """Fmt from a Fmt, a Qm.n / UQm.n string, or a (signed, width, frac) tuple."""
    if isinstance(x, Fmt):
        return x
    if isinstance(x, str):
        m = _Q_RE.fullmatch(x.strip())
        if not m:
            raise QError(f"bad Q format {x!r} (want Qm.n or UQm.n)")
        m_bits, n_bits = int(m.group(2)), int(m.group(3))
        return Fmt(m.group(1) == "", m_bits + n_bits, n_bits)
    if isinstance(x, Sequence) and len(x) == 3:
        signed, width, frac = x
        return Fmt(bool(signed), int(width), int(frac))  # type: ignore[call-overload]
    raise QError(f"bad format {x!r} (want Fmt, Q string or (signed, width, frac))")


def from_range(lo: Fraction, hi: Fraction, frac: int, signed: bool | None = None) -> Fmt:
    """Narrowest format at frac holding every value in [lo, hi]."""
    if lo > hi:
        raise QError(f"from_range: empty range [{lo}, {hi}]")
    if signed is None:
        signed = lo < 0
    if not signed and lo < 0:
        raise QError(f"from_range: unsigned format cannot hold {lo}")
    probe = Fmt(signed, 1, frac)
    lo_code, hi_code = Fraction(lo) / probe.lsb, Fraction(hi) / probe.lsb
    if lo_code.denominator != 1 or hi_code.denominator != 1:
        raise QError(f"from_range: bounds are not multiples of 2**-{frac}")
    width = 1
    while True:
        f = Fmt(signed, width, frac)
        if f.min_code <= lo_code and hi_code <= f.max_code:
            return f
        width += 1


# ---------------------------------------------------------------------- bounds
@dataclass(frozen=True)
class Bounds:
    """The reachable codes lo .. hi of a net, at frac fractional bits.

    A format is the power-of-two container of a range; a Bounds is the range itself. A
    derivation that carries Bounds from input to output and calls fmt() only where it
    declares a net gets the narrowest width at every step. Carrying formats can cost a
    bit wherever the next step widens the container but not the range: three terms
    reaching -31 .. 32 sum to -93 .. 96 and fit Q2.6, where add over three Q1.6 gives
    Q3.6.
    """

    lo: int
    hi: int
    frac: int
    signed: bool = True

    def __post_init__(self) -> None:
        if self.lo > self.hi:
            raise QError(f"Bounds: empty range {self.lo} .. {self.hi}")
        if not self.signed and self.lo < 0:
            raise QError(f"Bounds: unsigned range cannot hold {self.lo}")

    @classmethod
    def of(cls, fmt: FmtLike, sym: bool = False) -> Bounds:
        """Every code of fmt; with sym=True, every code but the most negative one."""
        f = parse(fmt)
        if sym and not f.signed:
            raise QError(f"Bounds.of: sym needs a signed format, got {f}")
        return cls(-f.max_code if sym else f.min_code, f.max_code, f.frac, f.signed)

    @property
    def lo_val(self) -> Fraction:
        return self.lo * _lsb(self.frac)

    @property
    def hi_val(self) -> Fraction:
        return self.hi * _lsb(self.frac)

    def fmt(self) -> Fmt:
        """Narrowest format holding every code in the range."""
        return from_range(self.lo_val, self.hi_val, self.frac, self.signed)


def _common_frac(fracs: Iterable[int], what: str) -> int:
    fs = set(fracs)
    if not fs:
        raise QError(f"{what}: no terms")
    if len(fs) > 1:
        raise QError(f"{what}: terms have different fractional bits {sorted(fs)}; align first")
    return fs.pop()


def bmult(a: Bounds, b: Bounds) -> Bounds:
    """Bounds of the exact product, at a.frac + b.frac."""
    corners = [x * y for x in (a.lo, a.hi) for y in (b.lo, b.hi)]
    return Bounds(min(corners), max(corners), a.frac + b.frac, a.signed or b.signed)


def badd(bs: Iterable[Bounds]) -> Bounds:
    """Bounds of the exact sum. Terms must share a frac."""
    terms = list(bs)
    frac = _common_frac((t.frac for t in terms), "badd")
    lo, hi = sum(t.lo for t in terms), sum(t.hi for t in terms)
    return Bounds(lo, hi, frac, any(t.signed for t in terms))


def _round_consts(shift: int, mode: str) -> tuple[int, int]:
    """The constant added before the arithmetic right shift, for a non-negative and for a
    negative code. Both are zero when no bit is dropped. Adding half - 1 to a negative code
    carries only when the remainder passes half, leaving an exact tie at the larger
    magnitude; adding 2**shift - 1 carries on any remainder, which is the ceiling."""
    if shift <= 0:
        return 0, 0
    half, full = 1 << (shift - 1), (1 << shift) - 1
    return {
        "trunc": (0, 0),
        "half_up": (half, half),
        "half_even": (half, half),
        "half_away": (half, half - 1),
        "to_zero": (0, full),
    }[mode]


def _round_code(code: int, shift: int, mode: str) -> int:
    """code moved by shift fractional bits and rounded as mode says; no clamp. shift > 0
    drops bits: the constant _round_consts gives for the code's sign is added first, and
    half_even then steps an exact tie back down to the even result. shift <= 0 appends
    zeros."""
    if shift <= 0:
        return code << -shift
    add_c, add_c_neg = _round_consts(shift, mode)
    acc = (code + (add_c_neg if code < 0 else add_c)) >> shift
    if mode == "half_even" and (code & ((1 << shift) - 1)) == (1 << (shift - 1)) and acc & 1:
        acc -= 1
    return acc


# ------------------------------------------------------------------ operations
def mult(a: FmtLike, b: FmtLike, sym: bool = False, bsym: bool = False) -> Fmt:
    """Product format, signed if either operand is.

    With sym=True the result holds every product except those where a takes its most
    negative code, and bsym=True does the same for b. The named operand must be signed,
    and the caller owns the precondition (f_sym enforces it in RTL). How much either
    saves depends on whether dropping that corner moves the required range across a
    power-of-two boundary, which from_range decides case by case:
    mult("Q3.0", "UQ3.0", sym=True) saves nothing, mult("Q2.0", "UQ2.0", sym=True) saves
    one bit, mult("Q1.0", "UQ2.0", sym=True) saves two. Neither flag is ever wider.

    The two are not redundant: excluding both minima can cross a further boundary that
    excluding either one alone does not. mult("Q2.0", "Q2.0") is 4 bits, 3 with either
    flag, and 2 with both.

    This is bmult over Bounds.of, materialized. A derivation with more than one step
    should carry the Bounds instead: see the Bounds docstring.
    """
    fa, fb = parse(a), parse(b)
    if sym and not fa.signed:
        raise QError(f"mult: sym needs a signed first operand, got {fa}")
    if bsym and not fb.signed:
        raise QError(f"mult: bsym needs a signed second operand, got {fb}")
    return bmult(Bounds.of(fa, sym), Bounds.of(fb, bsym)).fmt()


def add(fmts: Iterable[FmtLike]) -> Fmt:
    """Format holding every reachable sum of the terms. Terms must share a frac."""
    fs = [parse(f) for f in fmts]
    return badd(Bounds.of(f) for f in fs).fmt()


def align(fmts: Iterable[FmtLike]) -> tuple[list[Fmt], list[int]]:
    """Bring terms to a common frac (the maximum). Returns the aligned formats and the
    left shift each term needs, in that order."""
    fs = [parse(f) for f in fmts]
    if not fs:
        raise QError("align: no terms")
    frac = max(f.frac for f in fs)
    shifts = [frac - f.frac for f in fs]
    return [f.with_frac(frac) for f in fs], shifts


def envelope(fmts: Iterable[FmtLike]) -> Fmt:
    """Narrowest format whose range and resolution cover every input."""
    fs, _ = align(fmts)
    lo = min(f.min_val for f in fs)
    hi = max(f.max_val for f in fs)
    return from_range(lo, hi, fs[0].frac, any(f.signed for f in fs))


# -------------------------------------------------------------------- requant
@dataclass(frozen=True)
class Requant:
    """What a src -> dst conversion does, in integer terms the RTL can use directly.

    shift > 0 drops that many lsbs (with rounding), shift < 0 appends zeros. The rounding
    itself is a carry into the kept bits, which the emitter builds from mode and shift;
    nothing here is a constant the RTL adds. min_code/max_code are the dst clamp bounds.
    src_bounds is the set of source codes the conversion is asked about: the whole of src,
    or the narrower Bounds a caller gave requant() in its place, and an emitter reads it to
    tell whether a negative code can arrive at all.
    """

    src: Fmt
    dst: Fmt
    mode: str
    osym: bool
    shift: int
    min_code: int
    max_code: int
    src_bounds: Bounds

    @property
    def lossless(self) -> bool:
        """No bit is ever dropped and no value is ever clamped."""
        return self.shift <= 0 and not self.sat_reachable

    @property
    def sat_lo(self) -> bool:
        """The lowest code in src_bounds lands below the dst clamp."""
        return self.apply(self.src_bounds.lo, clamp=False) < self.min_code

    @property
    def sat_hi(self) -> bool:
        """The highest code in src_bounds lands above the dst clamp."""
        return self.apply(self.src_bounds.hi, clamp=False) > self.max_code

    @property
    def sat_reachable(self) -> bool:
        """Some code in src_bounds lands outside the dst range after rounding."""
        return self.sat_lo or self.sat_hi

    def image(self, b: Bounds | None = None) -> Bounds:
        """Bounds the conversion produces from b, clamped into dst; b defaults to
        src_bounds. Every mode is non-decreasing in its input code, so the image of a
        code interval is the interval between the images of its ends."""
        if b is None:
            b = self.src_bounds
        if b.frac != self.src.frac:
            raise QError(f"image: bounds at {b.frac} fractional bits do not match src {self.src}")
        return Bounds(self.apply(b.lo), self.apply(b.hi), self.dst.frac, self.dst.signed)

    def apply(self, code: int, clamp: bool = True) -> int:
        """The conversion on one src code, as the emitted RTL computes it."""
        acc = _round_code(code, self.shift, self.mode)
        if clamp:
            acc = max(self.min_code, min(self.max_code, acc))
        return acc


def requant(
    src: FmtLike | Bounds,
    dst: FmtLike | int,
    mode: str = "trunc",
    osym: bool = False,
    saturate: bool = True,
) -> Requant:
    """Describe the conversion from src to dst. With saturate=False, a conversion whose
    clamp can trigger is an error rather than a silent range loss. src may be a Bounds,
    in which case the source format is its container and the clamp is judged over the
    codes it names rather than over the whole format. dst may be an int, the target
    frac: src must then be a Bounds, and the target format is the container of its
    image at that frac, so the clamp is unreachable by construction; osym is rejected
    there. That is how a
    derivation names a product format it has no other reason to choose."""
    if mode not in ROUND_MODES:
        raise QError(f"bad round mode {mode!r} (want {', '.join(ROUND_MODES)})")
    if isinstance(src, Bounds):
        sb, fs = src, src.fmt()
    else:
        fs = parse(src)
        sb = Bounds.of(fs)
    if isinstance(dst, bool):
        raise QError(f"requant: bad target {dst!r} (want a format or a frac)")
    if isinstance(dst, int):
        if not isinstance(src, Bounds):
            raise QError(f"requant: a frac target ({dst}) needs a Bounds source, got {fs}")
        if osym:
            raise QError(f"requant: osym is not supported with a frac target ({dst})")
        img_shift = sb.frac - dst
        fd = Bounds(
            _round_code(sb.lo, img_shift, mode), _round_code(sb.hi, img_shift, mode), dst, sb.signed
        ).fmt()
    else:
        fd = parse(dst)
    shift = fs.frac - fd.frac
    min_code = -fd.max_code if (fd.signed and osym) else fd.min_code
    rq = Requant(
        src=fs,
        dst=fd,
        mode=mode,
        osym=bool(osym),
        shift=shift,
        min_code=min_code,
        max_code=fd.max_code,
        src_bounds=sb,
    )
    if not saturate and rq.sat_reachable:
        raise QError(f"requant {fs} -> {fd}: range does not fit and saturation is off")
    return rq
