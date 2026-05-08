"""Normalisation helpers for genesispy ↔ Genesis2 Verilog parity.

Two jobs:

1. ``parse_header(text)`` -> ``(base, sig)`` — extract the source-template
   base name and the param signature from a generated `.v` file's comment
   header. Handles both emitter dialects:

   - Genesis2 (Perl, ``UniqueModule.pm:to_verilog``):
       ``// Source template: <base>``
       ``// Parameter <name> = <value>``  (in priority sections)
   - genesispy (``unique_module.py:to_verilog``):
       ``// Source class: <base>``
       ``//   <name> = <value>``  (after ``// Parameters:``)

2. ``normalize(text, all_bases)`` -> str — strip comments and whitespace,
   collapse uniquified module-name suffixes to a canonical token, and drop
   preprocessor-directive lines that the .vpy templates added for
   simulator-specific gating but the .vp templates do not contain.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Tuple


_PERL_BASE_RE = re.compile(r"^\s*//\s*Source template:\s*(\S+)\s*$", re.M)
_PY_BASE_RE = re.compile(r"^\s*//\s*Source class:\s*(\S+)\s*$", re.M)

_PERL_PARAM_RE = re.compile(r"^\s*//\s*Parameter\s+(\w+)\s*=\s*(.+?)\s*$", re.M)
_PY_PARAM_RE = re.compile(r"^\s*//\s+(\w+)\s*=\s*(.+?)\s*$", re.M)


def parse_header(text: str) -> Tuple[str, Tuple[Tuple[str, str], ...]]:
    """Return ``(base_module_name, sorted_param_signature)``.

    Signature is a tuple of ``(name, canonical_value_str)`` pairs, sorted by
    name, with values stripped of surrounding quotes so Perl ``8`` matches
    Python ``'8'`` / ``8``.
    """
    m = _PERL_BASE_RE.search(text) or _PY_BASE_RE.search(text)
    if not m:
        raise ValueError("no Source template/class line in header")
    base = m.group(1)

    # Perl emits each param once per priority section it appears in; dedupe
    # by name, keeping the last (highest-priority) value seen.
    is_perl = _PERL_BASE_RE.search(text) is not None
    pairs: dict[str, str] = {}
    if is_perl:
        # Bound the search to the priority-status block so we don't pick up
        # user-template `// Parameter ...` lines further down.
        block = text.split("End Pre-Generation", 1)[0]
        for name, val in _PERL_PARAM_RE.findall(block):
            if val == "undef":
                continue
            pairs[name] = _canon_val(val)
    else:
        # genesispy: lines under `// Parameters:` until the first non-matching
        # line. We bound by stopping at the `module ` keyword.
        if "// Parameters:" in text:
            after = text.split("// Parameters:", 1)[1].split("module ", 1)[0]
            for name, val in _PY_PARAM_RE.findall(after):
                pairs[name] = _canon_val(val)

    sig = tuple(sorted(pairs.items()))
    return base, sig


def _canon_val(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        v = v[1:-1]
    return v


_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
_WS_RE = re.compile(r"\s+")

_IFDEF_RE = re.compile(r"^\s*`ifdef\b.*$", re.M)
_IFNDEF_RE = re.compile(r"^\s*`ifndef\b.*$", re.M)
_ELSE_RE = re.compile(r"^\s*`else\b.*$", re.M)
_ENDIF_RE = re.compile(r"^\s*`endif\b.*$", re.M)


def _strip_ifdef_blocks(text: str) -> str:
    r"""Drop `ifdef X ... [`else ...] `endif wrappers.

    Strategy: when an `else` is present, keep the *first* branch body and
    drop the else-branch body. When no `else`, just drop directive lines and
    keep the body. Handles nested ifdefs. Genesis2 .vp templates have no
    preprocessor directives, while genesispy .vpy templates wrap testbench
    code in `ifdef SIMULATION` and add `ifdef VCS / `else / `endif
    alternate forms — both should normalise to the same Verilog as Perl.
    """
    out: List[str] = []
    # stack entries: "keep" if we currently keep lines, "drop" otherwise.
    # On `else`, flip the top entry. On `endif`, pop.
    stack: List[str] = []
    for line in text.splitlines():
        s = line.lstrip()
        if s.startswith("`ifdef") or s.startswith("`ifndef"):
            stack.append("keep")
            continue
        if s.startswith("`else"):
            if stack:
                stack[-1] = "drop" if stack[-1] == "keep" else "keep"
            continue
        if s.startswith("`endif"):
            if stack:
                stack.pop()
            continue
        if all(st == "keep" for st in stack):
            out.append(line)
    return "\n".join(out)


def normalize(text: str, all_bases: Iterable[str]) -> str:
    r"""Return a canonical form of ``text`` suitable for equality comparison.

    Steps: strip preprocessor `ifdef blocks (per ``_strip_ifdef_blocks``),
    strip block + line comments, replace any uniquified token of the form
    ``<base>_unq\d+`` (genesispy numeric style) or ``<base>_<KEY>_<VAL>...``
    (Perl param style) with ``<base>__U``, then collapse whitespace.
    """
    text = _strip_ifdef_blocks(text)
    text = _BLOCK_COMMENT_RE.sub("", text)
    text = _LINE_COMMENT_RE.sub("", text)
    # genesispy .vpy templates use the modern `$fatal(<n>, "...")` form;
    # Genesis2 .vp templates use the legacy `$fatal("...")`. Normalise both
    # by stripping the leading finish-number argument when present.
    text = re.sub(r"\$fatal\s*\(\s*\d+\s*,\s*", "$fatal(", text)

    # Sort bases longest-first so e.g. `wallace_tree` is replaced before `wallace`.
    for base in sorted(set(all_bases), key=len, reverse=True):
        # Match `<base>` optionally followed by uniquification suffix:
        #   _unqN          (genesispy numeric)
        #   _NAME_VAL...   (Perl param style — chain of _Word_value pairs)
        # The replacement is `<base>__U` so paired files collapse together.
        pat = re.compile(
            rf"\b{re.escape(base)}(?:_unq\d+|(?:_[A-Za-z]\w*_[^\s,;.()\[\]{{}}]+)+)?\b"
        )
        text = pat.sub(f"{base}__U", text)

    text = _WS_RE.sub(" ", text).strip()
    return text
