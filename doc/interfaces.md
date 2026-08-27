# genesispy -- code interfaces

Canonical interfaces for the package in `genesispy/src/genesispy/`. These
signatures are the critical boundary between modules; coordinate before
changing them.

## genesispy.reporting

```python
# `code` is a stable string identifier on every subclass — assert on it
# in tests rather than matching prose. `msg` is the constructor argument
# preserved verbatim.
class GenesisPyError(Exception):
    code: str = "genesispy_error"
    msg: str
    # Optional location string (e.g. "file.vpy:42") appended to the
    # formatted message as " (at <location>)".
    location: Optional[str]
    def __init__(self, msg: str = "", location: Optional[str] = None) -> None: ...
class ParseError(GenesisPyError):       code = "parse_error"
class ConfigError(GenesisPyError):      code = "config_error"
class ParameterError(GenesisPyError):   code = "parameter_error"
class ElaborationError(GenesisPyError): code = "elaboration_error"

# Severity helpers. Coloring is TTY-gated by colorama (escapes stripped
# when stderr isn't a tty; NO_COLOR honored). Each helper tees an
# uncolored copy to the `--log` sink set via `set_log_file`.
# `cls=` lets the call site preserve subclass discrimination at the
# raise; default is GenesisPyError. fatal=False prints and returns.
def error(msg: str, *, fatal: bool = True, cls: type = GenesisPyError) -> None: ...
def warning(msg: str) -> None: ...
def info(msg: str) -> None: ...
# Open `path` as the `--log` sink; subsequent info/warning/error calls
# tee their output. Process-global state. Pass `None` to disable.
def set_log_file(path: Optional[str]) -> None: ...
```

## genesispy.manager.Manager

Attributes generated modules and other engine classes may read:

