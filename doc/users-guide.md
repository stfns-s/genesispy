# genesispy -- user's guide

This guide covers writing `.vpy` templates, running the `genesispy` and `gvpy` CLIs, and migrating from
Genesis2.

## 1. Syntax

A `.vpy` file is Verilog with two extensions: Python control lines and backtick-interpolated expressions.
Below is a representative example:

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

The legacy Genesis2 extensions `.vp` / `.svp` are intentionally rejected to prevent silently mis-executing
Perl-era `//;` bodies as Python.

### Syntax rules

- **Python lines**: start with `//;`. Indent inside the `//;` body to mark Python block bodies.
- **Block close**: needs a sentinel -- `//; # endfor`, `//; # endif`, `//; # endwhile`. The parser has no
  other way to detect block end.
- **Indent rule**: Python indent = (leading spaces in stripped `//;` content) // 4. Plain-Verilog lines
  inherit the indent of the most recent `//;` line ending in `:` (block opener).
- **Backticks**: `` `expr` `` interpolates a Python expression. Escape with `` \` `` for a literal backtick.
- **String formatting**: use Python f-strings inside backticks -- `` `f"{i:02d}"` `` for zero-padded indices,
  `` `f"{x:02x}"` `` for hex. (The `pp(value, fmt)` helper from upstream gvpy is gvpy-only: available in
  `bin/gvpy`-driven flows, not in genesispy elaboration.)

### Provided functions and short names

Bare names bound automatically inside every generated `execute()` body:

- **`mname`**: unique module name (also available as a callable name `` `mname()` ``).
- **`iname`**: instance name (also available as `` `iname()` ``).
- **`bname`**: base module name (also available as `` `bname()` ``).
- **`sname`**: synonym/unique name (also available as `` `sname()` ``).
- **`parameter(name, val)`**: defines/reads a module parameter. Returns the current value (precedence:
  explicit `unique_inst(..., NAME=VALUE)` kwarg > scoped `--parameter top.X.NAME=VAL` > flat
  `--parameter NAME=VAL` > JSON / `.cfg` > declared default).
- **`generate(base, inst, **params)`** / **`unique_inst(base, inst, **params)`**: request a sub-instance.
  Returns the child `UniqueModule`; useful fields are `.mname` (unique module name), `.iname` (instance
  name), and `.get_param(name)` for resolved parameters.
- **`<child>.instantiate()`**: returns the `<mname> <iname>` header text so backtick-interpolation can
  drop it into the surrounding Verilog (the port list comes after, in plain text).
- **`clone_inst(src_inst, new_iname)`**: another instance of the same unique module, no re-elaboration.
- **`generate_base(base, inst, **params)`** / **`ununique_inst(...)`**: instantiate without uniquification --
  every call reuses the same Verilog module name. Use when you want a single shared module regardless of
  params.
- **`synonym(name)`**: register an additional name for the current unique module; the same Verilog body is
  also written under `<name>.v`.
- **`include(path)`**: parse another `.vpy` and run its body inside the current module's `execute()`
  namespace. Mirrors Genesis2 `//;include("file.vpy")`. Resolves `path` against `--includepath`.
- **`pinclude(path)`**: gvpy-only raw-Python include. Available as a bare name when running under the `gvpy`
  entry point; bound to `None` in standard `genesispy` runs (calling it raises `TypeError`).

A handful of additional bare names mirror the `self.<method>` API for Perl-Genesis2 source compatibility:
`define_param`, `emit`, `unique_inst_param`, `clone` (alias for `clone_inst`), `generate_unq_numeric` /
`generate_unq_param` (numeric- vs param- suffixed `unique_inst*`), and `generate_w_name`. The canonical list
lives in `genesispy.template.aliases.SIMPLE_ALIASES`.

## 2. Walkthrough: `many_iterative_wallace_trees`

Files:

- `genesis_src/top.vpy` -- top-level testbench; sweeps a list of widths.
- `genesis_src/wallace.vpy` -- iterative Wallace-tree reduction, parameterised by `N`.
- `genesis_src/CSA.vpy` -- carry-save adder used by `wallace`.
- `config.json` -- optional per-instance overrides (JSON).
- `config.xml` -- ships *only* in this demo as the Perl-side input for the parity suite (the Perl
  Genesis2 reference reads XML; genesispy reads `config.json`). Convert legacy XML configs in your own
  trees via `genesispy-xml2json`.
