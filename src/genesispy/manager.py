"""Manager engine controller.

The integration layer wires up:

* :meth:`parse_files` -- parse each .vpy/.svpy input, emit a generated
  Python module file, and stash the (module name -> .py path) mapping.
* :meth:`load_top_module` -- import the generated module for ``self.top``.
* :meth:`gen_verilog` -- instantiate the top, run elaboration, populating
  ``cache.OUTFILE_CONTENT_CACHE`` with the produced Verilog text.
* :meth:`execute` -- end-to-end orchestration (clean / parse / elaborate /
  flush), with friendly :class:`GenesisPyError` reporting.
"""

from __future__ import annotations

import argparse
import atexit
import importlib
import importlib.util
import os
import shutil
import sys
import tempfile
from typing import Dict, List, Optional, Type

from . import cache, errors
from .errors import GenesisPyError, ParseError, error, warning
from .extensions import build_extension_map


class Manager:
    """Top-level engine controller.

    See ``doc/interfaces.md`` for the authoritative attribute list.
    """

    def __init__(self, args: argparse.Namespace) -> None:
        # ``args`` is always built by ``cli.parse_args()`` which sets a
        # ``default=`` for every flag; direct attribute access is safe.
        self.args = args
        self.top = args.top
        # synth_top default = None (Perl SynthTop=undef): without --synthtop,
        # every emitted file is tagged 'verif'.  Mirrors Manager.pm:89.
        self.synth_top = args.synthtop
        self.debug = int(args.debug)
        self.sources_path = list(args.srcpath)
        self.includes_path = list(args.includepath)
        self.cfg_path = list(args.cfgpath)

        outputdir_arg = args.outputdir
        synth_dir_arg = args.synth_dir
        verif_dir_arg = args.verif_dir
        self.output_dir = outputdir_arg or "genesis_synth"
        self.synth_dir = synth_dir_arg or outputdir_arg or "genesis_synth"
        self.verif_dir = verif_dir_arg or outputdir_arg or "genesis_verif"
        # build_extension_map raises ValueError on conflicts among args.extensions;
        # surface as GenesisPyError so the CLI prints a clean message.
        try:
            self.extension_map = build_extension_map(
                getattr(args, "extensions", []) or []
            )
        except ValueError as exc:
            raise GenesisPyError(str(exc)) from exc

        self.input_files = list(args.input)
        self.parameter_overrides = list(args.parameter)
        self.json_in = args.json
        self.json_out = args.jsonout
        self.cfg_files = list(args.cfg)
        self.flavor = args.flavor
        # Genesis2 -product: when set, write FILE.synth + FILE.verif lists.
        self.product_file = args.product
        self.depend_file = args.depend
        self.pathfile = args.pathfile
        self.log_file = args.log
        self.parse_only = args.parse_only
        self.generate_only = args.generate_only
        self.no_module_cache = args.no_module_cache
        self.gen_raw = args.gen_raw
        self.use_tmp = args.use_tmp
        self.keep_tmp = args.keep_tmp
        self.python_paths = list(args.pythonpath)
        self.pymodules = list(args.pymodule)
        self.clean_flag = args.clean
        self.stdout_mode = args.stdout
        self.syntax = "j2" if getattr(args, "j2", False) else "genesis"
        self.comment = getattr(args, "comment", "//")

        # Track every directory touched during elaboration for --pathfile.
        self.touched_dirs: List[str] = []

        # Resolve raw_dir; --use-tmp relocates it under a fresh /tmp scratch.
        if self.use_tmp:
            self._tmp_scratch = tempfile.mkdtemp(prefix="genesispy_")
            self.raw_dir = os.path.join(self._tmp_scratch, "genesis_raw")
            if not self.keep_tmp:
                atexit.register(
                    shutil.rmtree, self._tmp_scratch, ignore_errors=True
                )
        else:
            self._tmp_scratch = None
            self.raw_dir = "genesis_raw"

        # errors._LOG_FH is a process global: one Manager per process, same
        # single-threading caveat as cache.MODULE_CACHE.
        if self.log_file:
            errors.set_log_file(self.log_file)

        # User-supplied Python search paths and helper modules.
        for d in self.python_paths:
            if d and d not in sys.path:
                sys.path.insert(0, d)
        for name in self.pymodules:
            try:
                importlib.import_module(name)
            except ImportError as exc:
                raise GenesisPyError(
                    f"--pymodule: failed to import {name!r}: {exc}"
                ) from exc

        self.cfg_handler = None

        # Wave-2 additions: maps generated module class name -> .py file.
        self._generated_modules: Dict[str, str] = {}
        # Maps module name -> already-imported class object.
        self._loaded_classes: Dict[str, Type] = {}
        # Set by gen_verilog; flush_outputs walks it to tag synth/verif files.
        self._top_inst = None

    # ------------------------------------------------------------------
    # File search
    # ------------------------------------------------------------------
    def _record_dir(self, d: str) -> None:
        if d and d not in self.touched_dirs:
            self.touched_dirs.append(d)

    def _resolve_cfg_path(self, name: str) -> str:
        """Resolve a --cfg/--json input against ``--cfgpath`` dirs.

        Absolute paths and existing relative paths are returned unchanged
        (after being recorded). Otherwise the cfgpath list is searched in
        order.
        """
        if os.path.isabs(name) or os.path.exists(name):
            resolved = os.path.abspath(name)
            self._record_dir(os.path.dirname(resolved))
            return resolved
        for d in self.cfg_path:
            candidate = os.path.join(d, name)
            if os.path.exists(candidate):
                resolved = os.path.abspath(candidate)
                self._record_dir(os.path.dirname(resolved))
                return resolved
        # Fall through with the original name; downstream readers raise.
        return name


    def find_file(
        self, name: str, paths: Optional[List[str]] = None
    ) -> str:
        if os.path.isabs(name):
            if os.path.exists(name):
                return name
            raise ParseError(f"find_file: file not found: {name}")

        if paths is None:
            candidates = [*self.sources_path, *self.includes_path, "."]
        else:
            candidates = list(paths)

        for d in candidates:
            candidate = os.path.join(d, name)
            if os.path.exists(candidate):
                resolved = os.path.abspath(candidate)
                self._record_dir(os.path.dirname(resolved))
                return resolved

        raise ParseError(
            f"find_file: file '{name}' not found in search paths: {candidates}"
        )

    # ------------------------------------------------------------------
    # Wave-2: parse / emit / load / elaborate
    # ------------------------------------------------------------------
    def _discover_generated_modules(self) -> None:
        """Populate ``_generated_modules`` from existing .py files in raw_dir.

        Used by ``--generate-only`` so the elaboration phase can run without
        re-parsing .vpy sources.
        """
        if not os.path.isdir(self.raw_dir):
            raise GenesisPyError(
                f"--generate-only: raw_dir {self.raw_dir!r} does not exist."
            )
        for fname in os.listdir(self.raw_dir):
            if fname.endswith(".py"):
                stem = os.path.splitext(fname)[0]
                self._generated_modules[stem] = os.path.join(self.raw_dir, fname)

    def _output_suffix_for(self, path: str) -> str:
        """Return the output extension paired with ``path``'s input extension.

        Lookup is case-insensitive against :data:`self.extension_map`.
        Unknown extensions raise :class:`ParseError` -- the parser would
        reject them anyway, but tripping here gives a uniform error path.
        """
        ext = os.path.splitext(path)[1].lower()
        try:
            return self.extension_map[ext]
        except KeyError:
            allowed = ", ".join(sorted(self.extension_map.keys())) or "<none>"
            raise ParseError(
                f"{path}: unsupported extension {ext!r}; expected {allowed}."
            )

    def parse_files(self) -> None:
        """Parse every input template and write a generated .py module."""
        # Local import to avoid cycle at module import time.
        from .template import emitter

        os.makedirs(self.raw_dir, exist_ok=True)

        allowed = frozenset(self.extension_map.keys())
        for src in self.input_files:
            path = self.find_file(src) if not os.path.isabs(src) else src
            out_suffix = self._output_suffix_for(path)
            py_path = emitter.write_module(
                path,
                self.raw_dir,
                output_suffix=out_suffix,
                allowed=allowed,
                syntax=self.syntax,
                comment=self.comment,
            )
            stem = os.path.splitext(os.path.basename(path))[0]
            self._generated_modules[stem] = py_path

    def _import_generated(self, name: str, py_path: str) -> Type:
        """Import a generated .py file and return the class it defines as ``name``.

        Adds ``self.raw_dir`` to :data:`sys.path` for the duration of the
        import so user code in the generated module can reach sibling
        generated modules via plain ``import``.
        """
        raw_abs = os.path.abspath(self.raw_dir)
        added = raw_abs not in sys.path
        if added:
            sys.path.insert(0, raw_abs)
        try:
            mod_name = f"_gpy_generated_{name}"
            spec = importlib.util.spec_from_file_location(mod_name, py_path)
            if spec is None or spec.loader is None:
                raise GenesisPyError(
                    f"Failed to load generated module from {py_path}"
                )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            cls = getattr(module, name, None)
            if cls is None:
                raise GenesisPyError(
                    f"Generated module {py_path} does not define class {name!r}."
                )
            self._loaded_classes[name] = cls
            return cls
        finally:
            if added:
                try:
                    sys.path.remove(raw_abs)
                except ValueError:
                    pass

    def load_top_module(self) -> Type:
        """Import the generated .py file for ``self.top`` and return its class."""
        if self.top is None:
            raise GenesisPyError("No --top module specified.")

        if self.top in self._loaded_classes:
            return self._loaded_classes[self.top]

        py_path = self._generated_modules.get(self.top)
        if py_path is None:
            raise GenesisPyError(
                f"Top module '{self.top}' has no generated .py file; "
                f"known: {sorted(self._generated_modules)}"
            )

        return self._import_generated(self.top, py_path)

    def resolve_module_class(self, name: str) -> Type:
        """Look up a generated module class by name.

        Used by :meth:`UniqueModule.unique_inst` when the user passes a
        string module name. Loads the corresponding generated .py file on
        demand.
        """
        if name in self._loaded_classes:
            return self._loaded_classes[name]

        py_path = self._generated_modules.get(name)
        if py_path is None:
            for src in self.input_files:
                stem = os.path.splitext(os.path.basename(src))[0]
                if stem == name:
                    path = self.find_file(src) if not os.path.isabs(src) else src
                    from .template import emitter

                    out_suffix = self._output_suffix_for(path)
                    py_path = emitter.write_module(
                        path,
                        self.raw_dir,
                        output_suffix=out_suffix,
                        allowed=frozenset(self.extension_map.keys()),
                        syntax=self.syntax,
                        comment=self.comment,
                    )
                    self._generated_modules[name] = py_path
                    break

        if py_path is None:
            raise GenesisPyError(
                f"Module {name!r} not found among inputs "
                f"{sorted(self._generated_modules)}"
            )

        return self._import_generated(name, py_path)

    def synonym_class(self, src_name: str, target_name: str) -> Type:
        """Register ``target_name`` as a class-level synonym of ``src_name``.

        Mirrors Perl ``synonym(src, target)`` (UniqueModule.pm:1724) at the
        template/class level: a dynamic subclass of the resolved source
        class is created, named ``target_name``, and registered so that
        subsequent ``resolve_module_class(target_name)`` returns it.

        The subclass inherits ``execute`` and all behaviour from the source,
        but its ``__name__`` becomes ``target_name`` -- so unique-module
        names derived from the class (e.g. ``foo_unq3``) use the new base
        name.

        Idempotent: calling twice with the same pair returns the same
        subclass; calling with a different src under an already-registered
        target name raises ``GenesisPyError``.
        """
        src_cls = self.resolve_module_class(src_name)
        existing = self._loaded_classes.get(target_name)
        if existing is not None:
            if issubclass(existing, src_cls) or existing is src_cls:
                return existing
            raise GenesisPyError(
                f"synonym_class: cannot alias {target_name!r} to {src_name!r}; "
                f"{target_name!r} already registered to a different class."
            )
        new_cls = type(target_name, (src_cls,), {})
        self._loaded_classes[target_name] = new_cls
        return new_cls

    def _ensure_cfg_handler(self) -> None:
        """Lazily instantiate ConfigHandler and consume CLI config inputs."""
        if self.cfg_handler is not None:
            return
        from .config_handler import ConfigHandler

        def _wrap(label: str, fn, *fn_args):
            # Pass GenesisPyError through unchanged; wrap unexpected ones so
            # the caller sees a uniform message.
            try:
                return fn(*fn_args)
            except GenesisPyError:
                raise
            except Exception as exc:
                raise GenesisPyError(f"{label} failed: {exc}") from exc

        ch = _wrap("ConfigHandler init", ConfigHandler, self)
        if self.json_in:
            _wrap("read_json", ch.read_json, self._resolve_cfg_path(self.json_in))
        for cfg in self.cfg_files:
            _wrap(f"read_cfg ({cfg})", ch.read_cfg, self._resolve_cfg_path(cfg))
        # Command-line --parameter overrides are ingested by ConfigHandler
        # itself in _init_cmdln_from_manager (run from __init__ above).
        self.cfg_handler = ch

    def gen_verilog(self) -> None:
        """Elaborate ``self.top``: load class, instantiate, execute."""
        from . import user_config

        self._ensure_cfg_handler()
        top_cls = self.load_top_module()
        top = top_cls(self)
        self._top_inst = top
        with user_config.context(self, top):
            top.execute()

        self.flush_outputs()

    def flush_outputs(self) -> None:
        """Write the in-memory Verilog cache to disk + lists + clean script.

        Also dumps the resolved configuration tree to ``--jsonout`` if
        passed.

        When ``--stdout`` is set, the Verilog cache is concatenated to
        ``sys.stdout`` instead and the file-list / clean-script writers
        are skipped. The transient ``raw_dir`` is removed.
        """
        from . import output_writer

        self._populate_outfile_tags()

        if self.stdout_mode:
            output_writer.dump_to_stdout(self)
            if self.raw_dir and os.path.isdir(self.raw_dir):
                shutil.rmtree(self.raw_dir, ignore_errors=True)
        else:
            written = output_writer.flush_to_disk(self)
            output_writer.write_file_lists(self, written)
            output_writer.write_clean_script(self)
            if self.product_file:
                output_writer.write_product_lists(self, written, self.product_file)
            if self.pathfile:
                output_writer.write_pathfile(self, self.pathfile)

        if self.cfg_handler is not None:
            if self.json_out:
                try:
                    self.cfg_handler.write_json(self.json_out, self._top_inst)
                except Exception as exc:
                    raise GenesisPyError(f"write_json failed: {exc}") from exc

    def _populate_outfile_tags(self) -> None:
        """Walk the elaborated instance tree and fill ``cache.OUTFILE_TAGS``.

        Mirrors Perl ``Manager.pm:1330-1395``: each emitted Verilog file
        is tagged ``'synth'`` (instance at/under ``synth_top``),
        ``'verif'`` (otherwise), or ``'synth_and_verif'`` (same file
        seen on both sides).  Synonyms inherit the resolved tag.
        """
        cache.OUTFILE_TAGS.clear()
        if self._top_inst is None:
            return

        def _promote(name: str, new_tag: str) -> None:
            # Once 'synth_and_verif', sticky: never demoted to a single tag.
            existing = cache.OUTFILE_TAGS.get(name)
            if existing is None or existing == new_tag:
                cache.OUTFILE_TAGS[name] = new_tag
            elif existing != "synth_and_verif":
                cache.OUTFILE_TAGS[name] = "synth_and_verif"

        for inst, is_synth in self._top_inst.get_prod_list_insts(self.synth_top):
            fname = inst._outfile_name
            if fname is None:
                continue
            tag = "synth" if is_synth else "verif"
            _promote(fname, tag)
            # Synonym output files share the source module's extension.
            suffix = getattr(type(inst), "_OUTPUT_SUFFIX", ".v")
            for syn in inst._synonyms:
                _promote(f"{syn}{suffix}", tag)

    def clean(self) -> None:
        """Delete generated output directories and lists."""
        from . import output_writer

        output_writer.clean_outputs(self)
        if os.path.isdir(self.raw_dir):
            shutil.rmtree(self.raw_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Engine entry point
    # ------------------------------------------------------------------
    def execute(self) -> int:
        """End-to-end orchestration."""
        if self.clean_flag:
            self.clean()
            return 0

        if not self.input_files:
            # Default invocation: warn, exit 0 (Wave-1 stub behaviour).
            warning("genesispy: stub")
            return 0

        try:
            if not self.generate_only:
                self.parse_files()
            else:
                self._discover_generated_modules()
            if self.parse_only:
                return 0
            self.gen_verilog()
        except GenesisPyError as exc:
            error(str(exc), fatal=False)
            return 1
        except Exception as exc:  # noqa: BLE001 -- remap user-code traceback
            # Rewrite frames to .vpy positions; falls back when no LINE_MAP entry.
            from .template.runtime import remap_traceback
            sys.stderr.write(remap_traceback(exc))
            return 1
        return 0
