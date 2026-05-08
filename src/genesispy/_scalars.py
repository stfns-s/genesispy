"""Shared scalar coercion used by config_handler and json_io.

Single source of truth for parsing string-shaped scalars (from XML, JSON,
or CLI ``-parameter NAME=VALUE``) into native Python ``int``/``float``/
``bool``. Lives in its own leaf module so neither caller introduces an
import-time dependency on the other.

Behaviour: stricter than Python's ``float()`` — strings without a decimal
point or exponent character are not parsed as floats. This means
``"inf"``, ``"nan"``, ``"infinity"`` round-trip as strings rather than
silently becoming ``float('inf')`` / ``float('nan')``.
"""

from __future__ import annotations

from typing import Any


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