```python
class Manager:
    # Set in __init__; populated by load_config() / read_json() / read_cfg().
    # Treat as `ConfigHandler | None` at the type level.
    cfg_handler: "ConfigHandler | None"
    top: str | None
    debug: int
    src_path: list[str]
    # Resolved input-template paths, appended by parse_files() (one per
    # --input after find_file resolution). Consumed together with
    # cache.INCLUDED_FILES by output_writer.write_file_lists as the
    # `.depend` prerequisite list.
    parsed_source_files: list[str]
    inc_path: list[str]
    output_dir: str
    # Scratch directory for generated .py files and (when --gen-raw is set)
    # raw Verilog dumps. Defaults to "./genesis_raw"; overridden by --raw-dir
    # DIR; relocated under <tmp_scratch>/genesis_raw when --use-tmp is set
    # (--raw-dir and --use-tmp are mutually exclusive). Persists after the
    # run; removed by clean(), by --stdout at end of run, and by the
    # --use-tmp exit cleanup.
    raw_dir: str
    synth_dir: str
    verif_dir: str
    # Input -> output extension pairs. Defaults: {".vpy": ".v", ".svpy": ".sv"};
    # extended by repeatable --extension EXT_IN=EXT_OUT (and the -sv shorthand
    # which maps to (".vpy", ".sv")). The output extension paired with each
    # input is stamped onto the generated module class as _OUTPUT_SUFFIX in
    # template/emitter._header; UniqueModule._flush_outfile and
    # UniqueModule.synonym read type(self)._OUTPUT_SUFFIX at flush time.
    extension_map: dict[str, str]
    # Synthesis-top instance bounding the synth cone: either a top-level
    # instance name ("foo") or a dotted instance path ("top.foo.bar"); the
    # walker matches `path == synth_top or path.startswith(synth_top+".")`.
    # None means SynthTop=undef (Perl default) -> every emitted file is
    # tagged 'verif'. Set from --synth-top.
    synth_top: str | None
    # Every directory touched during elaboration: appended to by
    # find_file() and _resolve_cfg_path(); consumed by
    # output_writer.write_pathfile (the --path output). Plain list
    # of absolute directory paths in append order, deduped at read time.
    touched_dirs: list[str]
    # Search path for `.cfg` config files; consumed by
    # output_writer.write_pathfile alongside src_path /
    # inc_path. Set from --cfg-path.
    cfg_path: list[str]
    # Output-type override for emitted Verilog ('synth', 'verif', or 'both'
    # -- default 'both'). Read by output_writer when tagging files. Set from
    # --out-type.
    out_type: str
    # If True, also write raw (pre-out_type-tagging) Verilog under raw_dir.
    # Set from --gen-raw.
    gen_raw: bool
    # Override path for the `.depend` file; None falls back to
    # output_dir/<top>.depend. Set from --depend.
    depend_file: str | None
    # Named product file (mirrors Genesis2 `$ProductFileName`). None when
    # neither --product nor --vf-out is set. Set from --product FILE, or
    # from --vf-out FILE (with `.vf` auto-appended). Drives
    # output_writer.write_product_lists and suppresses the default
    # <top>.vlist / <top>.vlist.verif when not None.
    product_file: str | None
    # True when product_file came from --vf-out (single-file mode: only
    # the master is written, no .synth/.verif side-files). False
    # otherwise (--product triple-file mode, or product_file is None).
    product_single: bool
    # Disable post-elaboration MODULE_CACHE dedup. Set from
    # --no-module-cache. Read by unique_module.unique_inst[_param].
    no_module_cache: bool
    # Selected template directive flavour: "genesis" (default; //; lines
    # and backtick inline expressions) or "j2" (Jinja2-like flavour:
    # {% %}, {{ }}, {# #} delimiters with full Python inside). Set from
    # --j2; threaded through to parse_vpy / write_module /
    # user_config._include.
    syntax: str
    # Line-comment prefix of the source/target language (default "//"). Set
    # from --source-comment (deprecated --comment alias). Drives the directive
    # sentinel "<comment>;" and is threaded through parse_vpy / write_module /
    # user_config._include.
    source_comment: str
    # Style for comments emitted into the output stream. Set from
    # --output-comment; inherits source_comment when unset. A str is a line
    # prefix; a (open, close) tuple is a wrapping block (e.g. ("/*", "*/")).
    # Read by UniqueModule.to_verilog (banner) and
    # output_writer.dump_to_stdout (--stdout separator).
    output_comment: "str | tuple[str, str]"
    # Original argparse.Namespace as parsed by cli.parse_args(). Engine
    # classes (ConfigHandler) read late-bound flags directly off this
    # (e.g. args.unq_style, args.parameter).
    args: "argparse.Namespace"

    def __init__(self, args: argparse.Namespace) -> None: ...
    def find_file(self, name: str, paths: list[str] | None = None) -> str: ...
    def execute(self) -> int: ...
    # Phase gating: --parse-only stops after parse_files(); --gen-only skips
    # parse_files() and instead loads previously generated .py modules from
    # raw_dir via _discover_generated_modules() — no --input required, but
    # --top is mandatory and raw_dir must exist (GenesisPyError otherwise).
    # parsed_source_files is empty in gen-only mode, so .depend prerequisites
    # will be absent.

    # CLI orchestration entry points (also called directly by tests).
    def parse_files(self) -> None: ...
    def load_top_module(self) -> type: ...
    def gen_verilog(self) -> None: ...
    def flush_outputs(self) -> None: ...
    def clean(self) -> None: ...

    # Look up a generated module class by name (string form is what
    # user .vpy code passes to unique_inst / ununique_inst). Lookup order:
    #   1. _loaded_classes cache,
    #   2. _generated_modules cache,
    #   3. CLI input_files (parse + emit on demand),
    #   4. inc_path fallback over every registered input extension
    #      (mirrors Perl @INC scan in load_base_module).
    # Raises GenesisPyError on miss.
    def resolve_module_class(self, name: str) -> type: ...

    # Class-level synonym (mirrors Perl `synonym(src, target)`):
    # registers `target_name` as a dynamic subclass of `src_name`'s
    # generated class, so resolve_module_class(target_name) returns it
    # and ununique_inst derives unique names from `target_name`.
    # Stamps the new class with `_synonym_for = src_name` so that
    # UniqueModule.sname on instances of the synonym class returns
    # the original source template name (Perl get_source_name parity).
    # Idempotent: re-registering the same (src, target) pair returns
    # the existing subclass; rebinding `target_name` to a different
    # `src_name` raises GenesisPyError.
    def synonym_class(self, src_name: str, target_name: str) -> type: ...
```

## genesispy.config_handler.ConfigHandler

