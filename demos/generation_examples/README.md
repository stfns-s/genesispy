# Generation examples

Five tops that instantiate **the same** `pll.vpy` module in five
different ways. Each section shows the top source, how the same
underlying template gets elaborated, and the emitted Verilog.

## The shared module

`genesis_src/pll.vpy` -- a trivial parametric module reused by every
example:

```verilog
//; M = parameter('M', 8)
module `mname` (input clk_in, output clk_out);
   assign clk_out = clk_in;  // M=`M`
endmodule
```

Each example below picks a different generation primitive
(`unique_inst`, `ununique_inst`, `generate_w_name`, `synonym` +
`generate_base`, `clone_inst`) and emits a different module shape:
several `pll_unq*.v`, one bare `pll.v`, a renamed `my_pll.v`, or
multiple instances of one `pll_unq1.v`.

## Running

```sh
make gen                  # elaborate all five
make ex1_unique           # just example 1 (similar: ex2_ununique, ex3_genwname, ...)
make vlint                # verilator --lint-only over all five outputs
make clean
```

`make gen` elaborates each top into its own `genesis_synth_ex<N>/`
output directory. Equivalent direct invocation (example 1):

```sh
genesispy --input ex1_unique.vpy --input pll.vpy --top ex1_unique \
          --src-path genesis_src --out-dir genesis_synth_ex1
```

## 1. Distinct uniquified modules via `unique_inst`

Three `unique_inst` calls with **different resolved parameters** ->
three distinct uniquified modules (`pll_unq1.v`, `pll_unq2.v`,
`pll_unq3.v`), each instantiated once.

### `ex1_unique.vpy`

```verilog
//; multipliers = [2, 4, 8]
//; insts = []
//; for m in multipliers:
//;     insts.append(unique_inst('pll', f'u_pll_x{m}', M=m))
//; # endfor
module `mname` (input clk_in, output [`len(multipliers)-1`:0] clk_out);
//; for i, u in enumerate(insts):
   `u.instantiate()` (.clk_in(clk_in), .clk_out(clk_out[`i`]));
//; # endfor
endmodule
```

### Output

```
genesis_synth_ex1/
├── ex1_unique.v
├── pll_unq1.v       # M=2
├── pll_unq2.v       # M=4
└── pll_unq3.v       # M=8
```

```verilog
module ex1_unique (input clk_in, output [2:0] clk_out);
   pll_unq1 u_pll_x2 (.clk_in(clk_in), .clk_out(clk_out[0]));
   pll_unq2 u_pll_x4 (.clk_in(clk_in), .clk_out(clk_out[1]));
   pll_unq3 u_pll_x8 (.clk_in(clk_in), .clk_out(clk_out[2]));
endmodule
```

### Notes

- `unique_inst` is the default generation primitive: distinct resolved
  parameters always produce distinct uniquified modules. Calls that
  happen to resolve to the same parameter set collapse onto a single
  unique module (post-elaboration dedup).
- The numeric suffix (`_unq1`, `_unq2`, ...) is the default style.
  `--unq-style param` (or `unique_inst_param`) encodes the parameters
  in the name instead (e.g. `pll_M2.v`).
- Examples 2-4 cover the opposite pattern: a **single** emitted module
  shared across multiple instances.

## 2. One bare-name module shared by many instances: `ununique_inst`

A single module emitted under the bare base name (`pll.v`, no `_unq`
suffix), instantiated three times under different instance names.

### `ex2_ununique.vpy`

```verilog
//; insts = []
//; for i in range(3):
//;     insts.append(ununique_inst('pll', f'u_pll{i}', M=8))
//; # endfor
module `mname` (input clk_in, output [2:0] clk);
//; for i, u in enumerate(insts):
   `u.instantiate()` (.clk_in(clk_in), .clk_out(clk[`i`]));
//; # endfor
endmodule
```

### Output

```
genesis_synth_ex2/
├── ex2_ununique.v
└── pll.v
```

```verilog
module ex2_ununique (input clk_in, output [2:0] clk);
   pll u_pll0 (.clk_in(clk_in), .clk_out(clk[0]));
   pll u_pll1 (.clk_in(clk_in), .clk_out(clk[1]));
   pll u_pll2 (.clk_in(clk_in), .clk_out(clk[2]));
endmodule
```

### Notes

- The first `ununique_inst('pll', ..., M=8)` writes `pll.v`; calls 2
  and 3 carry the **same resolved params** and alias to it -- no
  re-elaboration, just new instance names. Differing params across
  calls would raise `ElaborationError` (only one bare `pll.v` can be
  emitted).
- `generate_base(...)` is a bare-name alias for `ununique_inst(...)`
  (Genesis2 source-level compat) -- same method, either name works.
- The plain-Verilog instantiation line uses `` `u.instantiate()` `` to
  interpolate the `<mname> <iname>` header followed by a literal
  port-binding list. Equivalent form: an explicit
  `emit(u.instantiate(clk_in=..., ...))` inside `//;` with ports as
  kwargs.
- Every `//; for` block needs the `//; # endfor` sentinel; without it
  the parser cannot detect the block end.
- To pick a custom module name instead of `pll.v`, use
  `generate_w_name(...)` -- example 3.

