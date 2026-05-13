# genesispy -- code structure

This document describes how the genesispy package fits together end-to-end: the layering, the pipeline that
turns a `.vpy` template into Verilog on disk, the deduplication model, and the major control surfaces. It is a
self-contained reference; deep detail (signatures, attribute names) lives in `interfaces.md` in this
directory. This document deliberately does not pin specific signatures -- it points at `interfaces.md` for
those so the two cannot disagree.

## 1. Purpose and scope

genesispy is a Python port of [Genesis2](https://github.com/StanfordVLSI/Genesis2). It parses templated
Verilog (`.vpy` / `.svpy`) into Python module files, imports those generated modules, executes them against an
elaboration runtime, and emits Verilog into `genesis_synth/` and `genesis_verif/`. Parameter values come from
JSON, trusted-input `.cfg` files, and explicit `unique_inst(...)` overrides; identical parameterisations are
deduplicated so the same module body is emitted once.

This document covers: the package layering, the orchestrator's order of operations, the lifecycle of a single
`.vpy` file, the dedup cache, and the top-level flag surface. It does **not** document the user-facing
template language (`user-guide.md`), the run instructions (`README.md`), or the contract surface between
modules (`interfaces.md`).

## 2. Layered view

The package separates into three layers with a one-way dependency: frontend imports engine, engine never
imports frontend.

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
- `tools/xml_json.py` -- standalone XML/JSON helper (not used by the elaboration core; invoked by
  `bin/genesispy-xml2json` / `bin/genesispy-json2xml`).
- `output_writer.py` -- flush cache to disk, write `.vlist` / `.depend` / `genesispy_clean.sh`.
- `errors.py` -- exception hierarchy and `error()` / `warning()` reporters.

The `template/` directory is a separate package because its job is the surface-syntax frontend: a different
surface language (Jinja, native Python, a different HDL target) would replace `template/parser.py` and adjust
the emitter without touching the engine.

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
`/tmp/genesispy_*` scratch with `--use-tmp`), applies user `--py-path` / `--py-import`, records
`output_suffix` (default `.v`; `--system-verilog` is shorthand for `.sv`), and prepares the yet-unbuilt
`cfg_handler`.

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
`OUTFILE_CONTENT_CACHE`, splits each file into `genesis_synth/` or `genesis_verif/` based on a synth/verif
heuristic (filterable with `--out-type synth|verif|both`), and writes only when content differs from disk. Then
`write_file_lists` emits `.vlist` and `.depend`, `write_clean_script` emits `genesispy_clean.sh`, optional
`write_product_lists` and `write_pathfile` handle `--product` and `--path`. With `--stdout` the cache is
concatenated to stdout instead and the list/clean-script writers are skipped. Resolved configuration is
optionally dumped via `cfg_handler.write_json` when `--json-out` is set.

**Clean.** `Manager.clean` (driven by `--clean`) calls `output_writer.clean_outputs` and removes `raw_dir`. It
runs as a short-circuit before parsing -- `--clean` exits before any `.vpy` is touched.

## 4. Frontend in detail (`template/`)

The frontend is the only place that knows the `.vpy` surface syntax. Three files:

- **`parser.py`** translates one `.vpy` source to a column-zero Python string: `//;` lines become bare Python
  at indent `(leading_spaces // 4)`; plain Verilog lines become `emit(...)` calls whose indent follows the
  controlling `//;` block; backtick interpolations become attribute references on `self`. Block ends are
  explicit sentinels (`# endfor`, `# endif`, `# endwhile`); the parser has no other way to detect block end.
- **`emitter.py`** wraps that body in a complete Python file: the `_HEADER` block declares the class, calls
  `super().execute()`, and binds bare-name aliases as locals so user code can write `parameter(...)` instead
  of `self.parameter(...)`. The `_FOOTER` block flushes the per-instance buffer into
  `cache.OUTFILE_CONTENT_CACHE` and mirrors synonyms.
- **`runtime.py`** is the import target for generated files. It re-exports `UniqueModule` and `UserMixin` (so
  generated files have a single import path), defines `StrCallable` (a `str` subclass whose `__call__` returns
  self, so `` `mname` `` and `` `mname()` `` both produce the same name), and owns the `LINE_MAP` registry
  plus `build_line_map` / `remap_traceback` which rewrite `File "<gen>.py", line N` frames back to the `.vpy`
  source for user-visible errors.

A generated `.py` file is therefore a thin shell: two `import` lines plus the rewritten body. All real work
happens in `unique_module.py` / `user_lib.py` / `cache.py` / `config_handler.py`, reached transitively via
`self.<method>` calls.

## 5. Dedup model

`cache.py` exposes three module-level singletons, reset between runs by `cache.clear_all()` (test-only):

- `MODULE_CACHE: Dict[str, UniqueModule]` -- `unique_name` -> elaborated instance.
- `MODULE_NAME_NUM_DERIVS: Dict[str, int]` -- base name -> next derivative index (drives `Foo`, `Foo_unq1`,
  `Foo_unq2`, ...); advanced via `cache.next_derivation`.
- `OUTFILE_CONTENT_CACHE: Dict[str, str]` -- emitted filename (`<unique_module_name><suffix>`) -> Verilog
  text. Flushed by `output_writer.flush_to_disk`.

Cache keys come from `hashing.sha256_param_signature(module_name, params)`. `unique_inst` runs a two-stage
cache: a *pre-key* over the explicit overrides (fast path) and a *post-key* over the fully resolved param dict
after `execute()` runs. See [genesis2-incompatibilities.md](./genesis2-incompatibilities.md) sections 1 and 6
for the hash algorithm choice and the post-elaboration dedup rationale.

Variants:

- `unique_inst` -- numeric suffix, two-stage dedup (above).
- `unique_inst_param` -- single-stage; unique name encodes the parameter values (`Foo_N8_W16`), so the
  resolved-name itself is the cache key.
- `ununique_inst` / `generate_base` -- no dedup; always allocates a fresh `Foo_unq{N}` and re-executes.
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
- Optional `--product FILE` (Genesis2 compat) -- writes `FILE.synth` and `FILE.verif` product lists.
- Optional `--path FILE` -- directories touched during elaboration.

## 8. Control surfaces

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
| `--suffix EXT`                | Override emitted Verilog extension (default `.v`).                            |
| `--system-verilog` / `-sv`     | Shorthand for `--suffix sv`. Mutually exclusive with `--suffix`.              |
| `--product FILE`              | Write `FILE.synth` / `FILE.verif` (Genesis2 semantics).                       |
| `--json-out`                   | Dump resolved configuration tree.                                             |

## 9. `gvpy` CLI

`gvpy_cli.py` is a lightweight flat-preprocessor entry that wraps `template.parser` with a stripped-down
`_GvpyManager` (single file in, single file out, no `genesis_synth/` / `genesis_verif/` split, `pp()`
formatter helper). Useful for one-off `.vpy` expansion outside the full elaboration flow. The flat-parameter
flag is `--parameter` / `-p`, matching genesispy; `--defparam` is retained as a hidden alias indefinitely and
emits a one-time deprecation warning.

## 10. Pointers

- [`interfaces.md`](./interfaces.md) -- frozen contract surface: every attribute, method, exception, and
  exec-namespace key the modules expose to each other. The source of truth for signatures.
- [`../README.md`](../README.md) and [`user-guide.md`](./user-guide.md) -- run instructions and end-user
  template guide.
