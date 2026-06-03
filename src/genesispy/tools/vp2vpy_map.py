"""Mapping tables for the Perl -> Python translator.

Pure data plus a few thin helpers. Imported by ``vp2vpy.py``; no I/O.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Operators.
#
# Maps the Perl spelling (as it appears in ``PPI::Token::Operator``) to the
# Python spelling. ``None`` marks operators that have no scalar Python
# equivalent and must be handled structurally upstream (e.g. ``..`` becomes
# ``range(...)`` rather than an infix operator).
# ---------------------------------------------------------------------------
INFIX_OPERATOR_MAP: dict[str, str] = {
    # Arithmetic.
    "+": "+", "-": "-", "*": "*", "/": "/", "%": "%", "**": "**",
    # Bitwise.
    "&": "&", "|": "|", "^": "^", "<<": "<<", ">>": ">>",
    # Numeric comparison.
    "==": "==", "!=": "!=", "<": "<", ">": ">", "<=": "<=", ">=": ">=",
    "<=>": None,  # spaceship; rare.
    # String comparison.
    "eq": "==", "ne": "!=", "lt": "<", "gt": ">", "le": "<=", "ge": ">=",
    "cmp": None,
    # Logical.
    "&&": "and", "||": "or", "//": "or",
    "and": "and", "or": "or", "not": "not", "xor": "!=",
    # Assignment.
    "=": "=",
    "+=": "+=", "-=": "-=", "*=": "*=", "/=": "/=", "%=": "%=", "**=": "**=",
    "&=": "&=", "|=": "|=", "^=": "^=", "<<=": "<<=", ">>=": ">>=",
    "&&=": None, "||=": None, "//=": None,
    # String concat.
    ".": "+", ".=": "+=",
    # Repetition.
    "x": "*", "x=": "*=",
    # Range -> handled specially (Python ``range``).
    "..": None, "...": None,
    # Defined-or already covered by ``//``.
    # Ternary ?: handled structurally.
}

PREFIX_OPERATOR_MAP: dict[str, str] = {
    "!": "not ", "not": "not ",
    "-": "-", "+": "+", "~": "~",
    "\\": None,   # reference-of; ignored (Python passes refs natively).
}

# ---------------------------------------------------------------------------
# Built-in functions.
#
# Value is either a string template (``"{0}.append({1})"``) or a callable
# taking the rendered arg strings and returning a string. ``None`` means
# unmappable -> TODO passthrough.
# ---------------------------------------------------------------------------
BUILTIN_MAP: dict[str, object] = {
    "print":   "print({args})",
    "printf":  "print({fmt0} % ({rest},), end='')",
    "sprintf": "({fmt0} % ({rest},))",
    "scalar":  "len({args})",
    "length":  "len({args})",
    "defined": "({args} is not None)",
    "exists":  "({arg0} in {arg1})",            # exists $h{k}  -- arg-order-dependent; see translator
    "delete":  "{arg0}.pop({arg1}, None)",      # delete $h{k}
    "keys":    "list({args})",
    "values":  "list({args}.values())",
    "die":     "(_ for _ in ()).throw(RuntimeError({args}))",
    "warn":    "print({args}, file=__import__('sys').stderr)",
    "push":    "{arg0}.append({rest})",
    "pop":     "{args}.pop()",
    "shift":   "{args}.pop(0)",
    "unshift": "{arg0}.insert(0, {rest})",
    "split":   "({arg1}).split({arg0})",
    "join":    "({arg0}).join({rest})",
    "lc":      "({args}).lower()",
    "uc":      "({args}).upper()",
    "chomp":   "{args}.rstrip('\\n')",          # not in-place
    "int":     "int({args})",
    "abs":     "abs({args})",
    "ref":     "type({args}).__name__",
    "wantarray": None,
    "qw":      None,  # handled structurally
    # Scalar::Util::looks_like_number -- routed via runtime helper.
    "looks_like_number": "_vp2vpy_looks_like_number({args})",
}

# POSIX:: math passthrough.
POSIX_MAP: dict[str, str] = {
    "ceil":  "math.ceil",
    "floor": "math.floor",
    "log":   "math.log",
    "log10": "math.log10",
    "log2":  "math.log2",
    "sqrt":  "math.sqrt",
    "pow":   "math.pow",
    "exp":   "math.exp",
    "sin":   "math.sin",
    "cos":   "math.cos",
    "tan":   "math.tan",
}

# ---------------------------------------------------------------------------
# Genesis2 user-template API.
#
# Maps Perl method/function names (case-sensitive in templates) to genesispy
# bare-name equivalents. The translator emits the value verbatim; callers
# rewrite the argument list separately, fat-comma -> keyword.
# ---------------------------------------------------------------------------
API_TABLE: dict[str, str] = {
    # Parameter / config.
    "Parameter":       "parameter",
    # Perl ``define_param`` registers AND returns the resolved value.
    # genesispy's ``define_param()`` only registers (returns None);
    # the equivalent value-returning entry-point is ``parameter()``.
    # Map to that so ``my $x = define_param(...)`` keeps its Perl semantics.
    "DefineParameter": "parameter",
    "ParamRange":      "param_range",
    # Instantiation.
    "Generate":             "generate",
    "GenerateBase":         "ununique_inst",
    "GenerateWithName":     "generate_w_name",
    "UniqueInst":           "unique_inst",
    "UniqueInstParam":      "unique_inst_param",
    "Ununique":             "ununique_inst",
    "UnUniqueInst":         "ununique_inst",
    "Clone":                "clone_inst",
    "CloneInst":            "clone_inst",
    "Instantiate":          "instantiate",
    "Synonym":              "synonym",
    # Emission.
    "Emit":     "emit",
    # Hierarchy.
    "GetSubInst":           "get_subinst",
    "ExistsSubInst":        "exists_subinst",
    "GetSubInstArray":      "get_subinst_array",
    "SearchSubInst":        "search_subinst",
    # Includes.
    "Include":  "include",
    "Pinclude": "pinclude",
    # Names (Perl returned scalars; Python: same names work as StrCallable).
    "MName": "mname",
    "IName": "iname",
    "BName": "bname",
    "SName": "sname",
    # Misc.
    "PP":     "pp",
    "pp":     "pp",
}

# Method-call rewrites: ``$obj->Foo(args)`` -> ``obj.foo(args)``.
METHOD_TABLE: dict[str, str] = {
    "error":          "_vp2vpy_error",   # see RUNTIME_HELPERS below
    "Error":          "_vp2vpy_error",
    "get_param":      "get_param",
    "GetParam":       "get_param",
    "getParam":       "get_param",
    "params":         "params",
    "Params":         "params",
    "tname":          "tname",
    "iname":          "iname",
    "Instantiate":    "instantiate",
    "Generate":       "generate",
    "Parameter":      "parameter",
    # define_param / force_param / override_param all map to ``parameter``
    # for return-value compatibility -- see the API_TABLE note above.
    "define_param":   "parameter",
    "DefineParam":    "parameter",
    "force_param":    "parameter",
    "ForceParam":     "parameter",
    "override_param": "parameter",
    "OverrideParam":  "parameter",
}

# Per-API uppercase-keyword normalisation.
#
# Genesis2 Perl templates idiomatically pass ``NAME => 'x', VAL => 1`` to
# ``parameter`` / ``define_param``. genesispy's Python equivalents declare
# their kwargs in lowercase. This table maps Perl uppercase kwarg ->
# Python lowercase kwarg, keyed by Perl API/method name (i.e. an
# ``API_TABLE`` or ``METHOD_TABLE`` key). Keys absent from the inner dict
# pass through verbatim, so APIs that forward arbitrary user-defined
# param names (``generate``, ``generate_base``, ``unique_inst``, ...)
# get no entry here and behave unchanged.
_PARAM_KWARGS: dict[str, str] = {
    "NAME":  "name",
    "VAL":   "default",
    "DOC":   "doc",
    "MIN":   "min",
    "MAX":   "max",
    "STEP":  "step",
    "LIST":  "list",
    "OPT":   "opt",
    "FORCE": "force",
}

API_KWARG_MAP: dict[str, dict[str, str]] = {
    # Perl Capital-P API_TABLE keys.
    "Parameter":       _PARAM_KWARGS,
    "DefineParameter": _PARAM_KWARGS,
    # Perl bare-lowercase calls (the same names appear in templates that
    # already use the genesispy-style bare-name API).
    "parameter":       _PARAM_KWARGS,
    "define_param":    _PARAM_KWARGS,
}

# APIs supporting the Genesis2 shortcut idiom
# ``define_param(MY_PRM => 42)`` -- equivalent to
# ``define_param("MY_PRM", 42)``.  When the translator sees a fat-comma
# pair whose key is *not* in API_KWARG_MAP[api], it emits the pair as
# two positional arguments instead of as a kwarg. Only legal for APIs
# whose Python signatures accept ``(name, default)`` positionally.
API_SHORTCUT_FIRST_PAIR: frozenset[str] = frozenset({
    "DefineParameter",
    "define_param",
    "DefineParam",
    "force_param",
    "ForceParam",
    "override_param",
    "OverrideParam",
})

# Tiny helpers we may emit at the top of an output file. Keys are the helper
# name; values are the Python source to inject (once) when used.
RUNTIME_HELPERS: dict[str, str] = {
    "_vp2vpy_error": (
        "def _vp2vpy_error(msg):\n"
        "    raise RuntimeError(msg)\n"
    ),
    "_vp2vpy_looks_like_number": (
        "def _vp2vpy_looks_like_number(x):\n"
        "    if isinstance(x, (int, float)):\n"
        "        return True\n"
        "    if isinstance(x, str):\n"
        "        try:\n"
        "            float(x)\n"
        "            return True\n"
        "        except ValueError:\n"
        "            return False\n"
        "    return False\n"
    ),
}

# Modules we may need to inject ``import`` lines for.
IMPORT_TRIGGERS: dict[str, str] = {
    "re":   "import re",
    "math": "import math",
    "sys":  "import sys",
}
