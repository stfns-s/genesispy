# genesispy -- code structure

How the genesispy package fits together: the layering, the pipeline from
`.vpy` template to Verilog on disk, the dedup model, and the main control
flags. Self-contained; signatures and attribute names live in
`interfaces.md` next door. This file does not pin specific signatures --
it points at `interfaces.md` so the two cannot disagree.

## 1. Purpose and scope

genesispy is a Python port of [Genesis2](https://github.com/StanfordVLSI/Genesis2). It parses templated
Verilog (`.vpy` / `.svpy`) into Python module files, imports those generated modules, executes them against an
elaboration runtime, and emits Verilog into `genesis_synth/` and `genesis_verif/`. Parameter values come from
JSON, trusted-input `.cfg` files, and explicit `unique_inst(...)` overrides; identical parameterisations are
deduplicated so the same module body is emitted once.

Covers: package layering, the orchestrator's order of operations, the
lifecycle of a single `.vpy` file, the dedup cache, and the top-level
flags. Does **not** cover the user-facing template language
(`user-guide.md`), run instructions (`README.md`), or the module-boundary
interfaces (`interfaces.md`).

## 2. Layered view

Three layers with a one-way dependency: frontend imports engine, engine
never imports frontend.

**CLI / orchestration**
- `cli.py` -- argparse, listfile expansion, entry point.
- `gvpy_cli.py` -- alternate flat-preprocessor CLI (see section 9).
- `manager.py` -- `Manager` class; owns the run, resolves paths, drives the parse -> elaborate -> flush
  sequence.

**Frontend (`.vpy` -> Python) -- `template/` package**
- `template/parser.py` -- `.vpy` state machine: `//;` Python lines, backtick interpolation, indent inference,
  plain-Verilog passthrough via `emit(...)`.
- `template/emitter.py` -- wraps the parsed body in a generated Python module (`class X(UniqueModule,
  UserMixin): def execute(self): ...`), binds the Genesis2 bare-name aliases (`parameter`, `instantiate`,
  `emit`, `unique_inst`, `generate*`, ...) as locals, writes the result into `raw_dir`, registers a line map
  for traceback remapping.
- `template/runtime.py` -- re-exports `UniqueModule` and `UserMixin` so generated files import from a single
  path; defines `StrCallable` (so `` `mname` `` and `` `mname()` `` both work) and the line-map registry used
  by `remap_traceback`.
- `template/aliases.py` -- the single source of truth for the Genesis2 bare-name alias table
  (`SIMPLE_ALIASES`, `EXPECTED_ALIAS_KEYS`, `alias_dict`, `alias_prelude_source`), consumed by both the
  emitter prelude and `user_config._include`.

**Elaboration engine**
- `unique_module.py` -- `UniqueModule` class: parameter resolution (`define_param`, `parameter`,
  `override_param`, `force_param`), hierarchy (`unique_inst`, `unique_inst_param`, `clone_inst`,
  `ununique_inst`, `synonym`, `generate*`, `generate_w_name`), Verilog emission (`emit`, `instantiate`,
  `execute`).
- `user_lib.py` -- `UserMixin` facade for user-visible helpers.
- `user_config.py` -- `include()` + `context(manager, top)` runtime context.
- `cache.py` -- process-wide singletons (section 5).
- `hashing.py` -- canonical-JSON SHA-256 parameter signatures.
- `config_handler.py` -- JSON/`.cfg` parameter store.
- `json_io.py` -- concrete loader/writer behind `ConfigHandler`.
- `extensions.py` -- `DEFAULT_EXTENSION_MAP` and `build_extension_map` (the `--extension` / `-sv` merge).
- `_scalars.py` -- scalar coercion shared by the config loaders.
- `output_writer.py` -- flush cache to disk, write `.vlist` / `.depend` / `genesispy_clean.sh`.
- `reporting.py` -- exception hierarchy and `error()` / `warning()` reporters.

**Standalone tools (`tools/`)** -- none are used by the elaboration core; each backs a `bin/` entry point.
- `tools/xml_json.py` + `tools/xml2json.py` + `tools/json2xml.py` -- XML/JSON config conversion, invoked by
  `bin/genesispy-xml2json` / `bin/genesispy-json2xml`.
- `tools/vp2vpy.py` + `tools/vp2vpy_map.py` + `tools/vp2vpy_helper.pl` -- the `.vp`/`.vph` -> `.vpy`
  translator behind `bin/genesispy-vp2vpy` (the helper is a Perl/PPI subprocess).
- `tools/jinja2j2.py` -- stock-Jinja2 -> j2 template porter behind `genesispy-jinja2j2`; needs the optional
  `jinja2` dependency.

The `template/` directory is a separate package because its job is the
input-syntax frontend: a different input language (Jinja, native Python,
a different HDL target) would replace `template/parser.py` and adjust the
emitter without touching the engine.

## 3. End-to-end pipeline

```
   .vpy / .svpy sources                JSON / .cfg params
          │                                       │
          ▼                                       ▼
   template.parser.parse_vpy            config_handler.ConfigHandler
          │                                       │
          ▼                                       │
   template.emitter.write_module                  │
          │  (writes raw_dir/<stem>.py)           │
          ▼                                       │
   importlib → generated module class             │
          │                                       │
          ▼                                       │
   Manager.gen_verilog                            │
    ├─ top = TopModule(manager) ──────────────────┘
    ├─ user_config.context(manager, top)
    └─ top.execute()
          │   (recursive: unique_inst → child.execute())
          │
          ├─► cache.MODULE_CACHE              (dedup, two-stage)
          ├─► cache.MODULE_NAME_NUM_DERIVS    (suffix counter)
          └─► cache.OUTFILE_CONTENT_CACHE     (filename → Verilog text)
                       │
                       ▼
          output_writer.flush_to_disk
                       │
                       ▼
   genesis_synth/   genesis_verif/   .vlist   .depend   genesispy_clean.sh
```

Stage by stage:

**Argument parsing & listfile expansion.** `cli.parse_args` builds the GNU flag set; `cli._expand_listfiles`
recursively expands `--input-list FILE` files containing `--input` / `--input-list` / `--src-path` /
`--inc-path` directives (bare paths default to `--input`).

**Manager construction.** `Manager.__init__` resolves `raw_dir` (`./genesis_raw` by default; relocated under a
`/tmp/genesispy_*` scratch with `--use-tmp`), applies user `--py-path` / `--py-import`, builds
`extension_map` from `extensions.build_extension_map` (defaults `.vpy=.v`, `.svpy=.sv`; extended by
`--extension`, and by `-sv`/`--system-verilog` as shorthand for `.vpy=.sv`), and prepares the yet-unbuilt
`cfg_handler`. There is no single run-wide output suffix: `Manager._output_suffix_for(path)` looks the
suffix up per input, and the emitter stamps the result on each generated class as `_OUTPUT_SUFFIX`.

**Parse phase.** `Manager.parse_files` iterates the input list and calls `emitter.write_module(path, raw_dir)`
for each; the emitter parses the `.vpy`, wraps it in a class deriving from `UniqueModule` + `UserMixin`,
writes `<raw_dir>/<stem>.py`, and registers a generated-line -> `.vpy`-line map. Skipped under
`--gen-only` (which calls `Manager._discover_generated_modules` instead, expecting `.py` files already
present in `raw_dir`). Terminal under `--parse-only`.

**Elaboration phase.** `Manager.gen_verilog` builds the `cfg_handler` (reads any `--json-cfg` / `--cfg` /
`--parameter` overrides), imports the generated `.py` for the top module via `Manager.load_top_module`,
instantiates it (`top = TopModule(manager)`), enters `user_config.context(manager, top)`, and calls
`top.execute()`. Recursion happens inside `execute()`: each `unique_inst` / `instantiate` / `generate*` call
resolves another generated class (`Manager.resolve_module_class` loads on demand), constructs a child
`UniqueModule`, and runs its `execute()`.

**Emission & caching.** Each `UniqueModule` instance has a private `_outfile_handle` populated by `emit(...)`
calls. After the body finishes, the footer in `template/emitter.py` calls `UniqueModule._flush_outfile()`,
which copies the buffer into `cache.OUTFILE_CONTENT_CACHE[<unique_module_name><output_suffix>]` and mirrors it
under every registered synonym name (from `clone_inst` / `synonym`).

**Flush phase.** `Manager.flush_outputs` calls into `output_writer`: `flush_to_disk` walks
`OUTFILE_CONTENT_CACHE`, splits each file into `genesis_synth/` or `genesis_verif/` according to
`cache.OUTFILE_TAGS` (populated by Manager before flush from a path-based DFS over the elaborated instance
tree; untagged files default to `verif`, filterable with `--out-type synth|verif|both`), and writes only
when content differs from disk. Then
`write_file_lists` emits `.vlist` and `.depend`, `write_clean_script` emits `genesispy_clean.sh`, optional
`write_product_lists` and `write_pathfile` handle `--product` and `--path`. With `--stdout` the cache is
concatenated to stdout instead and the list/clean-script writers are skipped. Resolved configuration is
optionally dumped via `cfg_handler.write_json` when `--json-out` is set.

**Clean.** `Manager.clean` (driven by `--clean`) calls `output_writer.clean_outputs` and removes `raw_dir`. It
runs as a short-circuit before parsing -- `--clean` exits before any `.vpy` is touched.

## 4. Frontend in detail (`template/`)

The frontend is the only place that knows the `.vpy` input syntax. Four files:

- **`parser.py`** translates one `.vpy` source to a column-zero Python string: `//;` lines become bare Python
  at indent `(leading_spaces // 4)`; plain Verilog lines become `emit(...)` calls whose indent follows the
  controlling `//;` block; backtick interpolations become attribute references on `self`. Block ends are
  explicit sentinels (`# endfor`, `# endif`, `# endwhile`); the parser has no other way to detect block end.

  `parse_vpy(syntax=...)` selects one of two directive flavours over the same downstream machinery. The
  default `"genesis"` is the syntax above. `"j2"` (`_parse_vpy_j2`, selected by `--j2` on both `genesispy`
  and `gvpy`) swaps the delimiters for `{% stmt %}`, `{{ expr }}` and `{# comment #}`, and additionally
  accepts the bare `{% endfor %}` block-close spelling; the embedded language is still full Python, and
  indent inference, line mapping and `emit(...)` generation are shared. `parse_vpy(comment=...)`
  independently sets the genesis-flavour directive sentinel (`--source-comment`), so a non-Verilog target
  language can use `#;` in place of `//;`.
- **`emitter.py`** wraps that body in a complete Python file: the `_HEADER` block declares the class, calls
  `super().execute()`, and binds bare-name aliases as locals so user code can write `parameter(...)` instead
  of `self.parameter(...)`. The `_FOOTER` block flushes the per-instance buffer into
  `cache.OUTFILE_CONTENT_CACHE` and mirrors synonyms.
- **`runtime.py`** is the import target for generated files. It re-exports `UniqueModule` and `UserMixin` (so
  generated files have a single import path), defines `StrCallable` (a `str` subclass whose `__call__` returns
  self, so `` `mname` `` and `` `mname()` `` both produce the same name), and owns the `LINE_MAP` registry
  plus `build_line_map` / `remap_traceback` which rewrite `File "<gen>.py", line N` frames back to the `.vpy`
  source for user-visible errors.
- **`aliases.py`** holds the bare-name alias table in one place. `SIMPLE_ALIASES` maps each bare name to the
  `UniqueModule` method it forwards to; `EXPECTED_ALIAS_KEYS` is the full set including the short names,
  `include` and `pinclude`. `alias_prelude_source()` renders the emitter's local-binding prelude and
  `alias_dict(mod)` builds the equivalent namespace for `user_config._include`, so the two paths cannot
  drift apart.

A generated `.py` file is therefore a thin shell: two `import` lines plus the rewritten body. All real work
happens in `unique_module.py` / `user_lib.py` / `cache.py` / `config_handler.py`, reached transitively via
`self.<method>` calls.

## 5. Dedup model

`cache.py` exposes seven module-level singletons, reset between runs by `cache.clear_all()` (test-only):

- `MODULE_CACHE: Dict[str, UniqueModule]` -- `unique_name` -> elaborated instance.
- `MODULE_NAME_NUM_DERIVS: Dict[str, int]` -- base name -> next derivative index (drives `Foo`, `Foo_unq1`,
  `Foo_unq2`, ...); advanced via `cache.next_derivation`.
- `OUTFILE_CONTENT_CACHE: Dict[str, str]` -- emitted filename (`<unique_module_name><suffix>`) -> Verilog
  text. Flushed by `output_writer.flush_to_disk`.
- `UNUNIQUE_REGISTRY: Dict[str, Dict]` -- base name -> ununique_inst call record; deduplication for
  `ununique_inst` / `generate_base`.
- `OUTFILE_TAGS: Dict[str, str]` -- filename -> `'synth' | 'verif' | 'synth_and_verif'`; built by
  Manager before flush from a path-based DFS over the elaborated instance tree.
- `OUTFILE_ORDER: List[str]` -- output filenames in DFS first-seen walk order; used by output_writer
  to emit product lists in a consistent order matching Perl Manager.pm:1330-1395.
- `INCLUDED_FILES: List[str]` -- resolved paths of `include()`'d template files; consumed by
  `output_writer.write_file_lists` as the `.depend` prerequisite list.

Cache keys come from `hashing.sha256_param_signature(module_name, params)` -- canonical-JSON SHA-256 hex
digest, stable across Python runs (see [genesis2-incompatibilities.md](./genesis2-incompatibilities.md) §1
for why this is not bit-equal to Perl `Digest::SHA` over `Data::Dumper`).

`unique_inst` runs a two-stage cache:

- **Pre-key** -- `"<base>::<sha256(explicit_overrides)>"`. Hashed before `execute()` runs; on hit, returns
  the cached instance without re-elaborating.
- **Post-key** -- `"<base>::post::<sha256(resolved_params)>"`. Hashed after `execute()` resolves every
  `parameter(...)` call against the override / ConfigHandler / default ladder. Collapses the case where two
  calls converge on the same final param state -- e.g. `unique_inst(Foo)` and `unique_inst(Foo, N=8)` when
  `Foo`'s body itself sets `parameter('N', 8)`. On a post-key hit, the freshly elaborated child is discarded
  and its `MODULE_CACHE` / `OUTFILE_CONTENT_CACHE` writes are rolled back via the `cache.journaled()` block
  wrapping the call (see [`interfaces.md`](./interfaces.md) `genesispy.cache`). Genesis2 had no
  equivalent post-elaboration dedup (see
  [genesis2-incompatibilities.md](./genesis2-incompatibilities.md) §3 for the parity implication).

Both keys also fold a **scoped-subtree signature**: every `--parameter top.A.B.x=2`-style hierarchical CLI
override rooted at the prospective instance contributes to the dedup hash. Two instances of the same parent
module at different paths therefore stay distinct when their descendants have different scoped overrides,
even before the descendants run. Implementation: `unique_module._scoped_subtree_signature`, mirroring
Perl `UniqueModule.pm:415-440`.

`unique_inst_param` uses a single stage: the cache key is
`"<base>::param::<sha256-of-resolved-params>"` (plus `"::sub::<sha256>"` on scoped-override paths),
so it needs no pre/post split. The resolved name (`Foo_N8_W16`) is the emitted module name, not the key.

Variants:

- `unique_inst` -- numeric suffix, two-stage dedup (above).
- `unique_inst_param` -- single-stage; cache key is `"<base>::param::<sha256>"` (not the resolved name).
- `ununique_inst` / `generate_base` -- emits under the bare base name (no `_unqN`), deduped via
  `cache.UNUNIQUE_REGISTRY`: a second call with the same resolved params and scoped-override subtree
  aliases the first instance; different params raise; a different subtree re-elaborates under a temp
  name and compares the generated bodies (identical -> alias, divergent -> raise).
- `clone_inst` / `synonym` -- registers an alias; no new Verilog is emitted. `OUTFILE_CONTENT_CACHE` is
  mirrored under the synonym name.

`generate(...)` dispatches to `unique_inst` or `unique_inst_param` based on `ConfigHandler.unq_style`
(`numeric` | `param`, default `numeric`). `--no-module-cache` disables the cache entirely (forces fresh
elaboration every call).

## 6. Configuration sources

Parameter values resolve in priority order:

1. **Explicit `unique_inst(..., NAME=VALUE)` overrides** -- set as `OVERRIDDEN`/`FORCED` on the child before
   its `execute()` runs.
2. **`ConfigHandler` lookup** (JSON / `.cfg` / `--parameter` CLI overrides) -- consulted by `parameter()` only
   when state is not already `OVERRIDDEN`/`FORCED`. This precedence is what stops a generic `Name`-keyed entry
   in a JSON config tree from clobbering an explicit `unique_inst(..., N=2)`.
3. **Default supplied to `define_param` or `parameter`** -- used only when no source above provides a value.

`.cfg` files run in a non-sandboxed Python `exec` (full `__builtins__` exposed, mirroring Perl `do FILE`)
exposing `configure`, `get_configuration`, `include`, and `error`; trusted-input only. JSON loader uses `_unwrap_array` / `_unwrap_hash` helpers in `config_handler.py`.
Legacy XML configs convert via `genesispy-xml2json`. Full `ConfigHandler` API: see
[`interfaces.md`](./interfaces.md).

## 7. Output products

- `genesis_synth/<name><suffix>` -- synthesisable flavour.
- `genesis_verif/<name><suffix>` -- verification flavour.
- `<top>.vlist` -- full compile-order file list (every emitted `.v`,
  regardless of synth/verif tag). Companion `<top>.vlist.verif` lists
  verif + synth_and_verif paths and is written only when at least one
  verif-tagged file exists.
- `<top>.depend` -- Make-style dependency list (override path with `--depend FILE`).
- `genesispy_clean.sh` -- sweeps the output products for the run.
- `genesis_raw/<stem>.py` -- generated Python intermediates. Persist by default in `./genesis_raw/`.
  `--use-tmp` relocates them under `/tmp/genesispy_*` (auto-cleaned at exit; `--keep-tmp` preserves the
  scratch). `--gen-raw` additionally writes the emitted Verilog into `raw_dir` for inspection.
- Optional `--json-out FILE` -- resolved configuration tree.
- Optional `--product FILE.ext` (Genesis2 compat) -- writes three product lists: `FILE.ext` (master),
  `FILE.synth.ext`, `FILE.verif.ext`. Suppresses the default `.vlist` pair.
- Optional `--vf-out FILE` -- writes just the master list to `FILE` (`.vf` auto-appended), no side-files.
- Optional `--path FILE` -- directories touched during elaboration.

## 8. Control flags

Selected flags (`genesispy --help` is authoritative for the full list, including
`--synth-top`, `--out-dir`, `--synth-dir`, `--verif-dir`, `--cfg`, `--cfg-path`,
`--depend`, `--path`, `--debug`, `--log`):

| Flag                          | Effect                                                                        |
|-------------------------------|-------------------------------------------------------------------------------|
| `--clean`                     | Delete outputs and `raw_dir`; skip parse/elaboration.                         |
| `--parse-only`                | Stop after parsing `.vpy` -> `.py`.                                            |
| `--gen-only`             | Skip parse; expect `genesis_raw/*.py` already present, then elaborate.        |
| `--no-module-cache`           | Disable `MODULE_CACHE` (every `unique_inst` re-elaborates).                   |
| `--use-tmp` / `--keep-tmp`    | Move `raw_dir` to `/tmp/genesispy_*`; optionally preserve the scratch.        |
| `--gen-raw`                   | Also write emitted Verilog into `raw_dir` for inspection.                     |
| `--stdout`                    | Concatenate the Verilog cache to stdout; skip `.vlist`/`.depend`/clean script.|
| `--out-type synth|verif|both`   | Filter outputs by flavour.                                                    |
| `--unq-style numeric|param`    | Selects `generate(...)` dispatch (numeric suffix vs. param-encoded names).    |
| `--input-list FILE`            | Recursively expand a listfile of `--input` / `--src-path` / `--inc-path`.   |
| `--extension EXT_IN=EXT_OUT`  | Map an input extension to an output extension (repeatable; default `.vpy=.v`, `.svpy=.sv`). |
| `--system-verilog` / `-sv`     | Shorthand for `--extension .vpy=.sv`. Conflicts with an explicit `--extension .vpy=...`. |
| `--product FILE.ext`          | Write `FILE.ext` / `FILE.synth.ext` / `FILE.verif.ext` (Genesis2 semantics).  |
| `--j2` / `-j2`                | Parse templates in the j2 directive flavour instead of `//;` + backticks.     |
| `--source-comment PREFIX`     | Line-comment prefix of the source language; sets the `<comment>;` sentinel.   |
| `--output-comment P\|O,C`      | Comment style genesispy emits (module banner, `--stdout` separator).         |
| `--vf-out FILE`               | Single-file product list (auto-appends `.vf`; no `.synth`/`.verif` side-files, unlike `--product`); conflicts with `--product`. |
| `--json-out`                   | Dump resolved configuration tree.                                             |

## 9. `gvpy` CLI

`gvpy_cli.py` is a lightweight flat-preprocessor entry that wraps `template.parser` with a stripped-down
`_GvpyManager` (single file in, single file out, no `genesis_synth/` / `genesis_verif/` split, `pp()`
formatter helper). Useful for one-off `.vpy` expansion outside the full elaboration flow. The flat-parameter
flag is `--parameter` / `-p`, matching genesispy; `--defparam` is retained as a hidden alias indefinitely and
emits a one-time deprecation warning.

## 10. Pointers

- [`interfaces.md`](./interfaces.md) -- module-boundary interfaces: every attribute, method, exception, and
  exec-namespace key the modules expose to each other. The source of truth for signatures.
- [`../README.md`](../README.md) and [`user-guide.md`](./user-guide.md) -- run instructions and end-user
  template guide.
