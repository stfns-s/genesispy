#!/usr/bin/env bash
# Generate, build and run one testbench in one configuration.
#
#   run-tb.sh <name> <config> <simulator|gen> [-data] [-plot] [-dump]
#
# <config> is colon-joined generation parameters, or the word 'default' for none:
#   run-tb.sh f_round IW=8:OW=6 verilator
#   run-tb.sh f_negate default iverilog -data
#   run-tb.sh f_shright IW=8:CW=2 verilator -plot
#
# Output goes to build/tb_<name>/<config>/<simulator>/, one directory per configuration
# and simulator:
#
#   raw/                generated Python intermediates
#   synth/              the DUT, for a module testbench that instantiates one
#   verif/              the testbench
#   tb.vf               file list, naming both synth/ and verif/
#   build.log run.log   what the build and the run printed
#
# Each simulator gets its own generated tree rather than sharing one. Generation is
# deterministic, so the trees hold identical Verilog and the only cost is a second
# elaboration; what it buys is that no two runs ever write the same file, so `make -j
# test test-extra` cannot have one run delete another's output mid-build. In place of a
# simulator, 'gen' elaborates into its own tree and stops, which is how the Makefile's
# sim target gets a testbench it can hand to any of the five simulators it supports.
#
# Exit status is meaningful, because the Makefile's XFAIL tables must apply only to a
# test that actually ran and mismatched -- never to one that failed to generate or build:
#   0  the testbench matches its reference
#   1  the test ran and reported a mismatch
#   2  usage error
#   3  generation failed
#   4  the build failed
#   5  the build produced a verilator warning
#   6  the simulator ran but reported no usable result -- neither PASS nor FAIL, or a
#      PASS over no cases at all
#   7  the run passed, but a parameter this run asked for is missing from the PASS line
#   8  generation crashed -- a Python traceback, not a rejection the template made
set -euo pipefail

readonly RC_MISMATCH=1
readonly RC_USAGE=2
readonly RC_GEN=3
readonly RC_BUILD=4
readonly RC_WARN=5
readonly RC_SIM=6
readonly RC_PARAM=7
readonly RC_CRASH=8

REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly REPO
readonly BUILDDIR="${BUILDDIR:-build}"
readonly TBDIR="${TBDIR:-verif}"
readonly INCDIR="${INCDIR:-functions}"
readonly LIBDIR="${LIBDIR:-lib}"
readonly MODDIR="${MODDIR:-modules}"
readonly GENESISPY="${GENESISPY:-genesispy}"

usage() {
    local rc=${1:-$RC_USAGE}
    local fd=2
    if [[ $rc -eq 0 ]]; then fd=1; fi
    cat >&"$fd" <<'USAGE'
usage: run-tb.sh <name> <config> <simulator> [-data] [-plot] [-dump]

  <name>       function or module under test, e.g. f_round or intg; the testbench is
               verif/functions/tb_<name>.vpy or verif/modules/tb_<name>.vpy
  <config>     generation parameters joined by ':', or the word 'default' for none
  <simulator>  verilator, iverilog, or gen to elaborate only and stop
  -data        also write data.csv next to the run logs, for plot.py
  -plot        as -data, then open the plot in a window
  -dump        build with DUMP defined, so the testbench writes dump.vcd next to the
               run logs. Worth asking for on a module testbench: a function one has no
               clock and finishes at time zero, so its trace holds only the last case.

All three default to off. 'data' without the dash is still accepted.

Run it from the demo root, with genesispy on PATH:

  source ../env_setup.sh

Examples:

  # one function in its default configuration
  verif/run-tb.sh f_sym default verilator

  # a chosen width, then the same case under the other simulator
  verif/run-tb.sh f_round IW=8:OW=6 verilator
  verif/run-tb.sh f_round IW=8:OW=6 iverilog

  # several options at once
  verif/run-tb.sh f_negate IW=5:APPROX=1:ISYM=1 iverilog
  verif/run-tb.sh f_shright IW=8:CW=4:OSYM=1 verilator

  # write the input, output and reference for every case, and plot it in one step
  verif/run-tb.sh f_shright IW=8:CW=2 verilator -plot

  # or keep the data file and plot it yourself, to narrow it down or write a PNG
  verif/run-tb.sh f_shright IW=8:CW=2 verilator -data
  verif/plot.py build/tb_f_shright/IW8_CW2/verilator/data.csv --key frac=3
  verif/plot.py build/tb_f_shright/IW8_CW2/verilator/data.csv --out shr.png

  # a waveform of one module run, next to the logs
  verif/run-tb.sh intg default iverilog -dump

  # elaborate only, leaving tb.vf for a simulator the script does not drive itself
  verif/run-tb.sh intg default gen

  # a whole sweep, or every testbench, comes from make instead
  make test-f_round
  make -j8 test

Exit status: 0 matched, 1 ran and mismatched, 2 usage, 3 generation failed,
4 build failed, 5 verilator warning, 6 ran but reported no usable result,
7 passed without applying every parameter asked for, 8 generation crashed.
USAGE
    exit "$rc"
}

