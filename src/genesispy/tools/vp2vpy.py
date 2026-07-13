"""Genesis2 (Perl) ``.vp`` / ``.vph`` -> genesispy (Python) ``.vpy`` translator.

Source-to-source translator that takes a Perl-templated Verilog file (the
Genesis2 input format) and emits a Python-templated Verilog file (the
genesispy input format). The Perl frontend is `PPI` (CPAN), invoked as a
long-lived subprocess via the sibling ``vp2vpy_helper.pl`` script.

Constructs that have no clean equivalent are passed through verbatim
wrapped in ``// TODO vp2vpy: <reason>`` comments so the user can fix
them by hand; ``--strict`` upgrades these to errors.

Environment: requires ``perl`` and the ``PPI`` module on @INC. On the
ramyx workstations: ``module load ramyx/perl/5.42.0/0.1.0``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from . import vp2vpy_map as M


# ---------------------------------------------------------------------------
# Helper subprocess: persistent perl process running vp2vpy_helper.pl.
# ---------------------------------------------------------------------------

HELPER_SCRIPT = Path(__file__).with_name("vp2vpy_helper.pl")


class HelperError(RuntimeError):
    """The Perl helper failed."""


class Helper:
    """Length-prefixed framed pipe to a long-lived ``perl`` subprocess.

    Frame format (both directions): ``"<n>\\n<n-bytes-utf8>"``.
    """

    def __init__(self, perl_exe: str = "perl") -> None:
        self._perl = perl_exe
        self._proc: subprocess.Popen | None = None

    def start(self) -> None:
        if self._proc is not None:
            return
        try:
            self._proc = subprocess.Popen(
                [self._perl, str(HELPER_SCRIPT)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError as e:
            raise HelperError(
                f"`{self._perl}` not on PATH. "
                "On ramyx hosts: `module load ramyx/perl/5.42.0/0.1.0`."
            ) from e

    def parse(self, perl_src: str) -> dict:
        """Send a Perl snippet, return the decoded JSON response."""
        if self._proc is None:
            self.start()
        if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
            raise HelperError("helper subprocess pipes are not open")
        payload = perl_src.encode("utf-8")
        self._proc.stdin.write(f"{len(payload)}\n".encode("ascii"))
        self._proc.stdin.write(payload)
        self._proc.stdin.flush()
        hdr = self._proc.stdout.readline()
        if not hdr:
            err = (self._proc.stderr.read() if self._proc.stderr else b"").decode(
                "utf-8", errors="replace"
            )
            raise HelperError(f"helper closed pipe; stderr: {err!r}")
        try:
            n = int(hdr.strip())
        except ValueError as e:
            raise HelperError(f"malformed frame header: {hdr!r}") from e
        if n < 0:
            raise HelperError(f"negative frame length: {n}")
        buf = b""
        while len(buf) < n:
            chunk = self._proc.stdout.read(n - len(buf))
            if not chunk:
                raise HelperError("helper EOF mid-frame")
            buf += chunk
        try:
            return json.loads(buf.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise HelperError(f"helper returned undecodable frame: {e}") from e

    def close(self) -> None:
        if self._proc is not None:
            try:
                self._proc.stdin.close()  # type: ignore[union-attr]
                self._proc.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                self._proc.kill()
            self._proc = None

    def __enter__(self) -> "Helper":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Source classification: split a .vp file into Verilog lines and directives.
# ---------------------------------------------------------------------------

DIRECTIVE_RE = re.compile(r"^([ \t]*)//;(.*)$")
BLOCK_OPEN_RE = re.compile(r"^([ \t]*)/\*;(.*)$")
BLOCK_CLOSE_RE = re.compile(r"^(.*?);\*/\s*$")

# Unescaped backtick spans in Verilog body. Matches `...` but not \`...\`.
# Greedy-but-bounded: stops at the next unescaped backtick.
BACKTICK_RE = re.compile(r"(?<!\\)`([^`\\]*(?:\\.[^`\\]*)*)`")


@dataclass
class Record:
    kind: str           # 'verilog' | 'directive' | 'block'
    line_no: int        # 1-based source line
    indent: str         # leading whitespace (for directives)
    text: str           # Verilog line for 'verilog'; Perl snippet for the others


def _paren_balance(s: str) -> int:
    """``( - ) + [ - ] + { - }`` outside strings. Best-effort: doesn't track
    string escapes precisely, but good enough to detect multi-line `//;`
    continuations like ``//; func(a,`` -> ``//;   b);``.
    """
    depth = 0
    in_str: str | None = None
    i = 0
    while i < len(s):
        c = s[i]
        if in_str:
            if c == "\\" and i + 1 < len(s):
                i += 2
                continue
            if c == in_str:
                in_str = None
            i += 1
            continue
        if c in ("'", '"'):
            in_str = c
        # ``{`` / ``}`` are intentionally excluded: a directive-opener line
        # ``//; for (...) {`` is *not* a continuation, it opens a block whose
        # body is on subsequent lines.
        elif c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        i += 1
    return depth


_CONTINUATION_TAIL_RE = re.compile(
    r"(?:[=+\-*/%&|^.?:,]|=>|\|\||&&|//)\s*$"
)


def _needs_continuation(s: str) -> bool:
    """True if this directive line clearly continues onto the next.

    Two cues, either of which counts:
    - unclosed ``(`` or ``[`` brackets (counted ignoring ``{}`` so block
      openers don't trigger);
    - the trimmed line ends with a binary/postfix operator that demands an
      RHS (``=``, ``,``, ``+``, ``=>``, ``||``, ``&&``, etc.).
    """
    s = s.rstrip()
    # Whole-line comment -> never a continuation (otherwise a comment that
    # happens to end in ``:`` or ``,`` would swallow the next statement).
    if s.lstrip().startswith("#"):
        return False
    # Strip trailing Perl comment so a comment can't mask the operator.
    s = re.sub(r"\s+#.*$", "", s).rstrip()
    if _paren_balance(s) > 0:
        return True
    if not s:
        return False
    # Don't merge lines whose only "trailing op" is an open brace.
    if s.endswith("{"):
        return False
    return bool(_CONTINUATION_TAIL_RE.search(s))


_POSTFIX_KEYWORDS = ("if", "unless", "while", "until", "for", "foreach")
_POSTFIX_LEAD_RE = re.compile(
    r"^\s*(?:" + "|".join(_POSTFIX_KEYWORDS) + r")\b"
)


def _is_postfix_continuation(prev: str, nxt: str) -> bool:
    """Detect ``STMT)``\\n``unless COND;`` Genesis2 line-split idiom.

    Triggers when the previous record's trimmed line ends with ``)`` (i.e.
    no trailing operator) and the next record's first non-whitespace token
    is a Perl postfix-conditional keyword. The two lines together form one
    statement that the AST walker needs to see joined.
    """
    p = prev.rstrip()
    p = re.sub(r"\s+#.*$", "", p).rstrip()
    if not p.endswith(")"):
        return False
    return bool(_POSTFIX_LEAD_RE.match(nxt))


def _merge_continuations(records: list["Record"]) -> list["Record"]:
    """Merge consecutive directive records that form one logical statement."""
    out: list[Record] = []
    i = 0
    while i < len(records):
        rec = records[i]
        needs = _needs_continuation(rec.text)
        if rec.kind == "directive" and not needs and i + 1 < len(records):
            nxt = records[i + 1]
            if nxt.kind == "directive" and _is_postfix_continuation(rec.text, nxt.text):
                needs = True
        if rec.kind == "directive" and needs:
            merged = rec.text
            j = i + 1
            while j < len(records):
                if records[j].kind != "directive":
                    break
                if not (
                    _needs_continuation(merged)
                    or _is_postfix_continuation(merged, records[j].text)
                ):
                    break
                merged = merged + " " + records[j].text.strip()
                j += 1
            out.append(Record("directive", rec.line_no, rec.indent, merged))
            i = j
            continue
        out.append(rec)
        i += 1
    return out


def classify(source: str) -> list[Record]:
    """Split a Genesis2 source file into Verilog / directive / block records."""
    out: list[Record] = []
    i = 0
    lines = source.splitlines(keepends=False)
    while i < len(lines):
        line = lines[i]
        m = DIRECTIVE_RE.match(line)
        if m:
            indent, payload = m.group(1), m.group(2)
            # Strip exactly one leading space if present (cosmetic; Perl doesn't
            # care).
            if payload.startswith(" "):
                payload = payload[1:]
            out.append(Record("directive", i + 1, indent, payload))
            i += 1
            continue
        m = BLOCK_OPEN_RE.match(line)
        if m:
            indent = m.group(1)
            first = m.group(2)
            # Collect lines until ``;*/``.
            collected = [first]
            start_line = i + 1
            i += 1
            while i < len(lines):
                close = BLOCK_CLOSE_RE.match(lines[i])
                if close:
                    collected.append(close.group(1))
                    i += 1
                    break
                collected.append(lines[i])
                i += 1
            out.append(Record("block", start_line, indent, "\n".join(collected)))
            continue
        out.append(Record("verilog", i + 1, "", line))
        i += 1
    return out


# ---------------------------------------------------------------------------
# AST walker: PPI JSON tree -> Python expression / statement text.
# ---------------------------------------------------------------------------


class Unmappable(Exception):
    """Raised when a construct has no Python mapping."""


@dataclass
class WalkCtx:
    """Mutable state threaded through a walk.

    Used to collect ``import`` requirements and runtime-helper requirements so
    the file writer can inject them at the top of the output.
    """
    imports: set[str] = field(default_factory=set)
    helpers: set[str] = field(default_factory=set)
    # Comments collected from the tree (PPI keeps them as tokens).
    inline_comments: list[str] = field(default_factory=list)
    # Set true when ``use POSIX;`` is seen at file scope: subsequent bare
    # calls to names in ``M.POSIX_MAP`` (``ceil``, ``log``, ``sqrt``, ...)
    # are then redirected to their Python equivalents.
    posix_imported: bool = False


def _is_node(n: dict) -> bool:
    return "c" in n


def _children(n: dict) -> list[dict]:
    return n.get("c", [])


def _significant_children(n: dict) -> list[dict]:
    """Children minus comments and stray structure punctuation."""
    out = []
    for c in _children(n):
        t = c["t"]
        if t == "Token::Comment":
            continue
        out.append(c)
    return out


# Python keywords + builtins commonly used as Perl variable names. When the
# translator strips a sigil and the result lands on one of these, suffix it
# so user code doesn't shadow the builtin (Genesis2's ``my $type``,
# ``my $list`` etc. are idiomatic and harmless in Perl, but the same
# unshadowed name in the emitted Python wraps a builtin and breaks the
# runtime-generated module shell).
_PY_RESERVED_NAMES: frozenset[str] = frozenset({
    "False", "None", "True", "and", "as", "assert", "async", "await",
    "break", "class", "continue", "def", "del", "elif", "else", "except",
    "finally", "for", "from", "global", "if", "import", "in", "is",
    "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try",
    "while", "with", "yield",
    # builtins likely to be referenced by the generated module shell.
    "type", "list", "dict", "set", "tuple", "str", "int", "float", "bool",
    "id", "input", "print", "len", "map", "filter", "min", "max", "open",
    "range", "sorted", "reversed", "sum", "all", "any", "enumerate", "zip",
    "object", "super",
})


def _safe_py_name(s: str) -> str:
    return f"{s}_" if s in _PY_RESERVED_NAMES else s


def _strip_sigil(sym: str) -> str:
    """``$x`` / ``@x`` / ``%x`` -> ``x``. ``$arr[0]`` -> ``arr``.

    Suffixes the name with ``_`` if it would shadow a Python keyword or
    common builtin (e.g. Genesis2's ``$type`` -> ``type_``).
    """
    s = sym.lstrip("$@%&")
    return _safe_py_name(s)


def _is_word(n: dict, *words: str) -> bool:
    return n["t"] == "Token::Word" and n.get("v") in words


def _is_op(n: dict, *ops: str) -> bool:
    return n["t"] == "Token::Operator" and n.get("v") in ops


def _is_struct(n: dict, *chars: str) -> bool:
    return n["t"] == "Token::Structure" and n.get("v") in chars


def render_string_literal(content: str, double: bool, ctx: WalkCtx) -> str:
    """Render a Perl string literal as a Python literal.

    Interpolated variables (``"foo $x bar"``) become f-strings. We don't try
    to handle every Perl interpolation quirk; ``$var``, ``${var}``, ``@var``,
    and ``$obj->{key}`` are recognized.
    """
    body = content[1:-1]  # strip surrounding quotes
    if not double:
        return repr(body)
    # Look for interpolations.
    pattern = re.compile(
        r"\\.|"
        r"\$\{(\w+)\}|"
        r"\$(\w+(?:->\{\w+\}|->\[\d+\])*)|"
        r"@\{(\w+)\}|"
        r"@(\w+)"
    )
    parts: list[str] = []
    last = 0
    any_interp = False
    for m in pattern.finditer(body):
        text = body[last:m.start()]
        if text:
            parts.append(text.replace("{", "{{").replace("}", "}}"))
        token = m.group(0)
        if token.startswith("\\"):
            # Escaped char.
            mapping = {"\\n": "\\n", "\\t": "\\t", "\\\\": "\\\\", "\\\"": "\\\""}
            parts.append(mapping.get(token, token[1:]))
        else:
            name = m.group(1) or m.group(2) or m.group(3) or m.group(4)
            # Use single quotes for dict keys: inside an f-string's
            # ``{...}`` Python (< 3.12) disallows backslash escapes, so
            # ``f"{reg[\"name\"]}"`` is a SyntaxError -- pick the inner quote
            # that doesn't collide with the outer.
            name = re.sub(r"->\{(\w+)\}", lambda m: f"['{m.group(1)}']", name)
            name = re.sub(r"->\[(\d+)\]", lambda m: f"[{m.group(1)}]", name)
            parts.append("{" + name + "}")
            any_interp = True
        last = m.end()
    rest = body[last:]
    if rest:
        parts.append(rest.replace("{", "{{").replace("}", "}}"))
    joined = "".join(parts)
    if any_interp:
        # Choose quote that avoids collisions; default to double.
        if '"' in joined and "'" not in joined:
            return "f'" + joined.replace("'", "\\'") + "'"
        return 'f"' + joined.replace('"', '\\"') + '"'
    # No interpolation: still need to translate escapes; cheapest is repr().
    return repr(body)


def render_token(n: dict, ctx: WalkCtx) -> str:
    """Render a single PPI token as Python."""
    t = n["t"]
    v = n.get("v", "")
    if t.startswith("Token::Number"):
        # ``0xFF`` / ``0b10101`` / ``3.14`` all parse fine as Python literals.
        return v
    if t == "Token::Symbol":
        # Strip sigil; numeric magicals ($_, @_) get special handling.
        if v == "$_":
            ctx.helpers.add("_vp2vpy_underscore")
            return "_"
        if v == "@_":
            return "_args"
        return _strip_sigil(v)
    if t == "Token::Word":
        if v in ("undef",):
            return "None"
        if v in ("true",):
            return "True"
        if v in ("false",):
            return "False"
        return v
    if t == "Token::Quote::Single":
        return repr(v[1:-1])
    if t == "Token::Quote::Double":
        return render_string_literal(v, double=True, ctx=ctx)
    if t == "Token::Quote::Interpolate":
        return render_string_literal('"' + v[2:-1] + '"', double=True, ctx=ctx)
    if t == "Token::Quote::Literal":
        # q{...}
        inner = v
        # Strip leading q + delim and trailing delim.
        m = re.match(r"q\s*(.)(.*)(.)$", inner, re.DOTALL)
        if m:
            return repr(m.group(2))
        return repr(v)
    if t == "Token::QuoteLike::Words":
        # qw(a b c) -> ["a", "b", "c"]
        m = re.match(r"qw\s*(.)(.*)(.)$", v, re.DOTALL)
        if m:
            words = m.group(2).split()
            return "[" + ", ".join(repr(w) for w in words) + "]"
        raise Unmappable(f"qw token: {v!r}")
    if t == "Token::Operator":
        if v in ("?", ":"):
            # Ternaries are rewritten structurally in render_expr; a ?/:
            # reaching the token level must never emit verbatim.
            raise Unmappable(f"ternary operator {v!r} in unsupported position")
        # Translate at the token level so we never rewrite a method-access
        # ``.`` into a string-concat ``+``.
        mapped = M.INFIX_OPERATOR_MAP.get(v)
        if mapped is None and v in M.PREFIX_OPERATOR_MAP:
            mapped = M.PREFIX_OPERATOR_MAP[v]
        return mapped if mapped is not None else v
    if t == "Token::Magic":
        if v == "$_":
            return "_"
        if v == "@_":
            return "_args"
        if v == "$0":
            ctx.imports.add("sys")
            return "sys.argv[0]"
        raise Unmappable(f"magic var {v!r}")
    if t == "Token::ArrayIndex":
        # $#arr -> len(arr) - 1
        name = v[2:]
        return f"(len({name}) - 1)"
    if t == "Token::Cast":
        # @{...}, %{...}, ${...} -- handled by caller; emit empty so it's a
        # no-op in the token stream.
        return ""
    if t == "Token::HereDoc":
        raise Unmappable("heredoc")
    raise Unmappable(f"token type {t!r} (value {v!r})")


# ---------------------------------------------------------------------------
# Expression renderer: takes a flat list of significant children and emits a
# Python expression string. Handles operator precedence by trusting Perl's
# left-to-right tokenization and parenthesizing each binary operation.
# ---------------------------------------------------------------------------


_ASSIGN_OPS = frozenset({
    "=", "+=", "-=", "*=", "/=", "%=", "**=", "&=", "|=", "^=",
    "<<=", ">>=", ".=", "x=", "//=", "||=", "&&=",
})


def _find_top_level_ternary(children: list[dict]) -> int | None:
    """Index of the first top-level ``?`` operator, or None.

    A ``:`` with no preceding ``?`` at this level has no ternary reading
    (e.g. a variable attribute) -> Unmappable, so the statement drivers
    record a TODO instead of emitting the token verbatim.
    """
    for i, c in enumerate(children):
        if _is_op(c, "?"):
            return i
        if _is_op(c, ":"):
            raise Unmappable("ternary ':' with no preceding '?'")
    return None


def _render_ternary(children: list[dict], q: int, ctx: WalkCtx) -> str:
    """``c ? a : b`` -> ``(a if c else b)``; recursion handles nesting.

    Perl ``?:`` binds tighter than assignment and ``render_expr`` receives
    whole ``x = c ? a : b`` sequences, so everything through the last
    top-level assignment operator before the ``?`` is rendered as a prefix
    rather than swallowed into the condition. Right-associative chains
    (``a ? b : c ? d : e``) fall out of the recursive ``render_expr`` calls
    on the branch slices.
    """
    a = -1
    for i in range(q):
        if children[i]["t"] == "Token::Operator" and children[i].get("v") in _ASSIGN_OPS:
            a = i
    depth = 0
    colon = None
    for i in range(q + 1, len(children)):
        if _is_op(children[i], "?"):
            depth += 1
        elif _is_op(children[i], ":"):
            if depth == 0:
                colon = i
                break
            depth -= 1
    if colon is None:
        raise Unmappable("ternary '?' with no matching ':'")
    cond = children[a + 1:q]
    true_b = children[q + 1:colon]
    false_b = children[colon + 1:]
    if not cond or not true_b or not false_b:
        raise Unmappable("ternary with an empty operand")
    py = (
        f"({render_expr(true_b, ctx)} if {render_expr(cond, ctx)} "
        f"else {render_expr(false_b, ctx)})"
    )
    if a >= 0:
        return f"{render_expr(children[:a + 1], ctx)} {py}"
    return py


def render_expr(children: list[dict], ctx: WalkCtx) -> str:
    """Render a token sequence (the body of a Statement or List) as Python."""
    q = _find_top_level_ternary(children)
    if q is not None:
        return _render_ternary(children, q, ctx)
    # First pass: collapse adjacent (function-word, list) and (symbol, subscript).
    rendered: list[str | dict] = []
    i = 0
    while i < len(children):
        c = children[i]
        t = c["t"]
        v = c.get("v")
        # Cast: @{EXPR}, %{EXPR}, ${EXPR} -- skip the cast; render the inner
        # expression (Python has no explicit deref).
        if t == "Token::Cast":
            if i + 1 < len(children) and children[i + 1]["t"] == "Structure::Block":
                blk = children[i + 1]
                # Block body is a Statement.
                inner = _inner_statement(blk)
                if inner is not None:
                    rendered.append(render_expr(_significant_children(inner), ctx))
                i += 2
                continue
            # Bare cast before a symbol (e.g. @$ref): drop the cast.
            i += 1
            continue
        # Regex bind: EXPR =~ m/pat/flags  -> bool(re.search(r"pat", EXPR, flags))
        # Negative: EXPR !~ m/pat/flags -> (re.search(...) is None)
        if (
            t == "Token::Operator" and v in ("=~", "!~")
            and i + 1 < len(children)
            and children[i + 1]["t"] == "Token::Regexp::Match"
        ):
            left = rendered.pop() if rendered else "_"
            body, flags = _parse_regex(children[i + 1].get("v", ""))
            ctx.imports.add("re")
            pyflags = _regex_flags_to_python(flags)
            fl = f", {pyflags}" if pyflags else ""
            if v == "=~":
                rendered.append(f'(re.search(r"{body}", {left}{fl}) is not None)')
            else:
                rendered.append(f'(re.search(r"{body}", {left}{fl}) is None)')
            i += 2
            continue
        # Fat comma -> keyword arg. Caller (render_call) handles it.
        # Range operator: NUM .. NUM -> range(start, end+1)
        if (
            t == "Token::Operator" and v in ("..", "...")
            and rendered and isinstance(rendered[-1], str)
            and i + 1 < len(children)
        ):
            left = rendered.pop()
            right_node = children[i + 1]
            right = render_token_or_node(right_node, ctx)
            if v == "..":
                rendered.append(f"range({left}, ({right}) + 1)")
            else:
                rendered.append(f"range({left}, {right})")
            i += 2
            continue
        # Arrow deref: $obj->{key} / $obj->[idx] / $obj->method(...)
        if t == "Token::Operator" and v == "->":
            # Look ahead: next child is Structure (Subscript), List, or Word.
            if i + 1 < len(children):
                nxt = children[i + 1]
                if nxt["t"] == "Structure::Subscript":
                    sub = render_subscript(nxt, ctx)
                    if rendered:
                        prev = rendered.pop()
                        rendered.append(f"{prev}{sub}")
                    i += 2
                    continue
                if nxt["t"] == "Token::Word":
                    # Method call: $obj->Method(args)
                    method = nxt.get("v", "")
                    py_method = M.METHOD_TABLE.get(method, method)
                    # ``_vp2vpy_*`` names are module-level helpers, not
                    # methods -- drop the receiver and emit a bare call.
                    bare_helper = py_method.startswith("_vp2vpy_")
                    if bare_helper:
                        ctx.helpers.add(py_method)
                    obj = rendered.pop() if rendered else ""
                    prefix = "" if bare_helper else f"{obj}."
                    # Following may be a List (args) or nothing.
                    if i + 2 < len(children) and children[i + 2]["t"] == "Structure::List":
                        args = render_call_args(children[i + 2], ctx, allow_fat_comma=True, api=method)
                        rendered.append(f"{prefix}{py_method}({args})")
                        i += 3
                    else:
                        rendered.append(f"{prefix}{py_method}()")
                        i += 2
                    continue
            # Fallback: drop arrow (Python deref is implicit).
            i += 1
            continue
        # Subscript directly after a symbol/word -> indexing.
        if t == "Structure::Subscript" and rendered and isinstance(rendered[-1], str):
            sub = render_subscript(c, ctx)
            prev = rendered.pop()
            rendered.append(f"{prev}{sub}")
            i += 1
            continue
        # Function-like: Word followed by List -> call.
        if t == "Token::Word" and i + 1 < len(children) and children[i + 1]["t"] == "Structure::List":
            call = render_call(c, children[i + 1], ctx)
            rendered.append(call)
            i += 2
            continue
        # Unary built-in without parens: ``defined $x``, ``scalar @a``, etc.
        if (
            t == "Token::Word"
            and v in ("defined", "exists", "scalar", "length", "keys", "values",
                      "int", "abs", "ref", "lc", "uc")
            and i + 1 < len(children)
            and children[i + 1]["t"] in ("Token::Symbol", "Token::Cast",
                                          "Structure::Subscript")
        ):
            # Consume one operand (Symbol + any chain of -> / subscript).
            j = i + 1
            operand_tokens: list[dict] = []
            while j < len(children):
                tj = children[j]["t"]
                if not operand_tokens:
                    if tj in ("Token::Symbol", "Token::Cast"):
                        operand_tokens.append(children[j])
                        j += 1
                        continue
                    break
                # Subsequent subscripts / arrow derefs.
                if tj == "Structure::Subscript":
                    operand_tokens.append(children[j])
                    j += 1
                    continue
                if (
                    tj == "Token::Operator" and children[j].get("v") == "->"
                    and j + 1 < len(children)
                    and children[j + 1]["t"] in ("Structure::Subscript", "Token::Word")
                ):
                    operand_tokens.append(children[j])
                    operand_tokens.append(children[j + 1])
                    j += 2
                    continue
                break
            operand = render_expr(operand_tokens, ctx)
            synthetic = {"t": "Structure::List", "c": [
                {"t": "Statement::Expression", "c": operand_tokens}
            ]}
            try:
                rendered.append(render_builtin(v, synthetic, ctx))
            except Unmappable:
                rendered.append(f"{v}({operand})")
            i = j
            continue
        # Word followed by a bareword arg (e.g. `print $x`) -- treat as call
        # with no parens.
        # We defer to the simple flow below.
        rendered.append(render_token_or_node(c, ctx))
        i += 1

    # Second pass: join with operator translation.
    parts = []
    for r in rendered:
        if isinstance(r, str):
            parts.append(r)
        else:
            parts.append(render_token_or_node(r, ctx))
    expr = " ".join(p for p in parts if p)
    expr = translate_operators(expr)
    return expr


def render_token_or_node(n: dict, ctx: WalkCtx) -> str:
    """Dispatch: token -> render_token, node -> render_node_expr."""
    if _is_node(n):
        return render_node_expr(n, ctx)
    return render_token(n, ctx)


def render_node_expr(n: dict, ctx: WalkCtx) -> str:
    """Render a non-leaf node as a Python expression."""
    t = n["t"]
    if t in ("Structure::List", "Structure::Condition"):
        return render_list(n, ctx)
    if t == "Structure::Constructor":
        return render_constructor(n, ctx)
    if t == "Structure::Subscript":
        return render_subscript(n, ctx)
    if t == "Statement" or t == "Statement::Expression":
        return render_expr(_significant_children(n), ctx)
    if t == "Structure::Block":
        # Anonymous block as expression: very rare; emit lambda placeholder.
        raise Unmappable("anonymous block as expression")
    if t == "Token::Regexp::Match":
        return render_regex_match(n, ctx)
    raise Unmappable(f"node expr {t!r}")


def render_list(n: dict, ctx: WalkCtx) -> str:
    """``( ... )`` rendered as a parenthesized Python expression.

    PPI wraps the content in a ``Statement::Expression`` child, so we descend
    one level before splitting on top-level commas.
    """
    inner = _inner_statement(n)
    if inner is None:
        return "()"
    items = split_top_level_commas(_significant_children(inner))
    rendered = [render_expr(it, ctx) for it in items]
    if not rendered:
        return "()"
    if len(rendered) == 1:
        return f"({rendered[0]})"
    return "(" + ", ".join(rendered) + ")"


def render_constructor(n: dict, ctx: WalkCtx) -> str:
    """``[1,2,3]`` -> list literal; ``{a => 1}`` -> dict literal."""
    inner = _inner_statement(n)
    if inner is None:
        return "[]"
    inner_items = split_top_level_commas(_significant_children(inner))
    # Distinguish dict vs list: dict iff items contain top-level ``=>``.
    is_dict = any(any(_is_op(c, "=>") for c in item) for item in inner_items)
    if is_dict:
        rendered = []
        for item in inner_items:
            k, v = split_fat_comma(item)
            rendered.append(f"{render_dict_key(k, ctx)}: {render_expr(v, ctx)}")
        return "{" + ", ".join(rendered) + "}"
    rendered = [render_expr(it, ctx) for it in inner_items]
    # If braces -> set? Perl doesn't have set literals; treat as anon hash if
    # empty pair or list otherwise. Default: list.
    return "[" + ", ".join(rendered) + "]"


def render_subscript(n: dict, ctx: WalkCtx) -> str:
    """``[i]`` / ``{k}`` -> Python ``[i]`` / ``["k"]``."""
    # PPI gives the inner statement as the child. The delimiter (square vs
    # brace) is in the .content -- which we don't have. We infer by content
    # heuristic: braces typically wrap a bareword/symbol; squares an integer
    # expression. Best-effort: if the inner is a single bareword, treat as
    # dict key.
    inner = _inner_statement(n)
    items = _significant_children(inner)
    if (
        len(items) == 1
        and items[0]["t"] == "Token::Word"
    ):
        return f'["{items[0]["v"]}"]'
    expr = render_expr(items, ctx)
    return f"[{expr}]"


def render_call(word: dict, args_list: dict, ctx: WalkCtx) -> str:
    """Render a function/builtin/API call: ``Word(args)``."""
    name = word.get("v", "")
    # Genesis2 API.
    if name in M.API_TABLE:
        py_name = M.API_TABLE[name]
        args = render_call_args(args_list, ctx, allow_fat_comma=True, api=name)
        return f"{py_name}({args})"
    # POSIX::ceil etc.
    if name.startswith("POSIX::"):
        sub = name[len("POSIX::"):]
        py = M.POSIX_MAP.get(sub)
        if py is None:
            raise Unmappable(f"POSIX::{sub}")
        ctx.imports.add("math")
        args = render_call_args(args_list, ctx)
        return f"{py}({args})"
    # Bare POSIX call after ``use POSIX;`` (ceil/log/sqrt/...).
    if ctx.posix_imported and name in M.POSIX_MAP:
        py = M.POSIX_MAP[name]
        ctx.imports.add("math")
        args = render_call_args(args_list, ctx)
        return f"{py}({args})"
    # Built-ins.
    if name in M.BUILTIN_MAP:
        return render_builtin(name, args_list, ctx)
    # User function -- pass through. Still consult API_KWARG_MAP so that
    # bare lowercase calls like ``parameter(NAME => ...)`` get the same
    # uppercase-kwarg normalisation as their Capital-P API_TABLE entries.
    args = render_call_args(args_list, ctx, allow_fat_comma=True, api=name)
    return f"{name}({args})"


def render_call_args(
    args_list: dict,
    ctx: WalkCtx,
    allow_fat_comma: bool = False,
    api: str | None = None,
) -> str:
    inner = _inner_statement(args_list)
    if inner is None:
        return ""
    items = split_top_level_commas(_significant_children(inner))
    kwarg_map = M.API_KWARG_MAP.get(api) if api else None
    shortcut = api in M.API_SHORTCUT_FIRST_PAIR if api else False
    parts: list[str] = []
    for idx, item in enumerate(items):
        if allow_fat_comma and any(_is_op(c, "=>") for c in item):
            k, v = split_fat_comma(item)
            kname = _bareword_key(k)
            if kname is not None:
                # Perl matches kwarg names case-insensitively (Perl wiki:
                # UniqueModule.pm parameter() uses ``m/^name$/i`` etc.).
                # The map is keyed uppercase by convention.
                if kwarg_map is not None and kname.upper() in kwarg_map:
                    parts.append(f"{kwarg_map[kname.upper()]}={render_expr(v, ctx)}")
                    continue
                # Genesis2 shortcut: ``define_param(NAME => VAL)`` ->
                # ``define_param("NAME", VAL)``.  Only the first pair is
                # eligible (Perl errors out on multi-pair shortcut).
                if shortcut and idx == 0:
                    parts.append(repr(kname))
                    parts.append(render_expr(v, ctx))
                    continue
                parts.append(f"{kname}={render_expr(v, ctx)}")
                continue
        parts.append(render_expr(item, ctx))
    return ", ".join(parts)


def render_builtin(name: str, args_list: dict, ctx: WalkCtx) -> str:
    tmpl = M.BUILTIN_MAP[name]
    if tmpl is None:
        raise Unmappable(f"builtin {name!r}")
    inner = _inner_statement(args_list)
    items = split_top_level_commas(_significant_children(inner)) if inner else []
    rendered = [render_expr(it, ctx) for it in items]
    if name in ("sprintf", "printf"):
        if not rendered:
            raise Unmappable(f"{name} with no format")
        fmt0 = rendered[0]
        rest = ", ".join(rendered[1:])
        if name == "sprintf":
            return f"({fmt0} % ({rest},))" if rest else f"({fmt0})"
        return f"print({fmt0} % ({rest},), end='')" if rest else f"print({fmt0}, end='')"
    if name == "die":
        ctx.helpers.add("_vp2vpy_error")
        return f"_vp2vpy_error({', '.join(rendered)})"
    if name == "looks_like_number":
        ctx.helpers.add("_vp2vpy_looks_like_number")
        return f"_vp2vpy_looks_like_number({', '.join(rendered)})"
    if name == "warn":
        ctx.imports.add("sys")
        return f"print({', '.join(rendered)}, file=sys.stderr)"
    if name == "push":
        return f"{rendered[0]}.append({', '.join(rendered[1:])})"
    if name == "unshift":
        return f"{rendered[0]}.insert(0, {', '.join(rendered[1:])})"
    if name == "pop":
        return f"{rendered[0]}.pop()"
    if name == "shift":
        return f"{rendered[0]}.pop(0)"
    if name == "scalar":
        return f"len({rendered[0]})"
    if name == "length":
        return f"len({rendered[0]})"
    if name == "defined":
        return f"({rendered[0]} is not None)"
    if name == "keys":
        return f"list({rendered[0]})"
    if name == "values":
        return f"list({rendered[0]}.values())"
    if name == "join":
        sep = rendered[0]
        rest = ", ".join(rendered[1:])
        return f"({sep}).join([{rest}])"
    if name == "split":
        return f"({rendered[1]}).split({rendered[0]})"
    if name == "lc":
        return f"({rendered[0]}).lower()"
    if name == "uc":
        return f"({rendered[0]}).upper()"
    if name == "int":
        return f"int({rendered[0]})"
    if name == "abs":
        return f"abs({rendered[0]})"
    if name == "print":
        return f"print({', '.join(rendered)})"
    if name == "exists":
        # exists $h{k} -- but here args have been parsed.
        if len(rendered) == 1:
            # Probably came as exists($h{k}); we don't have easy access to the
            # split. Best-effort: passthrough.
            raise Unmappable("exists() with non-trivial arg")
        return f"({rendered[1]} in {rendered[0]})"
    raise Unmappable(f"builtin {name!r}")


# ---------------------------------------------------------------------------
# Regex.
# ---------------------------------------------------------------------------

def render_regex_match(n: dict, ctx: WalkCtx) -> str:
    """Bare ``m/pat/`` (no ``=~`` / ``!~``) -- matches Perl's implicit ``$_``,
    which we don't model. Bound forms are handled in the binary-op path."""
    raise Unmappable("bare m// against implicit $_")


def _parse_regex(v: str) -> tuple[str, str]:
    # v is like ``m/pat/i`` or ``/pat/`` or ``m{pat}gi``.
    s = v
    if s.startswith("m"):
        s = s[1:]
    # Skip leading whitespace.
    s = s.lstrip()
    if not s:
        return "", ""
    open_d = s[0]
    pairs = {"(": ")", "{": "}", "[": "]", "<": ">"}
    close_d = pairs.get(open_d, open_d)
    # Find unescaped close.
    i = 1
    while i < len(s):
        if s[i] == "\\":
            i += 2
            continue
        if s[i] == close_d:
            break
        i += 1
    body = s[1:i]
    flags = s[i + 1:] if i + 1 <= len(s) else ""
    return body, flags


def _regex_flags_to_python(flags: str) -> str:
    out = []
    if "i" in flags:
        out.append("re.I")
    if "s" in flags:
        out.append("re.S")
    if "m" in flags:
        out.append("re.M")
    if "x" in flags:
        out.append("re.X")
    return " | ".join(out)


# ---------------------------------------------------------------------------
# Helpers: split lists by top-level commas / fat commas.
# ---------------------------------------------------------------------------

def _inner_statement(n: dict) -> dict | None:
    """Return the Statement child of a List/Subscript/Block, or None."""
    for c in _children(n):
        if c["t"].startswith("Statement"):
            return c
    return None


def split_top_level_commas(children: list[dict]) -> list[list[dict]]:
    """Split children on top-level ``,`` and ``=>`` tokens.

    Nested lists/subscripts/blocks are atomic, so this counts depth-zero
    commas only.
    """
    out: list[list[dict]] = [[]]
    for c in children:
        if c["t"] == "Token::Operator" and c.get("v") in (",", "=>"):
            if c.get("v") == ",":
                out.append([])
                continue
        out[-1].append(c)
    return [it for it in out if it]


def split_fat_comma(item: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split a ``key => value`` group on its top-level ``=>``."""
    for i, c in enumerate(item):
        if c["t"] == "Token::Operator" and c.get("v") == "=>":
            return item[:i], item[i + 1:]
    raise Unmappable("expected fat comma")


def _bareword_key(item: list[dict]) -> str | None:
    """If ``item`` is a single bareword or quoted string, return that name."""
    items = [c for c in item if c["t"] != "Token::Whitespace"]
    if len(items) != 1:
        return None
    c = items[0]
    if c["t"] == "Token::Word":
        return c.get("v")
    if c["t"] == "Token::Quote::Single":
        return c.get("v", "")[1:-1]
    return None


def render_dict_key(k: list[dict], ctx: WalkCtx) -> str:
    name = _bareword_key(k)
    if name is not None:
        return repr(name)
    return render_expr(k, ctx)


# ---------------------------------------------------------------------------
# Operator translation: textual fixups after expression rendering.
# ---------------------------------------------------------------------------

def translate_operators(expr: str) -> str:
    """No-op: operators are now translated at the token level (see
    ``render_token``). Kept as a hook in case post-pass cleanup is needed."""
    return expr


# ---------------------------------------------------------------------------
# Statement translation.
# ---------------------------------------------------------------------------

@dataclass
class StatementResult:
    lines: list[str]                   # Python lines (no leading indent)
    opens_block: str | None = None     # 'for'|'while'|'if'|'sub' if last line opens
    closes_block: bool = False         # True if statement was a closer
    chain_open: str | None = None      # 'elif'|'else' chain markers


def translate_statement(n: dict, ctx: WalkCtx) -> StatementResult:
    """Translate a single top-level PPI statement node to Python lines."""
    t = n["t"]
    if t == "Statement::Variable":
        return _translate_variable(n, ctx)
    if t == "Statement::Compound":
        return _translate_compound(n, ctx)
    if t == "Statement::Sub":
        return _translate_sub(n, ctx)
    if t == "Statement::Break":
        return _translate_break(n, ctx)
    if t == "Statement::Include":
        # use POSIX; -> drop (we inject math import on demand), but note it
        # so bare ``ceil(...)``/``log(...)``/... calls get the POSIX_MAP
        # treatment.
        for c in _significant_children(n):
            if c["t"] == "Token::Word" and c.get("v") == "POSIX":
                ctx.posix_imported = True
                break
        return StatementResult(lines=[])
    if t == "Statement::Package":
        return StatementResult(lines=[])
    if t == "Statement::Null":
        return StatementResult(lines=[])
    if t == "Statement::Expression" or t == "Statement":
        return _translate_expression_stmt(n, ctx)
    raise Unmappable(f"statement {t!r}")


def _translate_variable(n: dict, ctx: WalkCtx) -> StatementResult:
    children = _significant_children(n)
    # Drop leading ``my``/``our``/``local``.
    if children and _is_word(children[0], "my", "our", "local"):
        decl = children[0]["v"]
        if decl == "local":
            return StatementResult(lines=["# TODO vp2vpy: `local` not translated"])
        children = children[1:]
    # Drop trailing ``;``.
    if children and _is_struct(children[-1], ";"):
        children = children[:-1]
    # ``my ($a, $b, $c);`` or ``my ($a, $b) = RHS;`` -- Perl list-of-vars
    # declaration / parallel assignment.
    if children and children[0]["t"] == "Structure::List":
        names = _list_of_symbols(children[0])
        if names is not None:
            if len(children) == 1:
                # No RHS: just declare. Initialise all to None.
                lhs = ", ".join(names)
                rhs = ", ".join(["None"] * len(names))
                return StatementResult(lines=[f"{lhs} = {rhs}"])
            # ``my (...) = RHS;`` -- expect ``=`` then expression.
            if (
                len(children) >= 3
                and children[1]["t"] == "Token::Operator"
                and children[1].get("v") == "="
            ):
                rhs_expr = render_expr(children[2:], ctx)
                return StatementResult(lines=[f"{', '.join(names)} = {rhs_expr}"])
    # Track the LHS sigil so we can pick the right collection literal for the
    # RHS in array/hash assignments.
    lhs_sigil = ""
    if children and children[0]["t"] == "Token::Symbol":
        lhs_sigil = children[0]["v"][:1]
    expr = render_expr(children, ctx)
    # `@arr = (1, 2, 3)` -> `arr = [1, 2, 3]`; `%h = (k => v)` -> dict literal.
    if lhs_sigil in ("@", "%") and "=" in expr:
        lhs, _, rhs = expr.partition("=")
        rhs = rhs.strip()
        if (
            rhs.startswith("(")
            and rhs.endswith(")")
            and _outer_parens_enclose_all(rhs)
            # A rendered conditional `(a if c else b)` is not a Perl list.
            and not re.search(r"\bif\b", rhs)
        ):
            body = rhs[1:-1]
            if lhs_sigil == "@":
                expr = f"{lhs.rstrip()} = [{body}]"
            else:
                # Perl flat list of k,v,k,v -> Python dict; best-effort: if the
                # body looks like ``k=v, ...`` keyword-arg form, leave alone.
                expr = f"{lhs.rstrip()} = dict([{body}])" if "=" not in body else f"{lhs.rstrip()} = dict({rhs})"
    return StatementResult(lines=[expr])


def _list_of_symbols(list_node: dict) -> list[str] | None:
    """If ``list_node`` is a ``Structure::List`` of bare ``$name`` symbols,
    return the unsigiled Python names. Otherwise return None.
    """
    inner = _inner_statement(list_node)
    if inner is None:
        return None
    items = split_top_level_commas(_significant_children(inner))
    out: list[str] = []
    for item in items:
        sig = [c for c in item if c["t"] != "Token::Whitespace"]
        if len(sig) != 1 or sig[0]["t"] != "Token::Symbol":
            return None
        out.append(_strip_sigil(sig[0]["v"]))
    return out or None


def _outer_parens_enclose_all(s: str) -> bool:
    """True iff the leading ``(`` matches the trailing ``)``.

    Used by the ``@arr = (...)`` -> ``arr = [...]`` rewrite to avoid being
    fooled by RHS expressions like ``(x).method()`` where the leading and
    trailing parens belong to different groups.
    """
    depth = 0
    for i, ch in enumerate(s):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i == len(s) - 1
    return False


def _translate_expression_stmt(n: dict, ctx: WalkCtx) -> StatementResult:
    children = _significant_children(n)
    # Strip trailing ``;`` early so we can pattern-match the bare statement.
    if children and _is_struct(children[-1], ";"):
        children = children[:-1]
    # Postfix inc/dec: ``$x++`` -> ``x += 1``; ``$x--`` -> ``x -= 1``.
    if (
        len(children) == 2
        and children[0]["t"] == "Token::Symbol"
        and children[1]["t"] == "Token::Operator"
        and children[1].get("v") in ("++", "--")
    ):
        var = _strip_sigil(children[0]["v"])
        op = "+=" if children[1]["v"] == "++" else "-="
        return StatementResult(lines=[f"{var} {op} 1"])
    # Prefix inc/dec: ``++$x``.
    if (
        len(children) == 2
        and children[0]["t"] == "Token::Operator"
        and children[0].get("v") in ("++", "--")
        and children[1]["t"] == "Token::Symbol"
    ):
        var = _strip_sigil(children[1]["v"])
        op = "+=" if children[0]["v"] == "++" else "-="
        return StatementResult(lines=[f"{var} {op} 1"])
    # Postfix conditionals come BEFORE the bare-word-builtin path so
    # ``print 'hi' if $debug;`` becomes ``if debug: print('hi')`` rather than
    # ``print('hi' if debug)``.
    # Postfix conditionals: ``STMT if COND;`` / ``STMT unless COND;``
    pf_idx = None
    pf_word = None
    for i, c in enumerate(children):
        if _is_word(c, "if", "unless", "while", "for", "foreach"):
            # Only count as postfix if there is content to its left.
            if i > 0 and not _is_struct(c, ";"):
                pf_idx = i
                pf_word = c["v"]
                break
    if pf_idx is not None and pf_word in ("if", "unless"):
        body = children[:pf_idx]
        cond = children[pf_idx + 1:]
        # Strip trailing semicolon.
        if cond and _is_struct(cond[-1], ";"):
            cond = cond[:-1]
        body_py = render_expr(body, ctx)
        cond_py = render_expr(cond, ctx)
        if pf_word == "unless":
            return StatementResult(lines=[f"if not ({cond_py}):", f"    {body_py}"])
        return StatementResult(lines=[f"if {cond_py}:", f"    {body_py}"])
    # Bare-word builtin calls without parens: ``push @arr, $x;``.
    if (
        children
        and children[0]["t"] == "Token::Word"
        and children[0].get("v") in M.BUILTIN_MAP
        and len(children) > 1
        and children[1]["t"] != "Structure::List"
    ):
        name = children[0]["v"]
        synthetic = {"t": "Structure::List", "c": [
            {"t": "Statement::Expression", "c": children[1:]}
        ]}
        try:
            return StatementResult(lines=[render_builtin(name, synthetic, ctx)])
        except Unmappable:
            pass  # fall through to normal handling
    if not children:
        return StatementResult(lines=[])
    expr = render_expr(children, ctx)
    return StatementResult(lines=[expr])


def _translate_compound(n: dict, ctx: WalkCtx) -> StatementResult:
    """``for``/``foreach``/``while``/``until``/``if`` block.

    Genesis2 templates frequently put just the *opener* on one ``//;`` line
    and the body on subsequent lines (with `}` on another line). PPI handles
    this if we parse the whole `//;` content as one Perl text, but the
    line-by-line driver may see partial fragments. We render whatever the
    children give us; if the structure is malformed (no Block child), we
    treat it as an open-block opener.
    """
    children = _significant_children(n)
    if not children:
        return StatementResult(lines=[])
    head = children[0]
    kw = head.get("v") if head["t"] == "Token::Word" else None
    if kw in ("for", "foreach"):
        return _translate_for(children, ctx)
    if kw in ("while", "until"):
        return _translate_while(children, ctx, until=(kw == "until"))
    if kw in ("if", "unless"):
        return _translate_if(children, ctx, negate=(kw == "unless"))
    raise Unmappable(f"compound head {kw!r}")


def _translate_for(children: list[dict], ctx: WalkCtx) -> StatementResult:
    """``for/foreach`` translation."""
    # Shape A (foreach): foreach my $x (LIST) { ... }
    # Shape B (C-style): for (my $i=0; $i<N; $i++) { ... }
    # PPI distinguishes them: C-style wraps the head in ``Structure::For``;
    # foreach wraps the iterable in ``Structure::List``.
    rest = children[1:]
    var: str | None = None
    if rest and _is_word(rest[0], "my", "our"):
        rest = rest[1:]
    if rest and rest[0]["t"] == "Token::Symbol":
        var = _strip_sigil(rest[0]["v"])
        rest = rest[1:]
    if not rest:
        raise Unmappable("for: empty body")
    head = rest[0]
    rest = rest[1:]
    if head["t"] == "Structure::For":
        return _translate_c_for(head, rest, ctx)
    if head["t"] == "Structure::List":
        inner = _inner_statement(head)
        inner_children = _significant_children(inner) if inner else []
        iter_expr = render_expr(inner_children, ctx)
        if var is None:
            var = "_x"
        head_py = f"for {var} in {iter_expr}:"
        body_lines = _render_block_body(rest, ctx)
        return StatementResult(lines=[head_py] + body_lines + ["# endfor"])
    raise Unmappable(f"for: unexpected head {head['t']!r}")


def _translate_c_for(for_struct: dict, rest: list[dict], ctx: WalkCtx) -> StatementResult:
    """``for (init; cond; step) { ... }`` -> ``for var in range(...):``.

    PPI pre-splits the parens into three child statements inside
    ``Structure::For``. Recognised init/cond/step shapes only; anything more
    exotic falls back to TODO.
    """
    parts = [c for c in _children(for_struct) if c["t"].startswith("Statement")]
    if len(parts) != 3:
        raise Unmappable("C-for: needs init;cond;step")
    init = _significant_children(parts[0])
    cond = _significant_children(parts[1])
    step = _significant_children(parts[2])
    # Strip trailing ``;`` from each.
    for L in (init, cond, step):
        while L and _is_struct(L[-1], ";"):
            L.pop()
    # Init: my $var = EXPR  OR  $var = EXPR
    init_children = list(init)
    if init_children and _is_word(init_children[0], "my", "our"):
        init_children = init_children[1:]
    if not init_children or init_children[0]["t"] != "Token::Symbol":
        raise Unmappable("C-for: expected symbol in init")
    var = _strip_sigil(init_children[0]["v"])
    if len(init_children) < 3 or not _is_op(init_children[1], "="):
        raise Unmappable("C-for: expected `=` in init")
    start = render_expr(init_children[2:], ctx)
    # Cond: $var </<= EXPR
    cond_children = cond
    if (
        len(cond_children) >= 3
        and cond_children[0]["t"] == "Token::Symbol"
        and _strip_sigil(cond_children[0]["v"]) == var
        and _is_op(cond_children[1], "<", "<=")
    ):
        op = cond_children[1]["v"]
        end_expr = render_expr(cond_children[2:], ctx)
        end = f"({end_expr}) + 1" if op == "<=" else end_expr
    else:
        raise Unmappable("C-for: unsupported cond shape")
    # Step: $var++ / $var-- / $var += N
    step_children = step
    rest = list(rest)  # unused in the new shape; keep param symmetry
    step_str = ""
    if (
        len(step_children) == 2
        and step_children[0]["t"] == "Token::Symbol"
        and _is_op(step_children[1], "++")
    ):
        step_str = ""  # default +1
    elif (
        len(step_children) == 2
        and step_children[0]["t"] == "Token::Symbol"
        and _is_op(step_children[1], "--")
    ):
        # Negative range: start..end, step -1.
        step_str = "step=-1"
    elif (
        len(step_children) >= 3
        and step_children[0]["t"] == "Token::Symbol"
        and _is_op(step_children[1], "+=")
    ):
        step_str = render_expr(step_children[2:], ctx)
    else:
        raise Unmappable("C-for: unsupported step shape")
    if step_str == "step=-1":
        head = f"for {var} in range({start}, {end} - 1, -1):"
    elif step_str:
        head = f"for {var} in range({start}, {end}, {step_str}):"
    else:
        head = f"for {var} in range({start}, {end}):"
    body_lines = _render_block_body(rest, ctx)
    return StatementResult(lines=[head] + body_lines + ["# endfor"])


def _translate_while(children: list[dict], ctx: WalkCtx, until: bool) -> StatementResult:
    # while (COND) { ... } -- PPI wraps the cond in Structure::Condition.
    rest = children[1:]
    if not rest or rest[0]["t"] not in ("Structure::Condition", "Structure::List"):
        raise Unmappable("while missing parens")
    inner = _inner_statement(rest[0])
    cond = render_expr(_significant_children(inner), ctx) if inner else "True"
    if until:
        cond = f"not ({cond})"
    rest = rest[1:]
    body_lines = _render_block_body(rest, ctx)
    return StatementResult(lines=[f"while {cond}:"] + body_lines + ["# endwhile"])


def _translate_if(children: list[dict], ctx: WalkCtx, negate: bool) -> StatementResult:
    """``if/unless`` (+ ``elsif``/``else``) chain.

    PPI lays the chain out as: ``if`` cond block (``elsif`` cond block)*
    (``else`` block)? — the keyword tokens (``if``/``elsif``/``else``) and the
    Structure::Condition / Structure::Block nodes are flat siblings.
    """
    out: list[str] = []
    i = 1  # past the leading `if`/`unless` keyword
    first = True
    while i < len(children):
        c = children[i]
        if c["t"] == "Token::Word" and c.get("v") == "else":
            block_node = children[i + 1] if i + 1 < len(children) else None
            out.append("else:")
            out.extend(_render_block_body([block_node] if block_node else [], ctx))
            i += 2
            continue
        if c["t"] == "Token::Word" and c.get("v") == "elsif":
            # advance past the word
            i += 1
            continue
        if c["t"] in ("Structure::Condition", "Structure::List"):
            block_node = children[i + 1] if i + 1 < len(children) else None
            inner = _inner_statement(c)
            cond = render_expr(_significant_children(inner), ctx) if inner else "True"
            if negate and first:
                cond = f"not ({cond})"
            kw_py = "if" if first else "elif"
            out.append(f"{kw_py} {cond}:")
            out.extend(_render_block_body([block_node] if block_node else [], ctx))
            i += 2
            first = False
            continue
        i += 1
    out.append("# endif")
    return StatementResult(lines=out)


def _render_block_body(rest: list[dict], ctx: WalkCtx) -> list[str]:
    """Render the body of a compound statement (Structure::Block + tail)."""
    out: list[str] = []
    for c in rest:
        if c["t"] == "Structure::Block":
            inner_children = _children(c)
            stmts = [x for x in inner_children if x["t"].startswith("Statement")]
            for s in stmts:
                r = translate_statement(s, ctx)
                for line in r.lines:
                    out.append("    " + line)
    if not out:
        out.append("    pass")
    return out


def _split_by_semis(children: list[dict]) -> list[list[dict]]:
    """Split top-level by ``;`` structure tokens."""
    out: list[list[dict]] = [[]]
    for c in children:
        if _is_struct(c, ";"):
            out.append([])
            continue
        out[-1].append(c)
    return [it for it in out if it]


def _translate_sub(n: dict, ctx: WalkCtx) -> StatementResult:
    children = _significant_children(n)
    # sub NAME { ... }
    if len(children) >= 2 and _is_word(children[0], "sub") and children[1]["t"] == "Token::Word":
        name = children[1]["v"]
        body = [c for c in children[2:] if c["t"] == "Structure::Block"]
        if not body:
            return StatementResult(lines=[f"def {name}():", "    pass"])
        block = body[0]
        stmts = [s for s in _children(block) if s["t"].startswith("Statement")]
        body_lines: list[str] = []
        for s in stmts:
            r = translate_statement(s, ctx)
            for line in r.lines:
                body_lines.append("    " + line)
        if not body_lines:
            body_lines.append("    pass")
        return StatementResult(lines=[f"def {name}(*_args):"] + body_lines)
    raise Unmappable("anonymous sub")


def _translate_break(n: dict, ctx: WalkCtx) -> StatementResult:
    children = _significant_children(n)
    if children and _is_word(children[0], "last"):
        return StatementResult(lines=["break"])
    if children and _is_word(children[0], "next"):
        return StatementResult(lines=["continue"])
    if children and _is_word(children[0], "return"):
        if len(children) > 1 and not _is_struct(children[1], ";"):
            expr = render_expr(children[1:], ctx)
            return StatementResult(lines=[f"return {expr}"])
        return StatementResult(lines=["return"])
    return StatementResult(lines=["pass"])


# ---------------------------------------------------------------------------
# Top-level: file translator.
# ---------------------------------------------------------------------------


@dataclass
class TranslationResult:
    text: str
    todos: list[str] = field(default_factory=list)


def translate_perl_snippet(perl_src: str, helper: Helper, ctx: WalkCtx) -> list[str]:
    """Parse via the helper and translate to Python lines."""
    resp = helper.parse(perl_src)
    if not resp.get("ok"):
        raise Unmappable(f"PPI parse failed: {resp.get('error', '')}")
    doc = resp["tree"]
    out: list[str] = []
    for s in _children(doc):
        t = s["t"]
        if not t.startswith("Statement"):
            continue
        r = translate_statement(s, ctx)
        out.extend(r.lines)
    return out


def translate_backtick_expr(perl_src: str, helper: Helper, ctx: WalkCtx) -> str:
    """Translate a Perl expression (the body of a ``...`` span) to Python."""
    # Wrap with parens so PPI parses it as an expression statement.
    wrapped = "(" + perl_src + ");"
    resp = helper.parse(wrapped)
    if not resp.get("ok"):
        raise Unmappable(f"PPI parse failed: {resp.get('error', '')}")
    doc = resp["tree"]
    for s in _children(doc):
        if not s["t"].startswith("Statement"):
            continue
        # Strip trailing ``;``.
        children = _significant_children(s)
        if children and _is_struct(children[-1], ";"):
            children = children[:-1]
        # Unwrap the outer parens (List).
        if len(children) == 1 and children[0]["t"] == "Structure::List":
            inner = _inner_statement(children[0])
            if inner is not None:
                children = _significant_children(inner)
        return render_expr(children, ctx)
    return ""


def translate_verilog_line(line: str, helper: Helper, ctx: WalkCtx,
                           todos: list[str], src_line: int) -> str:
    """Translate backtick spans inside a Verilog body line.

    Lines that look like Verilog compiler directives (``\\`timescale``,
    ``\\`define``, ``\\`include`` etc. -- a backtick followed by an
    identifier with no matching close) are passed through with the leading
    backtick backslash-escaped, so the genesispy parser treats it as
    literal text.
    """
    # First, count unescaped backticks in the *original* line. If odd, the
    # line has at least one lone backtick (typically a Verilog directive).
    stripped = re.sub(r"\\.", "", line)  # remove escaped chars
    n_ticks = stripped.count("`")
    if n_ticks % 2 == 1:
        # Find the first unescaped lone backtick (one with no matching close
        # later in the line) and escape just that one.
        # Simple heuristic: a leading ``\\`<word>`` directive.
        m = re.match(r"^(\s*)`([A-Za-z_]\w*)", line)
        if m:
            line = m.group(1) + "\\`" + m.group(2) + line[m.end():]
    out = []
    last = 0
    for m in BACKTICK_RE.finditer(line):
        out.append(line[last:m.start()])
        body = m.group(1)
        try:
            py = translate_backtick_expr(body, helper, ctx)
            out.append(f"`{py}`")
        except Unmappable as e:
            todos.append(f"line {src_line}: backtick `{body}`: {e}")
            out.append(m.group(0))
        last = m.end()
    out.append(line[last:])
    return "".join(out)


# Brace-shape patterns: open/close detection for line-by-line block tracking.
_BLOCK_OPEN_END = re.compile(r"\{\s*$")
_BLOCK_CLOSE_START = re.compile(r"^\s*\}")
_ELSIF_ELSE_RE = re.compile(r"^\s*\}\s*(?:elsif|else)\b")


def _line_opens_block(perl: str) -> bool:
    return bool(_BLOCK_OPEN_END.search(perl))


def _line_closes_block(perl: str) -> bool:
    return bool(_BLOCK_CLOSE_START.match(perl)) and not _ELSIF_ELSE_RE.match(perl)


def _line_chain(perl: str) -> str | None:
    """``} elsif (...) {`` or ``} else {`` -> 'elif'/'else'."""
    m = re.match(r"^\s*\}\s*(elsif|else)\b", perl)
    if not m:
        return None
    return "elif" if m.group(1) == "elsif" else "else"


@dataclass
class _BlockState:
    kind: str           # 'for' / 'while' / 'if' / 'sub' / 'unknown'
    src_line: int


class FileTranslator:
    """Translate one .vp file. Maintains a brace-block stack across lines."""

    def __init__(self, helper: Helper, *, strict: bool = False) -> None:
        self.helper = helper
        self.strict = strict
        self.ctx = WalkCtx()
        self.stack: list[_BlockState] = []
        self.todos: list[str] = []

    @property
    def depth(self) -> int:
        return len(self.stack)

    def _indent_dir(self) -> str:
        return "    " * self.depth

    def _handle_directive(self, rec: Record, out: list[str]) -> None:
        perl = rec.text.strip()
        if not perl:
            out.append(f"//;")
            return
        # Strip a trailing Perl comment ("# ...") so `} # endwhile` still reads
        # as a bare closer.
        perl_no_cmt = re.sub(r"\s+#.*$", "", perl).rstrip()
        # Closer alone: ``}`` -> pop, emit endX.
        if perl_no_cmt == "}":
            if not self.stack:
                self._emit_todo(out, rec.line_no, "stray `}`", perl)
                return
            top = self.stack.pop()
            sentinel = self._sentinel_for(top.kind)
            if sentinel:
                out.append(f"//; {self._indent_dir()}# {sentinel}")
            return
        # Closer + chain: ``} elsif (...) {`` / ``} else {``
        chain = _line_chain(perl)
        if chain:
            if not self.stack:
                self._emit_todo(out, rec.line_no, "stray `} elsif/else`", perl)
                return
            # Pop the current branch's indent; same `if` chain continues.
            self.stack.pop()
            try:
                if chain == "elif":
                    m = re.match(r"^\s*\}\s*elsif\s*\((.*)\)\s*\{\s*$", perl)
                    if not m:
                        raise Unmappable("malformed `} elsif (...) {`")
                    py = self._translate_expr(m.group(1).strip())
                    out.append(f"//; {self._indent_dir()}elif {py}:")
                else:
                    if not re.match(r"^\s*\}\s*else\s*\{\s*$", perl):
                        raise Unmappable("malformed `} else {`")
                    out.append(f"//; {self._indent_dir()}else:")
                self.stack.append(_BlockState("if", rec.line_no))
            except Unmappable as e:
                self._emit_todo(out, rec.line_no, str(e), perl)
            return
        # Opener: ``KEYWORD (...) {`` at end.
        if _line_opens_block(perl):
            inner = perl[:perl.rstrip().rfind("{")].rstrip()
            kind = self._infer_kind(inner)
            try:
                py = self._translate_opener(inner, kind)
                for j, line in enumerate(py):
                    out.append(f"//; {self._indent_dir()}{line}")
                self.stack.append(_BlockState(kind, rec.line_no))
            except Unmappable as e:
                self._emit_todo(out, rec.line_no, str(e), perl)
            return
        # Plain statement.
        try:
            py_lines = translate_perl_snippet(perl, self.helper, self.ctx)
            if not py_lines:
                # Drop empty (e.g. ``;`` alone).
                return
            for line in py_lines:
                out.append(f"//; {self._indent_dir()}{line}")
        except Unmappable as e:
            self._emit_todo(out, rec.line_no, str(e), perl)

    def _emit_todo(self, out: list[str], src_line: int, reason: str, perl: str) -> None:
        msg = f"line {src_line}: {reason}: {perl!r}"
        self.todos.append(msg)
        if self.strict:
            raise Unmappable(msg)
        # Best-effort: emit a passthrough comment so the user sees the original.
        out.append(f"//; {self._indent_dir()}# TODO vp2vpy: {reason}")
        out.append(f"//; {self._indent_dir()}# {perl}")

    def _infer_kind(self, opener_head: str) -> str:
        # Extract the leading identifier; Genesis2 sources often write
        # ``while(...)`` with no space, so split-on-whitespace doesn't work.
        m = re.match(r"\s*}?\s*(\w+)", opener_head)
        kw = m.group(1) if m else ""
        if kw in ("for", "foreach"):
            return "for"
        if kw in ("while", "until"):
            return "while"
        if kw in ("if", "unless", "elsif"):
            return "if"
        if kw == "sub":
            return "sub"
        return "unknown"

    def _sentinel_for(self, kind: str) -> str | None:
        return {
            "for": "endfor",
            "while": "endwhile",
            "if": "endif",
            "sub": "enddef",
            "unknown": None,
        }.get(kind)

    def _translate_opener(self, opener_head: str, kind: str) -> list[str]:
        """Translate a Perl block-opener line (without the trailing ``{``)."""
        # Append a sentinel ``{ }`` so PPI sees a complete compound statement.
        synthetic = opener_head + " { ; }"
        resp = self.helper.parse(synthetic)
        if not resp.get("ok"):
            raise Unmappable(f"opener parse: {resp.get('error', '')}")
        doc = resp["tree"]
        # Find first compound statement.
        for s in _children(doc):
            if s["t"] == "Statement::Compound":
                r = _translate_compound(s, self.ctx)
                # Strip the synthetic ``pass`` body and trailing sentinel: keep
                # only the opener line.
                opener_lines = [ln for ln in r.lines if not (
                    ln.startswith("    ") or ln.startswith("# end")
                )]
                return opener_lines
            if s["t"] == "Statement::Sub":
                r = translate_statement(s, self.ctx)
                return [r.lines[0]] if r.lines else []
        raise Unmappable(f"opener: PPI returned no compound for {opener_head!r}")

    def _translate_expr(self, perl_expr: str) -> str:
        return translate_backtick_expr(perl_expr, self.helper, self.ctx)

    def _handle_block(self, rec: Record, out: list[str]) -> None:
        # Multi-line /*; ... ;*/ block: translate as a sequence of statements,
        # emit each on its own //; line.
        perl = rec.text.strip()
        if not perl:
            return
        try:
            py_lines = translate_perl_snippet(perl, self.helper, self.ctx)
            for line in py_lines:
                out.append(f"//; {self._indent_dir()}{line}")
        except Unmappable as e:
            self._emit_todo(out, rec.line_no, str(e), perl)

    def translate(self, source: str) -> TranslationResult:
        records = _merge_continuations(classify(source))
        out: list[str] = []
        for rec in records:
            if rec.kind == "verilog":
                line = translate_verilog_line(
                    rec.text, self.helper, self.ctx, self.todos, rec.line_no
                )
                out.append(line)
            elif rec.kind == "directive":
                self._handle_directive(rec, out)
            elif rec.kind == "block":
                self._handle_block(rec, out)
        # Prepend imports / helpers as //; lines at the file head, before the
        # first non-blank line.
        prelude: list[str] = []
        if self.ctx.imports:
            for name in sorted(self.ctx.imports):
                prelude.append(f"//; {M.IMPORT_TRIGGERS[name]}")
        if self.ctx.helpers:
            for name in sorted(self.ctx.helpers):
                src = M.RUNTIME_HELPERS.get(name)
                if src:
                    for line in src.splitlines():
                        prelude.append(f"//; {line}")
        if prelude:
            out = prelude + out
        return TranslationResult(text="\n".join(out) + "\n", todos=list(self.todos))


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------

DEFAULT_EXT_MAP = {".vp": ".vpy", ".vph": ".vpy"}


def translate_file(src: Path, dst: Path, helper: Helper, strict: bool) -> TranslationResult:
    text = src.read_text(encoding="utf-8")
    ft = FileTranslator(helper, strict=strict)
    result = ft.translate(text)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(result.text, encoding="utf-8")
    return result


def _resolve_inputs(inputs: list[Path]) -> list[Path]:
    files: list[Path] = []
    for inp in inputs:
        if inp.is_dir():
            for ext in DEFAULT_EXT_MAP:
                files.extend(sorted(inp.rglob(f"*{ext}")))
        else:
            files.append(inp)
    return files


def _dst_for(src: Path, root: Path | None, out: Path | None) -> Path:
    out_ext = DEFAULT_EXT_MAP.get(src.suffix, ".vpy")
    if out is None:
        return src.with_suffix(out_ext)
    if root is not None and root in src.parents:
        rel = src.relative_to(root)
        return (out / rel).with_suffix(out_ext)
    return out / (src.stem + out_ext)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="genesispy-vp2vpy",
        description="Translate Genesis2 (Perl) .vp/.vph templates to "
                    "genesispy (Python) .vpy.",
    )
    p.add_argument("inputs", nargs="+", type=Path,
                   help="input .vp/.vph file(s) or directory")
    p.add_argument("-o", "--out-dir", type=Path, default=None,
                   help="write translated files into this directory; "
                        "default: sibling to each input")
    p.add_argument("--strict", action="store_true",
                   help="fail on the first unmappable construct (default: "
                        "best-effort with TODO comments)")
    p.add_argument("--check", action="store_true",
                   help="exit nonzero if any file emits a TODO")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="print per-file translation summary")
    args = p.parse_args(argv)

    files = _resolve_inputs(args.inputs)
    if not files:
        print("vp2vpy: no input files matched", file=sys.stderr)
        return 1

    # Determine the common root for relative paths (only when reading dirs).
    root: Path | None = None
    if args.out_dir and any(p.is_dir() for p in args.inputs):
        dirs = [p for p in args.inputs if p.is_dir()]
        if len(dirs) == 1:
            root = dirs[0]

    total_todos = 0
    rc = 0
    with Helper() as helper:
        for src in files:
            dst = _dst_for(src, root, args.out_dir)
            try:
                result = translate_file(src, dst, helper, strict=args.strict)
            except Unmappable as e:
                print(f"vp2vpy: {src}: {e}", file=sys.stderr)
                return 2
            n = len(result.todos)
            total_todos += n
            if args.verbose or n:
                print(f"vp2vpy: {src} -> {dst}  ({n} TODO)")
                for t in result.todos:
                    print(f"  {t}")
    if args.check and total_todos:
        rc = 3
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
