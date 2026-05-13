# genesispy -- User Guide

This guide covers the genesispy hardware-generator framework: what it
is, how to install it, how to write `.vpy` / `.svpy` templates, how
elaboration resolves parameters and deduplicates modules, and how to
drive the tool from the command line. Sections 1 through 4 introduce
the tool, installation, a first run, and the file types involved.
Sections 5 through 8 describe the source layout, elaboration model,
template syntax, and a worked walkthrough. Sections 9 and 10 document
the `genesispy` and `gvpy` command-line interfaces. Section 11 covers
extending genesispy with Python libraries, section 12 lists migration
notes for users coming from Genesis2, and sections 13 through 15 cover
generated outputs, troubleshooting, and internals. Appendix A
documents the optional j2 (Jinja2-like) template flavour.

## 1. Synopsis

genesispy is a Python port of the Genesis2 hardware-generator framework.
It reads Verilog templates with embedded Python control flow (`.vpy` /
`.svpy` files), elaborates them into a tree of parameterised module
instances, deduplicates byte-equivalent variants, and emits plain
Verilog / SystemVerilog plus the supporting compile-order, dependency,
and product lists. The template language interleaves two layers in the
same source file: ordinary Verilog that describes the hardware, and
Python that decides *which* hardware to instantiate. A single template
plus a configuration tree can elaborate into an entire family of
related chips.

The implementation is pure Python; there is no Perl runtime to install
and no XML config schema in the core CLI. Legacy XML configs convert
once via `genesispy-xml2json`.

## 2. Installing genesispy

The repo lives at `genesispy/` and ships with shell launchers under
`genesispy/bin/` that set `PYTHONPATH` to the sibling `src/` and exec
`python3 -m genesispy.cli`. No build step is required.

### From a checkout (recommended)

```sh
git clone https://github.com/stfns-s/genesispy.git
cd genesispy
./bin/genesispy --help
```

To make `genesispy` and `gvpy` available on `PATH`, either prepend
`genesispy/bin/` directly or copy `bin/` and `src/` to a shared
location (the launchers resolve `src/` as `../src` relative to their
own directory):

```sh
DEST=/path/to/install-dir
mkdir -p "$DEST"
cp -a bin src "$DEST/"
export PATH="$DEST/bin:$PATH"
```

### Via pip

```sh
pip install -e .
# or
pip install --target /path/to/install-dir .
```

`pip install -e .` exposes `genesispy`, `gvpy`, `genesispy-xml2json`,
`genesispy-json2xml`, and `genesispy-jinja2j2` as console scripts.

### Optional dependency: stock Jinja2 import

The `genesispy-jinja2j2` helper that ports stock Jinja2 templates into
genesispy's `--j2` dialect (Appendix A) needs the Jinja2 library:

```sh
pip install 'genesispy[import-j2]'
```

Default installs skip this; the core CLI does not depend on Jinja2.

### Verifying the install

```sh
genesispy --version
genesispy --help
```

## 3. Getting Started

### Hello, world

Create `top.vpy`:

```verilog
//; W = parameter("W", 8)
module `mname()` (
    input  wire [`W-1`:0] din,
    output wire [`W-1`:0] dout
);
    assign dout = din;
endmodule
```

Elaborate it:

```sh
genesispy --input top.vpy --top top
```

The run produces `genesis_verif/top.v`, plus `top.vlist` and
`top.depend`. Override the parameter from the command line:

```sh
genesispy --input top.vpy --top top -p W=16
```

### Editor support

Filetype detection and syntax highlighting for `.vpy` / `.svpy` / `.gvpy` files is available from the
[genesis-editors](https://github.com/stfns-s/genesis-editors.git) repository (Vim/Neovim, Emacs, VS Code).
Install each per its own README.

### Virtual environments

`pip install -e .` works inside any virtualenv. For checkouts using
the in-tree `bin/genesispy` launcher, no venv is required, but the
launcher honours the active Python interpreter, so activating a venv
with a specific Python version simply works:

```sh
python3 -m venv .venv
source .venv/bin/activate
./bin/genesispy --help
```

## 4. File types

| Extension                | Role                                                                 |
|--------------------------|----------------------------------------------------------------------|
| `.vpy`                   | Verilog template with embedded Python (`//;` lines, backtick expressions). Parsed into a generated `.py`, executed, and emitted as `.v`. |
| `.svpy`                  | Same as `.vpy` but emits `.sv` by default (SystemVerilog).           |
| Generated `<stem>.py`    | Intermediate Python written under `genesis_raw/` (or `/tmp/genesispy_*` with `--use-tmp`). Removed after elaboration unless `--gen-raw` is passed. |
| Emitted `.v` / `.sv`     | Per-unique-module Verilog under `genesis_synth/` or `genesis_verif/`, named `<unique_module_name>.v`. |
| `.json` (config)         | Per-instance parameter overrides, passed via `--json-cfg`. Hierarchical schema (`SubInstances`, `Parameters`, `ImmutableParameters`). Replaces Genesis2's XML config. |
| `.py` / `.cfg` (config)  | Python config script, passed via `--cfg`. Uses `configure(name, value)`. Runs under `exec()` with a sandboxed namespace; full helper list in §11.6. |
| `<top>.vlist`            | Full compile-order file list (every emitted file regardless of synth/verif tag). |
| `<top>.vlist.verif`      | Verif + synth_and_verif file list (only when at least one verif-tagged file exists). |
| `<top>.depend`           | Make-style dependency list (override path with `--depend FILE`). |
| `genesispy_clean.sh`     | Per-run cleanup script that removes everything `genesispy` produced. |
| `.xml` (legacy)          | Genesis2 XML config. Not accepted by the core CLI; convert with `genesispy-xml2json in.xml out.json` and pass the resulting JSON. |

The legacy Genesis2 extensions `.vp` / `.svp` are intentionally rejected
to prevent silently mis-executing Perl-era `//;` bodies as Python.

## 5. Source-code structure for using genesispy

The canonical layout, used by every demo under `genesispy/demos/`:

```
my_design/
├── Makefile              # 3-line shim
├── config.json           # optional --json-cfg input
├── config.py             # optional --cfg input
└── genesis_src/
    ├── top.vpy
    ├── child_a.vpy
    └── child_b.vpy
```

The per-demo `Makefile` sets `TOP` and `INPUTS` and includes the shared
`genesispy/demos/genesispy.mk`:

```make
TOP    := top
INPUTS := top.vpy child_a.vpy child_b.vpy
include ../genesispy.mk
```

`INPUTS` are bare filenames; `genesispy.mk` resolves them via
`--src-path genesis_src`. The shared makefile knows about
`JSON_CONFIG=` and `CFG_CONFIG=` (composable, see section 8), plus
`SIMULATOR=verilator|vcs|vlog|iverilog|xrun` and
`VERILINT=verilator|slang` for downstream lint/sim targets.

### Search paths

- `--src-path DIR` (repeatable) -- search directory for source-file resolution.
- `--inc-path DIR` (repeatable) -- search directory for include-file resolution.
- Both flags feed the same lookup (`src_path + inc_path + ['.']`) for **both** `--input FILE` and `include("file.vpy")` calls inside `.vpy` bodies; the source/include split is conventional, not enforced.
- `--cfg-path DIR` (repeatable) -- search directory for `--cfg` / `--json-cfg` inputs and for `include(...)` calls inside `.cfg` files.
- `--py-path DIR` (repeatable) -- prepended to `sys.path` before parsing (for `import` statements inside `//;` bodies).

### Putting sources elsewhere

Nothing forces the `genesis_src/` convention; it is just what the demo
makefile expects. Standalone projects can place `.vpy` files anywhere
and pass `--input` / `--src-path` directly.

## 6. Elaboration and parameterization

### 6.1 Elaboration order

Elaboration is a depth-first walk rooted at the `--top` module. Each
`unique_inst(...)` / `generate(...)` / `clone_inst(...)` / `instantiate(...)`
call inside a module's body recursively elaborates the named sub-module
before the parent's body continues. Parameters propagate top-down; the
parent's overrides are visible to the child *before* the child's body
runs.

After every sub-instance is elaborated, dedup runs: two instances of
the same module name that resolve to the same parameter dict collapse
into one emitted unique module. The mechanics are in
[code-structure.md](./code-structure.md) §5 (pre-key / post-key cache,
scoped-subtree signature, journaled rollback).

### 6.2 Parameter binding priority

A parameter's value is determined in the following order (lowest to
highest):