case "${1:-}" in
-h | --help) usage 0 ;;
esac

[[ $# -ge 3 ]] || usage

func=$1
config=$2
sim=$3
shift 3

case "$sim" in
verilator | iverilog | gen) ;;
*)
    echo "run-tb.sh: unknown simulator '${sim}' (verilator|iverilog|gen)" >&2
    exit "$RC_USAGE"
    ;;
esac

want_data=""
want_plot=""
want_dump=""
while [[ $# -gt 0 ]]; do
    case "$1" in
    data | -data) want_data=1 ;;
    -plot)        want_data=1; want_plot=1 ;;
    -dump)        want_dump=1 ;;
    *)
        echo "run-tb.sh: unknown option '$1'" >&2
        usage
        ;;
    esac
    shift
done

if [[ "$sim" == "gen" && (-n "$want_data" || -n "$want_plot" || -n "$want_dump") ]]; then
    echo "run-tb.sh: -data, -plot and -dump need a simulator to run, not 'gen'" >&2
    exit "$RC_USAGE"
fi

tb="tb_${func}"
tag="${config//:/_}"
tag="${tag//=/}"
base="${REPO}/${BUILDDIR}/${tb}/${tag}/${sim}"

pflags=()
if [[ "$config" != "default" ]]; then
    IFS=':' read -r -a settings <<<"$config"
    for setting in "${settings[@]}"; do
        pflags+=(-p "$setting")
    done
fi

# Wipe the whole tree: it belongs to this simulator alone, so nothing else reads it and
# no stale file from an earlier run can survive into this one.
rm -rf "$base"
mkdir -p "${base}/verif"
cd -- "$REPO"

# Every module the testbench instantiates has to be an --input of its own; a module
# testbench drives modules/<name>.vpy, while a function testbench includes its function
# and needs nothing extra. Only the former has a DUT instance to bound the synth cone,
# and --synth-top takes the dotted path from the top, not the bare instance name.
inputs=(--input "${tb}.vpy")
synthtop=()
if [[ -f "${MODDIR}/${func}.vpy" ]]; then
    inputs+=(--input "${func}.vpy")
    synthtop=(--synth-top "${tb}.dut")
fi

# -sv for the same reason as the Makefile: .vpy in, .sv out.
if ! "$GENESISPY" -sv "${inputs[@]}" --top "$tb" \
        --src-path "${TBDIR}/functions" --src-path "${TBDIR}/modules" --src-path "$MODDIR" \
        --inc-path "$INCDIR" --inc-path "${TBDIR}/common" --py-path "$LIBDIR" \
        --out-dir "$base" --synth-dir "${base}/synth" --verif-dir "${base}/verif" \
        --raw-dir "${base}/raw" --vf-out "${base}/tb.vf" --log "${base}/genesispy.log" \
        "${synthtop[@]}" "${pflags[@]}" >"${base}/verif/gen.log" 2>&1; then
    # Two different things fail generation. A named error() from a template is a
    # rejection: the configuration is illegal and the generator said so. A Python
    # traceback is the generator breaking on a case it should have refused, and must
    # not count as a rejection, or a NEG_ entry would be satisfied by the crash it
    # was added to catch.
    if grep -q '^Traceback (most recent call last):' "${base}/verif/gen.log"; then
        echo "GEN-CRASH ${tb} ${config}"
        tail -3 "${base}/verif/gen.log" >&2
        exit "$RC_CRASH"
    fi
    echo "GEN-FAIL ${tb} ${config}"
    tail -3 "${base}/verif/gen.log" >&2
    exit "$RC_GEN"
fi

if [[ "$sim" == "gen" ]]; then
    echo "GEN-OK ${tb} ${config} -- ${base}/tb.vf"
    exit 0
fi

runargs=()
[[ -n "$want_data" ]] && runargs+=("+data=${base}/data.csv")

# The waveform costs build time and disk, so DUMP is defined only when asked for.
# verilator needs --trace as well: without it $dumpvars compiles away to nothing.
vflags=()
iflags=()
if [[ -n "$want_dump" ]]; then
    vflags+=(+define+DUMP --trace)
    iflags+=(-DDUMP)
fi

