"""User-facing configuration facade for generated module code.

Provides helpers (``_configure``, ``_get_configuration``, ``_include``,
...) that proxy to a "current manager" / "current module" set by the
runtime when generated module code is executed. The names are
underscored to signal "internal entry points": user template code reaches
the same functionality via the bound module methods or via the ``.cfg``
sandbox, which receives its own ``configure``/``include`` bindings from
:meth:`ConfigHandler.read_cfg`.

Runtime integration
-------------------

Before executing a generated module's body, the runtime wraps the call
in :func:`context`, which sets the active manager/module and clears them
on exit::

    from genesispy import user_config

    with user_config.context(manager, top_module):
        top_module.execute()

Single-threaded; the context is a plain module global. Concurrent
elaboration would also need to revisit ``cache.py``, ``runtime.LINE_MAP``,
and ``reporting._LOG_FH``.

Notes
-----

* Perl's ``caller()``-based access-control check is replaced by Python's
  underscore convention: the proxies are private; user template code
  should not import them directly.
* ``_include()`` is implemented by parsing the ``.vpy`` file with
  :func:`genesispy.template.parser.parse_vpy` and ``exec``-ing the
  result in a namespace where ``self`` is bound to the current module.
"""

from __future__ import annotations

import builtins
import os
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Iterator, Optional

if TYPE_CHECKING:  # pragma: no cover
    from .manager import Manager
    from .unique_module import UniqueModule


_active_manager: "Optional[Manager]" = None
_active_module: "Optional[UniqueModule]" = None


def _current_manager() -> "Manager":
    if _active_manager is None:
        raise RuntimeError(
            "genesispy.user_config: no active manager context. "
            "User-config helpers may only be called while a generated "
            "module is executing (wrap top.execute() in "
            "`with user_config.context(manager, top): ...`)."
        )
    return _active_manager


def _current_module() -> "UniqueModule":
    if _active_module is None:
        raise RuntimeError(
            "genesispy.user_config: no active module context. "
            "User-config helpers may only be called while a generated "
            "module is executing."
        )
    return _active_module


@contextmanager
def context(manager: "Manager", module: "UniqueModule") -> Iterator[None]:
    """Set the manager/module context for the duration of the ``with`` block.

    Save/restore so nested ``include()``-style calls keep the outer context.
    """
    global _active_manager, _active_module
    prev_mgr, prev_mod = _active_manager, _active_module
    _active_manager, _active_module = manager, module
    try:
        yield
    finally:
        _active_manager, _active_module = prev_mgr, prev_mod


# ---------------------------------------------------------------------------
# Configuration proxies
# ---------------------------------------------------------------------------
def _configure(name: str, value: Any, **flags: Any) -> None:
    """Set a configuration value via the active manager's ConfigHandler."""
    return _current_manager().cfg_handler.configure(name, value, **flags)


def _get_configuration(name: str) -> Any:
    """Return the highest-priority value for ``name`` (or None).

    Scoped to the active module's instance path so hierarchical CLI
    overrides like ``--parameter top.foo.X=2`` apply.
    """
    mgr = _current_manager()
    path = _current_module()._instance_path_segments()
    return mgr.cfg_handler.get_configuration(name, instance_path=path)


def _exists_configuration(name: str) -> bool:
    """True iff some source has defined ``name``. Scoped to the active module."""
    mgr = _current_manager()
    path = _current_module()._instance_path_segments()
    return mgr.cfg_handler.exists_configuration(name, instance_path=path)


def _remove_configuration(name: str) -> None:
    """Delete a previously-recorded configuration value."""
    return _current_manager().cfg_handler.remove_configuration(name)


def _print_configuration() -> str:
    """Return a formatted dump of all configuration sources."""
    return _current_manager().cfg_handler.print_configuration()


