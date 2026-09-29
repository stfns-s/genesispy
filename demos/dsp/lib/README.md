# dsp/lib

`qfmt.py` defines fixed-point formats and derives the widths they imply. The templates import it
through `--py-path lib`; it does not depend on genesispy.

The Verilog text helpers the templates use with it (`lit`, `sext`, `decl`, `idx`) are part of
genesispy, as `genesispy.lib.verilog`; the genesispy user guide, section 11.7, documents them.

## Q format

A format is the triple `(signed, width, frac)`. A stored code `c` denotes the value `c / 2**frac`,
read as two's complement when the format is signed and as a plain magnitude when it is not. The
format fixes the position of the binary point; nothing about it appears in the hardware, which sees
only `width` bits.

Integer bits are `width - frac`. That count may be zero or negative. A signed format holds
`[-2**(int_bits-1), 2**(int_bits-1))` and an unsigned one `[0, 2**int_bits)`: the low bound is
attained exactly, the high bound is one lsb above the largest value.

### Notation

`Qm.n` and `UQm.n` name a format in text. `n` is the number of fractional bits and `m + n` is
the width, so `m` is the integer-bit count. This is the ARM convention: the sign bit is part of
`m`, so a 16-bit signed integer is `Q16.0`. A leading `U` makes the format unsigned.

| Format  | Signed | Width | Integer bits | Fractional bits | lsb                | Range              |
|---------|--------|-------|--------------|-----------------|--------------------|--------------------|
| `Q16.0` | yes    | 16    | 16           | 0               | 1                  | -32768 .. 32767    |
| `UQ8.0` | no     | 8     | 8            | 0               | 1                  | 0 .. 255           |
| `Q4.4`  | yes    | 8     | 4            | 4               | 0.0625 (1/16)      | -8 .. 7.9375       |
| `Q0.8`  | yes    | 8     | 0            | 8               | 0.00390625 (1/256) | -0.5 .. 0.49609375 |
| `Q-1.5` | yes    | 4     | -1           | 5               | 0.03125 (1/32)     | -0.25 .. 0.21875   |

Every bound above is exact. The library computes in `Fraction`, never in floating point, so no
derived bound is off by a rounding error of its own.

### Negative integer bits

Only the width `m + n` is constrained, and only to be at least one bit.

`Q-1.5` is signed, `m + n = 4` bits wide, with `frac = 5`, so a code `c` denotes `c / 32`. Its
four bits weigh -1/4, 1/8, 1/16 and 1/32, the first being the sign bit, so no weight in the word
reaches 1/2. The codes -8 .. 7 denote -1/4 .. 7/32 in steps of 1/32.

`n` may be negative too, giving an lsb above one: `Q6.-2` is four bits stepping by 4. `parse` and
`f_qcvt` accept it.

## qfmt

### Fmt

A frozen dataclass over the three fields, with everything else derived.

| Member                    | Gives                                                        |
|---------------------------|--------------------------------------------------------------|
| `signed`, `width`, `frac` | the fields                                                   |
| `int_bits`                | `width - frac`                                               |
| `lsb`                     | the value of a one-code step, as a `Fraction`                |
| `min_code`, `max_code`    | the extreme codes                                            |
| `min_val`, `max_val`      | the extreme values                                           |
| `to_q()`                  | the `Qm.n` string; `str(f)` is the same                      |
| `decode(code)`            | the value a code denotes; raises if the code is out of range |
| `encode(value)`           | the code for a value; raises unless it is exact and in range |
| `contains(value)`         | whether `encode` would succeed                               |
| `codes()`                 | a `range` over every code                                    |
| `with_frac(n)`            | the same range at `n` fractional bits                        |

`encode` is exact by design: a value that is not a multiple of the lsb is an error, not a rounded
code. `with_frac` widens the word to keep the range, so it refuses to lower `frac`; dropping bits is
`requant`'s job.

