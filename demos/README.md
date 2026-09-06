# genesispy demos

Examples that run the `genesispy` elaborator. Each demo is self-contained. The four ported from the
matching tree under upstream `Genesis2/demo/` are checked for parity vs. the Perl reference by the
workspace-level `test_parity/` suite.

## Quick start

```sh
source env_setup.sh        # once per shell, from demos/
cd <demo>
make gen                   # elaborate -> genesis_synth/
```

From inside a demo subdirectory the path is `source ../env_setup.sh`.

`bin/genesispy` and `bin/gvpy` run from the tree; `pip install -e .` is
not required. `env_setup.sh` prepends `genesispy/bin` to `PATH`.

## Shared infrastructure

### `genesispy.mk`

Included by every demo's `Makefile` except `generation_examples`, `gvpy` and `dsp`, which carry standalone
Makefiles. The per-demo `Makefile` is a 3-line shim that sets `TOP`, `INPUTS`, optionally `JSON_CONFIG`, then
`include ../genesispy.mk`.

Targets:

| Target     | Effect                                                                    |
|------------|---------------------------------------------------------------------------|
| `gen`      | Elaborate `$(TOP)` to `$(OUTPUTDIR)` (default `genesis_synth/`)           |
| `gen-j2`   | Same, from the j2 twin sources; see "j2 twin sources" below               |
| `pylint`   | `py_compile` the generated Python modules                                 |
| `vlint`    | Lint the generated Verilog                                                |
| `lint`     | `pylint` + `vlint`                                                        |
| `sim`      | Run a simulator on the generated Verilog                                  |
| `cleangen` | Remove elaboration outputs (both flavours)                                |
| `cleansim` | Remove simulator intermediates (all engines)                              |
| `clean`    | `cleangen` + `cleansim`                                                   |
| `help`     | Print the target list and the current value of each override variable     |

Common overrides:

- `VERILINT=verilator|slang` (default `verilator`)
- `SIMULATOR=verilator|vcs|vlog|iverilog|xrun` (default `verilator`)
- `JSON_CONFIG=<file>` -- passed as `--json-cfg` to `genesispy`
- `CFG_CONFIG=<file>` -- passed as `--cfg`; composes with `JSON_CONFIG`. JSON has higher priority for keys
  set in both
- `EXTRA_FLAGS=...` -- passed verbatim to `genesispy`
- `VERILATOR_FLAGS=...` / `SLANG_FLAGS=...` -- extra flags for the matching `vlint` linter. `regfile` uses
  the former to waive a WIDTHEXPAND warning on an intended zero-extension

See `genesispy/doc/user-guide.md` section 9 for the full `genesispy` flag list.

### `env_setup.sh`

Sourceable shell snippet (bash/zsh). Prepends `genesispy/bin` to `PATH`
so `genesispy` and `gvpy` resolve from the checkout.

### j2 twin sources

The four Genesis2-derived demos each carry a second copy of their sources rewritten in the j2
directive flavour (`{% %}` / `{{ }}` / `{# #}` instead of `//;` and backticks; see user-guide
Appendix A). The two trees describe the same hardware, so they are a standing check that both
frontend flavours produce the same Verilog -- `test_parity/test_perl_parity.py` runs each demo in
both flavours against the same Perl reference.

| Demo                           | Genesis sources  | j2 sources          |
|--------------------------------|------------------|---------------------|
| `regfile`                      | `genesis_src/`   | `genesis_src.j2/`   |
| `iterative_wallace_tree`       | `genesis_src/`   | `genesis_src.j2/`   |
| `many_iterative_wallace_trees` | `genesis_src/`   | `genesis_src.j2/`   |
| `random_logic`                 | `genesis_src/`   | `genesis_src.j2/`   |
| `gvpy`                         | `example.vpy`    | `example.j2.vpy`    |

`generation_examples`, `include_examples`, `pyinclude_examples` and `dsp` have no j2 twin.

`make gen-j2` elaborates the twin tree with `--j2`. It writes to a parallel set of outputs, so the
two flavours never overwrite each other and `make gen` is unaffected:

| | `make gen` | `make gen-j2` |
|---|---|---|
| Sources     | `genesis_src/`     | `genesis_src.j2/`    |
| Output dir  | `genesis_synth/`   | `genesis_synth.j2/`  |
| Product list| `genesis_vlog.vf`  | `genesis_vlog.j2.vf` |

Override the defaults with `SRCDIR_J2=`, `OUTPUTDIR_J2=`, `VLOG_VF_J2=`. `make cleangen` removes
both flavours' outputs. In the `gvpy` demo the pair is `make gen` -> `example.out.v` and
`make gen-j2` -> `example.j2.out.v`.