# ---------------------------------------------------------------------------
# Include
# ---------------------------------------------------------------------------
def _include(path: str) -> None:
    """Parse the ``.vpy`` file at ``path`` and exec it in the current module.

    Mirrors ``UserConfigBase::include`` plus the Perl Manager ``parse_file``
    include directive: the parsed file's body is executed with ``self``
    bound to the current module so its ``self.emit(...)`` calls populate
    that module's output buffer.
    """
    from .template.parser import parse_vpy
    from .template import runtime

    if os.path.isabs(path) or os.path.exists(path):
        resolved = path
    else:
        mgr = _current_manager()
        resolved = mgr.find_file(path, list(mgr.inc_path) + ["."])
    ext_map = getattr(_active_manager, "extension_map", None)
    allowed = frozenset(ext_map.keys()) if ext_map else None
    syntax = getattr(_active_manager, "syntax", "genesis")
    comment = getattr(_active_manager, "source_comment", "//")
    # Record for the .depend prerequisite list (nested includes recurse
    # through _include, so every level registers itself).
    from . import cache

    cache.INCLUDED_FILES.append(resolved)
    src = parse_vpy(resolved, allowed, syntax=syntax, comment=comment)
    # Register a line map so tracebacks from the included .vpy point at the
    # author's source lines, not the generated Python.
    runtime.register_line_map(resolved, runtime.build_line_map(src))
    code = compile(src, resolved, "exec")
    mod = _current_module()
    g: dict = {
        "self": mod,
        "__file__": resolved,
        "__name__": "__genesispy_include__",
        "__builtins__": builtins,
    }
    # Perl-compat bare-name aliases — single source of truth in template.aliases.
    from .template.aliases import alias_dict
    g.update(alias_dict(mod, g))
    exec(code, g)


# ---------------------------------------------------------------------------
# Raw-Python include
# ---------------------------------------------------------------------------
# Compiled pyinclude bodies keyed by resolved path; cleared by cache.clear_all.
_PYINCLUDE_CODE: dict = {}
_PINCLUDE_WARNED = False


def _reset_pyinclude_state() -> None:
    """Clear the compile cache and the one-time pinclude warning."""
    global _PINCLUDE_WARNED
    _PYINCLUDE_CODE.clear()
    _PINCLUDE_WARNED = False


def _resolve_pyinclude(path: str) -> str:
    """Resolve a pyinclude target over cwd, --py-path, --inc-path, then '.'.

    Raises ParseError (via Manager.find_file) naming every candidate
    directory when nothing matches.
    """
    if os.path.isabs(path) or os.path.exists(path):
        return path
    mgr = _current_manager()
    search = list(getattr(mgr, "py_paths", [])) + list(mgr.inc_path) + ["."]
    return mgr.find_file(path, search)


def _make_pyinclude(ns: dict) -> Any:
    """Return a ``pyinclude(path)`` that execs raw Python into ``ns``.

    ``ns`` is the calling code's globals, so the file's top-level names stay
    reachable exactly where the caller's own are. Nothing is seeded into it:
    a generated module's globals are shared by every instance of that
    template, so a captured ``self`` would go stale under nested elaboration.
    """

    def pyinclude(path: str) -> None:
        from .reporting import ParseError

        resolved = _resolve_pyinclude(path)
        ext = os.path.splitext(resolved)[1].lower()
        ext_map = getattr(_active_manager, "extension_map", None) or {}
        if ext in ext_map:
            raise ParseError(
                f"pyinclude: {path!r} is a template ({ext}); "
                "use include() for templates"
            )
        code = _PYINCLUDE_CODE.get(resolved)
        if code is None:
            with open(resolved, "r", encoding="utf-8") as fh:
                code = compile(fh.read(), resolved, "exec")
            _PYINCLUDE_CODE[resolved] = code
        from . import cache

        cache.INCLUDED_FILES.append(resolved)
        exec(code, ns)

    return pyinclude


def _make_pinclude(ns: dict) -> Any:
    """Deprecated spelling of pyinclude; warns once per process."""
    inner = _make_pyinclude(ns)

    def pinclude(path: str) -> None:
        global _PINCLUDE_WARNED
        from .reporting import warning

        if not _PINCLUDE_WARNED:
            _PINCLUDE_WARNED = True
            warning("pinclude is deprecated; use pyinclude")
        return inner(path)

    return pinclude


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------
def _get_top_name() -> Optional[str]:
    """Return the name of the top module under elaboration."""
    return _current_manager().top


def _get_synthtop_path() -> str:
    """Return the absolute path of the synth output directory."""
    return os.path.abspath(_current_manager().synth_dir)


def error(msg: str) -> None:
    """Raise a fatal Genesis2 error (mirrors Perl ``error()``)."""
    from .reporting import error as _err

    _err(msg, fatal=True)
