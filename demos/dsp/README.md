# dsp

Fixed-point DSP building blocks for hardware, written as genesispy templates. This is the
largest example in the tree. The templates emit SystemVerilog, so every generator run passes
`-sv`, which maps `.vpy` input to `.sv` output instead of the default `.v`.

## Requirements

The genesispy generator, which is the enclosing repository. `env_setup.sh` one directory up
puts the in-tree launcher on `PATH`:

```sh
source ../env_setup.sh
```

The rest are the tools the make targets run:

- `iverilog`, in 2012 mode: `make test`
- `verilator`: `make test-extra`, `make plot`, and `vlint` by default
- `vcs`, `vlog` (Questa) or `xrun`: optional, and only for `make sim`, which drives any of
  them; `verif/run-tb.sh` takes `verilator`, `iverilog` or `gen` alone
- `pytest`: the Q format library tests
- matplotlib: `verif/plot.py`, installed with `pip install -r verif/requirements.txt`

## Directory structure

```text
functions/          arithmetic functions, pulled in with include()
lib/                qfmt.py and vexpr.py, imported by the templates; on --py-path
  tests/            pytest suite for both
modules/            synthesizable modules, one top each
verif/
  functions/        tb_f_<name>.vpy, one testbench per function
  modules/          tb_<name>.vpy, one testbench per module
  common/           tb_util.vpy (fdiv, clamp, tb_sext, check, data and report tasks) and
                    tb_ref_log2.vpy (64-bit f_log2 reference, shared by the three log tests)
  sweeps.mk         which configurations make test runs
  run-tb.sh         generate, build and run one testbench in one configuration
  plot.py           plot a data file
  requirements.txt  matplotlib, for plot.py
build/              everything generated; not in git
```

`build/` holds one directory per top and configuration, named after the genesispy top, and under it
one directory per simulator, for instance `build/tb_f_round/IW8_OW6/iverilog/`:

```text
raw/                  generated Python intermediates
synth/                the DUT, when the testbench instantiates one
verif/                the elaborated testbench, and gen.log from generating it
tb.vf                 file list naming both synth/ and verif/
build.log             what the build printed
run.log               what the run printed, including the simulator's $finish line
data.csv              the per-case data file, when the run was asked for one
obj/ or sim.vvp       the built binary, verilator or iverilog
tb_<name>.depend      the included functions, for make's dependency tracking
genesispy_clean.sh    genesispy's own cleanup script
```

`gen` is a simulator name here too: an elaborate-only run lands in `gen/`, which is where
`make sim` picks up its file list. `make sim` writes its own artifacts to `sim/` beside it.

Each simulator gets a whole tree of its own rather than sharing the generated Verilog. Generation
is deterministic, so the trees hold the same Verilog either way; what the separation buys is that
no two runs ever write the same file, which is what lets `make -j test test-extra` run both
simulators over one configuration at once.

`lib/` holds the utility functions the templates import at generation time:

- `qfmt.py`: defines fixed-point formats and derives the widths they imply.
- `vexpr.py`: common Verilog expression generation utilities:
  literals, sign extension, zero padding, declarations, and expression trees.

[lib/README.md](lib/README.md) defines the Q format and documents both modules call by call.

## Function library

Each function is emitted under the name given by `func_name`, defaulting to the file's own name.
Every function also accepts `lifetime` (`static` or `automatic`). Most take their operand width as
`iwidth`; the two multipliers take `awidth` and `bwidth` instead, and `f_qcvt` takes Q-format
strings.

