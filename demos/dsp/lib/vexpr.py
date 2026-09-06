"""Verilog expression text, built from generation-time values.

Nothing here computes a width or a format; that is qfmt's job. These helpers turn a Python
value into the Verilog that denotes it, so a template does not spell the notation out.
"""

from __future__ import annotations


class VExprError(ValueError):
    """A value that cannot be written in the requested Verilog form."""


def lit(value: int, width: int, signed: bool = True) -> str:
    """A sized Verilog decimal literal.

    A negative value is a unary negation of its magnitude, so the most negative code of a width
    is correct only in a self-determined context of that width. Raises if the value does not fit.
    """
    if width < 1:
        raise VExprError(f"lit: width must be at least one bit, got {width}")
    lo = -(1 << (width - 1)) if signed else 0
    hi = (1 << (width - 1)) - 1 if signed else (1 << width) - 1
    if not lo <= value <= hi:
        kind = "signed" if signed else "unsigned"
        raise VExprError(f"lit: {value} does not fit {width} {kind} bits [{lo}, {hi}]")
    if not signed:
        return f"{width}'d{value}"
    return f"{width}'sd{value}" if value >= 0 else f"-{width}'sd{-value}"


def sext(term: str, from_w: int, to_w: int, msb: int | None = None, signed: bool = True) -> str:
    """Widen a term by replicating its sign bit, or by zeros when unsigned.

    msb is the index of the sign bit, default from_w - 1; a net declared [int_bits-1:-frac] has
    it at int_bits-1, not at width-1. Raises unless to_w > from_w >= 1.
    """
    if to_w <= from_w:
        raise VExprError(f"sext: to_w ({to_w}) must exceed from_w ({from_w})")
    if from_w < 1:
        raise VExprError(f"sext: from_w must be at least one bit, got {from_w}")
    fill = f"{term}[{from_w - 1 if msb is None else msb}]" if signed else "1'b0"
    return f"{{ {{ {to_w - from_w} {{{fill}}} }}, {term} }}"


def pad_low(term: str, n: int) -> str:
    """Append n zero bits below a term's lsb, moving its binary point down.

    n == 0 returns the term unchanged. Raises if n is negative.
    """
    if n < 0:
        raise VExprError(f"pad_low: n must not be negative, got {n}")
    return term if n == 0 else f"{{ {term}, {{ {n} {{1'b0}} }} }}"


def decl(what: object, signed: bool | None = None, pad: bool = True) -> str:
    """The type part of a declaration: the signedness keyword and the bit range, no prefix.

    `what` is a width in bits or a qfmt.Fmt, whose range carries the binary point. With pad the
    unsigned form is blanked to the width of "signed", so a column of declarations lines up.
    """
    if hasattr(what, "int_bits"):
        hi, lo = what.int_bits - 1, -what.frac  # type: ignore[attr-defined]
        if signed is None:
            signed = what.signed  # type: ignore[attr-defined]
    else:
        width = int(what)  # type: ignore[call-overload]
        if width < 1:
            raise VExprError(f"decl: width must be at least one bit, got {width}")
        hi, lo = width - 1, 0
    if signed is None:
        raise VExprError("decl: signed must be given for a plain width")
    if signed:
        return f"signed [{hi}:{lo}]"
    return f"       [{hi}:{lo}]" if pad else f"[{hi}:{lo}]"


def parenthesize(terms: list[str], op: str = " + ", leaf: int = 2) -> str:
    """One expression from many terms, parenthesised into a balanced tree.

    Bisects until a group holds leaf terms or fewer, giving synthesis a tree rather than the
    left-associative ripple chain. The value is unchanged.
    """
    if leaf < 1:
        raise VExprError(f"parenthesize: leaf must be at least 1, got {leaf}")
    if not terms:
        raise VExprError("parenthesize: no terms")
    if len(terms) <= leaf:
        return op.join(terms)
    mid = (len(terms) + 1) // 2
    return (
        f"({parenthesize(terms[:mid], op, leaf)})"
        f"{op}"
        f"({parenthesize(terms[mid:], op, leaf)})"
    )


def idx(base: str, i: int, n: int, min_width: int = 1) -> str:
    """A numbered name from a family of n, zero-padded so the family sorts.

    The width comes from the family total, not the index, so every member matches and a parent
    connecting by name builds the same string. min_width holds a small family to a wider name.
    """
    if n < 1:
        raise VExprError(f"idx: family size must be at least 1, got {n}")
    if not 0 <= i < n:
        raise VExprError(f"idx: index {i} outside 0 .. {n - 1}")
    if min_width < 1:
        raise VExprError(f"idx: min_width must be at least 1, got {min_width}")
    return f"{base}{i:0{max(len(str(n - 1)), min_width)}d}"
