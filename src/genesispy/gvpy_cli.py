"""gvpy-compatible CLI built on the genesispy template engine.

A thin driver that lets users run a gvpy/gvp-style flat preprocessor
workflow on top of the genesispy parser and runtime: ``//;``-prefixed
Python lines, backtick interpolation, ``include()``/``pinclude()``,
``--parameter`` flat parameters, output to stdout.

Differences from the standalone ``gvpy.py`` in ../gvpy:

* No PRELUDE: bare-name helpers (``parameter``, ``emit``, ``generate``,
  ``instantiate``, ``synonym``, ``mname``, ...) come from genesispy's
  emitter/runtime aliases.
* ``generate(...)`` is the real genesispy ``unique_inst`` (richer than
  gvpy's record-only stub). Pass ``--gvpy-strict`` for the legacy
  record-only behaviour.
* ``parameter('NAME', default)`` consults the same ``--parameter`` flat
  dict as gvpy, via ``ConfigHandler.configure``. ``--defparam`` is kept
  as a hidden alias for backward compatibility.
* ``pinclude(path)`` execs raw Python in the current namespace.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Iterable

from genesispy import __version__, cache, user_config
from genesispy import reporting
from genesispy.cli import _add_deprecated_alias, _comment_arg
from genesispy.config_handler import ConfigHandler
from genesispy.reporting import ParameterError
from genesispy.extensions import build_extension_map, parse_extension_spec
from genesispy.template.aliases import alias_prelude_source
from genesispy.template.parser import parse_vpy
from genesispy.unique_module import UniqueModule


def pp(num, fmt: str = "%02d") -> str:
    """Printf-style integer formatter (gvpy-only ergonomic helper).

    Bound as a bare name in every gvpy-generated ``execute()`` and in
    ``pinclude()`` namespaces so gvpy templates can write
    ``stage_`pp(i)``` for zero-padded indices. Not available to the
    full genesispy elaboration path.
    """
    return fmt % num


# --------------------------------------------------------------------------
# Lightweight Manager: enough surface for ConfigHandler + resolve_module_class.
# --------------------------------------------------------------------------
class _GvpyManager:
    """Single-file driver Manager: no parse/emit pipeline, no output dirs."""

    def __init__(self, args: argparse.Namespace, incdirs: list[str]) -> None:
        # Patch attrs consumed by ConfigHandler/UniqueModule/output_writer
        # that gvpy's narrower argparse doesn't define.
        if not hasattr(args, "unq_style"):
            args.unq_style = None
        self.args = args
        self.top: str | None = args.mname
        self.debug = 0
        self.src_path: list[str] = list(incdirs)
        self.inc_path: list[str] = list(incdirs)
        self.cfg_path: list[str] = []
        self.output_dir = ""
        self.raw_dir = ""
        self.synth_dir = ""
        self.verif_dir = ""
        self.extension_map = build_extension_map(
            getattr(args, "extensions", []) or []
        )
        self.syntax = "j2" if getattr(args, "j2", False) else "genesis"
        self.comment = getattr(args, "comment", "//")
        self.no_module_cache = False
        self.out_type = "both"
        self.gen_raw = False
        self.depend_file: str | None = None
        self.touched_dirs: list[str] = []
        self.cfg_handler = ConfigHandler(self)
        self._synonym_classes: dict[tuple[str, str], type] = {}

    def _resolve_cfg_path(self, name: str) -> str | None:
        """No-op: gvpy does not invoke ConfigHandler.read_cfg."""
        return None

    def find_file(self, name: str, paths: list[str] | None = None) -> str:
        # Diverges from Manager.find_file: cwd always appended, inc_path-only,
        # raises FileNotFoundError (gvpy main's handler keys off built-ins).
        if os.path.isabs(name):
            if os.path.exists(name):
                return name
            raise FileNotFoundError(name)
        search = paths if paths is not None else self.inc_path
        for d in [*search, "."]:
            cand = os.path.join(d, name)
            if os.path.exists(cand):
                return os.path.abspath(cand)
        raise FileNotFoundError(name)

    def resolve_module_class(self, name: str) -> type:
        """Locate a sibling template by name and produce a UniqueModule class.

        Mirrors :meth:`Manager.resolve_module_class` minus the on-disk .py
        emission: we parse and exec the body directly into a class body.
        Searches every input extension registered in
        :attr:`self.extension_map`, plus ``.gvpy`` as a gvpy-only fallback.
        """
        candidates = list(self.extension_map.keys()) + [".gvpy"]
        for ext in candidates:
            try:
                path = self.find_file(name + ext)
            except FileNotFoundError:
                continue
            return _build_class_from_vpy(
                name, path, self.extension_map,
                syntax=self.syntax, comment=self.comment,
            )
        raise RuntimeError(
            f"Cannot resolve module {name!r}: no {name}{{{','.join(candidates)}}} found"
        )

    def synonym_class(self, src_name: str, target_name: str) -> type:
        # Cache per (src, target): same call returns the same class so
        # ununique_inst doesn't re-allocate `_unqN` on every visit.
        key = (src_name, target_name)
        existing = self._synonym_classes.get(key)
        if existing is not None:
            return existing
        src_cls = self.resolve_module_class(src_name)
        new_cls = type(target_name, (src_cls,), {"_synonym_for": src_name})
        self._synonym_classes[key] = new_cls
        return new_cls


# --------------------------------------------------------------------------
# Class factory: turn a .vpy into a UniqueModule subclass via parser.
# --------------------------------------------------------------------------
def _build_class_from_vpy(
    name: str,
    path: str,
    extension_map: dict[str, str] | None = None,
    *,
    syntax: str = "genesis",
    comment: str = "//",
) -> type:
    if not name.isidentifier():
        raise ValueError(
            f"_build_class_from_vpy: {name!r} is not a valid Python identifier"
        )
    # Allowed input extensions: keys of the configured map, plus the gvpy
    # ``.gvpy`` alias so resolve_module_class fallbacks still parse.
    if extension_map is None:
        allowed = None
        out_suffix = ".v"
    else:
        allowed = frozenset(list(extension_map.keys()) + [".gvpy"])
        ext = os.path.splitext(path)[1].lower()
        # ``.gvpy`` is gvpy's canonical input alias and is never present in
        # ``extension_map`` (the user configures ``.vpy``); resolve it to
        # whatever ``.vpy`` maps to so a ``--extension .vpy=.sv`` run emits
        # consistent suffixes across mixed ``.vpy`` / ``.gvpy`` inputs.
        lookup_ext = ".vpy" if ext == ".gvpy" else ext
        out_suffix = extension_map.get(lookup_ext, ".v")
    body = parse_vpy(path, allowed, syntax=syntax, comment=comment)
    indent = "        "
    indented = "\n".join(
        (indent + ln) if ln.strip() else ln for ln in body.splitlines()
    )
    src = (
        "from genesispy.template.runtime import UniqueModule, UserMixin, StrCallable\n"
        "from genesispy.gvpy_cli import pp\n"
        "from genesispy import user_config as _gpy_user_config\n"
        f"class {name}(UniqueModule, UserMixin):\n"
        f"    _OUTPUT_SUFFIX = {out_suffix!r}\n"
        "    def execute(self):\n"
        "        super().execute()\n"
        + alias_prelude_source(indent="        ")
    )
    src += indented
    if not src.endswith("\n"):
        src += "\n"
    ns: dict[str, Any] = {"__name__": f"_gvpy_{name}"}
    # Line map keyed by `path` so remap_traceback rewrites synthetic frames.
    from genesispy.template import runtime as _rt
    _rt.register_line_map(path, _rt.build_line_map(src))
    exec(compile(src, path, "exec"), ns)
    return ns[name]


# --------------------------------------------------------------------------
# gvpy-strict overrides: record-only generate/instantiate/synonym.
# --------------------------------------------------------------------------
def _strict_overrides(inst_for_cfg: UniqueModule, emit_fn) -> dict[str, Any]:
    """Return record-only generate/instantiate/synonym + kwargs-tolerant parameter.

    ``inst_for_cfg`` supplies the ConfigHandler for parameter lookups.
    """
    class _Inst(dict):
        def __getattr__(self, k):
            try:
                return self[k]
            except KeyError as e:
                raise AttributeError(k) from e

    registry: dict[str, dict[str, Any]] = {}

    def generate(tname, iname, **kwargs):
        registry.setdefault(tname, {})
        inst = _Inst(tname=tname, iname=iname, params=dict(kwargs))
        registry[tname][iname] = inst
        return inst

    def instantiate(inst):
        parts = [f"{inst['tname']} /*PARAMS:"]
        parts.extend(f"{k}=>{v}" for k, v in inst["params"].items())
        parts.append(f"*/ {inst['iname']}")
        emit_fn(" ".join(parts))

    def synonym(*_a, **_kw):
        return None

    def parameter(name=None, val=None, **kw):
        """Accept both gvpy ``parameter(name=, val=)`` and genesispy ``parameter(name, default)``."""
        n = kw.get("name", name)
        v = kw.get("val", val)
        cfg = inst_for_cfg._manager.cfg_handler
        if cfg is None or n is None:
            return v
        # Honour scoped overrides; distinguish explicit None from "not configured".
        path = inst_for_cfg._instance_path_segments()
        if cfg.exists_configuration(n, instance_path=path):
            return cfg.get_configuration(n, instance_path=path)
        return v

    return {
        "generate": generate,
        "generate_base": generate,
        "instantiate": instantiate,
        "synonym": synonym,
        "parameter": parameter,
    }


# --------------------------------------------------------------------------
# Top-level driver
# --------------------------------------------------------------------------
def _flatten_csv(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    for v in values:
        out.extend(s for s in v.split(",") if s)
    return out


def main(argv: list[str] | None = None) -> int:
    PROG = os.path.basename(sys.argv[0]) or "gvpy"
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="gvpy-compatible preprocessor on top of genesispy.",
        add_help=False,
    )
    parser.add_argument("-h", "--help", action="help")
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"gvpy {__version__}",
    )
    parser.add_argument(
        "--mname",
        default=None,
        help="Top module name (default: input filename stem).",
    )
    parser.add_argument(
        "--py-path",
        dest="py_path",
        action="append",
        default=[],
        help="Comma-separated dirs to add to sys.path (may be repeated).",
    )
    _add_deprecated_alias(
        parser, "--libdirs", "--py-path", dest="py_path",
        kind="append", prog=PROG,
    )
    parser.add_argument(
        "--inc-path",
        dest="inc_path",
        action="append",
        default=[],
        help="Comma-separated dirs for include()/pinclude() search.",
    )
    _add_deprecated_alias(
        parser, "--incdirs", "--inc-path", dest="inc_path",
        kind="append", prog=PROG,
    )
    parser.add_argument(
        "-p",
        "--parameter",
        action="append",
        dest="parameter",
        default=[],
        metavar="NAME=VALUE",
        help="Set a flat parameter (consulted by parameter()).",
    )
    _add_deprecated_alias(
        parser, "--defparam", "-p/--parameter", dest="parameter",
        kind="append", prog=PROG, metavar="NAME=VALUE",
    )
    parser.add_argument(
        "--comment",
        default="//",
        type=_comment_arg,
        help='Comment prefix of the target language (default "//").',
    )
    parser.add_argument(
        "--extension",
        dest="extensions",
        action="append",
        default=[],
        type=parse_extension_spec,
        metavar="EXT_IN=EXT_OUT",
        help=(
            "Pair an input template extension with its emitted-Verilog "
            "extension (may be repeated). Defaults: .vpy=.v, .svpy=.sv."
        ),
    )
    parser.add_argument(
        "-j2", "--j2",
        action="store_true",
        default=False,
        help=(
            "Parse templates with the j2 (Jinja2-like) flavour. Shares "
            "delimiters with stock Jinja2 -- '{%% stmt %%}' replaces "
            "'//; stmt', '{{ expr }}' replaces backticks, '{# comment #}' "
            "is a stripped comment -- but with expanded semantics: the "
            "embedded language is full Python (no filter pipes, no "
            "'is'-tests, no macro/block/extends). Stock Jinja2 sources "
            "do not parse here as-is; see 'genesispy-jinja2j2' to port "
            "them."
        ),
    )
    parser.add_argument(
        "--gvpy-strict",
        dest="gvpy_strict",
        action="store_true",
        help=(
            "Use gvpy's record-only generate/instantiate/synonym instead of "
            "genesispy's elaboration-based versions."
        ),
    )
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)

    libdirs = _flatten_csv(args.py_path) or ["./"]
    incdirs = _flatten_csv(args.inc_path) or ["./"]
    for d in libdirs:
        if d not in sys.path:
            sys.path.insert(0, d)

    # ConfigHandler validates --parameter specs and raises ParameterError
    # for any malformed entry; catch and re-emit with the gvpy prefix.
    cache.clear_all()
    try:
        mgr = _GvpyManager(args, incdirs)
    except ParameterError as exc:
        reporting.error(f"{PROG}: {exc}", fatal=False)
        return 2
    # ConfigHandler.__init__ has already ingested args.parameter into
    # _cmdln_db / _cmdln_scoped_db; no further seeding required.

    if not args.files:
        reporting.error(f"{PROG}: no input files", fatal=False)
        return 2

    from genesispy.template.runtime import remap_traceback

    rc = 0
    for fname in args.files:
        try:
            _process(fname, mgr, args, incdirs)
        except Exception as exc:  # surface the source location
            reporting.error(
                f"{PROG}: error processing {fname}: {exc}", fatal=False
            )
            sys.stderr.write(remap_traceback(exc))
            rc = 1
    return rc


def _process(
    fname: str, mgr: _GvpyManager, args: argparse.Namespace, incdirs: list[str]
) -> None:
    path = mgr.find_file(fname) if not os.path.isabs(fname) else fname
    stem = _stem(path, extra=mgr.extension_map.keys())
    name = args.mname or stem

    cls = _build_class_from_vpy(
        name, path, mgr.extension_map,
        syntax=mgr.syntax, comment=mgr.comment,
    )
    inst = cls(mgr)

    # Allow strict-mode overrides of generate/instantiate/synonym by
    # patching the bound methods on the instance before execute() binds
    # them as locals at the top of the generated body.
    if args.gvpy_strict:
        overrides = _strict_overrides(inst, inst.emit)
        for k, v in overrides.items():
            setattr(inst, k, v)
        inst.ununique_inst = overrides["generate"]  # type: ignore[assignment]

    _install_pinclude(inst, incdirs)

    with user_config.context(mgr, inst):
        inst.execute()

    out = inst._outfile_handle.getvalue() if inst._outfile_handle else ""
    sys.stdout.write(out)


def _install_pinclude(inst: UniqueModule, incdirs: list[str]) -> None:
    """Bind a ``pinclude(path)`` callable on the instance so generated
    code can call it as a bare name.

    pinclude is exposed as a bare name via template.aliases.alias_prelude_source.
    """

    def pinclude(path: str) -> None:
        target = path
        if not os.path.isabs(target):
            for d in incdirs:
                cand = os.path.join(d, path)
                if os.path.isfile(cand):
                    target = cand
                    break
            else:
                raise FileNotFoundError(
                    f"pinclude: cannot find {path!r} in {incdirs}"
                )
        with open(target, "r", encoding="utf-8") as fh:
            src = fh.read()
        ns: dict[str, Any] = {
            "self": inst,
            "emit": inst.emit,
            "parameter": inst.parameter,
            "__file__": target,
            "__name__": "__gvpy_pinclude__",
        }
        exec(compile(src, target, "exec"), ns)

    inst.pinclude = pinclude  # type: ignore[attr-defined]


def _stem(path: str, extra: Iterable[str] = ()) -> str:
    base = os.path.basename(path)
    # Built-in/legacy gvpy extensions stripped unconditionally. ``extra`` is
    # used by callers that know about user-registered extensions (e.g. from
    # an extension_map).
    candidates = list(extra) + [".vpy", ".gvpy", ".vp", ".gvp", ".svpy", ".svp"]
    for ext in candidates:
        if base.endswith(ext):
            return base[: -len(ext)]
    return base


if __name__ == "__main__":
    sys.exit(main())