- `config.py` -- optional Python `.cfg` overrides (lowest external priority -- JSON and CLI both take precedence).
- `Makefile` -- sets `TOP`/`INPUTS` and pulls in `../genesispy.mk`.

### Build

```
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

### Parameter setting precedence

(Genesis2 ranked XML above `.cfg`; genesispy reverses that for JSON -- see
[genesis2-incompatibilities.md](./genesis2-incompatibilities.md) section 5.)

A parameter's value is determined in the following order (lowest to highest):

1. **In-source default** -- the second argument to `parameter('NAME', default)` in the `.vpy` file. Used when
   nothing else fires.
2. **JSON config** (`--json`) -- per-instance overrides scoped by instance path. Beats the in-source default.
   Legacy XML configs convert via `genesispy-xml2json`.
3. **`.cfg` Python configs** (`--cfg`) -- call `configure(name, value)`. Beats JSON.
4. **CLI `--parameter NAME=VALUE`** (or `-p`, same in gvpy now) -- beats everything passed in files.
5. **Parent's `unique_inst(...)` / `instantiate(...)` kwargs** -- beats CLI. When the parent writes
   `unique_inst('wallace', 'wallace_2', N=2)`, the child sees `N=2` before its body runs, regardless of any
   config or CLI value.

(Genesis2 had a sixth tier, `ImmutableParameters` in JSON, that pinned values past the parent's kwargs.
genesispy does not honour the priority elevation: values nested under `ImmutableParameters` in input JSON
are still read (the lookup recurses structurally and matches on `Name`), but they sit at the same
`EXTERNAL_XML` tier as `Parameters`, so parent kwargs and CLI overrides still beat them.)

**Example:** trace the value of parameter `COND` on the elaborated sub-instance `top.wallace_2` (the
`wallace_2` instance created by `unique_inst('wallace', 'wallace_2', N=2)` in `top.vpy`). Each row below sets
up genesispy differently and shows which priority level applies and what value `COND` takes in the generated
`wallace_unq*.v`:

| Setup                                             | Highest level that fires | Final value |
|---------------------------------------------------|--------------------------|-------------|
| `make gen`                                        | in-source default        | `True`      |
| `make gen JSON_CONFIG=config.json`                | JSON `Parameters`        | `False`     |
| `make gen CFG_CONFIG=config.py`                   | `.cfg` `configure()`     | `True`      |
| `make gen JSON_CONFIG=config.json CFG_CONFIG=config.py` | JSON (beats `.cfg`) | `False`     |
| Same JSON run plus `-p COND=true` on the CLI      | CLI                      | `True`      |

### What `top.vpy` does

```python
//; widths = parameter('WALLACES_WIDTHS', [4, 8])
```

The default `[4, 8]` is used unless JSON/`.cfg` supplies a different list (see the ladder above). Each
iteration of the outer loop:

```python
//; for N in widths:
//;     wallace = unique_inst('wallace', f"wallace_{N}", N=N)
   `wallace.instantiate()` (.pp(pp_`N`), .sum(sum_`N`), .carry(carry_`N`));

//;     wallace_clone = clone_inst(wallace, f"clone_of_wallce_{N}")
   `wallace_clone.instantiate()` (.pp(pp_`N`), .sum(/* ignored */), .carry(/* ignored */));
//; # endfor
```

- `unique_inst('wallace', f"wallace_{N}", N=N)` requests a unique elaboration of `wallace` with `N`
  overridden. genesispy uniquifies by a canonical-JSON SHA over the resolved parameter dict -- two calls with
  the same `N` collapse to a single Verilog module.
- `clone_inst(wallace, ...)` adds another instance of the *same* unique module without re-running `wallace`'s
  body.
- Result depends on the ladder. With JSON `widths=[2,5,16,32,64]`: five unique `wallace_unq*` modules, each
  used twice (`wallace_<N>` + `clone_of_wallce_<N>`). With the in-source default `[4, 8]`: two unique modules
  + two clones. With the `.cfg` widths `[3, 7, 11]`: three of each.

### What `wallace.vpy` does

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

- The Python loop *generates SystemVerilog signals and instances* -- it doesn't emit a SystemVerilog
  `generate` block. genesispy is unrolling at elaboration time.
- `unique_inst('CSA', ..., Width=width-1)` creates one CSA per (step, i), but each unique `Width` resolves to
  a single Verilog module after dedup.
- Backtick interpolation builds signal names: `pp`2*i`_step`step``.

### What `CSA.vpy` does

A two-line carry-save adder:

```verilog
//; width = parameter('Width', 4)
module `mname()` (input logic [`width-1`:0] a,b,c, output logic[`width-1`:0] s, co);
   assign s  = a ^ b ^ c;
   assign co = a&b | b&c | a&c;
