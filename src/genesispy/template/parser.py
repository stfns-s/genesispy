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

j2 syntax (``syntax="j2"``)
---------------------------

Opt-in alternative directive style. ``j2`` is a Jinja2-*like* flavour: it
shares the delimiter set with the canonical Jinja2 library
(``{% python-stmt %}`` replaces ``//;``, ``{{ python-expr }}`` replaces
backticks, and ``{# comment #}`` is a comment that is stripped from
output) but the embedded language is full Python -- no Jinja2 expression
sub-language (no filter pipes, no ``is``-tests, no macros, no
``extends``/``block``/``include`` etc.). Indent, block-opener (trailing
``:``), and sentinel-close rules are identical to genesis flavour.
Whitespace modifiers ``{%-``, ``-%}``, ``{{-``, ``-}}`` are accepted as
a syntactic no-op (no whitespace stripping). All three forms may span
multiple physical lines; tracebacks land on the opener line.

Legacy extensions
-----------------

Files ending in ``.vp`` or ``.svp`` (the original Genesis2 extensions) are
rejected with :class:`ParseError`; users must rename to ``.vpy``/``.svpy``.
"""

from __future__ import annotations

import json
import os
from typing import Iterable, List, Optional

from genesispy.reporting import ParseError
from genesispy.extensions import DEFAULT_EXTENSION_MAP


__all__ = ["parse_vpy", "ParseError"]


_DEFAULT_COMMENT = "//"


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


def _check_extension(
    path: str, allowed: Optional[Iterable[str]] = None
) -> None:
    """Raise :class:`ParseError` if ``path`` has a disallowed extension.

    ``allowed`` is the set of accepted input extensions (e.g. the keys of
    :data:`Manager.extension_map`); defaults to the built-in
    :data:`DEFAULT_EXTENSION_MAP` keys. The legacy Genesis2 ``.vp``/``.svp``
    extensions raise a special-cased "rename to .vpy/.svpy" error first.
    """
    allowed_set = (
        frozenset(allowed) if allowed is not None
        else frozenset(DEFAULT_EXTENSION_MAP.keys())
    )
    _, ext = os.path.splitext(path)
    ext_lower = ext.lower()
    if ext_lower in (".vp", ".svp"):
        raise ParseError(
            f"{path}: legacy Genesis2 extension '{ext}' is not supported. "
            f"Rename the file to '{ext}y' (genesispy uses .vpy/.svpy)."
        )
    if ext_lower not in allowed_set:
        expected = ", ".join(sorted(allowed_set)) or "<none>"
        raise ParseError(
            f"{path}: unsupported extension '{ext}'; expected {expected}."
        )


def parse_vpy(
    path: str,
    allowed: Optional[Iterable[str]] = None,
    *,
    syntax: str = "genesis",
    comment: str = _DEFAULT_COMMENT,
) -> str:
    """Parse a ``.vpy``/``.svpy`` (or user-allowed) template file.

    Returns Python source text -- the body of a generated module's
    ``execute()`` method.  Raises :class:`ParseError` for legacy ``.vp``/
    ``.svp`` files, for any extension not in ``allowed``, or for malformed
    templates.

    ``syntax`` selects the directive flavour: ``"genesis"`` (default) uses
    ``//;`` line directives and backtick inline expressions; ``"j2"`` is
    the Jinja2-like flavour (``{% %}``, ``{{ }}``, ``{# #}`` delimiters
    with full Python inside).
    """
    _check_extension(path, allowed)

    if syntax == "genesis":
        with open(path, "r", encoding="utf-8") as fh:
            raw_lines = fh.readlines()
        out_lines = _parse_vpy_genesis(path, raw_lines, comment + ";")
    elif syntax == "j2":
        with open(path, "r", encoding="utf-8") as fh:
            source = fh.read()
        out_lines = _parse_vpy_j2(path, source)
    else:
        raise ValueError(
            f"parse_vpy: unknown syntax {syntax!r}; expected 'genesis' or 'j2'"
        )

    return "\n".join(out_lines) + ("\n" if out_lines else "")


def _parse_vpy_genesis(
    path: str, raw_lines: List[str], prl_esc: str = "//;"
) -> List[str]:
    """Genesis-flavour line-based scanner. Returns out_lines.

    ``prl_esc`` is the directive sentinel (default ``"//;"`` -- the
    configured ``--comment`` prefix plus a trailing ``;``).
    """
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
        if stripped_left.startswith(prl_esc):
            # Python line.
            content = stripped_left[len(prl_esc):]
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

    return out_lines


# ---------------------------------------------------------------------------
# j2 (Jinja2-like) flavour scanner
# ---------------------------------------------------------------------------

def _emit_call(pieces: List, indent: int) -> str:
    """Build a ``self.emit(...)`` Python statement from pieces.

    ``pieces`` is a list of ``("text", str)`` / ``("expr", str)`` tuples;
    ``indent`` is the number of 4-space units to prefix.
    """
    indent_str = "    " * indent
    if not pieces:
        return f'{indent_str}self.emit("")'
    has_expr = any(k == "expr" for k, _ in pieces)
    if not has_expr:
        text = "".join(seg for k, seg in pieces if k == "text")
        return f'{indent_str}self.emit("{_escape_plain(text)}")'
    parts: List[str] = []
    for kind, seg in pieces:
        if kind == "text":
            parts.append(_escape_fstring_text(seg))
        else:
            # Pad with spaces inside the braces so that a leading '{' or
            # trailing '}' in the expression (e.g. dict literals) doesn't
            # collide with f-string '{{'/'}}' literal-escape parsing.
            parts.append("{ " + seg + " }")
    return f'{indent_str}self.emit(f"{"".join(parts)}")'


def _scan_python_close(
    source: str, start: int, close_a: str, close_b: str, path: str, lineno: int
) -> int:
    """Scan a Python expression / statement looking for the close delimiter.

    Returns the index of the first character of the close delimiter
    (``}}`` or ``%}``, possibly preceded by ``-``). String literals and
    bracket nesting (``( [ {``) are honoured so braces inside the
    embedded Python don't false-close. Raises :class:`ParseError` on EOF.
    """
    i = start
    n = len(source)
    depth = 0  # nesting of (), [], {}
    in_str: Optional[str] = None  # one of '"', "'", "'''", '"""'
    while i < n:
        ch = source[i]
        if in_str is not None:
            # Inside a Python string literal.
            if len(in_str) == 3:
                if source.startswith(in_str, i):
                    i += 3
                    in_str = None
                    continue
            else:
                if ch == "\\" and i + 1 < n:
                    i += 2
                    continue
                if ch == in_str:
                    in_str = None
                    i += 1
                    continue
            i += 1
            continue
        # Not in a string.
        if ch in ('"', "'"):
            if source.startswith(ch * 3, i):
                in_str = ch * 3
                i += 3
                continue
            in_str = ch
            i += 1
            continue
        # At depth 0, a close delimiter (optionally preceded by '-') wins
        # over the brace-decrement that '}' or '%' would trigger.
        if depth == 0:
            if ch == "-" and (
                source.startswith(close_a, i + 1)
                or (close_b != close_a and source.startswith(close_b, i + 1))
            ):
                return i
            if source.startswith(close_a, i):
                return i
            if close_b != close_a and source.startswith(close_b, i):
                return i
        if ch in "([{":
            depth += 1
            i += 1
            continue
        if ch in ")]}":
            depth -= 1
            i += 1
            continue
        i += 1
    raise ParseError(
        f"{path}:{lineno}: unterminated {{{close_a[0]} ... {close_a}}}"
    )


_J2_END_KEYWORDS = frozenset({"endfor", "endif", "endwhile"})


def _parse_vpy_j2(path: str, source: str) -> List[str]:
    """j2 (Jinja2-like) flavour stream scanner. Returns out_lines."""
    out_lines: List[str] = []
    # Indent state (mirrors genesis-mode tracking).
    emit_indent = 0
    last_py_indent = 0
    last_was_opener = False
    # Stack of py_indent levels for blocks opened by directives ending in
    # `:`. Both close forms pop this stack: bare keyword (`{% endfor %}`)
    # and sentinel-comment (`{% # endfor %}`). Mismatch with an empty
    # stack raises "without matching opener" in either form.
    block_stack: List[int] = []

    n = len(source)
    i = 0

    # State for the current "logical text line": pieces accumulated since
    # the last top-level newline, plus the line number where the first
    # piece (or the line itself) began.
    pieces: List = []
    line_pieces_lineno: Optional[int] = None
    # Line number of the start of the current physical line (1-based).
    current_line = 1
    # Has the current physical line had any non-whitespace text emitted
    # outside of a form? Used to detect "directive sharing a line with
    # plain Verilog".
    line_has_nonspace_text = False
    # Beginning-of-physical-line index in source (used to detect "is the
    # next non-space token at start-of-line").
    line_start = 0

    def flush_logical_line(emit_lineno: int) -> None:
        nonlocal pieces, line_pieces_lineno
        out_lines.append(f"# line {emit_lineno} {json.dumps(path)}")
        out_lines.append(_emit_call(pieces, emit_indent))
        pieces = []
        line_pieces_lineno = None

    def at_line_start() -> bool:
        # True iff source[line_start:i] is all spaces/tabs.
        return source[line_start:i].strip(" \t") == ""

    text_buf: List[str] = []

    def push_text(s: str) -> None:
        nonlocal line_has_nonspace_text, line_pieces_lineno
        if not s:
            return
        text_buf.append(s)
        if line_pieces_lineno is None:
            line_pieces_lineno = current_line
        if s.strip(" \t"):
            line_has_nonspace_text = True

    def flush_text_to_pieces() -> None:
        if text_buf:
            pieces.append(("text", "".join(text_buf)))
            text_buf.clear()

    while i < n:
        ch = source[i]

        # Newline at top level → end of logical line.
        if ch == "\n":
            flush_text_to_pieces()
            emit_lineno = line_pieces_lineno if line_pieces_lineno is not None else current_line
            flush_logical_line(emit_lineno)
            i += 1
            current_line += 1
            line_start = i
            line_has_nonspace_text = False
            continue

        # `\{{`: literal `{{` in text.
        if ch == "\\" and source.startswith("\\{{", i):
            push_text("{{")
            i += 3
            continue

        # `{%` or `{%-` → directive.
        if source.startswith("{%", i):
            # Must be at start of physical line (only whitespace before on this line).
            if not at_line_start():
                raise ParseError(
                    f"{path}:{current_line}: '{{%' must start the line "
                    "(no plain Verilog before the directive)"
                )
            # Drop any leading-whitespace text that was buffered for this line.
            text_buf.clear()
            # Also discard pieces that came purely from leading whitespace.
            # (pieces should be empty here because a directive on a fresh
            # logical line means we haven't accumulated non-whitespace text;
            # if pieces are non-empty, that would mean the directive opens
            # mid-logical-line which we already rejected.)
            if pieces:
                # This shouldn't happen given at_line_start() == True, but
                # belt-and-braces: a logical line cannot start before the
                # directive and continue across the directive line.
                raise ParseError(
                    f"{path}:{current_line}: directive '{{%' cannot share "
                    "a logical line with prior text"
                )
            opener_line = current_line
            # Skip "{%" and optional "-".
            i += 2
            if i < n and source[i] == "-":
                i += 1
            close = _scan_python_close(source, i, "%}", "%}", path, opener_line)
            inner = source[i:close]
            # Step past the close ("-%}" or "%}").
            i = close
            if source.startswith("-%}", i):
                i += 3
            else:
                i += 2
            # Strip exactly one leading space (mirror "//; " convention).
            if inner.startswith(" "):
                inner = inner[1:]
            # Strip exactly one trailing space (mirror " %}" symmetry).
            if inner.endswith(" "):
                inner = inner[:-1]
            # Update current_line for any newlines consumed inside the directive.
            consumed_newlines = source.count("\n", line_start, i)
            current_line = opener_line + consumed_newlines
            # After close, the rest of the closing physical line must be
            # whitespace-only (until newline or EOF).
            j = i
            while j < n and source[j] != "\n":
                if source[j] not in " \t":
                    raise ParseError(
                        f"{path}:{current_line}: '%}}' must end the line "
                        "(no plain Verilog after the directive)"
                    )
                j += 1
            # Consume the trailing newline of the closer line (if any) so
            # the directive doesn't leave an empty self.emit("") behind.
            if j < n and source[j] == "\n":
                i = j + 1
                current_line += 1
                line_start = i
                line_has_nonspace_text = False
            else:
                i = j
            # Block close. Two equivalent forms:
            #   * Bare keyword: `{% endfor %}` / `{% endif %}` /
            #     `{% endwhile %}` (real Jinja2 spelling).
            #   * Sentinel-comment: `{% # endfor %}` etc. (Genesis2-style
            #     close, still a Python comment in the generated body).
            # Both pop `block_stack`; either form with an empty stack
            # raises "without matching opener".
            stripped_inner = inner.strip()
            end_kw: str | None = None
            if stripped_inner in _J2_END_KEYWORDS:
                end_kw = stripped_inner
            elif stripped_inner.startswith("#"):
                after_hash = stripped_inner[1:].strip()
                if after_hash in _J2_END_KEYWORDS:
                    end_kw = after_hash
            if end_kw is not None:
                if not block_stack:
                    raise ParseError(
                        f"{path}:{opener_line}: '{{% {stripped_inner} %}}' "
                        "without matching opener"
                    )
                popped = block_stack.pop()
                out_lines.append(f"# line {opener_line} {json.dumps(path)}")
                out_lines.append(f'{"    " * popped}# {end_kw}')
                last_py_indent = popped
                last_was_opener = False
                emit_indent = last_py_indent
                continue
            # Indent / opener handling on the joined inner content.
            inner_lines = inner.split("\n")
            first_line = inner_lines[0]
            leading_ws = first_line[: len(first_line) - len(first_line.lstrip(" \t"))]
            if "\t" in leading_ws:
                raise ParseError(
                    f"{path}:{opener_line}: tab character in {{% %}} indent; "
                    "use spaces (indent unit is 4 spaces)"
                )
            n_spaces = len(first_line) - len(first_line.lstrip(" "))
            if n_spaces % 4 != 0:
                raise ParseError(
                    f"{path}:{opener_line}: misaligned {{% %}} indent "
                    f"({n_spaces} spaces); expected multiple of 4"
                )
            py_indent = n_spaces // 4
            body_first = first_line[n_spaces:]
            indent_str = "    " * py_indent
            out_lines.append(f"# line {opener_line} {json.dumps(path)}")
            if body_first == "" and len(inner_lines) == 1:
                # Bare `{% %}` (or `{%  %}` etc.): blank line, indent state unchanged.
                out_lines.append("")
            else:
                # First inner line gets the computed indent prefix.
                out_lines.append(f"{indent_str}{body_first}")
                # Subsequent inner lines: append verbatim (Python's own
                # indentation rules govern the multi-line statement).
                for extra in inner_lines[1:]:
                    out_lines.append(extra)
                # Block-opener detection runs on the LAST non-blank inner line.
                last_nonblank = ""
                for ln in reversed(inner_lines):
                    if ln.strip():
                        last_nonblank = ln
                        break
                last_was_opener = _is_block_opener(last_nonblank.lstrip(" \t"))
                last_py_indent = py_indent
                emit_indent = last_py_indent + (1 if last_was_opener else 0)
                # Track open blocks for bare-keyword close. Push only when
                # this directive deepens the block stack; midblock
                # continuations (`else:`, `elif x:`, `except ...:`,
                # `finally:`) reuse the indent of the existing top-of-
                # stack opener and must not push a new entry.
                if last_was_opener and (
                    not block_stack or py_indent > block_stack[-1]
                ):
                    block_stack.append(py_indent)
            continue

        # `{{` or `{{-` → expression.
        if source.startswith("{{", i):
            opener_line = current_line
            flush_text_to_pieces()
            i += 2
            if i < n and source[i] == "-":
                i += 1
            close = _scan_python_close(source, i, "}}", "}}", path, opener_line)
            expr = source[i:close]
            # Step past the close ("-}}" or "}}").
            i = close
            if source.startswith("-}}", i):
                i += 3
            else:
                i += 2
            # Strip exactly one leading/trailing space.
            if expr.startswith(" "):
                expr = expr[1:]
            if expr.endswith(" "):
                expr = expr[:-1]
            # Newlines inside the expression are part of the Python source;
            # update current_line to match.
            consumed = expr.count("\n")
            current_line = opener_line + consumed
            if line_pieces_lineno is None:
                line_pieces_lineno = opener_line
            pieces.append(("expr", expr))
            line_has_nonspace_text = True
            continue

        # `{#` → comment.
        if source.startswith("{#", i):
            opener_line = current_line
            i += 2
            j = source.find("#}", i)
            if j < 0:
                raise ParseError(
                    f"{path}:{opener_line}: unterminated {{# ... #}}"
                )
            consumed = source.count("\n", i, j)
            current_line = opener_line + consumed
            i = j + 2
            # If the comment was the only non-whitespace content of the
            # logical line so far AND nothing follows on the closer's
            # physical line up to its newline, drop the line entirely.
            # Otherwise leave the surrounding text untouched (the comment
            # is just stripped from the logical line).
            # We don't add anything to pieces.
            continue

        # Plain text character.
        push_text(ch)
        i += 1

    # EOF: flush the in-flight logical line if there's anything to flush.
    flush_text_to_pieces()
    if pieces or text_buf or line_pieces_lineno is not None:
        emit_lineno = line_pieces_lineno if line_pieces_lineno is not None else current_line
        flush_logical_line(emit_lineno)

    return out_lines
