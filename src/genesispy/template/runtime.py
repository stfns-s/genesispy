"""Runtime helpers used by GENERATED .py module files.

The emitter (``template.emitter``) writes Python files that import from this
module.  Generated files use :class:`UniqueModule` and :class:`UserMixin` as
base classes (re-exported here for ergonomics) and the line-map registry
below to translate Python tracebacks back to ``.vpy`` source coordinates.
"""

from __future__ import annotations

import json
import re
import traceback
from typing import Dict, Tuple

from genesispy.unique_module import UniqueModule  # re-export
from genesispy.user_lib import UserMixin  # re-export

__all__ = [
    "UniqueModule",
    "UserMixin",
    "StrCallable",
    "LINE_MAP",
    "register_line_map",
    "remap_traceback",
    "build_line_map",
    "clear_line_maps",
]


class StrCallable(str):
    """A string that's also callable (returns self).

    Lets users write either ``\\`mname\\``` or ``\\`mname()\\``` in .vpy
    backtick contexts; both produce the same Verilog name.
    """

    def __call__(self) -> "StrCallable":
        return self


# Generated-file path -> {generated lineno: (source .vpy path, source lineno)}
LINE_MAP: Dict[str, Dict[int, Tuple[str, int]]] = {}


def register_line_map(
    generated_path: str, mapping: Dict[int, Tuple[str, int]]
) -> None:
    """Record line mapping for ``generated_path``.

    Subsequent calls to :func:`remap_traceback` consult this side table to
    rewrite ``File "<gen>.py", line N`` frames to point at the original
    ``.vpy`` source location.
    """
    LINE_MAP[generated_path] = dict(mapping)


def clear_line_maps() -> None:
    """Drop every registered line map. Called by :func:`cache.clear_all`."""
    LINE_MAP.clear()


# Anchor at line start (allowing the emitter's 8-space body indent) and
# require the directive to be the entire line, so substrings inside
# generated string literals can't masquerade as a directive. The path
# token is a JSON-encoded string (json.dumps) so embedded quotes /
# backslashes round-trip via json.loads.
_LINE_DIRECTIVE = re.compile(r'\s*#\s*line\s+(\d+)\s+(".*")\s*')


def build_line_map(generated_source: str) -> Dict[int, Tuple[str, int]]:
    """Walk ``generated_source`` and harvest a {gen_lineno -> (vpy, vpy_lineno)} map.

    The parser sprinkles ``# line N "file.vpy"`` directives before each
    translated statement.  Each such directive applies to the *following*
    code lines (until the next directive)."""
    mapping: Dict[int, Tuple[str, int]] = {}
    cur_file: str | None = None
    cur_line: int | None = None
    for idx, line in enumerate(generated_source.splitlines(), start=1):
        m = _LINE_DIRECTIVE.fullmatch(line)
        if m:
            cur_line = int(m.group(1))
            try:
                cur_file = json.loads(m.group(2))
            except json.JSONDecodeError:
                cur_file = m.group(2).strip('"')
            continue
        if cur_file is not None and cur_line is not None:
            mapping[idx] = (cur_file, cur_line)
    return mapping


def remap_traceback(exc: BaseException) -> str:
    """Format a traceback string with .vpy source locations substituted in."""
    tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    out: list[str] = []
    frame_re = re.compile(r'^(\s*)File "([^"]+)", line (\d+)(.*)$')
    for chunk in tb_lines:
        for line in chunk.splitlines(keepends=True):
            m = frame_re.match(line.rstrip("\n"))
            if m:
                indent, path, lineno_s, rest = m.groups()
                lineno = int(lineno_s)
                if path in LINE_MAP and lineno in LINE_MAP[path]:
                    src, src_lineno = LINE_MAP[path][lineno]
                    out.append(
                        f'{indent}File "{src}", line {src_lineno}{rest}'
                        f"  [generated: {path}:{lineno}]\n"
                    )
                    continue
            out.append(line if line.endswith("\n") else line + "\n")
    return "".join(out)
