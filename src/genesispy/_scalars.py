"""Scalar coercion for string-shaped values.

``coerce_scalar`` is the permissive rule for ``-parameter NAME=VALUE``;
``coerce_canonical`` is the lossless rule ``genesispy-xml2json`` applies to
XML text. Both live in this leaf module so config_handler and the tools
share them without importing each other.

Behaviour: stricter than Python's ``float()`` -- strings without a decimal
point or exponent character are not parsed as floats. This means
``"inf"``, ``"nan"``, ``"infinity"`` round-trip as strings rather than
silently becoming ``float('inf')`` / ``float('nan')``.
"""

from __future__ import annotations

import re
from typing import Any

_CANONICAL_INT_RE = re.compile(r"-?(0|[1-9][0-9]*)")
_CANONICAL_FLOAT_RE = re.compile(r"-?(0|[1-9][0-9]*)\.[0-9]+")


def coerce_scalar(s: Any) -> Any:
    """Coerce a string scalar to int/float/bool when unambiguous.

    Non-strings pass through. Empty / whitespace-only strings are kept
    as the original string. Recognised:
      * ``"true"`` / ``"false"`` (case-insensitive) -> ``bool``.
      * Optional sign + digits -> ``int``.
      * Strings containing ``.``, ``e``, or ``E`` that ``float()``
        accepts -> ``float``.
    Anything else returns the input unchanged.
    """
    if not isinstance(s, str):
        return s
    stripped = s.strip()
    if stripped == "":
        return s
    low = stripped.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if stripped.lstrip("+-").isdigit():
        try:
            return int(stripped)
        except ValueError:
            pass
    if any(c in stripped for c in ".eE"):
        try:
            return float(stripped)
        except ValueError:
            pass
    return s


def coerce_canonical(s: Any) -> Any:
    """Type a string only when the number reads back as the same text.

    ``"true"`` / ``"false"`` -> ``bool``; a decimal integer without leading
    zeros or sign prefix ``+`` -> ``int``; ``digits.digits`` -> ``float``.
    ``"010"``, ``"1e3"``, ``"+5"`` and everything else stay strings, so an
    XML value reaches the template as XML::Simple handed it to Genesis2
    unless typing it is lossless.
    """
    if not isinstance(s, str):
        return s
    if s == "true":
        return True
    if s == "false":
        return False
    if _CANONICAL_INT_RE.fullmatch(s):
        return int(s)
    if _CANONICAL_FLOAT_RE.fullmatch(s):
        return float(s)
    return s