## Demos

### `regfile`

Multi-module register file (`reg_file`, `flop`, `cfg_ifc`, `top_flop_only`) wired together at `top`. Single
deterministic variant; no config file. Entry: `genesis_src/top.vpy`.

### `iterative_wallace_tree`

One parametric Wallace-tree multiplier with a small simulation harness. Defaults are set in the template; no
config file. Entry: `genesis_src/top.vpy`.

### `many_iterative_wallace_trees`

The same Wallace core elaborated across an array of widths. Demonstrates multi-variant elaboration -- one `.vpy`
produces several unique modules plus clones -- and the layered config sources. Entry: `genesis_src/top.vpy`. Three
config files are at the demo root:

- `config.json` -- primary; passed via `--json-cfg`.
- `config.xml` -- legacy form, kept for parity. Convert once with `genesispy-xml2json in.xml out.json` (the shared
  `genesispy.mk` has a `%.json: %.xml` rule that runs this automatically).
- `config.py` -- low-priority `.cfg` fallback. Both `--json-cfg` and CLI `--parameter` take priority over it; it
  applies under JSON when both are passed.

The local `Makefile` documents the supported invocations; run `make help`
for the current list. Common modes:

| Invocation                                         | `WALLACES_WIDTHS`           | Result                       |
|----------------------------------------------------|-----------------------------|------------------------------|
| `make gen`                                         | `[4, 8]` (defaults)         | 2 unique modules + 2 clones  |
| `make gen JSON_CONFIG=config.json`                 | `[2, 5, 16, 32, 64]`        | 5 unique modules + 5 clones  |
| `make gen CFG_CONFIG=config.py`                    | `[3, 7, 11]`                | 3 unique modules + 3 clones  |
| `make gen JSON_CONFIG=config.json CFG_CONFIG=...`  | JSON values take precedence | 5 unique modules + 5 clones  |

`lint`, `sim`, and `clean` work as in the shared `genesispy.mk`.

### `generation_examples`

Five small tops illustrating the instance-generation primitives
(`unique_inst`, `ununique_inst`, `generate_w_name`,
`synonym`+`generate_base`, `clone_inst`). Each shows a different use:
distinct uniquified modules per parameter set, one shared module under
many instances, renaming the emitted module, registering a synonym up
front, or creating extra instances of an already-elaborated module
without re-running its body. One top per pattern under
`genesis_src/ex<N>_<style>.vpy`, sharing a single `pll.vpy` leaf.
`make gen` elaborates all five into `genesis_synth_ex<N>/`;
`make ex<N>_<style>` runs just one. See the demo's own `README.md` for
source listings, commands, and the expected Verilog per example.

### `random_logic`

Nested parametric one-hot mux. Generates six unique modules from hardcoded loops over signal and mux widths. No config.
Entry: `genesis_src/top.vpy`.

### `include_examples`

The `include()` mechanism on its own, with gray-code conversion as filler arithmetic. Three files under
`genesis_src/`. `gray.vpy` emits one Verilog `function` per include, encoding or decoding, generated one
XOR per bit; it takes `func_name`, `width`, `direction` (`encode` or `decode`) and `lifetime`, and calls
`error()` on a bad width or direction. `codec.vpy` includes `gray.vpy` twice under derived names and emits
a round-trip function `decode(encode(x))`, which must return `x`; it calls `warning()` at `width` 1, where
gray coding is the identity and the round trip proves nothing. `top.vpy` includes `codec.vpy` once per
width and `gray.vpy` once directly, so the emitted functions come from two nesting levels.

There is no wrapper module: every function lands in `top`. Each leaf reports its output width back to its
caller by setting an attribute on `self` named after the function it generated, which is how `codec.vpy`
learns the width of the halves it just included, and `top.vpy` the width of the round trip.

The width set comes from `widths = sorted({3, parameter('WIDTH', 5)})`. A scalar parameter rather than a
list, because the CLI coerces scalars only and a list-valued `-p` would arrive as a string. The fixed 3
keeps two round-trip functions in every build, so one leaf is always included twice under different names;
the set collapses to one when `WIDTH` is 3. `EXTRA_FLAGS` is a full override, not an append, so reaching
the two diagnostic paths means repeating the include path:
`make gen EXTRA_FLAGS='--inc-path genesis_src -p WIDTH=1'` hits the `warning()`, `-p WIDTH=0` the
`error()`, which writes no file.