1. **In-source default** -- the second argument to `parameter('NAME', default)` in the `.vpy` file. Used when nothing else fires.
2. **JSON config** (`--json-cfg`) -- per-instance overrides scoped by instance path. Beats the in-source default. Legacy XML configs convert via `genesispy-xml2json`.
3. **`.cfg` Python configs** (`--cfg`) -- call `configure(name, value)`. Beats JSON.
4. **CLI `--parameter NAME=VALUE`** (or `-p`, same in gvpy now) -- beats everything passed in files.
5. **Parent's `unique_inst(...)` kwargs** (also `unique_inst_param`, `clone_inst`, `ununique_inst`) -- beats CLI. When the parent writes `unique_inst('wallace', 'wallace_2', N=2)`, the child sees `N=2` before its body runs, regardless of any config or CLI value.
6. **`parameter('X', val, force=True)`** -- writes at FORCED priority and locks against further override; subsequent parent kwargs, configs, and CLI re-applies are ignored. Mirrors Perl's `force` flag (UniqueModule.pm:1981).

The ordering above matches Perl Genesis2's
(`UniqueModule.pm:64-73`: `DECLARATION=1 < EXTERNAL_CONFIG=2 <
EXTERNAL_XML=3 < CMD_LINE=4 < INHERITANCE=5 < IMMUTABLE=6`); only the
numeric spacing differs (genesispy spaces by 10). In both engines, no
external-config tier (`.cfg`, JSON, CLI) can beat a parent
`unique_inst` kwarg -- the only override is a child-side write at
`IMMUTABLE` (`force_param` in Perl, `force=True` in genesispy).

Note on `ImmutableParameters`. This JSON/XML tag is *emitted* by
`--json-out` / `-hierarchy` to mark parameters that were pinned (via
`force=True` / `force_param`) in the run that produced the file. As an
*input* tag it is ignored by both engines: Genesis2
(`ConfigHandler.pm:875-919`) reads only `{Parameters}` and never
descends into `{ImmutableParameters}`; genesispy
(`config_handler.py:_find_param`, via `_FIND_PARAM_SKIP_KEYS`) skips
the same subtree on read. The tag is writeback-only metadata in both
engines; values placed under it on input have no effect. To actually
pin a value past a parent's `unique_inst` kwarg, use `force_param`
(Genesis2) / `parameter(..., force=True)` (genesispy); both write at
`IMMUTABLE`.

### 6.3 Scoped CLI overrides

`--parameter PATH.NAME=VALUE` matches the instance at the exact full
path (rightmost dot splits path from name). The scoped value
participates in the dedup key via `_scoped_subtree_signature`, so
sibling instances with different scoped values don't collapse onto
one cached unique module. Flat `NAME=VALUE` applies to any instance
whose body reads `parameter('NAME', ...)`.

### 6.4 Parameter types

Parameter values may be any Python value. Scalars (`int`, `bool`,
`str`, `float`), lists, dicts, and nested combinations of the same all
work for in-source reads and for kwargs to `unique_inst`. Module
dedup hashing, JSON-config roundtrip, and the `list=` / `min=` / `max=`
range constraints assume JSON-shaped values; custom Python objects
bypass dedup and don't roundtrip to JSON.

`parameter(...)` accepts kwargs that mirror Perl's named-arg form
(UniqueModule.pm:1981):

- `force=True` -- write at FORCED priority and lock against override.
- `doc=` -- documentation string.
- `min=` / `max=` / `step=` -- numeric range guard, XOR-exclusive with `list=`.
- `list=` -- allowed-values constraint, XOR with `min/max/step`.
- `opt='yes'|'no'|'try'` -- store-only metadata.

Range is checked at register-time and on every subsequent
`override_param` / `force_param`.

## 7. Syntax

A `.vpy` file is Verilog with two extensions: Python control lines and
backtick-interpolated expressions. Below is a representative example:

```verilog
// (timescale|default_nettype|include|ifdef|...) need no literal escaping
`timescale 1ps/1ps
//; WIDTH = parameter("WIDTH", 8)
//; DEPTH = parameter("DEPTH", 4)
module `mname()` #(
    parameter WIDTH = `WIDTH`,
    parameter DEPTH = `DEPTH`
    ) (
    input  wire [`WIDTH-1`:0] data_in,
    output reg  [`WIDTH-1`:0] data_out
    );

    // Generated register bank
//; for i in range(DEPTH):
    reg [`WIDTH-1`:0] stage_`f"{i:02d}"`;     // i=`i` zero-padded=`f"{i:03d}"`
//; # endfor

    // Conditional initialisation
//; for i in range(DEPTH):
//;     if i % 2 == 0:
    initial stage_`f"{i:02d}"` = `WIDTH`'h`f"{0xa0+i:02x}"`;
//;     else:
    initial stage_`f"{i:02d}"` = `WIDTH`'h`f"{0x50+i:02x}"`;
//;     # endif
//; # endfor

    // Sub-instances via generate + instantiate
//; subs = []
//; for i in range(DEPTH):
//;     subs.append(generate("submod", f"u_sub_{i}",
//;                          WIDTH=WIDTH, STAGE=i,
//;                          MODE=("fast" if i % 2 == 0 else "slow")))
//; # endfor

//; for s in subs:
    `s.instantiate()`
     (.clk(clk), .din(stage_`f'{s.get_param("STAGE"):02d}'`), .dout());
//; # endfor

    // Manual instantiation: backtick access to the UniqueModule fields.
//; sub = generate("submod", "u_sub_manual", WIDTH=WIDTH, MODE="fast")
    `sub.mname` /*WIDTH=`sub.get_param("WIDTH")`*/ `sub.iname` (.clk(clk));

    // Literal backtick passthrough: \`not_an_expr\`

