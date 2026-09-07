"""argparse helpers shared by the ``genesispy`` and ``gvpy`` command lines:
deprecated-alias registration and the comment-prefix validators."""

from __future__ import annotations

import argparse

from . import reporting


# Module-level guard so each deprecated alias warns at most once per process.
_warned_aliases: set = set()


def _reset_deprecation_warnings() -> None:
    """Clear the one-time-per-flag deprecation guard. Test hook."""
    _warned_aliases.clear()


def _emit_deprecation(prog: str, old: str, new: str) -> None:
    if old in _warned_aliases:
        return
    _warned_aliases.add(old)
    reporting.warning(f"{prog}: {old} is deprecated; use {new}")


class _DeprecatedAliasAction(argparse.Action):
    """Deprecated alias for another flag: warns once, then stores, appends or
    sets True according to ``kind`` (``"store"`` | ``"append"`` |
    ``"store_true"``)."""

    def __init__(self, option_strings, dest, *, new_flag, kind="store",
                 prog="genesispy", **kw):
        self._new = new_flag
        self._prog = prog
        self._kind = kind
        kw.setdefault("default", argparse.SUPPRESS)
        if kind == "store_true":
            kw["nargs"] = 0
        super().__init__(option_strings, dest, help=argparse.SUPPRESS, **kw)

    def __call__(self, parser, namespace, values, option_string=None):
        _emit_deprecation(self._prog, option_string, self._new)
        if self._kind == "store_true":
            setattr(namespace, self.dest, True)
        elif self._kind == "append":
            items = list(getattr(namespace, self.dest, None) or [])
            items.append(values)
            setattr(namespace, self.dest, items)
        else:
            setattr(namespace, self.dest, values)


def _add_deprecated_alias(
    parser_or_group,
    old_flags,
    new_flag: str,
    dest: str,
    *,
    kind: str = "store",
    prog: str = "genesispy",
    arg_type=None,
    choices=None,
    metavar=None,
) -> None:
    """Register one or more deprecated aliases that forward to ``dest``.

    ``kind`` is ``"store"``, ``"append"`` or ``"store_true"``. Each old flag
    emits a one-time stderr warning naming ``new_flag``. ``help`` is always
    SUPPRESS so the alias is hidden from both the ``usage:`` synopsis and
    the body of ``--help``.
    """
    if isinstance(old_flags, str):
        old_flags = [old_flags]
    extras = {}
    if arg_type is not None:
        extras["type"] = arg_type
    if choices is not None:
        extras["choices"] = choices
    if metavar is not None:
        extras["metavar"] = metavar
    if kind not in ("store", "append", "store_true"):
        raise ValueError(f"_add_deprecated_alias: unknown kind {kind!r}")
    if kind == "store_true":
        # store_true has no value, so type/choices/metavar are nonsensical.
        extras = {}

    parser_or_group.add_argument(
        *old_flags,
        action=_DeprecatedAliasAction,
        dest=dest,
        new_flag=new_flag,
        kind=kind,
        prog=prog,
        **extras,
    )


def _comment_arg(raw: str) -> str:
    """argparse ``type=`` validator for ``--source-comment``.

    Rejects empty/whitespace-only values: an empty prefix collapses the
    directive sentinel to bare ``;`` and emits banner lines without any
    comment marker.
    """
    if not raw.strip():
        raise argparse.ArgumentTypeError(
            f"--source-comment {raw!r}: empty/whitespace-only comment prefix"
        )
    return raw


def _output_comment_arg(raw: str):
    """argparse ``type=`` for ``--output-comment``.

    A ``,`` splits the value into ``(open, close)`` block delimiters; both
    halves must be non-empty. Without a ``,`` the value is a line prefix.
    Empty/whitespace-only values (or halves) are rejected.
    """
    if "," in raw:
        open_d, _, close_d = raw.partition(",")
        if not open_d.strip() or not close_d.strip():
            raise argparse.ArgumentTypeError(
                f"--output-comment {raw!r}: both OPEN and CLOSE must be "
                f"non-empty (form 'OPEN,CLOSE')"
            )
        return (open_d, close_d)
    if not raw.strip():
        raise argparse.ArgumentTypeError(
            f"--output-comment {raw!r}: empty/whitespace-only comment prefix"
        )
    return raw