| File              | Does                                                    | Also accepts              |
|-------------------|---------------------------------------------------------|---------------------------|
| `f_abs.vpy`      | absolute value, saturating at the most negative input   | `approx`, `isym`          |
| `f_negate.vpy`   | two's complement negate                                 | `approx`, `isym`          |
| `f_sym.vpy`      | map the most negative value to one above it             | --                        |
| `f_sat.vpy`      | narrow the width, saturating on overflow                | `owidth`, `osym`          |
| `f_trunc.vpy`    | narrow the width by dropping low bits                   | `owidth`, `osym`          |
| `f_round.vpy`    | narrow the width, rounding half up, clamped on overflow | `owidth`, `osym`          |
| `f_sx.vpy`       | sign extend to a wider word; errors if not wider        | `owidth`                  |
| `f_sh.vpy`       | shift either way by a signed count, saturating          | `cwidth`                  |
| `f_shleft.vpy`   | shift left, saturating                                  | `cwidth`, `osym`          |
| `f_shright.vpy`  | shift right, saturating                                 | `cwidth`, `osym`          |
| `f_s2sm.vpy`     | two's complement to sign magnitude                      | `owidth`, `sm_plus`       |
| `f_sm2s.vpy`     | sign magnitude to two's complement                      | `owidth`, `sm_plus`       |
| `f_umod.vpy`     | unsigned remainder, by shift and subtract               | --                        |
| `f_log2.vpy`     | integer log2, as `{ sign, log2(abs x) }`                | `isym`, `approx`, `lfrac` |
| `f_logmult.vpy`  | multiply by adding logs                                 | see below                 |
| `f_slogmult.vpy` | multiply by shifting, `a * b =~ a << log2(b)`           | see below                 |
| `f_qcvt.vpy`     | convert between Q formats, rounding and saturating      | see below                 |

| Option              | Default       | Meaning                                                         |
|---------------------|---------------|-----------------------------------------------------------------|
| `iwidth`            | `8`           | input width in bits                                             |
| `owidth`            | `6`/`16`/`8`  | output width: narrowing functions / `f_sx` / `f_s2sm`, `f_sm2s` |
| `cwidth`            | `4`           | shift count width in bits                                       |
| `lifetime`          | `static`      | SystemVerilog function lifetime                                 |
| `approx`            | `0`/`1`       | negate as `~x` instead of `~x + 1`: one adder for one LSB       |
| `isym` / `osym`     | `0`           | input / output already symmetric, so no clamp is needed         |
| `sm_plus`           | `1`           | in sign magnitude, a set MSB means positive                     |
| `awidth`/`bwidth`   | `8`           | multiplier operand widths, in place of `iwidth`                 |
| `lfrac`             | `0`           | fractional bits in the log returned by `f_log2`                 |
| `iapprox`/`oapprox` | `1`/`0`       | approximate the input / output negate of a multiplier           |
| `q_in`/`q_out`      | `Q4.4`/`Q2.2` | `f_qcvt` source and target format, `Qm.n` or `UQm.n`            |
| `round_mode`        | `trunc`       | `f_qcvt` rounding, one of the five `qfmt.ROUND_MODES`           |
| `src_lo`/`src_hi`   | `None`        | `f_qcvt` source code range that actually arrives                |
| `saturate`          | `1`           | `0` rejects an `f_qcvt` configuration whose clamp can trigger   |

`approx` defaults to `0` in `f_negate` and `f_abs`, which are exact unless asked otherwise, and to
`1` in `f_log2` and in the multipliers' `iapprox`, where the cheap negate costs one LSB of a value
that is already an approximation. That is the operating point the algorithms were written for. The
`owidth` default differs per function so that each one is usable with no options at all.

`f_sh` and `f_shright` take an extra 2-bit `frac` port giving a finer step than a power of two: the
result is scaled by `1 + frac * 0.25`. Both scale before they shift, so the result is truncated once
rather than once per term. At `sh` of 0 the scaling can push the result past the output range, so
both saturate.

### Log multipliers

`f_log2` returns `{ sign, log2(abs x) }`. The log is the position of the leading one plus one, so a
power of two reports one more than its exponent, and with `lfrac` set the value carries that many
fractional bits: `floor(2**lfrac * log2(2 * m))`, `m` being the magnitude truncated to its top
`lfrac+1` significant bits.

`f_logmult` adds the two logs and shifts back, `f_slogmult` shifts `a` by the log of `b` alone. Both
are approximate. Because the log of a power of two is one high, a product can come out at twice its
true value: `f_log2` returns `floor(log2|x|) + 1`, and `f_logmult` removes only one of the two
offsets, so on a power-of-two pair the product comes out at exactly `2*a*b`. The testbenches check
every case bit-exact against their reference; they carry no relative-error bound, because a bound
loose enough to admit the 2x gain is also satisfied by an output stuck at zero, which scores the
same 100% with the opposite sign.