```python
class ConfigHandler:
    def __init__(self, manager: "Manager") -> None: ...
    # read_json deep-merges into the in-memory database. Repeated reads
    # accumulate (matching dicts merge, matching lists concatenate).
    # Legacy XML inputs must be converted via genesispy-xml2json first;
    # ConfigHandler no longer reads or writes XML.
    def read_json(self, path: str) -> None: ...
    def read_cfg(self, path: str) -> None: ...
    # Writes a HierarchyTop snapshot of the elaborated module tree at
    # ``top_inst`` -- port of Perl ConfigHandler.pm::WriteXml /
    # extract_stats. Emits three sibling files in dirname(path):
    # ``path`` (full), ``<stem>-small<ext>`` (no ImmutableParameters),
    # ``<stem>-tiny<ext>`` (priority >= EXTERNAL_PARAM_FILE only), where
    # ``<stem>``/``<ext>`` come from splitext(basename(path)). ``top_inst``
    # is required; passing None raises GenesisPyError.
    def write_json(self, path: str, top_inst: "UniqueModule") -> None: ...

    # Legacy name; underlying store is JSON-only. Returns None for absence
    # OR for an explicit null value; use exists_configuration to
    # disambiguate.
    def get_param_val(self, name: str) -> object | None: ...
    def get_cfg_param_val(self, name: str) -> object | None: ...
    def get_cmdln_param_val(self, name: str) -> object | None: ...

    def configure(self, name: str, value: object, **flags) -> None: ...
    # `instance_path`: optional tuple of segment names (root..self) used
    # to match hierarchical CLI overrides (`--parameter top.child.x=2`).
    # Match is exact-path equality; scoped match wins outright at CMD_LINE.
    def get_configuration(
        self, name: str, *, instance_path: tuple[str, ...] | None = None,
    ) -> object | None: ...
    def exists_configuration(
        self, name: str, *, instance_path: tuple[str, ...] | None = None,
    ) -> bool: ...
    def remove_configuration(self, name: str) -> None: ...
    def print_configuration(self) -> str: ...

    # `.cfg` sandbox namespace (read_cfg-time, ConfigHandler.pm:244-258 parity):
    # configure, get_configuration, exists_configuration, remove_configuration,
    # include, print_configuration, get_top_name, get_synthtop_path, error,
    # warning (Python extension over Perl, kept for `.vpy`/`.cfg` symmetry).
    # `get_top_name` and `get_synthtop_path` reach Manager.top and synth_dir
    # via the active manager context (user_config.context()).

    # Read-only shallow copies of the backing override stores. Used by
    # UniqueModule._scoped_*  helpers (cross-class internal access) and by
    # tests; mutating the returned dict does not affect the ConfigHandler.
    def cmdln_db_snapshot(self) -> dict[str, dict]: ...
    def cfg_db_snapshot(self) -> dict[str, dict]: ...
    def cmdln_scoped_db_snapshot(
        self,
    ) -> dict[tuple[tuple[str, ...], str], dict]: ...

    # Variant returning ``(value, priority)`` so callers can stamp the
    # winning source's priority onto a UniqueModule param. Used by
    # UniqueModule.parameter() so the resulting _params['priority']
    # reflects EXTERNAL_PARAM_FILE / EXTERNAL_CONFIG / CMD_LINE rather than
    # the declaration default (drives the --json-out tiny variant).
    def get_configuration_with_priority(
        self, name: str, *, instance_path: tuple[str, ...] | None = None,
    ) -> tuple[object | None, int | None]: ...

    # Module uniquification style ('numeric' | 'param'); read by
    # UniqueModule.generate to dispatch unique_inst vs unique_inst_param.
    unq_style: str  # default 'numeric', from --unq-style CLI flag
    def set_unq_style(self, style: str) -> None: ...
```

## genesispy.unique_module.UniqueModule