endmodule
```

### What `config.json` / `config.py` do

Optional per-instance overrides at two different priority levels (see the ladder above). Without any of them,
the demo falls back to in-source defaults. With them, you get a different RTL.

**`config.json`** -- JSON-native schema. Notable structures:

- `WALLACES_WIDTHS` is an `"__ArrayType__": [...]` -- a plain JSON list, fed into `top.vpy`'s outer loop. (The
  double-underscored sentinels prevent collisions with user hash keys.)
- Each `wallace_<N>` entry under `SubInstances` carries `ImmutableParameters` (the `N` override -- read at
  `EXTERNAL_XML`, same tier as `Parameters`; the per-instance kwargs from `unique_inst('wallace',
  'wallace_<N>', N=<N>)` in `top.vpy` set the same value at the `INHERITANCE` tier),
  `Parameters` (`COND`, `ParamHash`, plus showcase keys like `ParWithMin`, `ParamComplexStruct`),
  and a `UniqueModuleName` (`wallace_unq1` ... `wallace_unq5`).
- `clone_of_wallce_<N>` entries carry only `"CloneOf": {"InstancePath": ...}` and reuse the source's
  `UniqueModuleName` -- that's how genesispy records the clone relationship in the elaborated hierarchy.
- The showcase keys (`ParWithMin`, `ParWithMax`, `ParamComplexStruct`, ...) are not consumed by the RTL; they
  exercise the schema's range encodings (`Min`/`Max`/`Step`), `__HashType__`, nested arrays, and
  `InstancePath` references for the parser tests.

**`config.py`** -- a tiny Python script using `configure(name, value)`. Three lines override
`WALLACES_WIDTHS`, `COND`, and `ParamHash`. It is at the lowest level of the external priority ladder -- JSON,
CLI, and parent kwargs all take precedence over it for any key they set. Useful when you want overrides
expressed in Python (loops, computed values) for keys not also set in JSON.

### Output

Run `make gen`; you get:

- `genesis_synth/top.v`, `wallace_unq1.v` ... `wallace_unq5.v`, `CSA_unq*.v` -- one Verilog file per *unique*
  module.
- `genesis_synth/top.vlist` -- flat compile-order file list.
- `genesis_vlog.vf` -- Genesis2-style product list at the demo root (mirror of `top.vlist`).
- `genesis_synth/top.depend` -- Make-style dependency list.
- `genesis_synth/genesispy_clean.sh` -- removes everything `make gen` produced.

Inspect `genesis_synth/top.v` to see the unrolled instance sequence the loops in `top.vpy` produced.

## 3. CLI reference: `genesispy`

```
genesispy --input top.vpy --input child.vpy --top top --json config.json
# or short:
genesispy -i top.vpy -i child.vpy -t top -j config.json
```

> **Legacy XML configs:** genesispy is JSON-only. Convert once with
> `genesispy-xml2json in.xml out.json` and pass the `.json`. The reverse
> helper `genesispy-json2xml` is provided for symmetry. See section 5
> (Migrating from Genesis2) for the conversion notes.

Flags are grouped by pipeline phase. `--generate-only` is named for historical reasons but lives in the
elaborate group: it skips the parse phase and runs only the elaborate step.

### General

- `-h`, `--help` -- show help and exit.
- `--version` -- print version and exit.
- `-d`, `--debug LEVEL` -- debug verbosity level (default: `0`).
- `--log FILE` -- tee error/warning messages to `FILE` (in addition to stderr).
- `--clean` -- delete generated files and exit.
- `-t`, `--top NAME` -- name of the top module.
- `--synthtop PATH` -- synthesis-top instance: a top-level instance name (e.g. `core`) or dotted instance path
  (e.g. `top.core`) bounding the synth cone. Instances at or under this path emit to `genesis_synth/`, all
  others to `genesis_verif/`. When omitted (Genesis2 default), every emitted file goes to `genesis_verif/`.

### Generate (`.vpy` -> `.py`)

- `-i`, `--input FILE` -- source `.vpy` file to process. Repeatable.
- `-l`, `--inputlist FILE` -- listfile of inputs (bare paths or GNU directives
  `--input/--inputlist/--srcpath/--includepath`; inline `# ...` comments allowed; recursive). Repeatable.