| Option              | Default | Meaning                                                                     |
|---------------------|---------|-----------------------------------------------------------------------------|
| `awidth` / `bwidth` | `8`     | operand widths                                                              |
| `isym`              | `0`     | operands already use a symmetric range                                      |
| `iapprox`           | `1`     | approximate the negate that takes the input magnitude                       |
| `oapprox`           | `0`     | approximate the negate that signs the result                                |
| `zdet`              | `0`/`1` | force zero when an operand is zero (`1` in `f_slogmult`)                    |
| `alfrac` / `blfrac` | `0`     | fractional bits in each log (`f_logmult` only)                              |
| `antilog`           | `1`     | shift back to a product; `0` leaves it in the log domain (`f_logmult` only) |
| `osm`               | `0`     | leave the output in sign magnitude, not two's complement (`f_logmult` only) |
| `sign_only`         | `0`     | return only the sign, as `+1`, `-1` or `0` (`f_logmult` only)               |

The last four are `f_logmult`'s alone; `f_slogmult` takes only the first five. With `antilog` set,
`alfrac` and `blfrac` are forced to zero and `f_logmult` says so: the antilog of a fractional log is
a root, not a shift. With `antilog` clear and no fractional bits, it also emits
`<func_name>_antilog`, which turns a log-domain result into the product later. Both functions emit
`<func_name>_core`, which takes the logs already taken, so one log function can feed several cores
-- except under `f_logmult`'s `sign_only=1`, which emits neither the log functions nor the core and
reads the two sign bits directly.

### Q-format conversion

`f_qcvt` converts `Qm.n` to `Qm.n`, where `m + n` is the word width and `n` counts fractional
bits. This is the ARM convention, in which `m` includes the sign bit; the Texas Instruments
convention counts it separately and would call the same 16-bit integer `Q15.0` rather than
`Q16.0`. A leading `U` makes the format unsigned. `m` may be zero or negative: the sign bit is part
of the width, not of `m`, so `Q-1.5` is a four-bit signed word holding multiples of 1/32 below 1/4
in magnitude. The function shifts to align the binary points, rounds by `round_mode`, and saturates
into the output range; `osym` clamps the low end one above the most negative value. `trunc` rounds
toward minus infinity, which is what an arithmetic right shift does; `half_up` rounds a tie up,
`half_away` a tie away from zero, `half_even` a tie to the even neighbour, and `to_zero` truncates
toward zero.

`src_lo` and `src_hi` narrow the source range to the codes that actually arrive, so a clamp end no
code can reach is left out of the emitted logic; give neither and both ends are emitted, as before.
`saturate=0` turns a still-reachable clamp into a generation error, for a caller that means to lose
no range. Generation rejects a malformed or bitless format, an unknown `round_mode`, a source range
outside `q_in` or with `src_lo` above `src_hi`, and a reachable clamp under `saturate=0`.

```systemverilog
//; self.include_params = {'func_name': 'f_scale', 'q_in': 'Q4.12', 'q_out': 'Q2.6',
//;                        'round_mode': 'half_even'}
//; include('f_qcvt.vpy')
```

### Q format library

`lib/qfmt.py` is where a template derives a width instead of writing one down: it computes
fixed-point formats and the widths they imply, from exact ranges rather than from a bound on the
widths. `lib/vexpr.py` is the other half, writing the Verilog that denotes a generation-time value
and computing no width of its own. `f_qcvt` gets its shift, rounding constant and clamp bounds from
`qfmt.requant`; its testbench keeps its own arithmetic, so the two stay independent.

## Modules

### `modules/iir.vpy` -- single-pole IIR filter

`H(z) = f / (1 + (f - 1) * z^-1)`, where `f = 2^-mu`, refined by the 2-bit `mf` input to
`f = 2^-mu * (1 + mf * 0.25)`. Both `mu` and `mf` are runtime inputs, so the corner frequency can be
changed without regenerating. The file header lists the 3 dB corner for each `mu`.