```python
class UniqueModule:
    # Shared state (MODULE_CACHE / MODULE_NAME_NUM_DERIVS /
    # OUTFILE_CONTENT_CACHE) lives in :mod:`cache`; access it there.

    # Param-state sentinels exposed for tests; values are opaque strings
    # ("DEFINED" / "OVERRIDDEN" / "FORCED"). Use the public predicates
    # rather than indexing into _params directly.
    # These are module-level constants of genesispy.unique_module, not
    # class attributes: import as unique_module.STATE_DEFINED, etc.
    # STATE_DEFINED: str    (module-level)
    # STATE_OVERRIDDEN: str (module-level)
    # STATE_FORCED: str     (module-level)

    # construction
    def __init__(self, manager: "Manager") -> None: ...
    @classmethod
    def _new_as_son(cls, parent: "UniqueModule") -> "UniqueModule": ...
    @classmethod
    def _new_as_clone(cls, src: "UniqueModule",
                      parent: "UniqueModule") -> "UniqueModule": ...

    # Source instance for clones; None on non-clones. Set by
    # _new_as_clone, read by ConfigHandler.extract_stats to emit
    # CloneOf.InstancePath in --json-out snapshots.
    _clone_of: "UniqueModule | None"

    # parameters
    def define_param(self, name: str, default=None, **flags) -> None: ...
    # parameter(): Perl-compat kwargs (UniqueModule.pm:1981) — force/doc
    # plus min/max/step XOR list (range guard) plus opt store-only.
    # Range checked at register-time AND on every subsequent override.
    #
    # Range combination rules (mirrors Perl UniqueModule.pm:621-670):
    #   - min/max/step and list are mutually exclusive.
    #   - step requires min or max; step == 0 is an error.
    #   - When both min and max are given: min <= max.
    #   - When min, max, and step all given: (max - min) must be an
    #     integer multiple of step.
    # Value rules (Perl:705-723):
    #   - When step and min defined: (value - min) / step must be integer.
    #   - When step and only max defined: (max - value) / step must be integer.
    #
    # Re-defining a range (calling parameter() with range kwargs when a
    # range is already set, or calling param_range() after one is set)
    # raises ParameterError: "Re-definition of range for parameter ...".
    def parameter(
        self, name: str, default=None, *,
        force: bool = False,
        doc: str | None = None,
        min: object = None,
        max: object = None,
        step: object = None,
        list: object = None,
        opt: str | None = None,
    ) -> object: ...
    # Late-bind documentation / range; mirror older Perl APIs.
    # param_range() enforces the same combination and value rules as
    # parameter() above. Re-definition raises ParameterError.
    def doc_param(self, name: str, msg: str) -> None: ...
    def param_range(
        self, name: str, *,
        min: object = None, max: object = None,
        step: object = None, list_: object = None,
    ) -> None: ...
    def get_param(self, name: str) -> object: ...
    def override_param(self, name: str, value: object) -> None: ...

    # hierarchy. module_cls accepts a class OR a registered module name
    # string (resolved via Manager.resolve_module_class).
    # All four instantiation entry points (unique_inst, unique_inst_param,
    # clone_inst, ununique_inst) raise ElaborationError if inst_name (or
    # new_name for clone_inst) is already registered under self, mirroring
    # Perl UniqueModule.pm:1158.  On execute() failure the failed entry is
    # removed from _sub_instances so the same name can be retried.
    def unique_inst(self, module_cls: type | str, inst_name: str,
                    **params) -> "UniqueModule": ...
    # unique_inst_param emits the module under a name that encodes the
    # resolved parameters: <Base>_<KEY>_<VAL>[_<KEY>_<VAL>...], keys in
    # sorted order (mirrors Perl _${abbrev}_${val}, UniqueModule.pm:2718).
    # Non-word values fall back to <KEY>_<8-hex-digest>.
    # When the instance sits on a scoped-override path, appends _unqN.
    def unique_inst_param(self, module_cls: type | str, inst_name: str,
                          **params) -> "UniqueModule": ...
    def clone_inst(self, src_inst: "UniqueModule",
                   new_name: str) -> "UniqueModule": ...
    # ununique_inst preserves the bare base name on first call (no `_unqN`).
    # Second call for the same base name:
    #   - identical resolved params AND identical scoped-subtree signature
    #     -> aliases the previous instance under the new inst_name (Perl
    #     UnUniquifiedModules parity);
    #   - differing params, same subtree signature -> raises ElaborationError;
    #   - differing subtree signatures -> re-elaborates under a temp name and
    #     compares the generated body (blank lines and comments ignored)
    #     against the previous UN-uniquified generation (Perl
    #     UniqueModule.pm:1674): identical bodies reuse the previous file,
    #     divergence raises ElaborationError.
    # Tracked via cache.UNUNIQUE_REGISTRY.
    def ununique_inst(self, module_cls: type | str, inst_name: str,
                      **params) -> "UniqueModule": ...
    def synonym(self, name: str) -> None: ...

    # Forced override (pinned, cannot be re-overridden by parameter()).
    def force_param(self, name: str, value: object) -> None: ...
    # {name: value} for all parameters (Perl get_mod_param_list, :2691).
    def get_mod_param_list(self) -> dict[str, object]: ...
    # Perl-compat accessors (UniqueModule.pm:496/:550/:515).
    def exists_param(self, name: str) -> bool: ...
    def get_top_param(self, name: str) -> object: ...
    def list_params(self) -> list[str]: ...  # sorted names, distinct from get_mod_param_list

    # Perl-compat shortcuts (UniqueModule.pm:1846+).
    def generate(self, module_cls, inst_name: str,
                 **params) -> "UniqueModule": ...
    def generate_w_name(self, base_module_name: str,
                        gen_module_name: str,
                        inst_name: str, **params) -> "UniqueModule": ...

    # name/path
    def get_module_name(self) -> str: ...
    def get_unique_module_name(self) -> str: ...
    def get_instance_name(self) -> str: ...
    def get_instance_path(self) -> str: ...
    def get_parent(self) -> "UniqueModule | None": ...
    def get_top(self) -> "UniqueModule": ...
    # Shallow copy of synonym names registered via synonym(); read-only
    # accessor for tests instead of touching ``_synonyms`` directly.
    def get_synonyms(self) -> list[str]: ...

    # Product-list DFS for synth/verif partitioning (Manager.flush_outputs
    # walks this to populate cache.OUTFILE_TAGS and cache.OUTFILE_ORDER).
    # ``synth_top`` is the **dotted** instance path bounding the synth cone;
    # None matches Perl SynthTop=undef -> every (inst, is_synth) pair has
    # is_synth=False.  The walk order is the single source of truth for all
    # product-list ordering (vlist, vf, synth-side, verif-side).
    # Mirrors UniqueModule.pm::_get_prod_list_insts.
    def get_prod_list_insts(
        self, synth_top: str | None,
    ) -> list[tuple["UniqueModule", bool]]: ...

    # Genesis2 short-name properties. Each returns a StrCallable (str
    # subclass whose __call__ returns self) so both ``obj.mname`` and
    # ``obj.mname()`` work uniformly, matching Perl's ``$obj->mname()``
    # and bare ``mname`` usage. StrCallable preserves str semantics for
    # comparison, concatenation, f-strings, json.dumps, etc.
    mname: "StrCallable"  # unique module name
    iname: "StrCallable"  # instance name
    bname: "StrCallable"  # base module name
    sname: "StrCallable"  # source template name: _synonym_for if class was built
                          # via Manager.synonym_class, else bname (mirrors Perl
                          # get_source_name; UniqueModule.pm:377)

    # Sub-instance navigation (Perl UniqueModule.pm:760/780/797/932/1087).
    def get_subinst(self, name: str) -> "UniqueModule": ...
    def exists_subinst(self, name: str) -> bool: ...
    def get_subinst_array(self, pattern: str = "") -> list["UniqueModule"]: ...
    def get_instance_obj(
        self, inst: "str | UniqueModule"
    ) -> "UniqueModule": ...
    # DFS hierarchy walker with regex/predicate filters. Kwarg names are
    # snake_case (Perl wiki uses CamelCase: PathRegex, INameRegex,
    # MNameRegex, BNameRegex, SNameRegex, HasParamRegex, ApplyMap,
    # From/Depth/Reverse); rename on port.
    def search_subinst(
        self, *,
        start_from: "UniqueModule | str | None" = None,
        depth: int = 10000,
        reverse: bool = False,
        path_regex: str | None = None,
        iname_regex: str | None = None,
        mname_regex: str | None = None,
        bname_regex: str | None = None,
        sname_regex: str | None = None,
        has_param_regex: "str | list[str] | None" = None,
        apply_map: object = None,
    ) -> list["UniqueModule"]: ...

    # Diagnostics (Perl UniqueModule.pm:2803/:2863). Both bare-name
    # error/warning in .vpy bodies AND self.error/self.warning prefix
    # the user's message with `<module>@<instance-path>:` before
    # delegating to reporting.error / reporting.warning.
    def error(self, msg: str) -> None: ...
    def warning(self, msg: str) -> None: ...
    # pprint-based debug serialiser (Perl UniqueModule.pm:2911).
    # Self-method only; no bare-name alias.
    def to_string(self, *args: object) -> str: ...

    # emission
    def emit(self, text: str) -> None: ...
    def instantiate(self, **ports: object) -> str: ...
    def to_verilog(self, infile: str | None = None) -> None: ...
    # Runs child.execute() with user_config.context bound to the child, so
    # include() and other bare-name helpers inside a sub-instance body resolve
    # self to the child (not the parent). Used by unique_inst /
    # unique_inst_param / ununique_inst. Mirrors the top-level
    # user_config.context() wrap in Manager.gen_verilog.
    def _execute_child(self, child: "UniqueModule") -> None: ...
    def execute(self) -> None: ...
    # Called by template/emitter._FOOTER after the user body runs to
    # finalise the buffer into cache.OUTFILE_CONTENT_CACHE under
    # _unique_module_name and every registered synonym. Plain subclasses
    # rely on execute() to call this; generated subclasses re-flush in
    # the footer to overwrite the base-class banner with body content.
    def _flush_outfile(self) -> None: ...

```

