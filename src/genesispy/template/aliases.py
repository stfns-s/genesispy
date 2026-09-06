"""Canonical bare-name alias table for Genesis2-style user code.

Three sites bind the same set of bare names so user `.vpy`/`.gvpy` code can
call ``parameter(...)``, ``emit(...)``, ``include(...)`` etc. without
prefixing them with ``self.``:

1. :func:`genesispy.template.emitter._header` -- emitted into every generated
   module's ``execute()`` as Python source, so the parser-driven path picks
   the bindings up as locals.
2. :func:`genesispy.user_config._include` -- populates an exec-globals dict
   when a parsed `.vpy` is run inline via ``//;include("...")``.
3. :func:`genesispy.gvpy_cli._build_class_from_vpy` -- emits the same source
   prelude inside the gvpy class factory.

Historically each site kept its own copy and they drifted (``include`` and
``pinclude`` were missing from sites 2 and 3). This module is the single
source of truth; the three sites consume :data:`SIMPLE_ALIASES` via
:func:`alias_prelude_source` (source-string form) or :func:`alias_dict`
(dict form).

``pyinclude`` and its deprecated spelling ``pinclude`` are bound per-site
against the namespace the included Python must populate -- ``globals()`` in
the two source-string sites, the ``ns`` argument in :func:`alias_dict`.
"""

from __future__ import annotations

from typing import Any


SIMPLE_ALIASES: tuple[tuple[str, str], ...] = (
    ("parameter",            "parameter"),
    ("define_param",         "define_param"),
    ("doc_param",            "doc_param"),
    ("param_range",          "param_range"),
    ("exists_param",         "exists_param"),
    ("get_top_param",        "get_top_param"),
    ("list_params",          "list_params"),
    ("synonym",              "synonym"),
    ("instantiate",          "instantiate"),
    ("emit",                 "emit"),
    ("error",                "error"),
    ("warning",              "warning"),
    ("get_subinst",          "get_subinst"),
    ("exists_subinst",       "exists_subinst"),
    ("get_subinst_array",    "get_subinst_array"),
    ("get_instance_obj",     "get_instance_obj"),
    ("search_subinst",       "search_subinst"),
    ("unique_inst",          "unique_inst"),
    ("unique_inst_param",    "unique_inst_param"),
    ("clone_inst",           "clone_inst"),
    ("ununique_inst",        "ununique_inst"),
    ("generate",             "generate"),
    ("generate_unq_numeric", "unique_inst"),
    ("generate_unq_param",   "unique_inst_param"),
    ("generate_base",        "ununique_inst"),
    ("generate_w_name",      "generate_w_name"),
    ("clone",                "clone_inst"),
)

# Full set of bare-name aliases bound at every prelude site. The
# StrCallable shortname quartet (mname/iname/bname/sname) and the
# include/pyinclude/pinclude trio sit alongside SIMPLE_ALIASES; this constant
# is the single source of truth for tests that assert "every name is bound".
EXPECTED_ALIAS_KEYS: frozenset[str] = frozenset(
    {alias for alias, _ in SIMPLE_ALIASES}
    | {
        "mname", "iname", "bname", "sname",
        "include", "pyinclude", "pinclude",
    }
)