`IW`, `OW`, `MW` and `ARST` are all generation-time options. They appear in the emitted module as
Verilog parameters as well, but the module is uniquified per configuration and derives its internal
widths from the generation-time values, so overriding the Verilog parameter on an instance does not
work. `ARST` (default 1) selects an asynchronous or synchronous reset.

Generation rejects `IW` below 2, `MW` below 1, and an `OW` outside `1..IW+2**MW`, which would slice
below the accumulator's least significant bit.

### `modules/intg.vpy` -- integrator

Accumulates `in`, scaled by `2^-mu`, into a wide accumulator and returns its top `OW` bits. With
`lk_en` set, a fraction `2^-lk_mu` of the current output is subtracted each cycle. When `lim` is
nonzero, the output is held within `+/-lim`. The accumulator clamps rather than wrapping on
overflow. `ld` loads `ld_val`, `neg` negates the input, `en` gates updates.

| Parameter    | Default      | Meaning                                             |
|--------------|--------------|-----------------------------------------------------|
| `OW`         | 8            | output width                                        |
| `IW`         | 4            | input width                                         |
| `MW`         | 4            | width of `mu` and `lk_mu`                           |
| `AW`         | `IW+(1<<MW)` | accumulator width                                   |
| `LW`         | `OW>>1`      | how many top bits the leak feedback is taken from   |
| `NEG_APPROX` | 0            | use the cheap negate (see `approx` above)           |
| `ISYM`       | 0            | input is already symmetric, skip the `f_sym` clamp  |
| `DEBUG`      | 0            | reserved; no debug logic at present, and nothing is emitted |

`AW` must be greater than or equal to `OW`, `IW` and `LW`; `OW` must be at least 2; and `LW` must be
at least 2, since the leak negates a signed `LW`-bit word and a one-bit one negates to zero either
way. `LW` defaults to `OW>>1`, so `OW=2` and `OW=3` need an explicit `LW`. Each is checked at
generation time; a violation reports the offending value and writes no file.

### `modules/spec_mux.vpy` -- speculative decision multiplexer loop

Resolves the decision feedback loop that a parallel receiver cannot pipeline by registering. A slicer
array outside the module decides, for every assumed history, the symbol it would return; `spec_mux`
selects the right one for each of `N_SYM` symbols per clock, where the selection for one symbol is
the history the next one is made on:

```text
sym_i   = spec_i[state_{i-1}]
state_i = { state_{i-1}[STATE_W-SYM_W-1:0], sym_i }
```

Written that way a block costs `N_SYM` selects in series. `LOOKAHEAD` composes `LOOKAHEAD+1`
consecutive tables into a single one indexed by the state `LOOKAHEAD+1` symbols back, so the
recursive path is `ceil(N_SYM/(LOOKAHEAD+1))` selects deep instead. The tables are composed newest
first, so every level is one `PAM_N`-to-1 select per entry and the overhead is linear in `LOOKAHEAD`.
The composition reads only module inputs, making it feed-forward: `PIPE_LA` registers it and takes
its levels off the critical path too, at the cost of one more clock of latency. The method is
Parhi's, from "Pipelining of parallel multiplexer loops and decision feedback equalizers" (ICASSP
2004) and "Design of multigigabit multiplexer-loop-based decision feedback equalizers" (IEEE Trans.
VLSI Syst., April 2005).

| Parameter   | Default | Meaning                                                        |
|-------------|---------|----------------------------------------------------------------|
| `N_SYM`     | 32      | symbols resolved per clock                                     |
| `PAM_N`     | 4       | symbol levels, 2 to 16                                         |
| `N_HIST`    | 1       | past symbols the decision is made on                           |
| `LOOKAHEAD` | 2       | look-ahead depth; 0 is the plain serial chain                  |
| `PIPE_LA`   | 0       | register the composed tables, adding a clock of latency        |
| `UNROLL`    | 1       | 0 emits the tables as genvar loops instead of flat assignments |
| `RST_STATE` | 0       | the state held out of reset                                    |
| `MAX_NETS`  | 65536   | cap on composed table entries, a guard against a huge build    |