```python
Fmt(True, 8, 4).encode(Fraction(3, 2))   -> 24
Fmt(True, 8, 4).decode(24)               -> Fraction(3, 2)
Fmt(True, 8, 4).with_frac(6)             -> Q4.6
```

### Building a format

`parse(x)` accepts an `Fmt` unchanged, a `Qm.n` or `UQm.n` string, or a `(signed, width, frac)`
tuple whose `signed` is a bool or the int 0 or 1. Every operation calls it on its arguments, so a
caller may pass any of the three.

`from_range(lo, hi, frac, signed=None)` returns the narrowest format at `frac` fractional bits that
holds every value in `[lo, hi]`. Signedness follows `lo` unless given. The bounds must be exact
multiples of the lsb.

```python
from_range(Fraction(-1), Fraction(1), 4)   -> Q2.4
```

### Operations

Each returns the narrowest format holding every reachable value, derived from the exact ranges of
the operands rather than from a bound on their widths.

| Call                      | Returns                                                             |
|---------------------------|---------------------------------------------------------------------|
| `mult(a, b, symm, bsymm)` | the product format; `symm` and `bsymm` exclude an operand's minimum |
| `add(fmts)`               | the sum format; the terms must share `frac`, or it raises           |
| `align(fmts)`             | the terms at a common `frac`, and the left shift each one needs     |
| `envelope(fmts)`          | the format covering every input's range and resolution              |
| `bmult(a, b)`             | the product `Bounds` of two `Bounds`                                |
| `badd(bs)`                | the sum `Bounds`; the terms must share `frac`, or it raises         |

```python
mult("Q4.4", "Q4.4")                  -> Q8.8
mult("Q4.4", "Q4.4", symm=True)       -> Q7.8
add(["Q4.4"] * 4)                     -> Q6.4
align(["Q1.6", "Q-1.5", "Q5.2"])      -> ["Q1.6", "Q-1.6", "Q5.6"], [0, 1, 4]
envelope(["Q1.6", "Q5.2"])            -> Q5.6
```

`clog2(n)` returns `ceil(log2(n))`, the bits needed to count `n` distinct values.

`add` raises rather than aligning: terms at different binary points give a wrong sum that the
widths do not show.

`mult(a, b, symm=True)` excludes the products in which `a` takes its most negative code. The saving
is zero or more bits, depending on whether the dropped corner crosses a power-of-two boundary:

```python
mult("Q3.0", "UQ3.0", symm=True)      -> Q6.0, the same width as symm=False
mult("Q2.0", "UQ2.0", symm=True)      -> Q3.0, one bit narrower
mult("Q1.0", "UQ2.0", symm=True)      -> Q1.0, two bits narrower
```

`bsymm` says the same of `b`. Each flag constrains the operand it names and nobody else, and the
call raises if that operand is unsigned, since an unsigned format has no most negative code to
exclude. The two are not redundant: excluding both minima can cross a further power-of-two boundary
that excluding either alone does not, which is worth a bit or two on narrow operands.

```python
mult("Q2.0", "Q2.0")                         -> Q4.0
mult("Q2.0", "Q2.0", symm=True)              -> Q3.0
mult("Q2.0", "Q2.0", bsymm=True)             -> Q3.0
mult("Q2.0", "Q2.0", symm=True, bsymm=True)  -> Q2.0
```

Nothing in `qfmt` checks either precondition at run time -- `functions/f_symm.vpy` enforces it in
the RTL, and a generator that uses `symm` or `bsymm` without it is wrong.

### Bounds

A format is the power-of-two container of a range. `Bounds(lo, hi, frac, signed=True)` is the range
itself: the codes `lo .. hi` a net can reach, at `frac` fractional bits. `mult` and `add` are
`bmult` and `badd` over `Bounds.of` with the result converted by `fmt()`, and a one-step
derivation loses nothing by using them. A derivation with more than one step should carry `Bounds`
and call `fmt()` only where it declares a net, because the next step can widen a container where
it would not widen the range:

```python
Bounds.of("Q1.6")                          -> Bounds(lo=-64, hi=63, frac=6, signed=True)
Bounds.of("Q1.6", symm=True)               -> Bounds(lo=-63, hi=63, frac=6, signed=True)
badd([Bounds(-31, 32, 6)] * 3)             -> Bounds(lo=-93, hi=96, frac=6, signed=True)
badd([Bounds(-31, 32, 6)] * 3).fmt()       -> Q2.6
add([Bounds(-31, 32, 6).fmt()] * 3)        -> Q3.6
```

| Member                 | Gives                                                           |
|------------------------|-----------------------------------------------------------------|
| `lo`, `hi`, `frac`     | the fields; `signed` says how `fmt()` reads them                |
| `Bounds.of(fmt, symm)` | every code of a format, or every code but the most negative one |
| `lo_val`, `hi_val`     | the ends as values                                              |
| `fmt()`                | `from_range` over the ends: the narrowest format holding them   |

`bmult` takes the four corner products of the ends, at `a.frac + b.frac`. `badd` sums the ends.
`requant` with a frac as its target derives the format from the ends, and `Requant.image` carries
a `Bounds` through a conversion; see below. A `Bounds` with `lo > hi`, or
an unsigned one with `lo < 0`, is rejected.

### Requantization

`requant(src, dst, mode="trunc", osymm=False, saturate=True, container=None)` describes the
conversion from one format to another as the integer operations the RTL performs. It returns a
`Requant`. `src` may be a `Bounds` instead of a format; the source format is then its container,
and `sat_reachable` and the `saturate=False` check judge the saturation over the codes the
`Bounds` names rather than over the whole format. `container` overrides that source format, for a
net a caller declares wider than its bounds reach; it needs a `Bounds` `src`, and must be at the
same frac and hold every code the bounds name. `dst` may be an `int`, the target frac: `src` must
then be a `Bounds`, and the target format is the container of its image at that frac, so
saturation is unreachable by construction; `osymm` is rejected there. That is how a derivation
names a product format it has no other reason to choose.

| Field                  | Means                                                                 |
|------------------------|-----------------------------------------------------------------------|
| `shift`                | `src.frac - dst.frac`: bits to drop, or zeros to append when negative |
| `mode`                 | the rounding mode; an emitter builds the carry from it and `shift`    |
| `min_code`, `max_code` | the saturation bounds, in dst codes                                   |
| `src`                  | the source container: the `Bounds`' own, or the `container` given     |
| `src_bounds`           | the source codes judged: all of `src`, or the `Bounds` given          |
| `lossless`             | no bit is ever dropped and no value is ever saturated                 |
| `sat_lo`, `sat_hi`     | the lowest or highest code in `src_bounds` saturates                  |
| `sat_reachable`        | either of the two                                                     |

`apply(code, saturate=True)` runs the conversion on one code exactly as the emitted RTL computes it,
so a testbench or a check can compare against it directly. `image(b=None)` returns the `Bounds` the
conversion produces from `b`, or from `src_bounds` when `b` is omitted, saturated into `dst`: every
rounding mode is non-decreasing in its input code, so the two ends are enough. A `b` at another frac
than `src`, or with a code `src` cannot hold, raises `QError`.

```python
p  = bmult(Bounds.of("Q1.5", symm=True), Bounds.of("Q1.6", symm=True))
                                           -> Bounds(lo=-1953, hi=1953, frac=11, signed=True)
requant(p, "Q1.6", "half_up").image()      -> Bounds(lo=-61, hi=61, frac=6, signed=True)
requant(p, 6, "half_up").dst               -> Q1.6, the container of that image
requant(p.fmt(), "Q1.6", "half_up").sat_reachable  -> True: the container Q1.11 reaches 64
```