## genesispy.template.parser

```python
def parse_vpy(
    path: str,
    allowed: Iterable[str] | None = None,
    *,
    syntax: str = "genesis",
    comment: str = "//",
) -> str:
    """Parse a template file and return Python source text.

    ``allowed`` is the set of accepted input extensions (e.g. the keys of
    ``Manager.extension_map``); defaults to the built-in
    ``DEFAULT_EXTENSION_MAP`` keys (``.vpy``, ``.svpy``). Raises
    ParseError on .vp/.svp legacy extensions and on any extension not in
    ``allowed``.

    ``syntax`` selects the directive flavour:

    * ``"genesis"`` (default): ``//; stmt`` lines and ``\`expr\``` inline.
    * ``"j2"``: Jinja2-*like* flavour. ``{% stmt %}`` lines,
      ``{{ expr }}`` inline, ``{# comment #}`` stripped. Shares the
      delimiter set with the canonical Jinja2 library, but the
      embedded language is full Python (no filter pipes, no
      ``is``-tests, no macros, no ``extends``/``block``/``include``
      etc.). Whitespace modifiers ``{%-``/``-%}``/``{{-``/``-}}`` are
      accepted as a syntactic no-op. All three forms may span multiple
      physical lines; tracebacks land on the opener line.

    ``comment`` is the line-comment prefix of the source/target language
    (default ``"//"``, set per-run by ``--source-comment`` on both
    ``genesispy`` and ``gvpy``; deprecated ``--comment`` alias also accepted).
    In genesis flavour it determines the directive sentinel: ``<comment>;``
    lines are treated as Python; the default ``"//"`` keeps the historical
    ``//;`` behaviour. j2 flavour is unaffected. Fed from
    ``Manager.source_comment`` / ``_GvpyManager.source_comment``.

    Indent rules, block-opener detection (trailing ``:``), and the
    ``# line N "path"`` traceback directives are identical across
    flavours. Block close: genesis mode uses the lower-indent +
    sentinel-comment convention (``//; # endfor`` / ``# endif`` /
    ``# endwhile``). j2 mode accepts both the bare keyword form
    (``{% endfor %}`` / ``{% endif %}`` / ``{% endwhile %}``, matching
    the upstream Jinja2 spelling) and the sentinel-comment form
    (``{% # endfor %}`` etc., for symmetry with genesis mode). Both
    forms pop the same parser-side block stack, so an unmatched close
    raises ``ParseError("without matching opener")`` regardless of
    spelling. Selected per run by ``--j2`` on both ``genesispy`` and
    ``gvpy``; reflected in ``Manager.syntax`` / ``_GvpyManager.syntax``.
    """
```