- `--srcpath DIR` -- `.vpy`/source search directory (consulted by `--input`). Repeatable.
- `--includepath DIR` -- search directory for `--input` resolution and for `include(...)` calls inside `.vpy`
  bodies. Repeatable.
- `--pythonpath DIR` -- prepend `DIR` to `sys.path` before parsing. Repeatable.
- `--pymodule NAME` -- import a Python module before parsing. Repeatable.
- `--parse-only` -- run only the parse phase (`.vpy` -> `.py`); skip elaboration.
- `--gen-raw` -- also emit unprocessed Verilog into `<raw_dir>/`.
- `--use-tmp` -- place the raw directory under a `/tmp` scratch dir.
- `--keep-tmp` -- keep the `/tmp` scratch dir after exit (implies `--use-tmp`).

### Elaborate (`.py` -> Verilog)

- `--generate-only` -- skip the parse phase; expect generated `.py` files in `raw_dir`. (Despite the name,
  this runs the elaborate step only.)
- `-j`, `--json FILE` -- input JSON configuration file. Legacy XML configs: convert with `genesispy-xml2json`
  first.
- `--jsonout FILE` -- write a `HierarchyTop` snapshot of the elaborated module tree (port of Perl
  `-hierarchy`). Emits three files in `dirname(FILE)`: `FILE` (full), `small_<basename(FILE)>` (no
  `ImmutableParameters`), `tiny_<basename(FILE)>` (only params with priority `>= EXTERNAL_XML` -- JSON, CLI,
  parent-kwargs, and force-pinned; `.cfg` `configure(...)` overrides at `EXTERNAL_CONFIG` are excluded by
  design, matching Perl `ConfigHandler.pm::extract_stats`). Requires elaboration; errors if no top instance
  was built.
- `--cfg FILE` -- input Python config script (uses `configure(name, value)`). Repeatable.
- `--cfgpath DIR` -- search directory for `--cfg`/`--json` and for `include(...)` calls inside `.cfg` files.
  Repeatable.
- `-p`, `--parameter NAME=VALUE` (or `PATH.NAME=VALUE`) -- command-line parameter override. Plain `NAME=VALUE`
  applies to any instance whose body calls `parameter('NAME', ...)`. Dotted form (e.g. `top.child2.x=2`)
  applies only to the instance at that exact full path; rightmost dot separates path from name. Repeatable.
- `--no-module-cache` -- disable the unique-module dedup cache (forces fresh modules).
- `--unqstyle numeric|param` -- module uniquification style (default: `numeric`). Controls `generate(...)`
  dispatch.
- `--flavor synth|verif|both` -- which output flavour to emit (default: `both`).
- `--outputdir DIR` -- output directory (default: `genesis_synth`). When set, also supplies the default for
  `--synth-dir` and `--verif-dir`.
- `--synth-dir DIR` -- directory for synth-tagged Verilog (default: `--outputdir` if set, else
  `genesis_synth`).
- `--verif-dir DIR` -- directory for verif-tagged Verilog (default: `--outputdir` if set, else
  `genesis_verif`).
- `--suffix EXT` -- file extension for emitted Verilog files (default: `.v`). Leading dot added if missing.
- `-sv`, `--systemverilog` -- shortcut for `--suffix sv`. Mutually exclusive with `--suffix`.
- `--stdout` -- write generated Verilog to stdout instead of `genesis_synth`/`genesis_verif`. Skips
  `.vlist`/`.depend`/clean script and removes the raw dir on exit.
- `--product FILE` -- write Genesis2-style product file lists `FILE.synth` and `FILE.verif`.
- `--depend FILE` -- override the dependency-list output path (default: `<top>.depend`).
- `--pathfile FILE` -- write the list of directories touched during elaboration to `FILE`.

## 4. `gvpy` flat-preprocessor mode

