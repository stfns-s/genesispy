"""Input/output extension map for genesispy.

A genesispy template input has an extension (``.vpy``, ``.svpy``, or any
user-registered extension) that maps to an output extension (``.v``, ``.sv``,
``.sdc``, etc.). The mapping is configured via the repeatable
``--extension EXT_IN=EXT_OUT[:nolist][:comment=PREFIX]`` CLI flag or a template's
``register_extension`` call, merged onto :data:`DEFAULT_EXTENSION_MAP`, and held with
each extension's listing flag and comment prefix by :class:`ExtensionRegistry`.

The :func:`parse_extension_spec` helper turns one ``--extension`` value into a
normalised :class:`ExtensionSpec` (extensions lowercased, with a leading dot on each
side). It raises :class:`argparse.ArgumentTypeError` on malformed input so it plugs
into ``argparse(type=...)`` directly.
"""

from __future__ import annotations

import argparse
from typing import Dict, Iterable, NamedTuple, Optional, Tuple


DEFAULT_EXTENSION_MAP: Dict[str, str] = {
    ".vpy": ".v",
    ".svpy": ".sv",
}


def _normalise_ext(ext: str, *, side: str, where: str) -> str:
    """``where`` opens the error message: the flag argument or the registered extension."""
    if not ext:
        raise argparse.ArgumentTypeError(f"{where}: empty {side} extension")
    ext = ext.lower()
    if ext == ".":
        raise argparse.ArgumentTypeError(f"{where}: {side} extension is just '.'")
    if not ext.startswith("."):
        ext = "." + ext
    return ext


_COMMENT_OPT = ":comment="


class ExtensionSpec(NamedTuple):
    in_ext: str
    out_ext: str
    listed: bool = True
    comment: Optional[str] = None

    def __str__(self) -> str:
        """The spec in ``--extension`` form."""
        text = f"{self.in_ext}={self.out_ext}"
        if not self.listed:
            text += ":nolist"
        if self.comment is not None:
            text += f"{_COMMENT_OPT}{self.comment}"
        return text


def parse_extension_spec(raw: str) -> ExtensionSpec:
    """Parse ``EXT_IN=EXT_OUT[:nolist][:comment=PREFIX]`` into an :class:`ExtensionSpec`.

    Both extensions are lowercased and gain a leading dot if missing. Everything
    after ``:comment=`` is the prefix, verbatim. Raises
    :class:`argparse.ArgumentTypeError` for malformed input.
    """
    head, sep, prefix = raw.partition(_COMMENT_OPT)
    comment: Optional[str] = None
    if sep:
        if not prefix:
            raise argparse.ArgumentTypeError(
                f"--extension {raw!r}: empty comment prefix"
            )
        comment = prefix
    pair, *options = head.split(":")
    if "=" not in pair:
        raise argparse.ArgumentTypeError(
            f"--extension {raw!r}: expected EXT_IN=EXT_OUT[:nolist][:comment=PREFIX]"
        )
    listed = True
    for opt in options:
        if opt != "nolist":
            raise argparse.ArgumentTypeError(
                f"--extension {raw!r}: unknown suffix {opt!r}"
            )
        if not listed:
            raise argparse.ArgumentTypeError(
                f"--extension {raw!r}: repeated ':nolist'"
            )
        listed = False
    in_part, _, out_part = pair.partition("=")
    where = f"--extension {raw!r}"
    in_ext = _normalise_ext(in_part.strip(), side="input", where=where)
    out_ext = _normalise_ext(out_part.strip(), side="output", where=where)
    return ExtensionSpec(in_ext, out_ext, listed, comment)


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


class ExtensionRegistry:
    """Input -> output extension map plus per-extension listing and comment settings.

    ``map`` is mutated in place and never rebound, so holders of it see later
    registrations.
    """

    def __init__(self) -> None:
        self.map: Dict[str, str] = {}
        self._meta: Dict[str, Tuple[bool, Optional[str]]] = {}

    @classmethod
    def from_specs(cls, specs: Iterable[ExtensionSpec]) -> "ExtensionRegistry":
        """Build a registry from the defaults overridden by ``specs``.

        Raises ValueError when two specs for one input extension differ.
        """
        specs = list(specs)
        seen: Dict[str, ExtensionSpec] = {}
        for spec in specs:
            if seen.setdefault(spec.in_ext, spec) != spec:
                raise ValueError(
                    f"--extension: conflicting settings for {spec.in_ext!r}: "
                    f"{str(seen[spec.in_ext])!r} vs {str(spec)!r}"
                )
        reg = cls()
        reg.map.update(build_extension_map((s.in_ext, s.out_ext) for s in specs))
        for in_ext in reg.map:
            reg._meta[in_ext] = (True, None)
        for spec in specs:
            reg._meta[spec.in_ext] = (spec.listed, spec.comment)
        return reg

    def register(
        self,
        in_ext: str,
        out_ext: str,
        *,
        listed: bool = True,
        comment: Optional[str] = None,
    ) -> None:
        """Add a mapping; an identical existing one is a no-op.

        Raises ValueError for a different existing mapping or an empty comment.
        """
        if comment == "":
            raise ValueError(f"extension {in_ext!r}: empty comment prefix")
        try:
            where = f"extension {in_ext!r} -> {out_ext!r}"
            in_ext = _normalise_ext(in_ext, side="input", where=where)
            out_ext = _normalise_ext(out_ext, side="output", where=where)
        except argparse.ArgumentTypeError as exc:
            raise ValueError(str(exc)) from exc
        new = (out_ext, listed, comment)
        if in_ext in self.map:
            old = (self.map[in_ext], *self._meta[in_ext])
            if old != new:
                raise ValueError(
                    f"extension {in_ext!r} is already mapped as {old}; cannot register {new}"
                )
            return
        self.map[in_ext] = out_ext
        self._meta[in_ext] = (listed, comment)

    def listed(self, in_ext: Optional[str]) -> bool:
        """Return False only for a mapped extension registered ``nolist``."""
        return self._meta.get(in_ext, (True, None))[0] if in_ext else True

    def comment(self, in_ext: Optional[str]) -> Optional[str]:
        """Return the comment prefix of a mapped extension, else None."""
        return self._meta.get(in_ext, (True, None))[1] if in_ext else None


__all__ = [
    "DEFAULT_EXTENSION_MAP",
    "ExtensionRegistry",
    "ExtensionSpec",
    "parse_extension_spec",
    "build_extension_map",
]
