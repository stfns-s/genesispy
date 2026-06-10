# genesispy demos

Examples that run the `genesispy` elaborator on the ported demos.
Each demo is self-contained, derived from the matching tree under
upstream `Genesis2/demo/`; parity vs. the Perl reference is checked by
the workspace-level `test_parity/` suite.

## Quick start

```sh
source env_setup.sh        # once per shell, from demos/ or any demo subdir
cd <demo>
make gen                   # elaborate -> genesis_synth/
```

`bin/genesispy` and `bin/gvpy` run from the tree; `pip install -e .` is
not required. `env_setup.sh` prepends `genesispy/bin` to `PATH`.

## Shared infrastructure

### `genesispy.mk`

Included by every demo's `Makefile`. The per-demo `Makefile` is a 3-line shim that sets `TOP`, `INPUTS`, optionally
`JSON_CONFIG`, then `include ../genesispy.mk`.

Targets:

| Target     | Effect                                                          |
|------------|-----------------------------------------------------------------|
| `gen`      | Elaborate `$(TOP)` to `$(OUTPUTDIR)` (default `genesis_synth/`) |
| `pylint`   | `py_compile` the generated Python modules                       |
| `vlint`    | Lint the generated Verilog                                      |
| `lint`     | `pylint` + `vlint`                                              |
| `sim`      | Run a simulator on the generated Verilog                        |
| `cleangen` | Remove elaboration outputs                                      |
| `cleansim` | Remove simulator intermediates (all engines)                    |
| `clean`    | `cleangen` + `cleansim`                                         |

Common overrides:

- `VERILINT=verilator|slang` (default `verilator`)
- `SIMULATOR=verilator|vcs|vlog|iverilog|xrun` (default `verilator`)
- `JSON_CONFIG=<file>` -- passed as `--json-cfg` to `genesispy`
- `CFG_CONFIG=<file>` -- passed as `--cfg`; composes with `JSON_CONFIG`. JSON has higher priority for keys
  set in both
- `EXTRA_FLAGS=...` -- passed verbatim to `genesispy`

See `genesispy/doc/user-guide.md` section 3 for the full `genesispy` flag list.

### `env_setup.sh`

Sourceable shell snippet (bash/zsh). Prepends `genesispy/bin` to `PATH`
so `genesispy` and `gvpy` resolve from the checkout.

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

### `logmult`

Log-arithmetic approximate multipliers. Three include files under
`genesis_src/` define Verilog `function`s: `ilog2.vpy` (integer log2),
`logmult.vpy` (`a*b ~= antilog(log2 a + log2 b)`), and `slogmult.vpy`
(semi-log, `a*b ~= a << log2 b`). The multipliers pull in `ilog2` via
`include()`; wrapper modules (`logmult_wrap.vpy`, `slogmult_wrap.vpy`)
expose each as `a*b -> p` with widths from `unique_inst` parameters. The
`top` instantiates both and self-checks under `` `ifdef SIMULATION ``,
asserting the relative error against the exact product stays within a
documented bound (these are coarse approximations -- worst case near a
factor of two at powers of two). The includes are resolved via
`--inc-path genesis_src` (set in the demo `Makefile`). Entry:
`genesis_src/top.vpy`. `make sim` runs the self-check.

### `gvpy`

Standalone example for the `gvpy` flat-preprocessor entry point (not the full `genesispy` elaborator). Illustrates
backtick expressions, control flow (`for` / `if`), and `pp()`. Run via `bin/gvpy`, not `bin/genesispy`. Entry:
`example.vpy`; no `genesis_src/` subdirectory.

## See also

- `genesispy/doc/user-guide.md` -- full CLI and config reference.
- `genesispy/doc/interfaces.md` -- module-author API reference.
- `test_parity/README.md` -- running parity vs. Perl Genesis2.