def alias_prelude_source(indent: str = "        ") -> str:
    """Return the bare-name alias bindings as Python source lines.

    The source assumes ``self`` is in scope and that ``_gpy_user_config``
    is bound to :mod:`genesispy.user_config`, and that ``StrCallable`` is
    importable in the generated module's namespace (the emitter arranges
    both via the generated module's import block).
    """
    lines: list[str] = []
    for alias, attr in SIMPLE_ALIASES:
        if alias == "synonym":
            # Perl synonym is two-form: synonym(name) mirrors the outfile
            # under a new name (Python's instance-level semantics), while
            # synonym(src, trgt) creates a class-level template synonym
            # (Perl semantics). Dispatcher picks by arity.
            lines.append(f"{indent}def synonym(*_args):")
            lines.append(f"{indent}    if len(_args) == 1:")
            lines.append(f"{indent}        return self.synonym(_args[0])")
            lines.append(f"{indent}    if len(_args) == 2:")
            lines.append(f"{indent}        return self._manager.synonym_class(*_args)")
            lines.append(f"{indent}    raise TypeError(")
            lines.append(
                f"{indent}        'synonym() takes 1 or 2 positional arguments; '"
            )
            lines.append(f"{indent}        f'got {{len(_args)}}'")
            lines.append(f"{indent}    )")
        else:
            lines.append(f"{indent}{alias} = self.{attr}")
    # Genesis2 short-name quartet — kept here so _include's alias_dict matches.
    lines.append(f"{indent}mname = StrCallable(self._unique_module_name)")
    lines.append(f"{indent}iname = StrCallable(self._instance_name)")
    lines.append(f"{indent}bname = StrCallable(self._module_name)")
    # sname tracks Perl get_source_name: pre-synonym source-template name.
    lines.append(
        f"{indent}sname = StrCallable("
        f"getattr(type(self), '_synonym_for', None) or self._module_name)"
    )
    lines.append(f"{indent}include = _gpy_user_config._include")
    # globals() inside execute() is the generated module's own dict, which is
    # exactly the namespace a pyinclude'd file must populate.
    lines.append(
        f"{indent}pyinclude = _gpy_user_config._make_pyinclude(globals())"
    )
    lines.append(
        f"{indent}pinclude = _gpy_user_config._make_pinclude(globals())"
    )
    return "\n".join(lines) + "\n"


def alias_dict(self_obj: Any, ns: dict | None = None) -> dict[str, Any]:
    """Return bare-name alias bindings as a dict.

    Suitable for merging into the globals dict passed to ``exec()`` for a
    parsed `.vpy` body, e.g. by :func:`genesispy.user_config._include`.
    Mirrors :func:`alias_prelude_source`'s coverage so an `include()`-d
    .vpy sees the same names a top-level one does.

    ``ns`` is the namespace ``pyinclude``/``pinclude`` populate -- normally
    the same dict the caller merges the result into. Omitting it binds both
    to a stub that raises ``RuntimeError`` when called.
    """
    from genesispy import user_config as _uc
    from .runtime import StrCallable

    # All SIMPLE_ALIASES except synonym (handled as a dispatcher below).
    out: dict[str, Any] = {
        alias: getattr(self_obj, attr)
        for alias, attr in SIMPLE_ALIASES
        if alias != "synonym"
    }

    # synonym dispatcher: 1-arg = outfile mirror, 2-arg = class rename
    # (Perl-compat). Same semantics as alias_prelude_source's emitted def.
    def synonym(*args: Any) -> Any:
        if len(args) == 1:
            return self_obj.synonym(args[0])
        if len(args) == 2:
            return self_obj._manager.synonym_class(*args)
        raise TypeError(
            f"synonym() takes 1 or 2 positional arguments; got {len(args)}"
        )
    out["synonym"] = synonym

    # Reuse populated StrCallables when present; synthesise otherwise so
    # _include works before the emitter prelude has run.
    for short, src_attr in (
        ("mname", "_unique_module_name"),
        ("iname", "_instance_name"),
        ("bname", "_module_name"),
    ):
        existing = getattr(self_obj, short, None)
        if isinstance(existing, StrCallable):
            out[short] = existing
        else:
            base = getattr(self_obj, src_attr, None)
            out[short] = StrCallable(base) if base is not None else None

    # sname is synonym-aware: read the @property (or a pre-populated
    # StrCallable on a test stub) rather than falling back to the
    # post-uniquification _unique_module_name.
    existing_sname = getattr(self_obj, "sname", None)
    if isinstance(existing_sname, StrCallable):
        out["sname"] = existing_sname
    elif existing_sname is not None:
        out["sname"] = StrCallable(existing_sname)
    else:
        out["sname"] = None

    out["include"] = _uc._include
    if ns is None:
        def _needs_ns(_path: str) -> None:
            raise RuntimeError(
                "pyinclude: alias_dict was called without a namespace; "
                "pass the dict the bindings are merged into"
            )
        out["pyinclude"] = _needs_ns
        out["pinclude"] = _needs_ns
    else:
        out["pyinclude"] = _uc._make_pyinclude(ns)
        out["pinclude"] = _uc._make_pinclude(ns)
    return out
