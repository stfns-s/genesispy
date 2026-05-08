"""Parser for ``.vpy`` / ``.svpy`` Genesis templates.

A Genesis template is Verilog (or SystemVerilog) source with two extensions:

* Lines whose first non-whitespace characters are ``//;`` are *Python* lines.
  The remainder of the line is Python source.
* Within ordinary Verilog lines, text enclosed in matched back-ticks is a
  Python expression to be interpolated, e.g. ``[\\`$W-1\\`:0]``.

This module ports ``Genesis2::Manager::parse_file`` (Manager.pm lines 721-937)
to Python.  It does **not** include the surrounding module wrapper -- that
is the job of the Wave-2 emitter.  ``parse_vpy`` returns just the body of
``UniqueModule.execute()``: a sequence of Python statements that, when
exec'd with ``self`` bound to the module, produce the desired Verilog via
``self.emit("...")`` calls.

Indentation convention
----------------------

Each ``//;`` line carries its own indent.  After the ``//;`` prefix and one
optional space are stripped, the remaining leading-whitespace (in units of
four spaces) gives the *base* indent of that Python statement.

Following plain-Verilog (``self.emit``) lines are indented at the base
indent of the most recent ``//;`` line, plus one extra level if that line
ended with a colon (i.e. opened a Python block such as ``for``, ``if``,
``while``, ``def``, ``class``, ``try``, ``with``).  Block close is signalled
implicitly by the user writing the *next* ``//;`` line at a lower indent
(typically a sentinel comment such as ``//; # endfor``).

Example::

    //; if cond:
    //;     for i in range(N):
    emit-line-here
    //;     # endfor
    //; # endif

becomes (modulo line comments)::

    if cond:
        for i in range(N):
            self.emit("emit-line-here")
        # endfor
    # endif

Legacy extensions
-----------------

Files ending in ``.vp`` or ``.svp`` (the original Genesis2 extensions) are
rejected with :class:`ParseError`; users must rename to ``.vpy``/``.svpy``.
"""

from __future__ import annotations

import json
import os
from typing import List

from genesispy.errors import ParseError


__all__ = ["parse_vpy", "ParseError"]


_PRL_ESC = "//;"


def _is_block_opener(stripped: str) -> bool:
    """Return True if a Python source line opens a new indented block.

    The check is "ends with ``:`` after stripping a trailing ``#``-comment,
    where ``#`` and quotes inside ``'``/``"`` strings are honoured via a
    single-char quote toggle". Sufficient for ``//;`` lines, which are
    single-line statements by convention.

    Known limitations (no observed in-the-wild misclassification, but
    documented for posterity):
    - Triple-quoted strings whose body contains a ``"`` or ``'`` are
      tracked as alternating toggles, not as paired triples. A balanced
      triple-quoted literal still ends with the same toggle parity it
      started with, so endings are detected correctly; pathological
      content inside the literal could in principle confuse the strip.
    - f-string ``{...}`` interpolations are scanned as plain string body;
      a ``"`` or ``'`` *inside* the braces would invert the toggle.
    - Raw-string prefixes (``r"..."``, ``b"..."``) are not specially
      recognised; backslash-escapes inside strings are treated as plain
      characters (so ``"\\""`` toggles in_d twice — fine in practice).

    Replacing this with a ``tokenize``-based check would handle every
    edge case but raises on incomplete syntax (multi-line continuations
    not seen by a single ``//;`` line). The current heuristic has no
    known concrete failure case in practice — see review12 batch C #5.
    """
    # Strip a trailing comment, naively (does not understand strings, but
    # template Python lines are typically very simple statements).
    code = stripped
    in_s = False
    in_d = False
    cut = len(code)
    for i, ch in enumerate(code):
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            cut = i
            break
    code = code[:cut].rstrip()
    return code.endswith(":")


