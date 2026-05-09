# genesispy -- code interfaces

Canonical contracts for the package in `genesispy/src/genesispy/`. These signatures are the load-bearing
contract between modules; coordinate before changing them.

## genesispy.errors

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

# `cls=` lets the call site preserve subclass discrimination at the
# raise; default is GenesisPyError. fatal=False prints and returns.
def error(msg: str, *, fatal: bool = True, cls: type = GenesisPyError) -> None: ...
def warning(msg: str) -> None: ...
# Open `path` as the `--log` sink; subsequent error()/warning() calls
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
    sources_path: list[str]
    includes_path: list[str]
    output_dir: str
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
    # tagged 'verif'. Set from --synthtop.
    synth_top: str | None
    # Every directory touched during elaboration: appended to by
    # find_file() and _resolve_cfg_path(); consumed by
    # output_writer.write_pathfile (the --pathfile output). Plain list
    # of absolute directory paths in append order, deduped at read time.
    touched_dirs: list[str]
    # Search path for `.cfg` config files; consumed by
    # output_writer.write_pathfile alongside sources_path /
    # includes_path. Set from --cfgpath.
    cfg_path: list[str]
    # Flavor override for emitted Verilog ('synth', 'verif', or None for
    # auto). Read by output_writer when tagging files. Set from --flavor.
    flavor: str | None
    # If True, also write raw (pre-flavor-tagging) Verilog under raw_dir.
    # Set from --gen-raw.
    gen_raw: bool
    # Override path for the `.depend` file; None falls back to
    # output_dir/<top>.depend. Set from --depend.
    depend_file: str | None
    # Disable post-elaboration MODULE_CACHE dedup. Set from
    # --no-module-cache. Read by unique_module.unique_inst[_param].
    no_module_cache: bool
    # Original argparse.Namespace as parsed by cli.parse_args(). Engine
    # classes (ConfigHandler) read late-bound flags directly off this
    # (e.g. args.unqstyle, args.parameter).
    args: "argparse.Namespace"

    def __init__(self, args: argparse.Namespace) -> None: ...
    def find_file(self, name: str, paths: list[str] | None = None) -> str: ...
    def execute(self) -> int: ...

    # CLI orchestration entry points (also called directly by tests).
    def parse_files(self) -> None: ...
    def load_top_module(self) -> type: ...
    def gen_verilog(self) -> None: ...
    def flush_outputs(self) -> None: ...
    def clean(self) -> None: ...

    # Look up a generated module class by name (string form is what
    # user .vpy code passes to unique_inst / ununique_inst).
    def resolve_module_class(self, name: str) -> type: ...

    # Class-level synonym (mirrors Perl `synonym(src, target)`):
    # registers `target_name` as a dynamic subclass of `src_name`'s
    # generated class, so resolve_module_class(target_name) returns it
    # and ununique_inst derives unique names from `target_name`.
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
    # ``path`` (full), ``small_<basename>`` (no ImmutableParameters),
    # ``tiny_<basename>`` (priority >= EXTERNAL_XML only). ``top_inst``
    # is required; passing None raises GenesisPyError.
    def write_json(self, path: str, top_inst: "UniqueModule") -> None: ...

    # Legacy name; underlying store is JSON-only. Returns None for absence
    # OR for an explicit null value; use exists_configuration to
    # disambiguate.
    def get_xml_param_val(self, name: str) -> object | None: ...
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
    # reflects EXTERNAL_XML / EXTERNAL_CONFIG / CMD_LINE rather than
    # the declaration default (drives the --jsonout tiny variant).
    def get_configuration_with_priority(
        self, name: str, *, instance_path: tuple[str, ...] | None = None,
    ) -> tuple[object | None, int | None]: ...

    # Module uniquification style ('numeric' | 'param'); read by
    # UniqueModule.generate to dispatch unique_inst vs unique_inst_param.
    unq_style: str  # default 'numeric', from --unqstyle CLI flag
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
    STATE_DEFINED:    str
    STATE_OVERRIDDEN: str
    STATE_FORCED:     str

    # construction
    def __init__(self, manager: "Manager") -> None: ...
    @classmethod
    def _new_as_son(cls, parent: "UniqueModule") -> "UniqueModule": ...
    @classmethod
    def _new_as_clone(cls, src: "UniqueModule",
                      parent: "UniqueModule") -> "UniqueModule": ...

    # Source instance for clones; None on non-clones. Set by
    # _new_as_clone, read by ConfigHandler.extract_stats to emit
    # CloneOf.InstancePath in --jsonout snapshots.
    _clone_of: "UniqueModule | None"

    # parameters
    def define_param(self, name: str, default=None, **flags) -> None: ...
    def parameter(self, name: str, default=None) -> object: ...
    def get_param(self, name: str) -> object: ...
    def override_param(self, name: str, value: object) -> None: ...

    # hierarchy. module_cls accepts a class OR a registered module name
    # string (resolved via Manager.resolve_module_class).
    def unique_inst(self, module_cls: type | str, inst_name: str,
                    **params) -> "UniqueModule": ...
    def unique_inst_param(self, module_cls: type | str, inst_name: str,
                          **params) -> "UniqueModule": ...
    def clone_inst(self, src_inst: "UniqueModule",
                   new_name: str) -> "UniqueModule": ...
    def ununique_inst(self, module_cls: type | str, inst_name: str,
                      **params) -> "UniqueModule": ...
    def synonym(self, name: str) -> None: ...

    # Forced override (pinned, cannot be re-overridden by parameter()).
    def force_param(self, name: str, value: object) -> None: ...
    # {name: value} for all parameters (Perl get_mod_param_list, :2691).
    def get_mod_param_list(self) -> dict[str, object]: ...

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
    # walks this to populate cache.OUTFILE_TAGS).  ``synth_top`` is the
    # **dotted** instance path bounding the synth cone; None matches Perl
    # SynthTop=undef -> every (inst, is_synth) pair has is_synth=False.
    # Mirrors UniqueModule.pm::_get_prod_list_insts.
    def get_prod_list_insts(
        self, synth_top: str | None,
    ) -> list[tuple["UniqueModule", bool]]: ...

    # Genesis2 short-name properties (str values; the StrCallable
    # variants in the generated-module exec namespace wrap these).
    mname: str  # unique module name
    iname: str  # instance name
    bname: str  # base module name
    sname: str  # synthesis top name (== unique module name)

    # emission
    def emit(self, text: str) -> None: ...
    def instantiate(self, **ports: object) -> str: ...
    def to_verilog(self, infile: str | None = None) -> None: ...
    def execute(self) -> None: ...
    # Called by template/emitter._FOOTER after the user body runs to
    # finalise the buffer into cache.OUTFILE_CONTENT_CACHE under
    # _unique_module_name and every registered synonym. Plain subclasses
    # rely on execute() to call this; generated subclasses re-flush in
    # the footer to overwrite the base-class banner with body content.
    def _flush_outfile(self) -> None: ...

    # API-parity stub; base-module resolution actually goes through
    # normal Python import. No-op kept for Perl ``load_base_module``.
    def load_base_module(self, name: str) -> None: ...
```

## genesispy.template.parser

```python
def parse_vpy(
    path: str, allowed: Iterable[str] | None = None
) -> str:
    """Parse a template file and return Python source text.

    ``allowed`` is the set of accepted input extensions (e.g. the keys of
    ``Manager.extension_map``); defaults to the built-in
    ``DEFAULT_EXTENSION_MAP`` keys (``.vpy``, ``.svpy``). Raises
    ParseError on .vp/.svp legacy extensions and on any extension not in
    ``allowed``.
    """
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
parameter, define_param, synonym, instantiate, emit
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

## genesispy.hashing

```python
def sha256_param_signature(module_name: str,
                           params: dict[str, object]) -> str:
    """Canonical-JSON SHA-256 hex digest, stable across Python runs."""
```