`gvpy` is a companion console script for a gvpy/gvp-style flat preprocessor workflow on top of the same
parser/runtime: single input file, `--parameter NAME=VALUE` (or `-p`) flat parameters, output to stdout, no
synth/verif directory split.

```
gvpy --gvpy-strict --mname top --parameter WIDTH=8 top.vpy > top.v
# or short:
gvpy --gvpy-strict --mname top -p WIDTH=8 top.vpy > top.v
```

Use it when you want gvpy semantics (record-only `generate`/ `instantiate`, `pinclude()` raw-Python include)
instead of genesispy's full elaboration pipeline. See `demos/gvpy/` for a worked example.

Usage: `gvpy [options] FILE [FILE ...]` (output goes to stdout).

- `--mname NAME` -- top module name (default: input filename stem).
- `--libdirs DIR[,DIR...]` -- comma-separated dirs to add to `sys.path`. Repeatable.
- `--incdirs DIR[,DIR...]` -- comma-separated dirs for `include()`/`pinclude()` search. Repeatable.
- `-p`, `--parameter NAME=VALUE` -- set a flat parameter consulted by `parameter()`. Repeatable. (`--defparam`
  is a deprecated hidden alias; emits a one-time warning.)
- `--comment PREFIX` -- comment prefix of the target language (default: `//`).
- `--gvpy-strict` -- use gvpy's record-only `generate`/`instantiate`/`synonym` instead of genesispy's
  elaboration-based versions.
- `--version` -- print version and exit.
- `-h`, `--help` -- show help and exit.

## 5. Migrating from Genesis2

Superficial differences (file extensions, `//;` body language, CLI flag style) are listed below. For
behaviour-affecting incompatibilities -- unique-module hash, JSON-only configs (legacy XML via
`genesispy-xml2json`), post-elaboration dedup -- see
[genesis2-incompatibilities.md](./genesis2-incompatibilities.md).

- **File extension** -- `.vp` -> `.vpy`, `.svp` -> `.svpy`.
- **Config input** -- XML support removed from the core CLI; convert legacy XML once with `genesispy-xml2json
  in.xml out.json` and pass `--json out.json`. The reverse helper `genesispy-json2xml` is provided for
  symmetry.
- **`//;` body language** -- Perl -> Python.
- **`--cfg` config files** -- Perl `eval` -> Python `exec()` (trusted-input, full `__builtins__` exposed --
  mirrors Perl `do FILE`). Files are plain Python; `.py` is preferred over `.cfg`.
- **CLI flag style** -- GNU `--input`/`-i`, `--top`/`-t`, ... (Genesis2 used Perl-style `-input`, `-top`).
- **`--inputlist` listfile syntax** -- GNU directives only (`--input/--inputlist/--srcpath/--includepath`);
  Genesis2 used `-input/-inputlist/-srcpath/-incpath`. Bare paths default to `--input`.
- **`--jsonout`** (Perl `-hierarchy`) -- same three-file output (`<f>` / `small_<f>` / `tiny_<f>`) and same
  `HierarchyTop` schema, but emitted as JSON (use `genesispy-json2xml` for XML). The `tiny` variant filters by
  `priority
  >= EXTERNAL_XML`; genesispy's flat-key config lookup cannot replicate Perl's `inherit_param`-aware priority
  assignment, so the `tiny` set may be a strict superset of Perl's (params Perl tags as inherited may appear
  as user-overrides in genesispy).

## 6. Outputs

A `genesispy` run produces:

- `genesis_raw/<stem>.py` -- generated Python module per `.vpy` input.
- `genesis_synth/<module>.v` -- elaborated Verilog for instances at or under `--synthtop`. (Empty when
  `--synthtop` is omitted.)
- `genesis_verif/<module>.v` -- elaborated Verilog for instances outside the synth cone (everything when
  `--synthtop` is omitted, mirroring Genesis2's `SynthTop=undef` default).
- `<outputdir>/<top>.vlist` -- full compile-order file list (every emitted `.v`, regardless of synth/verif
  tag).
- `<outputdir>/<top>.vlist.verif` -- emitted only when at least one verif-tagged file exists; lists verif +
  synth_and_verif paths.
- `<top>.depend` -- Make-style dependency list.
- `genesispy_clean.sh` -- sweeps the run's output products.