## genesispy.template.emitter

```python
def write_module(
    vpy_path: str,
    output_dir: str,
    *,
    output_suffix: str = ".v",
    allowed: Iterable[str] | None = None,
    syntax: str = "genesis",
    comment: str = "//",
) -> str:
    """Forward ``syntax`` and ``comment`` to ``parse_vpy``; otherwise unchanged."""
```

## genesispy.template.runtime

Helpers used by generated module code:

```python
# Available in the exec namespace of generated modules
self  : UniqueModule            # the current instance

# Genesis2 short-name aliases (StrCallable: works as `mname` or `mname()`)
# Bound by both the emitter prelude AND user_config._include's exec namespace
# via genesispy.template.aliases.alias_dict / alias_prelude_source.
mname, iname, bname, sname

# Perl-compat bare-name aliases bound at the top of every execute()
# (also injected into user_config._include()'s exec namespace).
# Canonical table: genesispy.template.aliases.SIMPLE_ALIASES.
parameter, define_param, doc_param, param_range, instantiate, emit
exists_param, get_top_param, list_params
error, warning          # route to self.error / self.warning (UniqueModule.pm:2803/:2863)
get_subinst, exists_subinst, get_subinst_array
get_instance_obj, search_subinst
synonym                 # arity dispatcher:
                        #   synonym(name)      -> self.synonym(name)   (outfile mirror)
                        #   synonym(src, trgt) -> Manager.synonym_class(src, trgt)
                        #                                              (class rename, Perl semantics)
unique_inst, unique_inst_param, clone_inst, ununique_inst
generate                # dispatches via cfg_handler.unq_style
generate_unq_numeric    # alias for unique_inst
generate_unq_param      # alias for unique_inst_param
generate_base           # alias for ununique_inst
generate_w_name         # synonym_class + ununique_inst
clone                   # alias for clone_inst
include                 # user_config._include (Perl-style //;include(...))
pinclude                # gvpy-only; None outside gvpy contexts
```

