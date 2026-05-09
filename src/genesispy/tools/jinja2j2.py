"""Port stock-Jinja2 templates to the genesispy ``--j2`` dialect.

genesispy's ``--j2`` flag opts in to Jinja2-shaped *delimiters*
(``{% %}``, ``{{ }}``, ``{# #}``) but the embedded language is full
Python, not Jinja2's expression sub-language. This module converts a
stock-Jinja2 template into something ``parse_vpy(syntax="j2")`` can
elaborate.

Conversions performed:

- block openers gain a trailing ``:``  (``{% for x in xs %}`` ->
  ``{% for x in xs: %}``);
- filter pipes (``{{ x | upper }}``) are rewritten to Python equivalents
  via a built-in mapping;
- ``is`` tests are rewritten (``x is defined`` -> ``x is not None``);
- ``{% set N = E %}`` becomes a plain ``{% N = PY(E) %}`` assignment
  (genesispy-j2 statements are full Python);
- ``{% include "f" %}`` becomes ``{% include("f") %}`` (uses the
  bare-name include alias from the elaboration runtime);
- ``{# ... #}`` comments are preserved verbatim.

Constructs with no clean equivalent (``macro``, ``block``, ``extends``,
``import``, ``from``, ``call``, ``with``, ``do``, ``filter``-block,
``set``-block, ``raw``, ``autoescape``, custom filters, complex
``include`` forms) are unmappable. ``--strict`` (default) errors on the
first unmappable construct; ``--best-effort`` emits TODO comments and
warns.

Comments inside ``{% %}`` / ``{{ }}`` are not preserved (Jinja2's
expression parser strips them); top-level ``{# ... #}`` comments are.

The ``jinja2`` package is required and surfaced as the optional
dependency ``import-j2``.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple

try:
    import jinja2
    from jinja2 import nodes as j2nodes
except ImportError:  # pragma: no cover - exercised by missing-dep test path
    jinja2 = None  # type: ignore[assignment]
    j2nodes = None  # type: ignore[assignment]


# --------------------------------------------------------------------------- #
# Issue / result types
# --------------------------------------------------------------------------- #

@dataclass
class Issue:
    """A single conversion problem."""
    line: int
    col: int
    reason: str


class _Unmappable(Exception):
    """Raised internally when a construct cannot be ported."""
    def __init__(self, reason: str, line: int = 0, col: int = 0):
        super().__init__(reason)
        self.reason = reason
        self.line = line
        self.col = col


# --------------------------------------------------------------------------- #
# Filter and test mappings
# --------------------------------------------------------------------------- #

# Each entry: name -> callable(target_py: str, args_py: List[str]) -> str.
# target_py is the already-rewritten Python source for the filter target.
# args_py holds rewritten positional args (kwargs are unsupported here).
_FILTER_TABLE = {
    "upper":      lambda t, a: f"({t}).upper()",
    "lower":      lambda t, a: f"({t}).lower()",
    "capitalize": lambda t, a: f"({t}).capitalize()",
    "title":      lambda t, a: f"({t}).title()",
    "trim":       lambda t, a: f"({t}).strip()",
    "length":     lambda t, a: f"len({t})",
    "count":      lambda t, a: f"len({t})",
    "abs":        lambda t, a: f"abs({t})",
    "round":      lambda t, a: (f"round({t})" if not a else f"round({t}, {a[0]})"),
    "int":        lambda t, a: f"int({t})",
    "float":      lambda t, a: f"float({t})",
    "string":     lambda t, a: f"str({t})",
    "list":       lambda t, a: f"list({t})",
    "default":    lambda t, a: (f"({t} if {t} is not None else {a[0]})" if a else t),
    "d":          lambda t, a: (f"({t} if {t} is not None else {a[0]})" if a else t),
    "join":       lambda t, a: (f"{a[0]}.join(str(_) for _ in {t})" if a else f"''.join(str(_) for _ in {t})"),
    "first":      lambda t, a: f"({t})[0]",
    "last":       lambda t, a: f"({t})[-1]",
    "min":        lambda t, a: f"min({t})",
    "max":        lambda t, a: f"max({t})",
    "sum":        lambda t, a: f"sum({t})",
    "reverse":    lambda t, a: f"list(reversed({t}))",
    "sort":       lambda t, a: f"sorted({t})",
    "replace":    lambda t, a: f"({t}).replace({a[0]}, {a[1]})" if len(a) >= 2 else None,
    "split":      lambda t, a: f"({t}).split({a[0]})" if a else f"({t}).split()",
    "safe":       lambda t, a: t,
    "escape":     None,  # handled specially: warn in strict
    "e":          None,
    "tojson":     lambda t, a: f"__import__('json').dumps({t})",
}

_TEST_TABLE = {
    "defined":    lambda t, a: f"({t}) is not None",
    "undefined":  lambda t, a: f"({t}) is None",
    "none":       lambda t, a: f"({t}) is None",
    "number":     lambda t, a: f"isinstance({t}, (int, float))",
    "string":     lambda t, a: f"isinstance({t}, str)",
    "sequence":   lambda t, a: f"isinstance({t}, (list, tuple))",
    "mapping":    lambda t, a: f"isinstance({t}, dict)",
    "iterable":   lambda t, a: f"hasattr({t}, '__iter__')",
    "sameas":     lambda t, a: f"({t}) is ({a[0]})" if a else None,
    "equalto":    lambda t, a: f"({t}) == ({a[0]})" if a else None,
    "eq":         lambda t, a: f"({t}) == ({a[0]})" if a else None,
    "ne":         lambda t, a: f"({t}) != ({a[0]})" if a else None,
    "lt":         lambda t, a: f"({t}) < ({a[0]})"  if a else None,
    "le":         lambda t, a: f"({t}) <= ({a[0]})" if a else None,
    "gt":         lambda t, a: f"({t}) > ({a[0]})"  if a else None,
    "ge":         lambda t, a: f"({t}) >= ({a[0]})" if a else None,
    "true":       lambda t, a: f"({t}) is True",
    "false":      lambda t, a: f"({t}) is False",
    "odd":        lambda t, a: f"(({t}) % 2 == 1)",
    "even":       lambda t, a: f"(({t}) % 2 == 0)",
    "divisibleby": lambda t, a: f"(({t}) % ({a[0]}) == 0)" if a else None,
}


# --------------------------------------------------------------------------- #
# Source span scanner
# --------------------------------------------------------------------------- #

# Order matters: comment first (so `{#` doesn't get eaten by `{%`-class
# false matches), then statement, then variable.
_SPAN_RE = re.compile(
    r"""
    (?P<comment>  \{\#[\s\S]*?\#\}      ) |
    (?P<stmt>     \{%-?\s*[\s\S]*?\s*-?%\} ) |
    (?P<var>      \{\{-?\s*[\s\S]*?\s*-?\}\} )
    """,
    re.VERBOSE,
)


def _line_col(source: str, offset: int) -> Tuple[int, int]:
    """Return (1-based line, 1-based col) at byte offset within source."""
    head = source[:offset]
    line = head.count("\n") + 1
    col = offset - (head.rfind("\n") if "\n" in head else -1)
    return line, col


# --------------------------------------------------------------------------- #
# Expression rewriting (Jinja2 AST -> Python source)
# --------------------------------------------------------------------------- #

class _ExprRewriter:
    """Walk a Jinja2 expression AST and emit Python source."""

    def __init__(self, *, strict: bool, issues: List[Issue], lineno: int):
        self.strict = strict
        self.issues = issues
        self.lineno = lineno

    def visit(self, node) -> str:
        meth = getattr(self, f"v_{type(node).__name__}", None)
        if meth is None:
            return self._unmappable(
                f"unsupported Jinja2 expression node: {type(node).__name__}"
            )
        return meth(node)

    def _unmappable(self, reason: str) -> str:
        if self.strict:
            raise _Unmappable(reason, line=self.lineno)
        self.issues.append(Issue(line=self.lineno, col=0, reason=reason))
        return f"_TODO_{reason.replace(' ', '_').replace(':', '')}"

    # --- atoms -----------------------------------------------------------

    def v_Name(self, n) -> str:
        return n.name

    def v_NSRef(self, n) -> str:
        return f"{n.name}.{n.attr}"

    def v_Const(self, n) -> str:
        return repr(n.value)

    def v_TemplateData(self, n) -> str:
        return repr(n.data)

    def v_List(self, n) -> str:
        return "[" + ", ".join(self.visit(i) for i in n.items) + "]"

    def v_Tuple(self, n) -> str:
        items = [self.visit(i) for i in n.items]
        if len(items) == 1:
            return f"({items[0]},)"
        return "(" + ", ".join(items) + ")"

    def v_Dict(self, n) -> str:
        pairs = [f"{self.visit(p.key)}: {self.visit(p.value)}" for p in n.items]
        return "{" + ", ".join(pairs) + "}"

    # --- access ----------------------------------------------------------

    def v_Getattr(self, n) -> str:
        return f"{self.visit(n.node)}.{n.attr}"

    def v_Getitem(self, n) -> str:
        return f"{self.visit(n.node)}[{self.visit(n.arg)}]"

    def v_Slice(self, n) -> str:
        s = "" if n.start is None else self.visit(n.start)
        e = "" if n.stop  is None else self.visit(n.stop)
        if n.step is None:
            return f"{s}:{e}"
        return f"{s}:{e}:{self.visit(n.step)}"

    def v_Call(self, n) -> str:
        target = self.visit(n.node)
        parts = [self.visit(a) for a in n.args]
        parts += [f"{kw.key}={self.visit(kw.value)}" for kw in n.kwargs]
        if n.dyn_args is not None:
            parts.append(f"*{self.visit(n.dyn_args)}")
        if n.dyn_kwargs is not None:
            parts.append(f"**{self.visit(n.dyn_kwargs)}")
        return f"{target}({', '.join(parts)})"

    # --- arithmetic / logic ---------------------------------------------

    def _binop(self, n, op: str) -> str:
        return f"({self.visit(n.left)} {op} {self.visit(n.right)})"

    def v_Add(self, n): return self._binop(n, "+")
    def v_Sub(self, n): return self._binop(n, "-")
    def v_Mul(self, n): return self._binop(n, "*")
    def v_Div(self, n): return self._binop(n, "/")
    def v_FloorDiv(self, n): return self._binop(n, "//")
    def v_Mod(self, n): return self._binop(n, "%")
    def v_Pow(self, n): return self._binop(n, "**")
    def v_And(self, n): return self._binop(n, "and")
    def v_Or(self, n):  return self._binop(n, "or")

    def v_Concat(self, n) -> str:
        return "(" + " + ".join(f"str({self.visit(x)})" for x in n.nodes) + ")"

    def v_Pos(self, n) -> str: return f"(+{self.visit(n.node)})"
    def v_Neg(self, n) -> str: return f"(-{self.visit(n.node)})"
    def v_Not(self, n) -> str: return f"(not {self.visit(n.node)})"

    def v_Compare(self, n) -> str:
        out = self.visit(n.expr)
        for op in n.ops:
            sym = {"eq": "==", "ne": "!=", "lt": "<", "lteq": "<=",
                   "gt": ">", "gteq": ">=", "in": "in",
                   "notin": "not in"}.get(op.op)
            if sym is None:
                return self._unmappable(f"unknown compare op {op.op!r}")
            out += f" {sym} {self.visit(op.expr)}"
        return f"({out})"

    def v_CondExpr(self, n) -> str:
        # Jinja2: <expr1> if <test> else <expr2>
        test = self.visit(n.test)
        if_ = self.visit(n.expr1)
        else_ = self.visit(n.expr2) if n.expr2 is not None else "None"
        return f"({if_} if {test} else {else_})"

    # --- filters and tests ----------------------------------------------

    def v_Filter(self, n) -> str:
        # n.node is the target expression (None for filter-block, unused).
        if n.node is None:
            return self._unmappable("filter-block is not supported")
        target = self.visit(n.node)
        args = [self.visit(a) for a in (n.args or [])]
        if n.kwargs or n.dyn_args is not None or n.dyn_kwargs is not None:
            return self._unmappable(
                f"filter '{n.name}' with kwargs/*args/**kwargs is not supported"
            )
        if n.name in ("escape", "e"):
            self.issues.append(
                Issue(self.lineno, 0,
                      f"filter '{n.name}' has no effect in genesispy-j2 (no HTML output); dropped")
            )
            return target
        mapper = _FILTER_TABLE.get(n.name)
        if mapper is None:
            return self._unmappable(f"unknown filter '{n.name}'")
        result = mapper(target, args)
        if result is None:
            return self._unmappable(
                f"filter '{n.name}' wrong arity ({len(args)} args)"
            )
        return result

    def v_Test(self, n) -> str:
        target = self.visit(n.node)
        args = [self.visit(a) for a in (n.args or [])]
        if n.kwargs or n.dyn_args is not None or n.dyn_kwargs is not None:
            return self._unmappable(
                f"test '{n.name}' with kwargs/*args/**kwargs is not supported"
            )
        mapper = _TEST_TABLE.get(n.name)
        if mapper is None:
            return self._unmappable(f"unknown test '{n.name}'")
        result = mapper(target, args)
        if result is None:
            return self._unmappable(
                f"test '{n.name}' wrong arity ({len(args)} args)"
            )
        return result


def _parse_expr(env, source: str, lineno: int):
    """Parse a Jinja2 expression string and return its AST node."""
    # Wrap in a synthetic variable block so we can use env.parse, then peel
    # the nodes.Output / nodes.Filter / etc. back out.
    template = env.parse("{{ " + source + " }}")
    body = template.body
    if not body or not isinstance(body[0], j2nodes.Output):
        raise ValueError(
            f"line {lineno}: could not parse expression {source!r}"
        )
    nodes = body[0].nodes
    if len(nodes) != 1:
        # Concatenation -> wrap in Concat
        concat = j2nodes.Concat(nodes)
        return concat
    return nodes[0]


def _rewrite_expr(env, expr_src: str, *, strict: bool, issues: List[Issue],
                  lineno: int) -> str:
    expr_src = expr_src.strip()
    if not expr_src:
        return ""
    node = _parse_expr(env, expr_src, lineno)
    rw = _ExprRewriter(strict=strict, issues=issues, lineno=lineno)
    return rw.visit(node)


# --------------------------------------------------------------------------- #
# Statement / variable / comment span rewriting
# --------------------------------------------------------------------------- #

# Block openers that need a trailing colon in genesispy-j2.
_OPENERS = ("for", "if", "elif", "else", "while")
# Recognised closers (left untouched).
_CLOSERS = ("endfor", "endif", "endwhile")
# Keywords whose stock-Jinja2 forms we explicitly reject.
_UNMAPPABLE_KEYWORDS = (
    "macro", "endmacro", "call", "endcall",
    "block", "endblock", "extends",
    "import", "from",
    "do", "with", "endwith",
    "filter", "endfilter",
    "raw", "endraw",
    "autoescape", "endautoescape",
    "endset",
)

# Match  {%- or {%, optional whitespace, body, optional whitespace, -%} or %}.
_STMT_INNER_RE = re.compile(
    r"\{%(-?)\s*(.*?)\s*(-?)%\}", re.DOTALL
)
_VAR_INNER_RE = re.compile(
    r"\{\{(-?)\s*(.*?)\s*(-?)\}\}", re.DOTALL
)


def _strip_block_delims(span: str) -> Tuple[str, str, str, str]:
    """Return (open, lstrip, body, rstrip, close) for `{% ... %}` span."""
    m = _STMT_INNER_RE.fullmatch(span)
    assert m, f"bad statement span: {span!r}"
    return ("{%", m.group(1), m.group(2), m.group(3), "%}")


def _strip_var_delims(span: str) -> Tuple[str, str, str, str, str]:
    m = _VAR_INNER_RE.fullmatch(span)
    assert m, f"bad variable span: {span!r}"
    return ("{{", m.group(1), m.group(2), m.group(3), "}}")


def _rewrite_var_span(env, span: str, *, strict: bool, issues: List[Issue],
                      lineno: int) -> str:
    _, lws, body, rws, _ = _strip_var_delims(span)
    py = _rewrite_expr(env, body, strict=strict, issues=issues, lineno=lineno)
    return "{{" + lws + " " + py + " " + rws + "}}"


_INCLUDE_LITERAL_RE = re.compile(
    r"""include\s+(?P<q>['"])(?P<path>[^'"]+)(?P=q)\s*$"""
)


def _rewrite_stmt_span(env, span: str, *, strict: bool, issues: List[Issue],
                       lineno: int) -> str:
    _, lws, body, rws, _ = _strip_block_delims(span)
    body_stripped = body.strip()

    # Closers pass through.
    first = body_stripped.split(None, 1)[0] if body_stripped else ""
    if first in _CLOSERS:
        return "{%" + lws + " " + body_stripped + " " + rws + "%}"

    # Sentinel-comment closers (`# endfor` etc.) pass through.
    if body_stripped.startswith("#"):
        sentinel = body_stripped.lstrip("#").strip()
        if sentinel in _CLOSERS:
            return "{%" + lws + " # " + sentinel + " " + rws + "%}"
        return "{%" + lws + " " + body_stripped + " " + rws + "%}"

    # Hard-rejected keywords.
    if first in _UNMAPPABLE_KEYWORDS:
        reason = f"'{first}' has no genesispy-j2 equivalent"
        if strict:
            raise _Unmappable(reason, line=lineno)
        issues.append(Issue(lineno, 0, reason))
        return f"{{# TODO(genesispy-jinja2j2): {reason} -- original: {span} #}}"

    # `set NAME = EXPR`
    if first == "set":
        rest = body_stripped[3:].strip()
        if "=" not in rest:
            reason = "set-block ({% set X %}...{% endset %}) is not supported"
            if strict:
                raise _Unmappable(reason, line=lineno)
            issues.append(Issue(lineno, 0, reason))
            return f"{{# TODO(genesispy-jinja2j2): {reason} -- original: {span} #}}"
        name, expr = rest.split("=", 1)
        name = name.strip()
        py = _rewrite_expr(env, expr, strict=strict, issues=issues, lineno=lineno)
        return "{%" + lws + " " + name + " = " + py + " " + rws + "%}"

    # `include "FILE"` -- bare form only
    if first == "include":
        m = _INCLUDE_LITERAL_RE.fullmatch(body_stripped)
        if m is None:
            reason = "complex 'include' (with context / ignore missing / dynamic path) is not supported"
            if strict:
                raise _Unmappable(reason, line=lineno)
            issues.append(Issue(lineno, 0, reason))
            return f"{{# TODO(genesispy-jinja2j2): {reason} -- original: {span} #}}"
        path = m.group("path")
        return "{%" + lws + " include(" + repr(path) + ") " + rws + "%}"

    # Block openers: ensure trailing colon, rewrite expression part.
    if first in _OPENERS:
        if first == "else":
            return "{%" + lws + " else: " + rws + "%}"
        # for/if/elif/while EXPR  (already-trailing colon stripped)
        kw_rest = body_stripped[len(first):].strip()
        if kw_rest.endswith(":"):
            kw_rest = kw_rest[:-1].rstrip()
        if first == "for":
            # for TARGET in ITER
            if " in " not in kw_rest:
                reason = "malformed 'for' (no 'in')"
                if strict:
                    raise _Unmappable(reason, line=lineno)
                issues.append(Issue(lineno, 0, reason))
                return f"{{# TODO(genesispy-jinja2j2): {reason} -- original: {span} #}}"
            target, iter_src = kw_rest.split(" in ", 1)
            iter_py = _rewrite_expr(env, iter_src, strict=strict,
                                    issues=issues, lineno=lineno)
            return ("{%" + lws + " for " + target.strip() + " in " +
                    iter_py + ": " + rws + "%}")
        # if / elif / while
        cond_py = _rewrite_expr(env, kw_rest, strict=strict, issues=issues,
                                lineno=lineno)
        return "{%" + lws + " " + first + " " + cond_py + ": " + rws + "%}"

    # Anything else: pass through verbatim. genesispy-j2 statements are full
    # Python, so a bare `{% x = 1 %}` or `{% pass %}` is already legal.
    return "{%" + lws + " " + body_stripped + " " + rws + "%}"


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #

def convert(source: str, *, strict: bool = True
            ) -> Tuple[str, List[Issue]]:
    """Convert a stock-Jinja2 ``source`` string into genesispy-j2 form.

    On strict=True, raises _Unmappable on the first construct that cannot
    be ported. On strict=False, emits TODO comments and collects Issue
    records for the caller to display.
    """
    if jinja2 is None:
        raise RuntimeError(
            "the 'jinja2' package is required for genesispy-jinja2j2; "
            "install with: pip install 'genesispy[import-j2]'"
        )

    env = jinja2.Environment(
        # Disable autoescape and any stock-Jinja2 extensions we don't
        # support; we don't actually render -- we only parse.
        autoescape=False,
        extensions=[],
    )

    issues: List[Issue] = []
    out: List[str] = []
    last = 0
    for m in _SPAN_RE.finditer(source):
        out.append(source[last:m.start()])
        last = m.end()
        lineno, _col = _line_col(source, m.start())
        if m.group("comment") is not None:
            out.append(m.group("comment"))
        elif m.group("stmt") is not None:
            out.append(_rewrite_stmt_span(env, m.group("stmt"),
                                          strict=strict, issues=issues,
                                          lineno=lineno))
        else:  # var
            out.append(_rewrite_var_span(env, m.group("var"),
                                         strict=strict, issues=issues,
                                         lineno=lineno))
    out.append(source[last:])
    return "".join(out), issues


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="genesispy-jinja2j2",
        description=(
            "Port a stock-Jinja2 template to genesispy's --j2 dialect "
            "(Jinja2-style delimiters, full-Python embedded language)."
        ),
    )
    p.add_argument("input",
                   help="path to the stock-Jinja2 source (or '-' for stdin)")
    p.add_argument("-o", "--output", default=None,
                   help="output path (default: stdout)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--strict", dest="strict", action="store_true",
                      default=True,
                      help="(default) error and exit non-zero on the first "
                           "construct with no clean genesispy-j2 equivalent")
    mode.add_argument("--best-effort", dest="strict", action="store_false",
                      help="emit TODO comments for unmappable constructs "
                           "instead of failing")
    p.add_argument("--check", action="store_true",
                   help="parse and report only; write no output")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    if jinja2 is None:
        sys.stderr.write(
            "genesispy-jinja2j2 requires the optional 'jinja2' dependency. "
            "Install with: pip install 'genesispy[import-j2]'\n"
        )
        return 2

    args = _build_argparser().parse_args(argv)

    if args.input == "-":
        source = sys.stdin.read()
        in_label = "<stdin>"
    else:
        try:
            with open(args.input, "r") as fh:
                source = fh.read()
        except OSError as e:
            sys.stderr.write(f"genesispy-jinja2j2: {e}\n")
            return 2
        in_label = args.input

    try:
        result, issues = convert(source, strict=args.strict)
    except _Unmappable as e:
        sys.stderr.write(f"{in_label}:{e.line}:{e.col}: cannot port: {e.reason}\n")
        return 1

    for iss in issues:
        sys.stderr.write(
            f"{in_label}:{iss.line}:{iss.col}: warning: {iss.reason}\n"
        )

    if args.check:
        if issues:
            sys.stderr.write(
                f"genesispy-jinja2j2: {len(issues)} unmappable construct(s) "
                f"in {in_label}\n"
            )
            return 1
        return 0

    if args.output is None or args.output == "-":
        sys.stdout.write(result)
    else:
        with open(args.output, "w") as fh:
            fh.write(result)

    if issues and not args.strict:
        sys.stderr.write(
            f"genesispy-jinja2j2: {len(issues)} manual fixup(s) needed in "
            f"{args.output or '<stdout>'}\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