`UNROLL` changes only the text, not the logic: the unrolled form keeps the rolled loops above it as a
comment, so either build reads the same. A parent generator reads back `SYM_W`, `STATE_W`, `N_SPEC`,
`LATENCY`, `CHAIN_DEPTH`, `COMP_DEPTH` and `N_ENTRIES` from the instance rather than deriving them
again.

Generation rejects a `PAM_N` outside 2 to 16, an `N_HIST` or `N_SYM` below 1, a `LOOKAHEAD` outside
`0..N_SYM-1`, a `RST_STATE` outside `0..N_SPEC-1`, and a table set larger than `MAX_NETS`. The last
one is the check that matters in practice: entries grow as `N_SYM * LOOKAHEAD * PAM_N**N_HIST`, so a
wide history with any look-ahead reaches millions of nets quickly.

## Make targets

| Target                    | Does                                                                      |
|---------------------------|---------------------------------------------------------------------------|
| `gen` (default)           | elaborate every top in `TOPS`                                             |
| `iir`, `intg`, `spec_mux` | elaborate one top                                                         |
| `vlint`, `vlint-<top>`    | lint, with `VERILINT=verilator` (default) or `slang`                      |
| `pylint`                  | `py_compile` the generated Python modules                                 |
| `vlint-tb`                | lint each function testbench with `-Wall`, in every swept configuration   |
| `pytest`                  | the Q format library in `lib/tests`; no simulator                         |
| `lint`                    | `pylint`, `vlint` and `vlint-tb`                                          |
| `sim`                     | run `SIM_TOP` (default `tb_intg`) once under `SIMULATOR`; `DUMP=1` traces |
| `test`                    | `pytest`, plus every function and module under `TB_SIMS`; use `-j`        |
| `test-extra`              | re-run the whole suite under verilator                                    |
| `test-smoke`              | every function and module in its default configuration, both simulators   |
| `test-<name>`             | one function or module, e.g. `test-f_round`, `test-intg`                  |
| `plot`                    | `make plot FUNC=f_shright [CFG=IW=8:CW=4] [OUT=x.png]`                    |
| `clean`                   | remove `build/` and the simulator intermediates                           |

Generation-time options go in `EXTRA_FLAGS_<top>`:

```sh
make intg EXTRA_FLAGS_intg='-p OW=12 -p IW=6 -p ISYM=1'
```

Manually with everything in one directory, the same options are `-p` arguments:

```sh
genesispy -sv --input modules/intg.vpy --top intg \
          --inc-path functions --py-path lib --out-dir build/intg -p OW=12 -p IW=6
```

`--py-path lib` is required: the templates import `vexpr` and `qfmt` from there, and without it
generation stops at `ModuleNotFoundError: No module named 'vexpr'`. Drop `-sv` and the same
Verilog lands in `intg.v`.

This writes `build/intg/intg.sv`, plus `intg.vlist` (file list), `intg.vlist.verif`,
`intg.depend` (dependency list, which tracks the included functions) and `genesispy_clean.sh`.
`modules/iir.vpy` and `modules/spec_mux.vpy` need no `--inc-path`; they include nothing.

A run that gives no `--raw-dir` writes its Python intermediates to `genesis_raw/` in the current
directory, whether it succeeds or fails; genesispy's `.gitignore` covers that.

## Tests

`verif/functions/` holds a self-checking testbench per function: it includes the function under test,
sweeps its whole input space, and compares the result against a reference written in 64-bit
arithmetic. The function works in `IW` bits with slices and two's-complement tricks; the reference
works in 64 bits where nothing overflows. They agree only if the bit manipulation is right.
`verif/modules/` holds one per module, which instantiates it and steps a 64-bit reference alongside,
one clock at a time. There are no vector files. The check happens inside the simulator.

```sh
make test                  # pytest, then every function and module under iverilog; use -j
make test-f_round          # one function
make pytest                # the Q format library, no simulator involved
make test test-extra       # and again under verilator
make -j8 test-smoke        # default configuration only, both simulators
```