`round_consts(shift, mode)` returns the pair of constants the shift adds, one for a
non-negative code and one for a negative one, and is public so that an emitter or a model
outside `qfmt` builds the same carry rather than its own. `half_even` needs the tie correction
`apply` makes afterwards, so the pair alone gives `half_up`.

The five `ROUND_MODES` are `trunc`, `half_up`, `half_even`, `half_away` and `to_zero`. `trunc`
rounds toward minus infinity, which is what an arithmetic right shift already does and so costs
nothing; `half_up` adds half an lsb first; `half_even` adds half an lsb and then steps an exact tie
down to the even neighbour; `half_away` rounds a tie to the larger magnitude; `to_zero` drops the
fraction toward zero. Each is one carry into the kept bits, so all five cost an incrementer and
differ only in what drives its carry-in. Below, `Q4.12 -> Q2.6`, where one dst lsb is 64 src
codes:

| src code | value  | `trunc` | `half_up` | `half_even` | `half_away` | `to_zero` |
|----------|--------|---------|-----------|-------------|-------------|-----------|
| 32       | 1/128  | 0       | 1         | 0           | 1           | 0         |
| 96       | 3/128  | 1       | 2         | 2           | 2           | 1         |
| 160      | 5/128  | 2       | 3         | 2           | 3           | 2         |
| -32      | -1/128 | -1      | 0         | 0           | -1          | 0         |
| -96      | -3/128 | -2      | -1        | -2          | -2          | -1        |
| -160     | -5/128 | -3      | -2        | -2          | -3          | -2        |

`osymm` puts a signed output's low end at `-max_code` instead of `min_code`, giving a range
symmetric about zero. `saturate=False` turns a conversion that can saturate into an error,
so a generator that means to lose no range says so and finds out.

### Errors

Everything the library rejects raises `QError`, a subclass of `ValueError`, with the offending
value in the message. A template catches it and reports it as a generation error.

```text
bad Q format 'Q1' (want Qm.n or UQm.n)
badd: terms have different fractional bits [4, 5]; align first
mult: symm needs a signed first operand, got UQ4.4
requant: osymm needs a signed target, got UQ4.4
requant Q4.4 -> Q2.4: range does not fit and saturation is off
```

Rejected: a width below one bit; a string that is not `Qm.n` or `UQm.n`; `add` or `badd` over
terms whose `frac` disagree, and `badd` or `align` over no terms; `mult(..., symm=True)` or
`Bounds.of(..., symm=True)` on an unsigned format, and `mult(..., bsymm=True)` on an unsigned
second operand; `with_frac` to fewer fractional bits; `decode` of a code outside the range;
`encode` of a value the format cannot hold exactly; `from_range` over an empty range, a negative
`lo` for an unsigned format, or bounds that are not multiples of the lsb; `requant` with a mode
outside `ROUND_MODES`; `requant` with `saturate=False` to a format that cannot hold the source
range; `requant` to a target that is neither a format nor a frac, a `bool` included; `requant` to a
frac from a format rather than a `Bounds`, or with `osymm`; `requant` with `osymm` to an unsigned
target, which has no most negative code to exclude; `requant` with a `container` from a format
rather than a `Bounds`, or a `container` at another `frac` than the source or not holding its
codes; `image` of a `Bounds` at another `frac` than `src`; a `Bounds` with `lo > hi`, or an
unsigned one with `lo < 0`; `clog2(0)`.

## Using the library from a template

Import in the Python prologue, then call in a backtick expression. `functions/f_qcvt.vpy` derives its
whole datapath from one `requant` call. This is its prologue, verbatim:

```systemverilog
//; from genesispy.lib.verilog import decl, lit, sext
//; import qfmt
//; h          = self.include_params
//; func_name  = h.get('func_name', 'f_qcvt')
//; q_in       = h.get('q_in',  'Q4.4')
//; q_out      = h.get('q_out', 'Q2.2')
//; round_mode = h.get('round_mode', 'trunc')
//; osymm      = h.get('osymm', 0)
//; lifetime   = h.get('lifetime', 'static')
//; src_lo     = h.get('src_lo', None)      # lowest source code that arrives; None: f_in.min_code
//; src_hi     = h.get('src_hi', None)      # highest; None: f_in.max_code
//; saturate   = h.get('saturate', 1)       # 0: reject a configuration whose clamp is reachable
//; def q_or_error(fn, *args):
//;     try:
//;         return fn(*args)
//;     except qfmt.QError as e:
//;         error(f"{func_name}: {e}")
//; # enddef
//; f_in     = q_or_error(qfmt.parse, q_in)
//; f_out    = q_or_error(qfmt.parse, q_out)
//; bounded  = src_lo is not None or src_hi is not None
//; lo_c     = f_in.min_code if src_lo is None else int(src_lo)
//; hi_c     = f_in.max_code if src_hi is None else int(src_hi)
//; if lo_c < f_in.min_code or hi_c > f_in.max_code or lo_c > hi_c:
//;     error(f"{func_name}: source codes {lo_c} .. {hi_c} do not lie in {f_in} "
//;         f"({f_in.min_code} .. {f_in.max_code})")
//; # endif
//; src      = q_or_error(qfmt.Bounds, lo_c, hi_c, f_in.frac, f_in.signed)
//; rq       = q_or_error(qfmt.requant, src, f_out, round_mode, bool(osymm))
//; # A clamp end is emitted where a source code can reach it. Without source bounds both
//; # are emitted, so a caller that gives none gets the output it always got.
//; sat_lo, sat_hi = rq.sat_lo, rq.sat_hi
//; if not saturate and (sat_lo or sat_hi):
//;     ends = ' and '.join(e for e, hit in (('low', sat_lo), ('high', sat_hi)) if hit)
//;     error(f"{func_name}: {f_in} -> {f_out} under {round_mode} clamps at the {ends} end over "
//;         f"source codes {lo_c} .. {hi_c}, and saturate=0 forbids a clamp")
//; # endif
//; emit_lo  = sat_lo or not bounded
//; emit_hi  = sat_hi or not bounded
//; iwidth   = f_in.width
//; owidth   = f_out.width
//; shift    = rq.shift
//; acc_w    = max(iwidth + abs(shift) + 2, owidth + (0 if f_out.signed else 1))
```

`rq` then carries what the RTL needs -- `rq.shift`, `rq.min_code`, `rq.max_code`, and `rq.sat_lo` /
`rq.sat_hi` saying which clamp end a source code can actually reach -- and the body below it emits a
shift in whichever direction `shift` calls for, the rounding carry the mode asks for, and only the
clamp ends `sat_lo` and `sat_hi` report as reachable. Rounding is a carry into the kept bits rather
than a constant added before the shift, so the template builds the carry expression itself and
`Requant` holds no rounding constant. Read the file for the body; it is short, and copying it here
is how this section came to describe something the file never did.

`acc_w` is the one derived width worth explaining. The accumulator has to hold the shifted input
before the clamp, hence `iwidth + abs(shift) + 2`; and it has to hold the clamp bounds themselves as
signed literals, hence `owidth` for a signed output and `owidth + 1` for an unsigned one, whose
largest code needs a bit above the sign.

`q_or_error` is the idiom worth copying: a `QError` carries a message naming the bad format, and
wrapping the call turns it into a generation error that names the function too, instead of a Python
traceback.

## Tests

```sh
make pytest                  # or: python3 -m pytest lib/tests
```

`lib/tests/conftest.py` is the whole of the wiring: it puts `lib/` on `sys.path`. No simulator and
no generator is involved.

`lib/tests/test_qfmt.py` cross-checks the algebra against `Fraction` arithmetic over every code
of every format up to six bits wide, so a claim that a result format holds every reachable value
is checked by enumerating them. It also pins `requant`'s constants to what `f_qcvt` emits.