case "$sim" in
verilator)
    # -O0: these binaries simulate for milliseconds, so optimising the generated C++ costs
    # more build time than it ever saves at run time.
    if ! verilator --binary -CFLAGS -O0 "${vflags[@]}" --top-module "$tb" -f "${base}/tb.vf" \
            -Mdir "${base}/obj" >"${base}/build.log" 2>&1; then
        echo "BUILD-FAIL ${tb} ${config} ${sim}"
        # grep exits 1 on no match and 141 when head closes the pipe, and pipefail plus
        # set -e would turn either into exit 1 -- a mismatch, per the contract above.
        grep -E '%Error' "${base}/build.log" | head -5 >&2 || true
        exit "$RC_BUILD"
    fi
    # A width or lint warning is a failure: the output has to stay warning-free.
    if grep -q '%Warning' "${base}/build.log"; then
        echo "WARN-FAIL ${tb} ${config} ${sim}"
        grep -E '%Warning' "${base}/build.log" | head -5 >&2 || true
        exit "$RC_WARN"
    fi
    run_cmd=("${base}/obj/V${tb}")
    ;;
iverilog)
    if ! iverilog -g2012 "${iflags[@]}" -s "$tb" -o "${base}/sim.vvp" -f "${base}/tb.vf" \
            >"${base}/build.log" 2>&1; then
        echo "BUILD-FAIL ${tb} ${config} ${sim}"
        head -5 "${base}/build.log" >&2
        exit "$RC_BUILD"
    fi
    run_cmd=(vvp "${base}/sim.vvp")
    ;;
esac

# Classify on what the testbench reported, not on the simulator's exit status: verilator
# aborts with 134 on $fatal while iverilog exits 1, and a simulator that dies without
# reporting anything must not be mistaken for a mismatch.
# Run from the simulator's own directory: the testbench names its waveform dump.vcd
# with no path, so the file lands beside the logs rather than in the repo root.
# The terminal gets the testbench's own lines; run.log keeps everything, including the
# one epilogue line each simulator prints on $finish -- iverilog's "$finish called at"
# and verilator's "Verilog $finish" -- which doubles the length of a sweep for nothing.
set +e
(cd -- "$base" && "${run_cmd[@]}" "${runargs[@]}") 2>&1 |
    tee "${base}/run.log" |
    grep -vE '^(- )?\S+\.sv:[0-9]+: (\$finish called at|Verilog \$finish)'
set -e

# Every testbench ends its verdict with "-- <n> cases, <m> skipped", so a PASS that
# counts no cases checked nothing and must not be read as a result.
if grep -qE "^PASS ${tb} .* -- [1-9][0-9]* cases" "${base}/run.log"; then
    rc=0
elif grep -q "^PASS ${tb} " "${base}/run.log"; then
    echo "SIM-FAIL ${tb} ${config} ${sim} -- PASS over no cases, nothing was checked"
    rc=$RC_SIM
elif grep -q "^FAIL ${tb} " "${base}/run.log"; then
    rc=$RC_MISMATCH
else
    echo "SIM-FAIL ${tb} ${config} ${sim} -- simulator reported neither PASS nor FAIL"
    rc=$RC_SIM
fi

# genesispy takes an unknown -p name without complaint, so a typo in a sweep table would
# quietly rerun the default configuration and still report PASS. Every testbench echoes
# the parameters it was generated with, one NAME=VALUE per word, so a setting missing
# from the PASS line is one that never reached the testbench. f_sat and the two
# sign-magnitude conversions append a clamped width as "OW=8 (ow=7)"; the requested
# NAME=VALUE is still a word of its own, which is why this compares whole words.
if [[ $rc -eq 0 && "$config" != "default" ]]; then
    read -r -a reported <<<"$(grep -m1 "^PASS ${tb} " "${base}/run.log")"
    missing=()
    for setting in "${settings[@]}"; do
        found=""
        for word in "${reported[@]}"; do
            if [[ "$word" == "$setting" ]]; then
                found=1
                break
            fi
        done
        [[ -n "$found" ]] || missing+=("$setting")
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
        echo "PARAM-FAIL ${tb} ${config} ${sim} -- not echoed by the testbench: ${missing[*]}"
        rc=$RC_PARAM
    fi
fi

# Plot last, and never let it change the verdict. A mismatching function is exactly the
# one worth looking at, and the Makefile classifies runs by this exit status.
if [[ -n "$want_plot" ]]; then
    if [[ -r "${base}/data.csv" ]]; then
        "${REPO}/verif/plot.py" "${base}/data.csv" ||
            echo "run-tb.sh: plot failed; the test result stands (rc=${rc})" >&2
    else
        echo "run-tb.sh: no data file at ${base}/data.csv, nothing to plot" >&2
    fi
fi

exit "$rc"