These are plain Python locals: a user `.vpy` may rebind them (e.g. `parameter = ...`) and standard Python
scoping wins.

`user_config._include` builds that namespace fresh for each included file -- `self`, the aliases above,
`__file__`, `__name__`, `__builtins__` -- and discards it after `exec`. The caller's `execute()` locals
are not visible to the included body, and names the body binds are not returned to the caller. `self` is
the only channel between the two. Demos pass arguments as a `self.include_params` dict; that attribute is
a user-level convention, not framework state (nothing in `src/` reads, writes, or clears it).

`gvpy_cli._install_pinclude` does the same for `pinclude`, with a narrower namespace: `self`, `emit`,
`parameter`, `__file__`, `__name__` and builtins only -- none of the other aliases above.

## genesispy.cache

Process-wide singletons backing elaboration dedup and outfile flushing.
Reset between runs by ``clear_all()`` (test-only). Every ``UniqueModule``
instance shares this state -- the module is intentionally global to mirror
Perl's ``shared-ref`` UniqueModule.pm globals.

```python
# Dedup-signature -> elaborated instance, plus instance-name -> instance.
# Keys live in two disjoint namespaces partitioned by the `::` separator:
#   "<base>::<sha256>[::sub::<sha256>]"        pre-elaboration param key (unique_inst)
#   "<base>::post::<sha256>[::sub::<sha256>]"  post-elaboration full-param key
#   "<base>::param::<sha256>[::sub::<sha256>]" parametric form (unique_inst_param)
# The optional `::sub::` tail (unique_module._subtree_tag) folds the
# scoped-subtree override signature into the key: instances whose
# descendants carry different scoped CLI overrides get separate entries.
# unique_inst_param additionally appends `_unqN` to the emitted module
# *name* when that tail is non-empty (Perl gen_override_path_ext parity,
# UniqueModule.pm:1431).
# Plain instance identifiers (`<base>_unqN`, user synonyms) MUST NOT
# contain `::`; cache.register asserts this so a future synonym name can
# never collide with a dedup signature.
MODULE_CACHE: _JournaledDict          # _JournaledDict <: dict

# Base-class-name -> next derivative counter (drives `Foo_unq1`, `Foo_unq2`
# for unique_inst, and for unique_inst_param names on override paths).
# Namespaced keys like `<base>::ununq_tmp` number ununique_inst's temp
# re-elaborations. Advanced via cache.next_derivation. Best-effort
# contiguous; post-elaboration dedup may leave gaps when a rollback fires.
MODULE_NAME_NUM_DERIVS: Dict[str, int]

# Filename -> emitted Verilog text. Flushed by output_writer.flush_to_disk.
OUTFILE_CONTENT_CACHE: _JournaledDict # _JournaledDict <: dict

# Base-name -> {"instance": UniqueModule, "params": dict[str, Any],
# "subtree_sig": tuple}. Tracks `ununique_inst` calls; a second call with
# the same base name aliases the previous instance (identical resolved
# params and subtree signature), raises (different params), or
# re-elaborates and compares generated bodies (different subtree
# signatures; divergence raises). Global scope, not per-parent, because
# the on-disk filename is global. Mirrors Perl UnUniquifiedModules +
# does_generate_same + compare_generated_files.
UNUNIQUE_REGISTRY: Dict[str, Dict[str, Any]]

# Filename -> 'synth' | 'verif' | 'synth_and_verif'. Built by Manager
# before flush from a path-based DFS over the elaborated instance tree.
# Empty when synth_top is None -> output_writer treats unmapped files as
# 'verif'. Mirrors Perl Manager.pm:1330-1395.
OUTFILE_TAGS: Dict[str, str]

# Output filenames in DFS first-seen walk order, populated by Manager
# _populate_outfile_tags alongside OUTFILE_TAGS. output_writer iterates
# this order when writing all product lists so every list (vlist, vf,
# synth-side, verif-side) uses a single consistent DFS ordering.
# Cache keys absent here (test-only raw entries) follow alphabetically
# after all ordered entries. Cleared by clear_all().
OUTFILE_ORDER: List[str]

# Resolved paths of include()'d template files, appended by
# user_config._include. Consumed together with Manager.parsed_source_files
# by output_writer.write_file_lists as the `.depend` prerequisite list.
# Append order; deduped at read time. Cleared by clear_all().
INCLUDED_FILES: List[str]


def clear_all() -> None: ...
def next_derivation(base_name: str) -> int: ...
def register(unique_name: str, instance: "UniqueModule") -> None: ...
    # Re-registering the same instance is a silent no-op. Re-registering
    # a *different* instance under an existing name emits a one-line
    # stderr warning and overwrites. `::` in unique_name raises ValueError.

@contextmanager
def journaled() -> Iterator[Tuple[Dict, Dict]]: ...
    # Capture first-touch writes to MODULE_CACHE and OUTFILE_CONTENT_CACHE
    # inside the block. Yields (mc_journal, oc_journal) for rollback_journal.
    # Nests; each scope tracks its own first-touch set. Used by
    # UniqueModule.unique_inst to discard a post-key dedup hit's writes.

def rollback_journal(mc_j: Dict, oc_j: Dict) -> None: ...
```

