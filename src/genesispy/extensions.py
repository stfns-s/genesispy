"""Input/output extension map for genesispy.

A genesispy template input has an extension (``.vpy``, ``.svpy``, or any
user-registered extension) that maps to an emitted-Verilog output extension
(``.v``, ``.sv``, etc.). The mapping is configured via the repeatable
``--extension EXT_IN=EXT_OUT`` CLI flag and merged onto
:data:`DEFAULT_EXTENSION_MAP`.

The :func:`parse_extension_spec` helper turns a single ``EXT_IN=EXT_OUT``
string into a normalised ``(in_ext, out_ext)`` pair (lowercased, with a
leading dot on each side). It raises :class:`argparse.ArgumentTypeError`
on malformed input so it plugs into ``argparse(type=...)`` directly.
"""

from __future__ import annotations

import argparse
from typing import Dict, Iterable, List, Tuple


DEFAULT_EXTENSION_MAP: Dict[str, str] = {
    ".vpy": ".v",
    ".svpy": ".sv",
}


def _normalise_ext(ext: str, *, side: str, raw: str) -> str:
    if not ext:
        raise argparse.ArgumentTypeError(
            f"--extension {raw!r}: empty {side} extension"
        )
    ext = ext.lower()
    if ext == ".":
        raise argparse.ArgumentTypeError(
            f"--extension {raw!r}: {side} extension is just '.'"
        )
    if not ext.startswith("."):
        ext = "." + ext
    return ext


def parse_extension_spec(raw: str) -> Tuple[str, str]:
    """Parse ``EXT_IN=EXT_OUT`` into a ``(in_ext, out_ext)`` pair.

    Both sides are lowercased and prefixed with a leading dot if missing.
    Raises :class:`argparse.ArgumentTypeError` for malformed input.
    """
    if "=" not in raw:
        raise argparse.ArgumentTypeError(
            f"--extension {raw!r}: expected EXT_IN=EXT_OUT"
        )
    in_part, _, out_part = raw.partition("=")
    in_ext = _normalise_ext(in_part.strip(), side="input", raw=raw)
    out_ext = _normalise_ext(out_part.strip(), side="output", raw=raw)
    return in_ext, out_ext


def build_extension_map(
    pairs: Iterable[Tuple[str, str]],
) -> Dict[str, str]:
    """Merge ``pairs`` over :data:`DEFAULT_EXTENSION_MAP`.

    Conflicts among ``pairs`` themselves raise :class:`ValueError`
    (last-wins is too surprising for users hand-typing CLI flags).
    Conflicts with the defaults silently override -- that's how a user
    redirects ``.vpy`` to ``.sv`` (e.g. via ``-sv``).
    """
    result: Dict[str, str] = dict(DEFAULT_EXTENSION_MAP)
    user_seen: Dict[str, str] = {}
    for in_ext, out_ext in pairs:
        if in_ext in user_seen and user_seen[in_ext] != out_ext:
            raise ValueError(
                f"--extension: conflicting mappings for {in_ext!r}: "
                f"{user_seen[in_ext]!r} vs {out_ext!r}"
            )
        user_seen[in_ext] = out_ext
        result[in_ext] = out_ext
    return result


def allowed_inputs(extension_map: Dict[str, str]) -> List[str]:
    """Return the list of accepted input extensions (sorted)."""
    return sorted(extension_map.keys())


__all__ = [
    "DEFAULT_EXTENSION_MAP",
    "parse_extension_spec",
    "build_extension_map",
    "allowed_inputs",
]
