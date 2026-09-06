"""Fixed-point width and range helpers for the pyinclude_examples demo.

pyinclude'd into a module's namespace, so every name here is callable as a
bare name for the rest of that module. Nothing in this file may reference
``self``: a pyinclude'd file has no module (user-guide section 11.3).
"""

from __future__ import annotations

import math

# Refuse to build an accumulator wider than this; a guard on TERM_W/NTERMS.
ACC_W_MAX = 32


def clog2(n: int) -> int:
    """Bits needed to index ``n`` values, floored at 1 so a width is never 0."""
    if n < 1:
        raise ValueError(f"clog2: n must be >= 1, got {n}")
    return max(1, math.ceil(math.log2(n)))


def acc_width(term_w: int, nterms: int) -> int:
    """Width of a sum of ``nterms`` signed terms of ``term_w`` bits each."""
    return term_w + clog2(nterms)


def sat_bounds(width: int) -> tuple[int, int]:
    """Inclusive (min, max) codes of a signed two's-complement word."""
    return -(1 << (width - 1)), (1 << (width - 1)) - 1