`make test` runs iverilog only: it builds in about a sixth of verilator's wall time over the sweep,
and being four-state it is the only one that catches an X coming out of a function, where verilator
turns an X into 0 and notices only when 0 differs from the expected value. `TB_SIMS` picks the
simulators explicitly. Each writes under its own directory, so `make test test-extra` keeps both
sets of logs.

`test-smoke` is the quick check: it runs each function and module once, in its default
configuration, under both simulators, and skips the sweeps entirely. `SMOKE_SIMS` picks the
simulators, and one rule per name means `-j` runs them at once.

The `SWEEP_<name>` tables in `verif/sweeps.mk` list the configurations to try, written per function
because several reject parts of the space. `NEG_<name>` lists configurations the generator must
reject: `make test` fails if one of them generates instead of erroring.

### Writing a testbench

Both simulators have to accept every testbench, so two constructs are barred:

- No `continue` or `break` in a loop. Icarus Verilog 12.0 rejects both with `-g2012`; verilator
  accepts them, so the failure only shows up on the second simulator. Use `if`/`else`.
- No function call inside a ternary (`?:`). Verilator 5.020 aborts with an internal fault when the
  calling function runs in a loop, which every testbench here does. Write `if (sign) ix = neg(ix);`
  instead of `ix = sign ? neg(ix) : ix;`. Plain operators in a ternary are fine.

In a clocked testbench, generate only legal stimulus. Applying an input and then skipping the check
does not stop the clock: the design consumes the input, the reference does not, and the two diverge
from that point on. Step over an excluded value in the loop, or map it to a legal one.

### Waveforms

`tb_util.vpy` wraps its `$dumpvars` in `` `ifdef DUMP ``, so a waveform costs nothing unless asked
for. `verif/run-tb.sh <name> <config> <simulator> -dump` builds with `DUMP` defined and leaves
`dump.vcd` beside the run logs; `make sim DUMP=1` does the same for an interactive run and writes
`dump.vcd` in the repo root, where `make cleansim` removes it. Ask for one on a module testbench: a
function testbench has no clock and finishes at time zero, so its trace holds only the last case.

### Expected failures

`XFAIL_<name>` in `verif/sweeps.mk` lists configurations known to disagree with the function or
module it names. A listed configuration reports `XFAIL` when it mismatches and does not fail the
run; one that passes reports `XPASS` and does fail it, so fixing a function forces the table to be
updated. An entry excuses a wrong answer, never a missing one: a listed configuration that fails to
generate, build, or run reports `ERROR` and still fails the run. `verif/run-tb.sh` separates the two
by exit status, taken from the `PASS` or `FAIL` line the testbench prints rather than the
simulator's own exit code, because verilator aborts with 134 on `$fatal` while iverilog exits 1.

| Status | Meaning                                                                     |
|--------|-----------------------------------------------------------------------------|
| 0      | matches the reference                                                       |
| 1      | ran and mismatched -- the only `XFAIL`-able case                            |
| 2      | usage error                                                                 |
| 3      | generation failed                                                           |
| 4      | build failed                                                                |
| 5      | build produced a verilator warning                                          |
| 6      | ran but reported neither PASS nor FAIL, or passed over no cases             |
| 7      | passed, but a parameter the run asked for is missing from the PASS line     |
| 8      | generation crashed -- a Python traceback, not a rejection the template made |

The tables are currently empty. Every function and module matches its reference on every
configuration.

### Plotting

Each testbench can write a CSV of its inputs, its result and the reference, gated behind a plusarg
so `make test` stays quiet. `verif/plot.py` draws the result solid and the reference dashed, one
pair of lines per distinct value of the leading input columns, and marks differences.
A data file including multiple series is unreadable all at once, so `--key` narrows it:

```sh
make plot FUNC=f_shright CFG=IW=8:CW=2 OUT=shr.png
verif/run-tb.sh f_shright IW=8:CW=2 verilator -plot
verif/plot.py build/tb_f_shright/IW8_CW2/verilator/data.csv --key frac=3 --out shr.png
```

Manually, `verif/run-tb.sh` takes `-data` to write the file and `-plot` to write it and open the plot.
Plotting needs matplotlib, which `make test` does not import: `pip install -r verif/requirements.txt`.
