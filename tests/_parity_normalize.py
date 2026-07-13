"""Normalisation helpers for genesispy ↔ Genesis2 Verilog parity.

Renaming is a per-base function of normalised definition-body content, applied
uniformly to definitions and references within one side's file set. A reference
normalises identically on both sides iff the referenced variants have identical
normalised bodies — independent of numbering scheme and file/emission order.

Three public functions:

1. ``parse_header(text)`` -> ``(base, sig)`` — extract the source-template
   base name and the param signature from a generated `.v` file's comment
   header. Handles both emitter dialects:

   - Genesis2 (Perl, ``UniqueModule.pm:to_verilog``):
       ``// Source template: <base>``
       ``// Parameter <name> = <value>``  (in priority sections)
   - genesispy (``unique_module.py:to_verilog``):
       ``// Source class: <base>``
       ``//   <name> = <value>``  (after ``// Parameters:``)

2. ``build_variant_map(texts, all_bases)`` -> ``dict[str, str]`` — scan a
   collection of Verilog texts (one side's full output), find each variant
   token (e.g. ``Foo_unq1``, ``Foo_width_2``, bare ``Foo``), and assign a
   content-ranked canonical name ``<base>__U<rank>`` (or ``<base>__U?`` for
   referenced-but-undefined variants). Rank is determined by sorted normalised
   body content, with fixpoint refinement so grandchild variant distinctions
   propagate up.

3. ``normalize(text, all_bases, variant_map=None)`` -> str — strip comments
   and whitespace, collapse uniquified module-name suffixes. When
   ``variant_map`` is None (old path): all variants of a base collapse to
   ``<base>__U`` (blind collapse, including bare base name). When
   ``variant_map`` is supplied (new two-phase path): each variant token is
   replaced by its content-ranked name from the map (e.g. ``Foo__U0``).
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Tuple


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


def _variant_pattern(base: str) -> re.Pattern[str]:
    """Return a pattern matching a suffixed variant token for ``base``.

    Matches ``<base>_unqN`` (genesispy numeric) or ``<base>_KEY_VAL...``
    (Perl param-style chains). Does NOT match the bare base name.
    """
    return re.compile(
        rf"\b{re.escape(base)}(?:_unq\d+|(?:_[A-Za-z]\w*_[^\s,;.()\[\]{{}}]+)+)\b"
    )


def _any_token_pattern(base: str) -> re.Pattern[str]:
    """Return a pattern matching the bare base name OR any suffixed variant."""
    return re.compile(
        rf"\b{re.escape(base)}(?:_unq\d+|(?:_[A-Za-z]\w*_[^\s,;.()\[\]{{}}]+)+)?\b"
    )


def build_variant_map(
    texts: Dict[str, str] | Iterable[str],
    all_bases: Iterable[str],
) -> Dict[str, str]:
    """Assign content-ranked canonical names to all variant tokens in ``texts``.

    Parameters
    ----------
    texts:
        Either a ``dict`` mapping filename -> text, or a plain iterable of
        texts. One side's complete Verilog output (synth + verif).
    all_bases:
        The set of known base module names (e.g. ``{"Foo", "parent"}``).

    Returns
    -------
    A dict mapping each variant token (e.g. ``"Foo_unq1"``, ``"Foo_width_2"``,
    bare ``"Foo"``) to its canonical name (``"Foo__U0"``, ``"Foo__U1"``, …,
    or ``"Foo__U?"`` for referenced-but-undefined variants).

    Bare base names (e.g. Perl output where only one variant exists and
    no uniquification suffix is appended) are treated as valid variant tokens
    and included in the map alongside suffixed tokens.
    """
    if isinstance(texts, dict):
        all_texts: List[str] = list(texts.values())
    else:
        all_texts = list(texts)

    bases = sorted(set(all_bases), key=len, reverse=True)

    # Step 1: discover every variant token referenced anywhere in the corpus.
    # variant_body[base][token] = defining_text | None
    # Tokens include both suffixed variants AND the bare base name when it
    # appears as a module name (Perl emits bare names for single-variant bases).
    variant_body: Dict[str, Dict[str, str | None]] = {b: {} for b in bases}

    # Pre-strip comments from all texts for token scanning (so identifiers
    # in comments do not register as references or definitions).
    stripped_texts: List[str] = []
    for text in all_texts:
        s = _BLOCK_COMMENT_RE.sub("", text)
        s = _LINE_COMMENT_RE.sub("", s)
        stripped_texts.append(s)

    for base in bases:
        # Pattern for any reference: bare name or suffixed.
        any_pat = _any_token_pattern(base)
        # Pattern for module definitions: catches both bare and suffixed names.
        # Note: only matches `module` definitions, not `interface`. SystemVerilog
        # interface variants (e.g., cfg_ifc) never rank and always collapse to
        # the sentinel on both sides; a wiring swap between interface variants
        # would not be detected.
        mod_def_re = re.compile(
            rf"\bmodule\s+({re.escape(base)}"
            rf"(?:_unq\d+|(?:_[A-Za-z]\w*_[^\s,;.()\[\]{{}}]+)+)?)\b"
        )
        for raw_text, stripped in zip(all_texts, stripped_texts):
            # Collect all tokens referenced in this text (bare or suffixed),
            # scanning comment-free text only.
            for m in any_pat.finditer(stripped):
                token = m.group(0)
                if token not in variant_body[base]:
                    variant_body[base][token] = None
            # If this text defines a module for this base, record it.
            # Module definitions are always in non-comment code.
            dm = mod_def_re.search(stripped)
            if dm:
                defined_token = dm.group(1)
                if variant_body[base].get(defined_token) is None:
                    variant_body[base][defined_token] = raw_text

    # Step 2: global fixpoint ranking.
    # On each round, normalize each variant's defining body using the current
    # global map, re-rank per base by sorted normalised body, repeat until stable.
    # Global (not per-base) so that Foo's rank can depend on Bar's rank.
    all_tokens_count = sum(len(v) for v in variant_body.values())
    max_iters = all_tokens_count + 2

    current_map: Dict[str, str] = {}

    for _iteration in range(max_iters):
        new_map: Dict[str, str] = {}

        for base in bases:
            tokens = sorted(variant_body[base].keys())
            if not tokens:
                continue

            normed: Dict[str, str] = {}
            for token in tokens:
                body = variant_body[base][token]
                if body is None:
                    normed[token] = ""
                else:
                    normed[token] = normalize(body, all_bases, current_map if current_map else None)

            # Group by normalised body; sort groups deterministically; assign rank.
            body_to_tokens: Dict[str, List[str]] = {}
            for token, nb in normed.items():
                body_to_tokens.setdefault(nb, []).append(token)

            for rank, body_str in enumerate(sorted(body_to_tokens.keys())):
                for token in body_to_tokens[body_str]:
                    body = variant_body[base][token]
                    if body is None:
                        new_map[token] = f"{base}__U?"
                    else:
                        new_map[token] = f"{base}__U{rank}"

        if new_map == current_map:
            break
        current_map = new_map

    return current_map


def normalize(
    text: str,
    all_bases: Iterable[str],
    variant_map: Dict[str, str] | None = None,
) -> str:
    r"""Return a canonical form of ``text`` suitable for equality comparison.

    Steps: strip preprocessor `ifdef blocks (per ``_strip_ifdef_blocks``),
    strip block + line comments, replace any uniquified token of the form
    ``<base>_unq\d+`` (genesispy numeric style) or ``<base>_<KEY>_<VAL>...``
    (Perl param style), or bare ``<base>`` (Perl single-variant output).

    When ``variant_map`` is None (old path): all tokens (bare or suffixed)
    collapse to ``<base>__U``.

    When ``variant_map`` is supplied (new two-phase path): each token is
    replaced by its content-ranked name from the map. Tokens absent from the
    map fall back to ``<base>__U?``.
    """
    text = _strip_ifdef_blocks(text)
    text = _BLOCK_COMMENT_RE.sub("", text)
    text = _LINE_COMMENT_RE.sub("", text)
    # genesispy .vpy templates use the modern `$fatal(<n>, "...")` form;
    # Genesis2 .vp templates use the legacy `$fatal("...")`. Normalise both
    # by stripping the leading finish-number argument when present.
    text = re.sub(r"\$fatal\s*\(\s*\d+\s*,\s*", "$fatal(", text)

    # Sort bases longest-first so e.g. `wallace_tree` is replaced before `wallace`.
    bases = sorted(set(all_bases), key=len, reverse=True)

    if variant_map is None:
        # Old blind-collapse path: bare name and all variants -> <base>__U.
        for base in bases:
            pat = _any_token_pattern(base)
            text = pat.sub(f"{base}__U", text)
    else:
        # New content-ranked path: apply map entries as exact-token substitutions.
        # Sort by token length descending to avoid partial matches.
        sorted_entries = sorted(variant_map.items(), key=lambda kv: len(kv[0]), reverse=True)
        for token, canonical in sorted_entries:
            text = re.sub(rf"\b{re.escape(token)}\b", canonical, text)
        # Fallback: any remaining unmatched tokens (bare or suffixed) -> <base>__U?
        for base in bases:
            pat = _any_token_pattern(base)
            text = pat.sub(f"{base}__U?", text)

    text = _WS_RE.sub(" ", text).strip()
    return text
