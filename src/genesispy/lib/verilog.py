"""Verilog text built from generation-time values: literals, extensions, declarations, port
lists, names and expression trees.

Nothing here computes a width or a format; the caller supplies both. Templates reach the module as
the bare name `verilog`, or by importing `genesispy.lib.verilog`.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence


class VerilogError(ValueError):
    """A value that cannot be written in the requested Verilog form."""


def lit(value: int, width: int, signed: bool = True) -> str:
    """A sized Verilog decimal literal.

    Verilog has no sign inside a sized literal, so a negative value is emitted as a
    unary negation of its magnitude. The most negative value of a width is the one
    case where that magnitude does not itself fit: the negation wraps back to the
    same bit pattern, which is the intended value only in a self-determined context
    of that width -- a comparison against an operand of it, or an assignment to a
    target of it. In a wider context the literal sign-extends first and the negation
    then yields the positive magnitude. lit cannot see the context it lands in, so
    the caller owns that.

    The base is decimal because every caller states a numeric bound. Raises if the
    value does not fit the width.
    """
    if width < 1:
        raise VerilogError(f"lit: width must be at least one bit, got {width}")
    lo = -(1 << (width - 1)) if signed else 0
    hi = (1 << (width - 1)) - 1 if signed else (1 << width) - 1
    if not lo <= value <= hi:
        kind = "signed" if signed else "unsigned"
        raise VerilogError(f"lit: {value} does not fit {width} {kind} bits [{lo}, {hi}]")
    if not signed:
        return f"{width}'d{value}"
    return f"{width}'sd{value}" if value >= 0 else f"-{width}'sd{-value}"


def sext(term: str, from_w: int, to_w: int, msb: int | None = None, signed: bool = True) -> str:
    """Widen a term by replicating its sign bit, or by zeros when unsigned.

    msb is the index of the term's sign bit, defaulting to from_w - 1. It is a
    separate argument because a net declared with the binary point in its range,
    [int_bits-1:-frac], has its sign bit at int_bits-1 rather than at width-1.
    """
    if to_w <= from_w:
        raise VerilogError(f"sext: to_w ({to_w}) must exceed from_w ({from_w})")
    if from_w < 1:
        raise VerilogError(f"sext: from_w must be at least one bit, got {from_w}")
    fill = f"{term}[{from_w - 1 if msb is None else msb}]" if signed else "1'b0"
    return f"{{ {{ {to_w - from_w} {{{fill}}} }}, {term} }}"


def pad_low(term: str, n: int) -> str:
    """Append n zero bits below a term's lsb, moving its binary point down."""
    if n < 0:
        raise VerilogError(f"pad_low: n must not be negative, got {n}")
    return term if n == 0 else f"{{ {term}, {{ {n} {{1'b0}} }} }}"


def _range(what: object, signed: bool | None) -> tuple[int, int, bool | None]:
    """The bounds of `what` and its signedness: `signed`, else the format's own."""
    if hasattr(what, "int_bits"):
        hi, lo = what.int_bits - 1, -what.frac  # type: ignore[attr-defined]
        if signed is None:
            signed = what.signed  # type: ignore[attr-defined]
        return hi, lo, signed
    width = int(what)  # type: ignore[call-overload]
    if width < 1:
        raise VerilogError(f"decl: width must be at least one bit, got {width}")
    return width - 1, 0, signed


