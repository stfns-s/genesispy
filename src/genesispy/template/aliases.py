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
"""

from __future__ import annotations

from typing import Any


SIMPLE_ALIASES: tuple[tuple[str, str], ...] = (
    ("parameter",            "parameter"),
    ("define_param",         "define_param"),
    ("synonym",              "synonym"),
    ("instantiate",          "instantiate"),
    ("emit",                 "emit"),
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
# include/pinclude pair sit alongside SIMPLE_ALIASES; this constant is
# the single source of truth for tests that assert "every name is bound".
EXPECTED_ALIAS_KEYS: frozenset[str] = frozenset(
    {alias for alias, _ in SIMPLE_ALIASES}
    | {"mname", "iname", "bname", "sname", "include", "pinclude"}
)


def alias_prelude_source(indent: str = "        ") -> str:
    """Return the bare-name alias bindings as Python source lines.

    The source assumes ``self`` is in scope and that ``_gpy_user_config``
    is bound to :mod:`genesispy.user_config`, and that ``StrCallable`` is
    importable in the generated module's namespace (the emitter arranges
    both via the generated module's import block).
    """
    lines = [f"{indent}{alias} = self.{attr}" for alias, attr in SIMPLE_ALIASES]
    # Genesis2 short-name quartet — kept here so _include's alias_dict matches.
    lines.append(f"{indent}mname = StrCallable(self._unique_module_name)")
    lines.append(f"{indent}iname = StrCallable(self._instance_name)")
    lines.append(f"{indent}bname = StrCallable(self._module_name)")
    lines.append(f"{indent}sname = StrCallable(self._unique_module_name)")
    lines.append(f"{indent}include = _gpy_user_config._include")
    lines.append(f'{indent}pinclude = getattr(self, "pinclude", None)')
    return "\n".join(lines) + "\n"


def alias_dict(self_obj: Any) -> dict[str, Any]:
    """Return bare-name alias bindings as a dict.

    Suitable for merging into the globals dict passed to ``exec()`` for a
    parsed `.vpy` body, e.g. by :func:`genesispy.user_config._include`.
    Mirrors :func:`alias_prelude_source`'s coverage so an `include()`-d
    .vpy sees the same names a top-level one does.
    """
    from genesispy import user_config as _uc
    from .runtime import StrCallable

    out: dict[str, Any] = {alias: getattr(self_obj, attr) for alias, attr in SIMPLE_ALIASES}
    # Reuse populated StrCallables when present; synthesise otherwise so
    # _include works before the emitter prelude has run.
    for short, src_attr in (
        ("mname", "_unique_module_name"),
        ("iname", "_instance_name"),
        ("bname", "_module_name"),
        ("sname", "_unique_module_name"),
    ):
        existing = getattr(self_obj, short, None)
        if isinstance(existing, StrCallable):
            out[short] = existing
        else:
            base = getattr(self_obj, src_attr, None)
            out[short] = StrCallable(base) if base is not None else None
    out["include"] = _uc._include
    out["pinclude"] = getattr(self_obj, "pinclude", None)
    return out