`top` self-checks under `` `ifdef SIMULATION ``: every code of every width through the round trip, and the
directly included encoder against a table computed at elaboration time. Leaves resolve via
`--inc-path genesis_src`, set in the demo `Makefile`. Entry: `genesis_src/top.vpy`. `make sim` runs the
self-check and prints `include_examples: all vectors PASS`.

### `pyinclude_examples`

The `pyinclude()` mechanism on its own, with a saturating fixed-point accumulator as filler
arithmetic. Three `.vpy` files under `genesis_src/` and two plain Python helper libraries under
`lib/`, reached with `--py-path lib`.

`pyinclude()` execs a raw `.py` into the *calling code's own* namespace, so the names it defines
stay reachable as bare names -- unlike `include()`, whose snippet gets a fresh namespace and hands
values back on `self`. The demo exists to make that rule visible, and each module emits a comment
naming what it can actually see:

| File                    | pyincludes    | Emits |
|-------------------------|---------------|-------|
| `genesis_src/top.vpy`   | `emitters.py` | `decl_signed, check_eq` -- not `acc_width` |
| `genesis_src/leaf.vpy`  | `fixed.py`    | `acc_width, sat_bounds` -- not `decl_signed` |
| `genesis_src/frag.vpy`  | `fixed.py`    | included into `top` by `include()`; `(none)` leak back |

So the three namespaces are disjoint: `top` and `leaf` are separate generated modules, and
`frag.vpy` is an `include()`'d snippet whose own `pyinclude` dies with it. `top` reads the
accumulator width back from the leaf with `get_param` rather than re-deriving it, because it
cannot call `acc_width` itself.

`lib/emitters.py` shows the other half of the rule: a pyinclude'd file has no `self`, so its
emitters take the module as their first argument (`decl_signed(self, 'reg', w, 'exp_hi')`).
Nothing is seeded into the namespace, because a generated module's globals are shared by every
instance of that template.

`top` self-checks under `` `ifdef SIMULATION ``: it drives twice as many terms as the accumulator
is sized for, in both directions, and checks the result clamps at the bounds `lib/fixed.py`
computed. `make sim` prints `pyinclude_examples: all vectors PASS`. The leaf rejects a `TERM_W`
outside 2..24 and any parameter pair whose accumulator would exceed `ACC_W_MAX`, so
`make gen EXTRA_FLAGS='--inc-path genesis_src --py-path lib -p TERM_W=40'` reaches the first
`error()`. Entry: `genesis_src/top.vpy`.

### `gvpy`

Standalone example for the `gvpy` flat-preprocessor entry point (not the full `genesispy` elaborator). Illustrates
backtick expressions, control flow (`for` / `if`), and `pp()`. Run via `bin/gvpy`, not `bin/genesispy`. Entry:
`example.vpy`; no `genesis_src/` subdirectory.

### `dsp`

A fixed-point DSP library, and the widest exercise of the tool in this tree: 17 arithmetic functions pulled in with
`include()` (`functions/f_*.vpy`), three synthesizable tops (`modules/iir.vpy`, `modules/intg.vpy`,
`modules/spec_mux.vpy`), a Python helper library reached through `--py-path` (`lib/qfmt.py`, `lib/vexpr.py`), and
one testbench per function and per module run over a sweep of configurations. The templates emit SystemVerilog, so
both generator call sites pass `-sv` and the output is `.sv` -- the only demo that covers that path.

The `Makefile` is its own -- `genesispy.mk` is not included, there is no `genesis_src/` and no j2 twin. Its targets are
`gen`, `pylint`, `vlint`, `lint`, `sim`, `pytest`, `test`, `test-extra`, `test-smoke`, `plot` and `clean`; everything
generated lands in `build/<top>/default/`. `make test` needs `iverilog` and `make plot` needs matplotlib, neither of
which the other demos use.

`genesispy/tests/test_demo_dsp.py` covers `gen`, `pylint`, `pytest`, `vlint` and `clean`, and CI runs the same
three of those it runs for the other demos. `make test` stays out of both: it sweeps roughly 124 configurations
through a simulator, so it is the demo's own gate, run by hand. `test_parity/` does not cover it -- there is no Perl
reference.

Entry: `modules/iir.vpy` and `modules/intg.vpy`, one top each. See the demo's own `README.md` for the build layout
and the testbench flow.

## See also

- `genesispy/doc/user-guide.md` -- full CLI and config reference.
- `genesispy/doc/interfaces.md` -- module-author API reference.
- `test_parity/README.md` -- running parity vs. Perl Genesis2.