def _escape_plain(text: str) -> str:
    """Escape a Verilog text fragment for inclusion in a regular ``"..."``
    Python string literal.  Doubles backslashes and escapes ``"``."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _escape_fstring_text(text: str) -> str:
    """Escape a Verilog text fragment for inclusion in an f-string literal.

    Same as :func:`_escape_plain` plus doubling of ``{`` and ``}`` so they
    are emitted literally."""
    return (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("{", "{{")
        .replace("}", "}}")
    )


def _process_verilog_line(line: str, lineno: int, infile: str) -> str:
    """Translate a single non-``//;`` line of Verilog into a Python statement.

    Backtick-delimited regions become f-string interpolations; everything else
    becomes literal text.  Returns the Python source for a single ``self.emit``
    call (no trailing newline, no leading indent).
    """
    pieces: List[str] = []  # alternating text / expr fragments (already escaped)
    has_expr = False
    buf = []
    i = 0
    n = len(line)
    in_expr = False

    # Backtick toggles text/expr mode; backslash escapes only in text mode.
    # Mirrors Manager.pm:866-880.
    prev_backslash = False
    while i < n:
        ch = line[i]
        if ch == "`":
            if prev_backslash and not in_expr:
                # Escaped backtick in text mode -- include the literal backtick.
                buf.append("`")
                prev_backslash = False
            else:
                # toggle modes; flush current buffer
                if in_expr:
                    expr_text = "".join(buf)
                    pieces.append(("expr", expr_text))
                    has_expr = True
                else:
                    pieces.append(("text", "".join(buf)))
                buf = []
                in_expr = not in_expr
                prev_backslash = False
        else:
            if not in_expr and ch == "\\" and not prev_backslash:
                prev_backslash = True
                # Don't append yet; if next is a backtick, it'll be eaten as
                # an escape; otherwise, we restore the backslash below.
            else:
                if prev_backslash:
                    # The preceding backslash was not consumed by a backtick
                    # escape; keep it as a literal backslash in the output.
                    buf.append("\\")
                    prev_backslash = False
                buf.append(ch)
        i += 1

    if in_expr:
        raise ParseError(
            f'Unterminated backtick expression in "{infile}", line {lineno}: '
            f"{line!r}"
        )
    if prev_backslash:
        buf.append("\\")
    pieces.append(("text", "".join(buf)))

    if not has_expr:
        # Plain text -- emit a regular string literal.
        text = "".join(seg for kind, seg in pieces if kind == "text")
        return f'self.emit("{_escape_plain(text)}")'

    # Build an f-string.
    parts: List[str] = []
    for kind, seg in pieces:
        if kind == "text":
            parts.append(_escape_fstring_text(seg))
        else:
            # Verbatim paste; compile() validates the expression later.
            parts.append("{" + seg + "}")
    return f'self.emit(f"{"".join(parts)}")'


def _check_extension(path: str) -> None:
    """Raise :class:`ParseError` if ``path`` has a legacy extension."""
    _, ext = os.path.splitext(path)
    ext_lower = ext.lower()
    if ext_lower in (".vp", ".svp"):
        raise ParseError(
            f"{path}: legacy Genesis2 extension '{ext}' is not supported. "
            f"Rename the file to '{ext}y' (genesispy uses .vpy/.svpy)."
        )
    if ext_lower not in (".vpy", ".svpy"):
        raise ParseError(
            f"{path}: unsupported extension '{ext}'; expected .vpy or .svpy."
        )


def parse_vpy(path: str) -> str:
    """Parse a ``.vpy``/``.svpy`` template file.

    Returns Python source text -- the body of a generated module's
    ``execute()`` method.  Raises :class:`ParseError` for legacy ``.vp``/
    ``.svp`` files or for malformed templates (e.g. unterminated backticks).
    """
    _check_extension(path)

    with open(path, "r", encoding="utf-8") as fh:
        raw_lines = fh.readlines()

    out_lines: List[str] = []
    # Indent level (in 4-space units) for *emit* lines and continuation
    # statements that follow the most recent //; line.
    emit_indent = 0
    # Indent level of the most recent //; line itself.
    last_py_indent = 0
    # True if the most recent //; line ended in a colon (block opener).
    last_was_opener = False

    for idx, raw in enumerate(raw_lines):
        lineno = idx + 1
        # Strip only the trailing newline (preserve other whitespace).
        if raw.endswith("\r\n"):
            line = raw[:-2]
        elif raw.endswith("\n"):
            line = raw[:-1]
        else:
            line = raw

        stripped_left = line.lstrip(" \t")
        if stripped_left.startswith(_PRL_ESC):
            # Python line.
            content = stripped_left[len(_PRL_ESC):]
            # Drop ONE optional leading space after //; (matches Perl
            # convention for the `//; ` prefix).
            if content.startswith(" "):
                content = content[1:]

            # Indent = leading spaces // 4. Tabs reject (would silently zero-collapse scope).
            leading_ws = content[: len(content) - len(content.lstrip(" \t"))]
            if "\t" in leading_ws:
                raise ParseError(
                    f"{path}:{lineno}: tab character in //; indent; "
                    "use spaces (indent unit is 4 spaces)"
                )
            n_spaces = len(content) - len(content.lstrip(" "))
            if n_spaces % 4 != 0:
                raise ParseError(
                    f"{path}:{lineno}: misaligned //; indent "
                    f"({n_spaces} spaces); expected multiple of 4"
                )
            py_indent = n_spaces // 4
            body = content[n_spaces:]  # Python source without leading indent

            indent_str = "    " * py_indent
            out_lines.append(f"# line {lineno} {json.dumps(path)}")
            if body == "":
                # Bare ``//;``: blank line, indent state unchanged.
                out_lines.append("")
            else:
                out_lines.append(f"{indent_str}{body}")
                last_was_opener = _is_block_opener(body)
                last_py_indent = py_indent
                emit_indent = last_py_indent + (1 if last_was_opener else 0)
        else:
            # Plain Verilog line -- emit a self.emit(...) call.
            indent_str = "    " * emit_indent
            out_lines.append(f"# line {lineno} {json.dumps(path)}")
            if line == "":
                out_lines.append(f'{indent_str}self.emit("")')
            else:
                stmt = _process_verilog_line(line, lineno, path)
                out_lines.append(f"{indent_str}{stmt}")

    return "\n".join(out_lines) + ("\n" if out_lines else "")