## 3. Custom module name via `generate_w_name`

Same shape as example 2, but the emitted Verilog file gets a chosen
name (`my_pll.v`) rather than the base template name. Useful when the
base name would clash, or when downstream tools expect a specific
filename.

### `ex3_genwname.vpy`

```verilog
//; insts = []
//; for i in range(3):
//;     insts.append(generate_w_name('pll', 'my_pll', f'u_pll{i}', M=8))
//; # endfor
module `mname` (input clk_in, output [2:0] clk);
//; for i, u in enumerate(insts):
   `u.instantiate()` (.clk_in(clk_in), .clk_out(clk[`i`]));
//; # endfor
endmodule
```

### Output

```
genesis_synth_ex3/
├── ex3_genwname.v
└── my_pll.v          # synonym name, not 'pll'
```

```verilog
module ex3_genwname (input clk_in, output [2:0] clk);
   my_pll u_pll0 (.clk_in(clk_in), .clk_out(clk[0]));
   my_pll u_pll1 (.clk_in(clk_in), .clk_out(clk[1]));
   my_pll u_pll2 (.clk_in(clk_in), .clk_out(clk[2]));
endmodule
```

### Notes

- `generate_w_name` is idempotent on the `(base, gen)` synonym pair --
  same-params aliasing happens inside `ununique_inst` as before.
- The same result is obtainable by splitting the synonym registration
  out of the loop -- example 4.

## 4. Same result via `synonym` + `generate_base`

`generate_w_name(base, gen, inst, **params)` is shorthand for a
class-level synonym registration plus an ununiquified instantiation.
The split form is occasionally cleaner when the synonym registration
belongs in a setup block separate from the instance loop.

### `ex4_synonym.vpy`

```verilog
//; synonym('pll', 'my_pll')
//; insts = []
//; for i in range(3):
//;     insts.append(generate_base('my_pll', f'u_pll{i}', M=8))
//; # endfor
module `mname` (input clk_in, output [2:0] clk);
//; for i, u in enumerate(insts):
   `u.instantiate()` (.clk_in(clk_in), .clk_out(clk[`i`]));
//; # endfor
endmodule
```

### Output

Same shape as example 3 (output dir is `genesis_synth_ex4/`):

```verilog
module ex4_synonym (input clk_in, output [2:0] clk);
   my_pll u_pll0 (.clk_in(clk_in), .clk_out(clk[0]));
   my_pll u_pll1 (.clk_in(clk_in), .clk_out(clk[1]));
   my_pll u_pll2 (.clk_in(clk_in), .clk_out(clk[2]));
endmodule
```

### Notes

- `synonym('pll', 'my_pll')` delegates to `Manager.synonym_class`,
  which creates a dynamic subclass of `pll` named `my_pll` and
  registers it -- subsequent class lookups by `'my_pll'` resolve to it.
- `generate_base('my_pll', ...)` is the bare-name alias of
  `ununique_inst('my_pll', ...)`. Since `my_pll` is now a registered
  class, passing it as a string works just like a real template.
- Re-running `synonym('pll', 'my_pll')` with the same pair is a no-op,
  so the split form is safe to put inside a loop as well.

## 5. Many instances of one unique module via `clone_inst`

Elaborate one uniquified module, then create additional instances of
it without re-elaboration. The emitted module keeps the `_unq` suffix
(unlike examples 2-4, which strip it).

### `ex5_clone.vpy`

```verilog
//; src = unique_inst('pll', 'u_pll0', M=8)
//; insts = [src] + [clone_inst(src, f'u_pll{i}') for i in range(1, 3)]
module `mname` (input clk_in, output [2:0] clk);
//; for i, u in enumerate(insts):
   `u.instantiate()` (.clk_in(clk_in), .clk_out(clk[`i`]));
//; # endfor
endmodule
```

### Output

```
genesis_synth_ex5/
├── ex5_clone.v
└── pll_unq1.v          # note the _unq1 suffix (kept, unlike examples 2-4)
```

```verilog
module ex5_clone (input clk_in, output [2:0] clk);
   pll_unq1 u_pll0 (.clk_in(clk_in), .clk_out(clk[0]));
   pll_unq1 u_pll1 (.clk_in(clk_in), .clk_out(clk[1]));
   pll_unq1 u_pll2 (.clk_in(clk_in), .clk_out(clk[2]));
endmodule
```

### Notes

- `clone_inst(src, new_iname)` (alias `clone(...)`) takes an
  already-elaborated `UniqueModule` and a new instance name. It does
  **not** accept `**params`; the clone reuses the source's resolved
  parameters. Override params -> use `unique_inst`.
- vs. example 2 (`ununique_inst` same-params aliasing): same outcome
  (one emitted module, multiple instances) but **different module
  name** -- `clone_inst` keeps the source's uniquified name
  (`pll_unq1`); `ununique_inst` strips it to the bare base (`pll`).
- vs. a second `unique_inst(..., M=8)`: post-elaboration dedup would
  also collapse it, but `unique_inst` still runs the param override
  pass and pre-elaboration setup each time. `clone_inst` skips both --
  use it when you explicitly want "another instance of *this exact*
  module."