endmodule
```

### 7.1 Syntax rules

- **Python lines**: start with `//;`. Indent inside the `//;` body to mark Python block bodies.
- **Block close**: needs a sentinel -- `//; # endfor`, `//; # endif`, `//; # endwhile`. The parser has no other way to detect block end.
- **Indent rule**: Python indent = (leading spaces in stripped `//;` content) // 4. Plain-Verilog lines inherit the indent of the most recent `//;` line ending in `:` (block opener).
- **Backticks**: `` `expr` `` interpolates a Python expression. Escape with `` \` `` for a literal backtick.
- **String formatting**: use Python f-strings inside backticks -- `` `f"{i:02d}"` `` for zero-padded indices, `` `f"{x:02x}"` `` for hex. (The `pp(value, fmt)` helper from upstream gvpy is gvpy-only: available in `bin/gvpy`-driven flows, not in genesispy elaboration.)

### 7.2 j2 syntax (opt-in: `--j2`)

genesispy ships a second template flavour that uses Jinja2-style
delimiters (`{% %}`, `{{ }}`, `{# #}`) instead of the default `//;` /
backtick markers. The embedded language stays full Python; there is no
filter-pipe / `is`-test / macro / `set` / `block` sub-language. Opt in
per run with `--j2` (works on both `genesispy` and `gvpy`); engines do
not mix within a file.

No extra install is required for `--j2` itself; the `import-j2` pip
extra is only needed if you want to convert stock Jinja2 templates
with `genesispy-jinja2j2`.

For the full syntax description, the brace-collision rules with
Verilog source, and the `genesispy-jinja2j2` helper that ports stock
Jinja2 templates, see **Appendix A: j2 syntax**.

### 7.3 Provided functions and short names

Bare names bound automatically inside every generated `execute()` body.
The canonical list is `genesispy.template.aliases.SIMPLE_ALIASES`; this
section enumerates every entry. Backticked forms (e.g. `` `mname` ``)
work in plain-Verilog lines via the template parser.

**Short-name strings** (each is a `StrCallable`, so both `mname` and
`mname()` work the same):

- **`mname`** -- unique module name.
  - _Example:_ ``module `mname` (...);``
- **`iname`** -- instance name.
  - _Example:_ ``// instance: `iname` ``
- **`bname`** -- base module name (the `.vpy` filename stem).
  - _Example:_ `//; if bname == 'wallace': ...`
- **`sname`** -- source template name; equals `bname` for non-synonym classes, else the source it was registered against via `synonym(src, trgt)`.
  - _Example:_ `//; print(f"derived from {sname}")`

**Parameter definition and access:**

- **`parameter(name, default, **kwargs)`** -- define/read a module parameter. Returns the resolved value (precedence per §6.2). Kwargs: `force=True`, `doc=`, `min=`/`max=`/`step=`, `list=`, `opt=` (see §6.4).
  - _Example:_ `//; N = parameter('N', 8, min=1, max=64, doc='bit width')`
- **`define_param(name, default, doc=, type=)`** -- register a parameter at `DECLARATION` state without reading it. Accepted kwargs: `doc=` (documentation string) and `type=` (type hint, mirrors Genesis2's `Type` flag). To attach a range, follow up with `param_range(...)`. To register a range in a single call, use `parameter(...)` instead.
  - _Example:_ `//; define_param('MODE', 'fast', doc='clock mode')`
- **`doc_param(name, msg)`** -- attach/replace a docstring on an existing parameter. Errors if the parameter isn't registered.
  - _Example:_ `//; doc_param('N', 'partial-product bit width')`
- **`param_range(name, *, min=, max=, step=, list_=)`** -- attach/replace the range guard on an existing parameter. Errors on re-definition.
  - _Example:_ `//; param_range('N', min=1, max=64, step=1)`
- **`exists_param(name)`** -- `bool`: has this module's body registered `name` via `parameter`/`define_param`?
  - _Example:_ `//; if exists_param('DEBUG'): emit('// debug build')`
- **`get_top_param(name)`** -- read a parameter from the top-level module (for cross-hierarchy lookups). Errors if absent.
  - _Example:_ `//; clk_mhz = get_top_param('CLK_MHZ')`
- **`list_params()`** -- sorted list of every parameter name registered on this module. Distinct from `get_mod_param_list()` (which returns a `{name: value}` dict).
  - _Example:_ `//; for p in list_params(): print(p)  # diagnostic print to stdout, not the outfile`

**Sub-instance creation:**

- **`unique_inst(base, inst, **params)`** / **`generate(base, inst, **params)`** -- request a uniquified sub-instance. `generate` dispatches to `unique_inst` when `unq_style=='numeric'` (default), else to `unique_inst_param`. Returns the child `UniqueModule`.
  - _Example:_ `//; w = unique_inst('wallace', 'w0', N=8)`
- **`unique_inst_param(base, inst, **params)`** / **`generate_unq_param(...)`** -- like `unique_inst` but the unique name encodes the resolved parameters (Perl-style param-suffix uniquification) instead of a numeric counter.
  - _Example:_ `//; w = unique_inst_param('wallace', 'w0', N=8)  # -> wallace_N8`
- **`generate_unq_numeric(...)`** -- explicit numeric-suffix form of `unique_inst`.
  - _Example:_ `//; w = generate_unq_numeric('wallace', 'w0', N=8)  # -> wallace_unq1`
- **`ununique_inst(base, inst, **params)`** -- instantiate without uniquification: the bare base name is preserved. First call wins the emitted name; same-params re-calls alias to it; different resolved params raise `ElaborationError`. **`generate_base(...)`** is a bare-name alias for the same method.
  - _Example:_ `//; pll = ununique_inst('pll', 'u_pll')  # emits pll.v`
- **`generate_w_name(base, gen, inst, **params)`** -- register `gen` as a class-level synonym of `base`, then `ununique_inst` the synonym; the emitted module takes `gen`'s name.
  - _Example:_ `//; rx = generate_w_name('uart', 'uart_rx', 'u_rx')  # emits uart_rx.v`
- **`clone_inst(src_inst, new_iname)`** / **`clone(...)`** -- another instance of an already-elaborated `UniqueModule`. No re-elaboration; reuses the source's `.v` file. `clone` is a bare-name alias.
  - _Example:_ `//; w1 = clone_inst(w0, 'w1')`
- **`synonym(...)`** -- two forms, selected by argument count. With one argument, `synonym(name)` mirrors the current module's outfile under `name` (genesispy instance-level extension). With two arguments, `synonym(src, trgt)` registers `trgt` as a class-level template synonym of `src` (Genesis2 semantics).
  - _Example (one argument):_ `//; synonym('adder_alias')`
  - _Example (two arguments):_ `//; synonym('adder', 'adder_v2')`

**Sub-instance navigation and query:**

- **`get_subinst(name)`** -- return the child `UniqueModule` for instance `name`; errors if absent.
  - _Example:_ `//; w = get_subinst('w0')`
- **`exists_subinst(name)`** -- `bool` membership check.
  - _Example:_ `//; if exists_subinst('debug_unit'): ...`
- **`get_subinst_array(pattern="")`** -- list of child `UniqueModule`s whose instance name matches `pattern` (regex; empty = all).
  - _Example:_ `//; for w in get_subinst_array(r'^w\d+$'): emit(w.instantiate())`
- **`get_instance_obj(path_or_obj)`** -- resolve a hierarchical path (dotted string walked from the top instance) to the corresponding `UniqueModule`. A `UniqueModule` argument passes through unchanged.
  - _Example:_ `//; child = get_instance_obj('top.cluster0.w0')`
- **`search_subinst(*, start_from=, depth=, reverse=, path_regex=, iname_regex=, mname_regex=, bname_regex=, sname_regex=, has_param_regex=, apply_map=)`** -- recursive search over the instance tree. Returns a list of matching `UniqueModule` instances (not a count); each element is the live child object, so `.mname` / `.get_param(name)` / etc. work on it. All regex filters AND-compose; `apply_map` is a final predicate. Snake_case kwargs (Genesis2's CamelCase form is not accepted). Starts from `start_from` (default: top); `depth` bounds the search; `reverse=True` returns post-order.
  - _Example:_
    ```python
    //; matches = search_subinst(
    //;     start_from='top.cluster0',          # root of search; default is the top module (optional)
    //;     depth=3,                            # max levels below start_from (optional)
    //;     reverse=False,                      # pre-order (parents before children) (optional)
    //;     bname_regex=r'^wallace$',           # match base module name (optional)
    //;     iname_regex=r'_lo$',                # match instance name (optional)
    //;     path_regex=r'cluster0\.',           # match full instance path (optional)
    //;     mname_regex=r'_unq\d+',             # match unique module name (optional)
    //;     sname_regex=r'wallace',             # match source template name (optional)
    //;     has_param_regex=['^N$', '^WIDTH$'], # require both params present (optional)
    //;     apply_map=lambda m: m.get_param('N') >= 8,  # final predicate (optional)
    //; )
    //; for m in matches:
    //;     emit(f"// {m.iname}: N={m.get_param('N')}")
    //; # endfor
    ```

**Output and template helpers:**

- **`instantiate(**ports)`** / **`<child>.instantiate(**ports)`** -- return a Verilog instance fragment. With ports: `MName iname (.p(v), ...)`. Without: `MName iname` so the caller supplies the port list in surrounding text.
  - _Example:_ `` `w.instantiate(a=A, b=B, y=Y)` ``
- **`emit(text)`** -- write `text` to the current module's Verilog outfile. Appends a newline automatically (no need for a trailing `\n`). Use this instead of Python `print(...)`, which goes to stdout, not the outfile.
  - _Example:_ `//; emit(f'  wire [{N-1}:0] sum;')`

**Diagnostics:**

- **`error(msg)`** -- raise `GenesisPyError`. Prefixes `<module_name>@<instance_path>`.
  - _Example:_ `//; if N < 1: error(f'N={N} must be positive')`
- **`warning(msg)`** -- write to stderr and return. Same prefix.
  - _Example:_ `//; if N > 32: warning('large N may slow synthesis')`

**Other:**

- **`include(path)`** -- parse another `.vpy` and run its body inside the current module's `execute()` namespace. Mirrors Genesis2 `//;include("file.vp")`. Resolves `path` against `--inc-path`.
  - _Example:_ `//; include('common_ports.vpy')`
- **`pinclude(path)`** -- gvpy-only raw-Python include. Bound to `None` in standard `genesispy` runs; calling it under `genesispy` raises `TypeError`.
  - _Example (gvpy):_ `//; pinclude('helpers.py')`

## 8. Examples

### 8.1 `many_iterative_wallace_trees`

Files (under `genesispy/demos/many_iterative_wallace_trees/`):

- `genesis_src/top.vpy` -- top-level testbench; sweeps a list of widths.
- `genesis_src/wallace.vpy` -- iterative Wallace-tree reduction, parameterised by `N`.
- `genesis_src/CSA.vpy` -- carry-save adder used by `wallace`.
- `config.json` -- optional per-instance overrides (JSON).
- `config.xml` -- ships *only* in this demo as the Perl-side input for the parity suite (the Perl Genesis2 reference reads XML; genesispy reads `config.json`). Convert legacy XML configs in your own trees via `genesispy-xml2json`.
- `config.py` -- optional Python `.cfg` overrides (lowest external priority -- JSON and CLI both take precedence).
- `Makefile` -- sets `TOP`/`INPUTS` and pulls in `../genesispy.mk`.

#### Build

```sh
cd demos/many_iterative_wallace_trees
make gen                                # default (no config) -- widths=[4,8]
make gen JSON_CONFIG=config.json        # JSON overrides defaults -- widths=[2,5,16,32,64]
# Legacy XML: convert once with `genesispy-xml2json config.xml config.json`
make gen CFG_CONFIG=config.py           # .cfg overrides -- widths=[3,7,11]
make gen JSON_CONFIG=config.json CFG_CONFIG=config.py  # layered: cfg wins per key
make sim                                # default SIMULATOR=verilator
make sim SIMULATOR=vcs                  # override
make clean
make help                               # demo-specific usage table
```

#### Parameter setting precedence (worked example)

Trace the value of parameter `COND` on the elaborated sub-instance
`top.wallace_2` (the `wallace_2` instance created by
`unique_inst('wallace', 'wallace_2', N=2)` in `top.vpy`). Each row
below sets up genesispy differently and shows which priority level
applies and what value `COND` takes in the generated `wallace_unq*.v`:

| Setup                                             | Highest level that fires | Final value |
|---------------------------------------------------|--------------------------|-------------|
| `make gen`                                        | in-source default        | `True`      |
| `make gen JSON_CONFIG=config.json`                | JSON `Parameters`        | `False`     |
| `make gen CFG_CONFIG=config.py`                   | `.cfg` `configure()`     | `True`      |
| `make gen JSON_CONFIG=config.json CFG_CONFIG=config.py` | JSON (beats `.cfg`) | `False`     |
| Same JSON run plus `-p COND=true` on the CLI      | CLI                      | `True`      |

#### What `top.vpy` does

```python
//; widths = parameter('WALLACES_WIDTHS', [4, 8])
```

The default `[4, 8]` is used unless JSON/`.cfg` supplies a different
list (see the ladder above). Each iteration of the outer loop:

```python
//; for N in widths:
//;     wallace = unique_inst('wallace', f"wallace_{N}", N=N)
   `wallace.instantiate()` (.pp(pp_`N`), .sum(sum_`N`), .carry(carry_`N`));

//;     wallace_clone = clone_inst(wallace, f"clone_of_wallce_{N}")
   `wallace_clone.instantiate()` (.pp(pp_`N`), .sum(/* ignored */), .carry(/* ignored */));
//; # endfor
```

- `unique_inst('wallace', f"wallace_{N}", N=N)` requests a unique elaboration of `wallace` with `N` overridden. genesispy uniquifies by a canonical-JSON SHA over the resolved parameter dict -- two calls with the same `N` collapse to a single Verilog module.
- `clone_inst(wallace, ...)` adds another instance of the *same* unique module without re-running `wallace`'s body.
- Result depends on the ladder. With JSON `widths=[2,5,16,32,64]`: five unique `wallace_unq*` modules, each used twice (`wallace_<N>` + `clone_of_wallce_<N>`). With the in-source default `[4, 8]`: two unique modules + two clones. With the `.cfg` widths `[3, 7, 11]`: three of each.

#### What `wallace.vpy` does

Iterative Wallace-tree reduction in Python control flow:

```python
//; from math import floor
//; N = parameter('N', 4)
//; height = N
//; width = 2*N
//; step = 0
   ...rectangularise pp[i] into pp_step0...
//; while height > 2:
//;     step += 1
//;     width += 1
//;     for i in range(floor(height/3)):
//;         csa_obj = unique_inst('CSA', f"csa_step{step}_{i}", Width=width-1)
   `csa_obj.instantiate()` (.a(pp`3*i`_step`step-1`), ...);
//;     # endfor
//;     for i in range(height % 3):
        ...carry forward leftovers...
//;     # endfor
//;     height = 2 * floor(height/3) + height%3
//; # endwhile
```

Key points:

- The Python loop *generates SystemVerilog signals and instances* -- it doesn't emit a SystemVerilog `generate` block. genesispy is unrolling at elaboration time.
- `unique_inst('CSA', ..., Width=width-1)` creates one CSA per (step, i), but each unique `Width` resolves to a single Verilog module after dedup.
- Backtick interpolation builds signal names: `pp`2*i`_step`step``.

#### What `CSA.vpy` does

A two-line carry-save adder:

```verilog
//; width = parameter('Width', 4)
module `mname()` (input logic [`width-1`:0] a,b,c, output logic[`width-1`:0] s, co);
   assign s  = a ^ b ^ c;
   assign co = a&b | b&c | a&c;
endmodule
```

#### What `config.json` / `config.py` do

**`config.json`** -- JSON-native schema. Notable structures:

- `WALLACES_WIDTHS` is an `"__ArrayType__": [...]` -- a plain JSON list, fed into `top.vpy`'s outer loop. (The double-underscored sentinels prevent collisions with user hash keys.)
- Each `wallace_<N>` entry under `SubInstances` carries `ImmutableParameters` (informational marker only -- ignored on input by both engines; `N` is set by the `unique_inst('wallace', 'wallace_<N>', N=<N>)` kwargs in `top.vpy` at the `INHERITANCE` tier), `Parameters` (`COND`, `ParamHash`, plus showcase keys like `ParWithMin`, `ParamComplexStruct`), and a `UniqueModuleName` (`wallace_unq1` ... `wallace_unq5`).
- `clone_of_wallce_<N>` entries carry only `"CloneOf": {"InstancePath": ...}` and reuse the source's `UniqueModuleName` -- that's how genesispy records the clone relationship in the elaborated hierarchy.

**`config.py`** -- a tiny Python script using `configure(name, value)`.
Three lines override `WALLACES_WIDTHS`, `COND`, and `ParamHash`. It is
at the lowest level of the external priority ladder -- JSON, CLI, and
parent kwargs all take precedence over it for any key they set. Useful
when you want overrides expressed in Python (loops, computed values)
for keys not also set in JSON.

#### Output

Run `make gen`; you get:

- `genesis_synth/top.v`, `wallace_unq1.v` ... `wallace_unq5.v`, `CSA_unq*.v` -- one Verilog file per *unique* module.
- `genesis_synth/top.vlist` -- flat compile-order file list.
- `genesis_vlog.vf` -- Genesis2-style product list at the demo root (mirror of `top.vlist`).
- `genesis_synth/top.depend` -- Make-style dependency list.
- `genesis_synth/genesispy_clean.sh` -- removes everything `make gen` produced.

Inspect `genesis_synth/top.v` to see the unrolled instance sequence
the loops in `top.vpy` produced.

### 8.2 Instance generation examples

The `generation_examples/` demo walks through five ways to drive
module generation, one top module per pattern. Each primitive serves
a different purpose -- distinct uniquified modules per parameter set,
a single shared module instantiated many times, renaming the emitted
module, registering a synonym up front, or duplicating an
already-elaborated module without re-running its body:

- `ex1_unique.vpy` -- `unique_inst` in a loop with distinct parameters
  (one uniquified module per param set).
- `ex2_ununique.vpy` -- `ununique_inst` with same-params aliasing (one
  bare-name module shared by multiple instances).
- `ex3_genwname.vpy` -- `generate_w_name` to choose a custom emitted
  module name.
- `ex4_synonym.vpy` -- the split form: explicit `synonym(...)`
  registration + `generate_base(...)` per instance.
- `ex5_clone.vpy` -- `clone_inst` of an already-elaborated unique
  module (keeps the `_unq` suffix; no re-elaboration).

See `genesispy/demos/generation_examples/README.md` for the full
walkthrough -- source listings, exact commands, and expected Verilog
output for each.

## 9. Invoking genesispy

```sh
genesispy --input top.vpy --input child.vpy --top top --json-cfg config.json
# or short:
genesispy -i top.vpy -i child.vpy -t top -j config.json
```

> **Legacy XML configs:** genesispy is JSON-only. Convert once with
> `genesispy-xml2json in.xml out.json` and pass the `.json`. The reverse
> helper `genesispy-json2xml` is provided for symmetry. See section 12
> (Migrating from Genesis2) for the conversion notes.

`genesispy --help` is authoritative; the groupings below mirror that
output.

### 9.1 General

- `-h`, `--help` -- show help and exit.
- `-v`, `--version` -- print version and exit.
- `-d`, `--debug LEVEL` -- debug verbosity level (default: `0`).
- `--log FILE` -- tee error/warning messages to `FILE` (defaults to `genesispy.log`, lazy-opened on first error/warning so clean runs leave no log artifact). Suppress by pointing at `/dev/null`.
- `--clean` -- delete generated files and exit.
- `-t`, `--top NAME` -- name of the top module.
- `--synth-top PATH` -- synthesis-top instance: a top-level instance name (e.g. `core`) or dotted instance path (e.g. `top.core`) bounding the synth cone. Instances at or under this path emit to `genesis_synth/`, all others to `genesis_verif/`. When omitted (Genesis2 default), every emitted file goes to `genesis_verif/`.

### 9.2 Parse phase (`.vpy` -> `.py`)

- `-i`, `--input FILE` -- source `.vpy` file to process. Repeatable.
- `-f`, `--input-list FILE` -- listfile of inputs (bare paths or GNU directives `--input/--input-list/--src-path/--inc-path`; inline `# ...` comments allowed; recursive). Repeatable.
- `--src-path DIR` -- search directory for source-file resolution. Repeatable.
- `--inc-path DIR` -- search directory for include-file resolution. Repeatable.
- Both flags feed the same lookup (`src_path + inc_path + ['.']`) for **both** `--input FILE` and `include(...)` calls inside `.vpy` bodies; the source/include split is conventional, not enforced.
- `--py-path DIR` -- prepend `DIR` to `sys.path` before parsing. Repeatable.
- `--py-import NAME` -- import a Python module before parsing. Repeatable.
- `--parse-only` -- run only the parse phase (`.vpy` -> `.py`); skip elaboration.
- `-j2`, `--j2` -- parse templates with the j2 (Jinja2-like) flavour (Appendix A). Stock Jinja2 sources do not parse here as-is; see `genesispy-jinja2j2`.
- `--gen-raw` -- keep the raw directory after elaboration (preserving the generated `<stem>.py` intermediates) and also dump the raw per-module Verilog into `<raw_dir>/`. Without this flag the raw dir is removed at end of run.
- `--raw-dir DIR` -- override the raw_dir location (default `./genesis_raw`). Mutually exclusive with `--use-tmp`/`--keep-tmp`. Orthogonal to `--gen-raw`: without `--gen-raw` the directory is still removed after elaboration.
- `--use-tmp` -- place the raw directory under a `/tmp` scratch dir.
- `--keep-tmp` -- keep the `/tmp` scratch dir after exit (implies `--use-tmp`).

### 9.3 Elaborate phase (`.py` -> Verilog)

- `--gen-only` -- skip the parse phase; expect generated `.py` files in `raw_dir`. (Despite the name, this runs the elaborate step only.)
- `-j`, `--json-cfg FILE` -- input JSON configuration file. Legacy XML: convert with `genesispy-xml2json` first.
- `--cfg FILE` (alias `--py-cfg`) -- input Python config script (uses `configure(name, value)`). Repeatable.
- `--cfg-path DIR` -- search directory for `--cfg`/`--json-cfg` and for `include(...)` calls inside `.cfg` files. Repeatable.
- `-p`, `--parameter NAME=VALUE` (or `PATH.NAME=VALUE`) -- command-line parameter override. Plain `NAME=VALUE` applies to any instance whose body calls `parameter('NAME', ...)`. Dotted form (e.g. `top.child2.x=2`) applies only to the instance at that exact full path; rightmost dot separates path from name. Repeatable.
- `--no-module-cache` -- disable the unique-module dedup cache (forces fresh modules).
- `--unq-style numeric|param` -- module uniquification style (default: `numeric`). Controls `generate(...)` dispatch.

### 9.4 Output selection and directories

- `--out-type synth|verif|both` -- which output flavour to emit (default: `both`).
- `--out-dir DIR` -- output directory (default: `genesis_synth`). When set, also supplies the default for `--synth-dir` and `--verif-dir`.
- `--synth-dir DIR` -- directory for synth-tagged Verilog.
- `--verif-dir DIR` -- directory for verif-tagged Verilog.
- `--extension EXT_IN=EXT_OUT` -- pair an input template extension with its emitted-Verilog extension (repeatable). Defaults: `.vpy=.v`, `.svpy=.sv`. User entries override defaults; e.g. `--extension .vpy=.sv` or `--extension .tvpy=.tv`. Leading dots are added on either side if missing; both sides are case-folded.
- `-sv`, `--system-verilog` -- shorthand for `--extension .vpy=.sv`. Errors out if combined with a conflicting `--extension .vpy=...` entry.
- `--comment PREFIX` -- line-comment prefix of the target output language (default: `//`). Sets both the template directive sentinel (`<comment>;` replaces `//;` in genesis flavour) and the prefix used by the auto-generated module banner. j2 mode is unaffected.
- `--stdout` -- write generated Verilog to stdout instead of `genesis_synth`/`genesis_verif`. Skips `.vlist`/`.depend`/clean script and removes the raw dir on exit. Overrides `--gen-raw`: no raw `.v` siblings are written and the raw dir is removed regardless.
- `--product FILE` -- write Genesis2-style product file lists. `--product FILE.ext` produces three files: `FILE.ext` (all modules), `FILE.synth.ext` (synth-cone), `FILE.verif.ext` (verif-cone).
- `--json-out FILE` -- write a `HierarchyTop` snapshot of the elaborated module tree (port of Perl `-hierarchy`). Emits three files in `dirname(FILE)`: `FILE` (full), `<stem>-small<ext>` (no `ImmutableParameters`), `<stem>-tiny<ext>` (only params with priority `>= EXTERNAL_PARAM_FILE`).
- `--vf-out FILE` -- permanent alias for `--product FILE.vf` (auto-appends `.vf` if missing). Mutually exclusive with `--product`.
- `--depend FILE` -- override the dependency-list output path (default: `<top>.depend`).
- `--path FILE` -- write the list of directories touched during elaboration to `FILE`.

## 10. gvpy flat-preprocessor mode

`gvpy` is a companion console script for a gvpy/gvp-style flat
preprocessor workflow on top of the same parser/runtime: single input
file, `--parameter NAME=VALUE` (or `-p`) flat parameters, output to
stdout, no synth/verif directory split.

```sh
gvpy --gvpy-strict --mname top --parameter WIDTH=8 top.vpy > top.v
# or short:
gvpy --gvpy-strict --mname top -p WIDTH=8 top.vpy > top.v
```

Use it when you want gvpy semantics (record-only `generate`/
`instantiate`, `pinclude()` raw-Python include) instead of genesispy's
full elaboration pipeline. See `demos/gvpy/` for a worked example.

Usage: `gvpy [options] FILE [FILE ...]` (output goes to stdout).

- `--mname NAME` -- top module name (default: input filename stem).
- `--py-path DIR[,DIR...]` -- comma-separated dirs to add to `sys.path`. Repeatable.
- `--inc-path DIR[,DIR...]` -- comma-separated dirs for `include()`/`pinclude()` search. Repeatable.
- `-p`, `--parameter NAME=VALUE` -- set a flat parameter consulted by `parameter()`. Repeatable. (`--defparam` is a deprecated hidden alias; emits a one-time warning.)
- `--comment PREFIX` -- line-comment prefix of the target output language (default: `//`). Sets both the directive sentinel (`<comment>;` replaces `//;`) and the banner prefix.
- `--extension EXT_IN=EXT_OUT` -- pair an input template extension with its emitted-Verilog extension. Defaults `.vpy=.v`, `.svpy=.sv`. Repeatable.
- `-j2`, `--j2` -- parse templates with the j2 (Jinja2-like) flavour (Appendix A).
- `--gvpy-strict` -- use gvpy's record-only `generate`/`instantiate`/`synonym` instead of genesispy's elaboration-based versions.
- `--version` -- print version and exit.
- `-h`, `--help` -- show help and exit.

## 11. Extending genesispy with Python libraries

Perl Genesis2's "Extending With Homemade Perl Libraries" facility
covered `@ISA` injection, `Exporter` patterns, and `-perl_libs`
search paths. The genesispy equivalents are simpler because Python
already has `import` and `sys.path`.

### 11.1 Importing a helper module from a `.vpy` body

Any `//;` line is plain Python, so `import` works directly:

```verilog
//; from math import ceil, log2
//; W = parameter("W", 8)
//; ADDR_BITS = ceil(log2(W))
module `mname()` (
    input wire [`ADDR_BITS-1`:0] addr,
    ...
);
```

For project-local helpers, put them anywhere on `sys.path`:

```sh
genesispy --py-path ./mylib --input top.vpy --top top
```

Then inside `.vpy`:

```python
//; from mylib.utils import next_pow_of_2
//; N = parameter("N", 13)
//; ROUNDED = next_pow_of_2(N)
```

`--py-path` is repeatable. `--py-import NAME` performs the import
itself before parsing if you want side effects (e.g. registering
classes in a module-level registry).

### 11.2 Sharing `.vpy` snippets via `include(...)`

`include("file.vpy")` parses another `.vpy` and runs its body inside
the *current* module's `execute()` namespace. Variables, parameters,
and any signals emitted by the included file land in the caller's
module:

```python
//; include("common_ports.vpy")
//; include("debug_signals.vpy")
```

`include()` resolves against `--inc-path DIR` (repeatable). Mirrors
Genesis2's `//;include("file.vp")` semantics.

### 11.3 gvpy-only: raw-Python include via `pinclude(...)`

Inside `gvpy`-driven flows, `pinclude("helpers.py")` execs a plain
`.py` file in the caller's namespace -- useful for sharing helper
functions when you don't want the included file to look like a
template. Bound to `None` in standard `genesispy` runs; calling it
there raises `TypeError`.

### 11.4 Rebinding bare-name aliases

The bare names `parameter`, `generate`, `unique_inst`, etc. are just
Python locals in the generated `execute()`. Standard Python scoping
applies: a `.vpy` may rebind them locally (`parameter = my_wrapper`)
to wrap behavior. The original methods are still reachable via
`self.parameter(...)`, etc.

### 11.5 Defining a `UniqueModule` mixin

For shared methods that should be visible on every elaborated module,
write a Python mixin module and have it imported via `--py-import` or
the `genesispy.user_lib.UserMixin` hook (see
[interfaces.md](./interfaces.md), section `genesispy.user_lib`). The
mixin's methods become available as `self.<method>` on every
`UniqueModule`. This replaces Perl Genesis2's `@ISA` global-injection
pattern.

### 11.6 `.cfg` sandbox helpers

A `.cfg` Python config script (passed via `--cfg`) runs under `exec()`
in a namespace pre-bound with the following names. Full `__builtins__`
are also available (mirrors Genesis2 `do FILE` semantics).

| Name | Purpose |
|------|---------|
| `configure(name, value, **flags)` | Write a value at `EXTERNAL_CONFIG` priority. |
| `get_configuration(name)` | Read the currently-resolved value. |
| `exists_configuration(name)` | `bool` membership check. |
| `remove_configuration(name)` | Delete a previously-`configure`d entry. |
| `include(path)` | Recursively load another `.cfg` file. |
| `print_configuration()` | Dump the full param database (stderr; debug aid). |
| `get_top_name()` | Name of the `--top` module. |
| `get_synthtop_path()` | Path to the `--synth-top` instance, or `None`. |
| `error(msg)` | Raise `GenesisPyError` (fatal). |
| `warning(msg)` | Write a warning to stderr; return normally. |

Note that `.cfg` files do **not** receive the bare-name `.vpy` API
(`parameter`, `unique_inst`, etc.) -- there is no module under
elaboration at config-load time. Use `configure(...)` to set values,
not `parameter(...)`.

## 12. Migrating from Genesis2

Superficial differences (file extensions, `//;` body language, CLI
flag style) are listed below. For behaviour-affecting incompatibilities
-- unique-module hash, JSON-only configs (legacy XML via
`genesispy-xml2json`), post-elaboration dedup -- see
[genesis2-incompatibilities.md](./genesis2-incompatibilities.md).

- **File extension** -- `.vp` -> `.vpy`, `.svp` -> `.svpy`. Configurable via the repeatable `--extension EXT_IN=EXT_OUT` flag (e.g. `--extension .tvpy=.tv` to register a custom pair, or `--extension .vpy=.sv` to redirect the default).
- **`--suffix` removed** -- replaced by `--extension`. `-sv`/`--system-verilog` is preserved as a shorthand for `--extension .vpy=.sv`.
- **Config input** -- XML support removed from the core CLI; convert legacy XML once with `genesispy-xml2json in.xml out.json` and pass `--json-cfg out.json`. The reverse helper `genesispy-json2xml` is provided for symmetry.
- **`ImmutableParameters` (input config)** -- ignored by both engines. Genesis2 `ConfigHandler.pm:875-919` reads only `{Parameters}` from input XML; `{ImmutableParameters}` is touched only by the writeback path (`ConfigHandler.pm:677, 724`). genesispy matches via `_FIND_PARAM_SKIP_KEYS` in `config_handler.py:_find_param`. The tag is writeback-only metadata in both engines. To actually pin past a parent's `unique_inst` kwarg, use `force_param` (Genesis2) / `parameter(..., force=True)` (genesispy); both write at `IMMUTABLE`.
- **`//;` body language** -- Perl -> Python.
- **`--cfg` config files** -- Perl `eval` -> Python `exec()` (trusted-input, full `__builtins__` exposed -- mirrors Perl `do FILE`). Files are plain Python; `.py` is preferred over `.cfg`.
- **CLI flag style** -- GNU `--input`/`-i`, `--top`/`-t`, ... (Genesis2 used Perl-style `-input`, `-top`).
- **`--input-list` listfile syntax** -- GNU directives only (`--input/--input-list/--src-path/--inc-path`); Genesis2 used `-input/-inputlist/-srcpath/-incpath`. Bare paths default to `--input`.
- **`parameter(...)` kwargs** -- mirrors Perl's named-arg form (UniqueModule.pm:1981). Supports `force=True` (write at FORCED priority and lock against override), `doc=` (documentation), `min=`/`max=`/`step=` (range guard), `list=` (allowed-values constraint, XOR with min/max/step), and `opt='yes'|'no'|'try'` (store-only metadata). Range is checked at `parameter()` register-time and on every subsequent `override_param` / `force_param`. Parameter values may be any Python value, but module dedup hashing, JSON-config roundtrip, and the `list=`/`min=`/`max=` constraints assume JSON-shaped values (scalars, lists, dicts of same); custom Python objects bypass dedup and don't roundtrip to JSON.
- **`doc_param(name, msg)` / `param_range(name, *, min, max, step, list_)`** -- late-bind documentation and range on an existing parameter (mirror Perl's older API at UniqueModule.pm:558 / :582). Errors if the parameter doesn't exist; `param_range` errors on re-definition.
- **`print(...)` inside `//;` escapes** -- Perl `print "..."` inside `//;` blocks routes to the **generated Verilog file** by default; `print STDOUT/STDERR` explicitly route to the screen. Python `print(...)` writes to `sys.stdout`, not to the module's outfile. Use `emit(...)` to write to the module's Verilog output, or pass `file=sys.stderr` for the diagnostic channel. A mechanical port of debug `print` lines silently loses them from the `.v` output.
- **`Genesis2::UserConfigBase` class form** -- Perl `.cfg` scripts can subclass `Genesis2::UserConfigBase` (PerlLibs/Genesis2/UserConfigBase.pm) to share helper code via OO inheritance. genesispy has no class-form equivalent; import helper modules from the `.cfg` script directly. The injected sandbox functions (`configure`, `get_configuration`, `print_configuration`, `get_top_name`, `get_synthtop_path`, ...) remain in scope through any imported helpers.
- **`--log` default** -- now defaults to `genesispy.log` (lazy-opened on first error/warning so clean runs leave no log artifact). Mirrors Perl's `LogFileName = 'genesis.log'` (Manager.pm:103). Suppress by pointing at `/dev/null` or any non-writable path.
- **`--product FILE.ext`** -- writes three files: `FILE.ext` (master, every emitted Verilog file), `FILE.synth.ext` (synth-cone files), `FILE.verif.ext` (verif-cone files). Mirrors Perl `-product` (Manager.pm:1302-1319). Extension split via `os.path.splitext` (last-dot only).
- **`--vf-out FILE`** -- permanent alias for `--product FILE.vf` (auto-appends `.vf` if missing). Mutually exclusive with `--product`.
- **`self.to_string(*args)`** -- debug serialiser using `pprint.pformat` per argument (newline-separated). Mirrors Perl `$self->to_string(...)` (UniqueModule.pm:2911); not a byte-for-byte port of `CfgHandler::PrintToString`. Self-method only -- no bare-name alias in `.vpy` bodies.
- **Parameter accessors** -- `exists_param(name)`, `get_top_param(name)`, and `list_params()` (sorted list of names; distinct from the existing `get_mod_param_list()` which returns a `{name: value}` dict). Mirror Perl UniqueModule.pm:496/:550/:515.
- **Sub-instance navigation** -- `get_subinst(name)`, `exists_subinst(name)`, `get_subinst_array(pattern="")`, `get_instance_obj(path_or_obj)`, and `search_subinst(...)` are now available on every `UniqueModule` (mirrors Perl UniqueModule.pm:760/780/797/932/1087). `search_subinst` kwargs are **snake_case**: `start_from=`, `depth=`, `reverse=`, `path_regex=`, `iname_regex=`, `mname_regex=`, `bname_regex=`, `sname_regex=`, `has_param_regex=`, `apply_map=`. Translate from Perl Genesis2's CamelCase (`PathRegex`, `INameRegex`, ...) when porting.
- **`iname` / `mname` / `bname` / `sname` callable** -- on a `UniqueModule` instance, the four short-name properties return a `StrCallable` (a `str` subclass), so both `obj.mname` and `obj.mname()` work the same way (and equal each other as strings). Mirrors Perl `$obj->mname()` / `$obj->bname()`.
- **`error(...)` / `warning(...)`** -- bare-name `error("msg")` and `warning("msg")` are now bound inside `.vpy` bodies (routing through `self.error` / `self.warning`), mirroring Perl `$myself->error(...)` (UniqueModule.pm:2803). Both forms prefix the message with `<module_name>@<instance_path>` and delegate to `genesispy.errors`. `self.error(msg)` raises `GenesisPyError` (fatal); `self.warning(msg)` returns normally after writing to stderr.
- **`ununique_inst` / `generate_base`** -- preserves the bare base name on first call (matches Perl `UnUniquifiedModules`, UniqueModule.pm:1610). A second call for the same base name with the same resolved params aliases the first instance under the new instance name. Different resolved params raise `ElaborationError` with both param dicts (the emitted module name is global, so two distinct elaborations can't both keep the bare name).
- **`synonym(...)` arity** -- the bare-name `synonym(...)` in `.vpy` bodies is an arity dispatcher: `synonym(name)` mirrors the current module's outfile under `name` (genesispy instance-level semantics); `synonym(src, trgt)` registers `trgt` as a class-level template synonym of `src` via `Manager.synonym_class` (Perl semantics). Perl supports only the 2-arg form; the 1-arg form is a genesispy extension.
- **`sname`** -- mirrors Perl `get_source_name` (UniqueModule.pm:377): returns the source template name (`_synonym_for` set by `Manager.synonym_class` on a synonym-derived class, else the base module name == `bname`).
- **`--json-out`** (Perl `-hierarchy`) -- same three-file output and same `HierarchyTop` schema, but emitted as JSON (use `genesispy-json2xml` for XML). Sibling filenames diverge from Perl: Perl emits `<f>`/`small_<f>`/`tiny_<f>`; genesispy splits `<f>` into `<stem><ext>` and emits `<stem><ext>`/`<stem>-small<ext>`/`<stem>-tiny<ext>`. The `tiny` variant filters by `priority >= EXTERNAL_PARAM_FILE`; genesispy's flat-key config lookup cannot replicate Perl's `inherit_param`-aware priority assignment, so the `tiny` set may be a strict superset of Perl's (params Perl tags as inherited may appear as user-overrides in genesispy).

## 13. Outputs

A `genesispy` run produces:

- `genesis_raw/<stem>.py` -- generated Python intermediate per `.vpy` input. The raw directory is removed at end of run unless `--gen-raw` is set (which also writes the per-module `.v` siblings into it). `--raw-dir DIR` relocates the directory; `--use-tmp` puts it under `/tmp/genesispy_*` (auto-cleaned at exit; `--keep-tmp` preserves the scratch).
- `genesis_synth/<module>.v` -- elaborated Verilog for instances at or under `--synth-top`. (Empty when `--synth-top` is omitted.)
- `genesis_verif/<module>.v` -- elaborated Verilog for instances outside the synth cone (everything when `--synth-top` is omitted, mirroring Genesis2's `SynthTop=undef` default).
- `<outputdir>/<top>.vlist` -- full compile-order file list (every emitted `.v`, regardless of synth/verif tag).
- `<outputdir>/<top>.vlist.verif` -- emitted only when at least one verif-tagged file exists; lists verif + synth_and_verif paths.
- `<top>.depend` -- Make-style dependency list.
- `genesispy_clean.sh` -- sweeps the run's output products.
- Optional `--json-out FILE` -- resolved configuration tree (three siblings, see section 9.4).
- Optional `--product FILE` (Genesis2 compat) -- writes `FILE`, `FILE.synth`, `FILE.verif` product lists.
- Optional `--path FILE` -- directories touched during elaboration.

## 14. Troubleshooting

### "ParseError: without matching opener"

The parser saw a `//; # endfor` / `# endif` / `# endwhile` (or the
j2 equivalent) with no opener on the block stack. Causes:

- The block opener (`//; for ...:`, `//; if ...:`, `//; while ...:`) is missing the trailing `:` -- without it the parser doesn't recognise the line as opening a block, so the matching close looks unmatched.
- An earlier close was already eaten by a parent block.
- In j2 mode, a `{% %}` directive whose body strips to exactly `endfor` / `endif` / `endwhile` is always treated as a block close, even if you intended it as a Python expression.

### "ElaborationError: parameter X overridden after register"

A `parameter('X', default)` call ran *after* the same name had been
set via the override path (CLI `--parameter`, JSON config, parent
kwargs). Restructure the `.vpy` body so all `parameter()` reads happen
before any computation that depends on them; or use
`parameter(..., force=True)` if you intend to lock the value.

### Tracebacks point at `<gen>.py` line numbers

`template/runtime.py` maintains a `LINE_MAP` that rewrites
`File "<gen>.py", line N` frames back to the `.vpy` source. When that
remap is absent, you are looking at the generated intermediate; pass
`--gen-raw` plus `--debug 1` to keep the `.py` under `genesis_raw/`
for inspection, and check that the failing line matches what you
expected the template to emit.

### `include("file.vpy")` raises `FileNotFoundError`

`include()` resolves against `--inc-path DIR` (repeatable). Without an
`--inc-path` pointing at the directory holding `file.vpy`, the parser
only looks in the cwd and alongside the calling `.vpy`. Add the
include directory:

```sh
genesispy --inc-path ./shared --input top.vpy --top top
```

### JSON `Parameters` value comes through wrapped

`config_handler` unwraps `__ArrayType__` / `__HashType__` / `__Val__`
wrappers when it loads JSON, but only at the boundaries it knows
about. Custom nested structures may surface as raw dict / list with
the sentinel keys still visible. Inspect with `--json-out hier.json`
to see the resolved tree, and add an explicit unwrap helper call in
`.vpy` body if you need a particular shape.

### `genesispy.log` appearing in clean repos

`--log` defaults to `genesispy.log` (lazy-opened on first
error/warning). Clean runs do not create the file. Suppress entirely
by passing `--log /dev/null`.

### Debug flags

- `--debug 1` -- enable per-phase progress messages.
- `--debug 2` -- include traceback context on caught errors.
- `--log FILE` -- tee errors and warnings to `FILE` in addition to stderr.

## 15. Behind the curtain

Three core subsystems do the work, backed by two shared modules:

- **`genesispy.template`** -- the `.vpy` parser, generated-module emitter, and runtime. See [interfaces.md](./interfaces.md) sections `genesispy.template.parser` / `emitter` / `runtime` and [code-structure.md](./code-structure.md) §4.
- **`genesispy.unique_module.UniqueModule`** -- the elaborated-instance class. Owns parameter state, sub-instance registration, output buffering, and the bare-name API (`parameter`, `unique_inst`, `instantiate`, `emit`, ...). See `interfaces.md` `genesispy.unique_module.UniqueModule`.
- **`genesispy.manager.Manager`** -- pipeline orchestrator: parse, elaborate (DFS from `--top`), flush outputs. See `interfaces.md` `genesispy.manager.Manager` and [code-structure.md](./code-structure.md) §3 (Pipeline).

Shared dedup and output state lives in **`genesispy.cache`**
(`MODULE_CACHE`, `OUTFILE_CONTENT_CACHE`, `UNUNIQUE_REGISTRY`,
`OUTFILE_TAGS`); see `interfaces.md` `genesispy.cache` for the
canonical surface. Configuration resolution lives in
**`genesispy.config_handler.ConfigHandler`**; see
`interfaces.md` `genesispy.config_handler.ConfigHandler`.

For incompatibilities relative to Perl Genesis2 (hash algorithm,
post-elaboration dedup, `--json-out` sibling-filename divergence), see
[genesis2-incompatibilities.md](./genesis2-incompatibilities.md).

## Appendix A: j2 syntax

`j2` is genesispy's Jinja2-*like* template flavour: it shares the
delimiter set with the canonical Jinja2 library (`{% %}`, `{{ }}`,
`{# #}`) but the embedded language is **full Python** with **expanded
semantics** -- arbitrary statements, multi-line expressions, and
side-effecting calls inside `{% %}` and `{{ }}`. There is no Jinja2
expression sub-language: no filter pipes, no `is`-tests, no macros,
no `extends`/`block`/`include` keywords. Pass `--j2` (works on both
`genesispy` and `gvpy`) to opt in.

> **`j2` is not stock Jinja2.** The two share delimiters, not
> semantics. Templates written for the canonical Jinja2 library will
> **not** parse here as-is. To port stock Jinja2 sources into the j2
> dialect, see the companion CLI `genesispy-jinja2j2` below.

The deltas vs stock Jinja2:

- Block openers need a trailing `:` -- `{% for x in xs: %}`, not `{% for x in xs %}` (Python syntax).
- Continuations are `{% else: %}` / `{% elif cond: %}`, not `{% else %}` / `{% elif cond %}`.
- No `set` / `macro` / `block` / `extends` / `include` keywords; use Python (`{% x = 1 %}`, `def`, `import`, etc.).
- No filter pipe (`{{ x | upper }}` is bitwise-or in Python); use function calls (`{{ str.upper(x) }}`) or methods (`{{ x.upper() }}`).
- No tests (`is defined`, `is none`); use Python (`x is None`).

Conversely, anything inside `{% %}` / `{{ }}` is full Python -- arbitrary
statements, multi-line expressions, side-effecting calls -- which stock
Jinja2 forbids.

| genesis (default)             | j2 (`--j2`)                    |
|-------------------------------|--------------------------------|
| `//; <python stmt>` line      | `{% <python stmt> %}` line     |
| `` `<python expr>` `` inline  | `{{ <python expr> }}` inline   |
| (no comment form)             | `{# ... #}` (stripped)         |

**Block close**: j2 mode accepts the bare keywords `{% endfor %}`,
`{% endif %}`, and `{% endwhile %}` (matching the upstream Jinja2
spelling -- recommended). The genesis-style sentinel-comment form
`{% # endfor %}` etc. is also accepted for symmetry with `//; # endfor`
in genesis mode. Both forms pop the parser-side block stack; an
unmatched close in either spelling raises
`ParseError("without matching opener")`. Indent rules and block-opener
detection (trailing `:`) are identical to genesis mode.

The bare keywords `endfor` / `endif` / `endwhile` are reserved in
j2-mode `{% %}` directives: a directive whose body strips to exactly
one of these names is always treated as a block close, not as a Python
expression that evaluates a same-named local. Use a different name
(e.g. `endfor_x = ...`) if you need to bind a variable that shadows
them.

The whitespace modifiers `{%-`, `-%}`, `{{-`, `-}}` are accepted as a
syntactic no-op (same output as the unmodified delimiters; no
whitespace-stripping behavior). All three delimiter forms
(`{% %}`, `{{ }}`, `{# #}`) may span multiple physical lines; tracebacks land on the opener line. Selecting the
engine is per run -- engines do not mix within a file.

Example (genesis vs j2):

```
//; W = 4
//; for i in range(W):
wire r`i`;
//; # endfor
```

```
{% W = 4 %}
{% for i in range(W): %}
wire r{{ i }};
{% endfor %}
```

Both produce identical Verilog.

### Brace collisions with Verilog source

Any `{{` in plain text opens a j2 expression and consumes through the
matching `}}` -- including `{{` that the user intends as adjacent
literal braces (genesis-flavour `.vpy` is unaffected). Common Verilog
collisions:

1. **Replication concat `{{N{value}}`** opens with `{{`, which the parser would consume as an expression. Escape with a leading backslash: `\{{N{value}}` emits a literal `{{`. Implemented at `template/parser.py` (`\{{` consumes 3 chars, emits `{{`). The same escape covers any other adjacent-brace form (e.g. concat-of-concat `\{{a, b}}` -> `{{a, b}}`).
2. **Single literal `{` immediately before an inline expression** -- e.g. translating genesis `` {`i`{1'b0}} `` to j2 yields the ambiguous `{{{ i }}{1'b0}}`. There is no escape for a bare single `{`. Two workarounds:

   ```
   {{ "{" }}{{ i }}{1'b0}}      # byte-identical output: {3{1'b0}}
   { {{ i }} {1'b0}}            # extra spaces in output: { 3 {1'b0}}
   ```

   The first emits the literal `{` via a tiny string expression and is
   byte-identical to the genesis-flavour output; the second relies on
   Verilog's whitespace insensitivity but inserts visible spaces.

A trailing `}}` in plain text needs no escape -- only `{{` opens an
expression.

Each ported demo carries a j2 twin source tree under
`demos/<demo>/genesis_src.j2/` (the gvpy demo carries
`demos/gvpy/example.j2.vpy`), elaborated via `make gen-j2`. Outputs
land in a parallel `genesis_synth.j2/` directory so the default
`make gen` flow is untouched.

### Porting stock Jinja2 templates

Templates written for the canonical Jinja2 library do not parse under
`--j2` as-is (filter pipes, `is`-tests, missing trailing `:`, etc.).
The companion CLI `genesispy-jinja2j2` mechanically rewrites the
mappable cases:

```sh
# Strict (default): error on the first unmappable construct
genesispy-jinja2j2 stock.j2 -o ported.vpy
genesispy --j2 ported.vpy

# Best-effort: emit `{# TODO(genesispy-jinja2j2): ... #}` placeholders
# for unmappable constructs and warn
genesispy-jinja2j2 --best-effort stock.j2 -o ported.vpy
```

Conversions: block openers gain a trailing `:`, filters become Python
(`x | upper` -> `(x).upper()`, `xs | join(',')` -> `','.join(...)`,
etc.), `is`-tests become Python predicates (`x is defined` ->
`(x) is not None`), `{% set N = E %}` becomes `{% N = E %}`, and
`{% include "f" %}` becomes `{% include("f") %}`. Macros, blocks,
`extends`, `import`, `raw`, and custom filters are unmappable. The
tool requires the optional `jinja2` dependency
(`pip install 'genesispy[import-j2]'`).