def decl(
    what: object, signed: bool | None = None, pad: bool = True, col: Iterable[object] = ()
) -> str:
    """The type part of a declaration: the signedness keyword and the bit range.

    Only the type is returned, never a whole declaration, because what precedes it
    differs at every call: a net says "logic", a function says "function static",
    a port says "input". Callers keep their own prefix.

    `what` is a width in bits, or any object exposing int_bits/frac/signed -- a
    fixed-point format -- whose range carries the binary point. With pad set, the unsigned
    form is blanked to the width of "signed" so the ranges line up in a column of
    declarations. `col` holds the other members of that column; both bounds are
    right-justified to the widest among them and `what`, so with pad set every
    member's text has one length.
    """
    hi, lo, signed = _range(what, signed)
    if signed is None:
        raise VerilogError("decl: signed must be given for a plain width")
    bounds = [(hi, lo)] + [_range(w, False)[:2] for w in col]
    hi_w = max(len(str(h)) for h, _ in bounds)
    lo_w = max(len(str(v)) for _, v in bounds)
    rng = f"[{str(hi).rjust(hi_w)}:{str(lo).rjust(lo_w)}]"
    if signed:
        return f"signed {rng}"
    return f"       {rng}" if pad else rng


def port_map(ports: Sequence[tuple[str, str]], indent: int = 8) -> str:
    """The port list of an instance, one `.port (net)` per line, the parens in one column.

    `ports` is a list of (port, net) pairs, in order. Every line but the last ends in
    a comma and no line ends in a newline; the caller writes the closing `);`.
    """
    if not ports:
        raise VerilogError("port_map: no ports")
    names = [p for p, _ in ports]
    dup = sorted({p for p in names if names.count(p) > 1})
    if dup:
        raise VerilogError(f"port_map: port {', '.join(dup)} connected more than once")
    w = max(len(p) for p in names) + 1
    lines = [f"{' ' * indent}{('.' + p).ljust(w)} ({n})" for p, n in ports]
    return ",\n".join(lines)


def idx(base: str, i: int, n: int, min_width: int = 1) -> str:
    """A numbered name from a family of n, zero-padded so the family sorts.

    The width comes from the family's total, not from the index, so every member
    of one family has the same width and a parent that connects by name builds the
    same string. min_width holds a small family to a wider name, for a module whose
    port names should not change shape with the family size; a family that needs
    more digits than that still gets them.
    """
    if n < 1:
        raise VerilogError(f"idx: family size must be at least 1, got {n}")
    if not 0 <= i < n:
        raise VerilogError(f"idx: index {i} outside 0 .. {n - 1}")
    if min_width < 1:
        raise VerilogError(f"idx: min_width must be at least 1, got {min_width}")
    return f"{base}{i:0{max(len(str(n - 1)), min_width)}d}"


def wrap_sum(head: str, expr: str, width: int = 100) -> list[str]:
    """Lines of head and a ' + '-joined sum, broken after a '+' near width columns.
    Continuation lines sit under the first term; a term is never split."""
    parts = expr.split(" + ")
    lines, cur = [], parts[0]
    for part in parts[1:]:
        # the joined line, and the " +" a later break appends to it, have to fit
        if len(head) + len(cur) + len(" + ") + len(part) + len(" +") > width:
            lines.append(cur + " +")
            cur = part
        else:
            cur = f"{cur} + {part}"
    lines.append(cur)
    pad = " " * len(head)
    return [head + lines[0]] + [pad + line for line in lines[1:]]


def parenthesize(terms: list[str], op: str = " + ", leaf: int = 2) -> str:
    """One expression from many terms, parenthesised into a balanced tree.

    Verilog parses a chain of additions left-associatively, which hands synthesis
    a ripple chain. Bisecting the term list until a group holds `leaf` terms or
    fewer gives it a balanced tree instead.

    This cannot change the value. Every term is already at the width of the net
    being assigned, and two's complement addition is associative modulo that
    width, so the grouping is a hint about structure and nothing more.
    """
    if leaf < 1:
        raise VerilogError(f"parenthesize: leaf must be at least 1, got {leaf}")
    if not terms:
        raise VerilogError("parenthesize: no terms")
    if len(terms) <= leaf:
        return op.join(terms)
    mid = (len(terms) + 1) // 2
    return (
        f"({parenthesize(terms[:mid], op, leaf)})"
        f"{op}"
        f"({parenthesize(terms[mid:], op, leaf)})"
    )