Only ``__setitem__`` / ``__delitem__`` on the journaled dicts are journaled;
``.clear()`` (test-only via ``clear_all``) bypasses journaling on purpose.
No call site uses ``.update()`` / ``.pop()`` / ``.popitem()`` while a journal
is active -- add overrides on ``_JournaledDict`` if that changes.

## genesispy.hashing

```python
def sha256_param_signature(module_name: str,
                           params: dict[str, object]) -> str:
    """Canonical-JSON SHA-256 hex digest, stable across Python runs."""
```

## genesispy.tools.jinja2j2

Stand-alone helper, not used by the elaboration core. Ports a stock-Jinja2
template to genesispy's ``--j2`` dialect (Jinja2-style delimiters with
full-Python embedded language). Requires the optional ``jinja2`` dependency
(``pip install 'genesispy[import-j2]'``); a missing import raises a clear
error at CLI start. Uses Jinja2's own parser to handle filter pipelines
and ``is``-tests. Block openers gain a trailing ``:``;
filters and tests are translated to Python via fixed mapping tables;
``{% set N = E %}`` becomes ``{% N = PY(E) %}``; ``{% include "f" %}``
becomes ``{% include("f") %}``. Macros, blocks, ``extends``, ``import``,
``raw``, custom filters, and complex ``include`` forms are unmappable;
``--strict`` (default) errors on the first such construct,
``--best-effort`` emits ``{# TODO(genesispy-jinja2j2): ... #}`` placeholders
and warns. Top-level ``{# ... #}`` comments pass through verbatim;
comments inside ``{% %}`` / ``{{ }}`` are not preserved (Jinja2's parser
strips them).

```python
@dataclass
class Issue:
    line: int
    col: int
    reason: str

def convert(source: str, *, strict: bool = True) -> tuple[str, list[Issue]]:
    """Port `source` (stock Jinja2) to genesispy-j2.

    On strict=True, raises tools.jinja2j2._Unmappable on the first
    construct with no clean equivalent. On strict=False, emits TODO
    comments and returns collected Issue records for the caller to
    display. The companion CLI is `genesispy-jinja2j2` (entry point:
    `tools.jinja2j2.main`)."""
```

