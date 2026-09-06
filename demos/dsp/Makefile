# Makefile for dsp.
#
# Target and variable names follow the genesispy demo rules in
# genesispy/demos/genesispy.mk. Those rules are not included directly: they
# require sources under ./genesis_src/ and hardcode that as the --src-path,
# while this repo keeps modules in modules/ and functions in functions/. The tops
# are independent, so each gets its own rules, the way the
# generation_examples demo handles its five.
#
# Needs genesispy on PATH:
#   source ../env_setup.sh

TOPS      ?= iir intg spec_mux
SRCDIR    ?= modules
INCDIR    ?= functions
LIBDIR    ?= lib
VERIFDIR  ?= verif
BUILDDIR  ?= build

SIMULATOR ?= verilator
SIM_TOP   ?= tb_intg
SIM_CFG   ?= default
VERILINT  ?= verilator

DUMP      ?= 0

EXTRA_FLAGS     ?=
VERILATOR_FLAGS ?=
SLANG_FLAGS     ?=

GENESISPY ?= genesispy
PYTHON    ?= python3

# One build directory per top, laid out like a testbench's: raw/, synth/, verif/. A
# parameterised build reuses it, and the .flags stamp below forces the rebuild.
topdir = $(BUILDDIR)/$(1)/default

VLOG_VF    = $(foreach t,$(TOPS),$(call topdir,$(t))/$(t).vf)
FLAGSTAMPS = $(foreach t,$(TOPS),$(call topdir,$(t))/$(t).flags)

# make sim drives a testbench, which verif/run-tb.sh elaborates: it owns the two
# --input files, the verif/ search paths and --synth-top. run-tb.sh puts one tree per
# simulator under the configuration directory, so an elaborate-only run lands in gen/;
# the simulator artifacts go in sim/ beside it, and an interactive run therefore never
# overwrites a recorded test result.
SIM_NAME = $(patsubst tb_%,%,$(SIM_TOP))
SIM_TAG  = $(subst =,,$(subst :,_,$(SIM_CFG)))
SIM_DIR  = $(BUILDDIR)/$(SIM_TOP)/$(SIM_TAG)
SIM_OUT  = $(SIM_DIR)/sim
SIM_VF   = $(SIM_DIR)/gen/tb.vf

# run-tb.sh reads BUILDDIR, so `make BUILDDIR=x test` moves the testbench output too.
export BUILDDIR

ifeq ($(VERILINT),slang)
vlint_cmd = slang --lint-only -Weverything -Wpedantic $(SLANG_FLAGS) --top $(1) -f $(2)
else ifeq ($(VERILINT),verilator)
vlint_cmd = verilator --lint-only -Wall $(VERILATOR_FLAGS) --top-module $(1) -f $(2)
else
$(error vlint: unknown VERILINT='$(VERILINT)' (slang|verilator))
endif

.PHONY: gen pylint vlint lint sim pytest test test-extra test-smoke plot cleangen cleansim clean
.PHONY: help FORCE
.DEFAULT_GOAL := gen

gen: $(VLOG_VF)

# One set of rules per top. EXTRA_FLAGS_<top> adds per-top options:
#   make intg EXTRA_FLAGS_intg='-p OW=12 -p IW=6'
define top_rules

TOPDIR_$(1) := $$(call topdir,$(1))

# --synth-top names the top's own instance, so the module lands in synth/ and only
# genesispy's bookkeeping stays at the top of the build directory. -sv maps .vpy input
# to .sv output: the templates emit SystemVerilog, which the default .v does not say.
GEN_CMD_$(1) := $$(GENESISPY) -sv --input $(1).vpy --top $(1) \
    --src-path $$(SRCDIR) --inc-path $$(INCDIR) --py-path $$(LIBDIR) --synth-top $(1) \
    --out-dir $$(TOPDIR_$(1)) \
    --synth-dir $$(TOPDIR_$(1))/synth --verif-dir $$(TOPDIR_$(1))/verif \
    --raw-dir $$(TOPDIR_$(1))/raw --log $$(TOPDIR_$(1))/genesispy.log \
    --vf-out $$(TOPDIR_$(1))/$(1).vf \
    $$(EXTRA_FLAGS) $$(EXTRA_FLAGS_$(1))

$$(TOPDIR_$(1)):
	@mkdir -p $$@

# Records the command line, rewritten only when it changes, so a flag or
# parameter change forces a rebuild and an unchanged one does not.
$$(TOPDIR_$(1))/$(1).flags: FORCE | $$(TOPDIR_$(1))
	@printf '%s\n' "$$(GEN_CMD_$(1))" | cmp -s - $$@ 2>/dev/null || \
	    printf '%s\n' "$$(GEN_CMD_$(1))" > $$@

# genesispy leaves an output file alone when its content is unchanged, and
# the .vf content never varies, so touch it to mark the build done.
$$(TOPDIR_$(1))/$(1).vf: $$(SRCDIR)/$(1).vpy $$(TOPDIR_$(1))/$(1).flags
	$$(GEN_CMD_$(1))
	@touch $$@

.PHONY: $(1) vlint-$(1)

$(1): $$(TOPDIR_$(1))/$(1).vf

vlint-$(1): $$(TOPDIR_$(1))/$(1).vf
	$$(call vlint_cmd,$(1),$$(TOPDIR_$(1))/$(1).vf)

# Pull in the generated depfile so a change to an include()'d function
# also triggers a rebuild.
-include $$(TOPDIR_$(1))/$(1).depend

endef

$(foreach t,$(TOPS),$(eval $(call top_rules,$(t))))

vlint: $(addprefix vlint-,$(TOPS))

# A top's raw/ sits two levels down and a testbench's three, since run-tb.sh adds a
# directory per simulator, so find the directories rather than glob a fixed depth.
pylint: gen
	$(PYTHON) -m py_compile $$(find $(BUILDDIR) -path '*/raw/*.py')

# vlint-tb is part of the gate, not a report run by hand: it is the only place the 17
# functions get verilator-linted, since the default TB_SIMS is iverilog and never
# calls verilator at all.
lint: pylint vlint vlint-tb

# DUMP=1 defines DUMP, which is what tb_util wraps its $dumpvars in. The
# waveform lands in the repo root as dump.vcd, where cleansim removes it. verilator needs
# --trace as well: without it $dumpvars compiles away to nothing.
ifneq ($(DUMP),0)
DUMP_DEF   = +define+DUMP
DUMP_IDEF  = -DDUMP
DUMP_TRACE = --trace
endif

# One interactive run of SIM_TOP under any of the five simulators. run-tb.sh only drives
# verilator and iverilog, so this target elaborates through it and runs the result itself.
# The checked, self-verifying run is test-$(SIM_NAME).
sim:
	$(VERIFDIR)/run-tb.sh $(SIM_NAME) $(SIM_CFG) gen
	@mkdir -p $(SIM_OUT)
ifeq ($(SIMULATOR),xrun)
	xrun -sv -access +rwc -64bit +define+SIMULATION $(DUMP_DEF) -f $(SIM_VF) -top $(SIM_TOP)
else ifeq ($(SIMULATOR),vcs)
	vcs -sverilog +define+SIMULATION $(DUMP_DEF) -f $(SIM_VF) -top $(SIM_TOP) -o $(SIM_OUT)/simv \
	    && $(SIM_OUT)/simv
else ifeq ($(SIMULATOR),vlog)
	vlog -sv +define+SIMULATION $(DUMP_DEF) -f $(SIM_VF) && vsim -c -do "run -all; quit" $(SIM_TOP)
else ifeq ($(SIMULATOR),verilator)
	verilator --binary -Wno-fatal --timing -CFLAGS -std=c++20 \
	    +define+SIMULATION $(DUMP_DEF) $(DUMP_TRACE) --top-module $(SIM_TOP) -f $(SIM_VF) \
	    -Mdir $(SIM_OUT)/obj && $(SIM_OUT)/obj/V$(SIM_TOP)
else ifeq ($(SIMULATOR),iverilog)
	iverilog -g2012 -DSIMULATION $(DUMP_IDEF) -s $(SIM_TOP) -o $(SIM_OUT)/$(SIM_TOP).vvp -f $(SIM_VF) \
	    && vvp $(SIM_OUT)/$(SIM_TOP).vvp
else
	$(error sim: unknown SIMULATOR='$(SIMULATOR)' (xrun|vcs|vlog|verilator|iverilog))
endif

# ---------------------------------------------------------------------------
# Unit tests for the function library in functions/ and the modules in modules/
#
# Each function has a testbench in verif/functions/ that checks it against a 64-bit
# reference over an exhaustive input sweep. A module testbench in verif/modules/
# instantiates the module and steps a 64-bit reference alongside it, one clock at a
# time. verif/run-tb.sh generates, builds and runs one of either in one configuration;
# the tables in verif/sweeps.mk say which configurations to try.
# ---------------------------------------------------------------------------

# Simulators make test runs. iverilog alone by default: the suite compiles a program per
# configuration and then simulates for milliseconds, so build time decides the total, and
# iverilog builds in about no time -- measured at roughly a sixth of verilator's wall time
# over the whole sweep. It is also four-state, so it catches an X coming out of a function,
# which verilator cannot: verilator turns an X into 0 and then only notices when 0 happens
# to differ from the expected value. verilator is the extra regression, via test-extra.
TB_SIMS  ?= iverilog

include $(VERIFDIR)/sweeps.mk

# Serves both the functions in FUNCS and the modules in MODS: the tables are keyed by
# name, and run-tb.sh finds either kind from tb_<name>.vpy.
#
# A NEG_ entry asks the generator to reject a configuration, which does not involve a
# simulator, so it runs under 'gen'. Only rc 3 counts as the rejection: any other nonzero
# status means the run died for some unrelated reason and the check never happened.
#
# The loops also count what they ran and compare it against the tables, so a target that
# silently walks a shorter list than the one in sweeps.mk turns red instead of reporting
# a clean sweep over fewer configurations.
define func_test_rules
.PHONY: test-$(1)
test-$(1):
	@fail=0; runs=0; \
	for cfg in $$(SWEEP_$(1)); do \
	    for sim in $$(TB_SIMS); do \
	        runs=$$$$((runs + 1)); \
	        if $$(VERIFDIR)/run-tb.sh $(1) $$$$cfg $$$$sim; then \
	            case " $$(XFAIL_$(1)) " in \
	            *" $$$$cfg "*) \
	                echo "XPASS $(1) $$$$cfg $$$$sim -- expected a mismatch; update XFAIL_$(1)"; \
	                fail=1 ;; \
	            esac; \
	        else \
	            rc=$$$$?; \
	            case " $$(XFAIL_$(1)) " in \
	            *" $$$$cfg "*) \
	                if [ $$$$rc -eq 1 ]; then \
	                    echo "XFAIL $(1) $$$$cfg $$$$sim -- known, see XFAIL_$(1)"; \
	                else \
	                    echo "ERROR $(1) $$$$cfg $$$$sim -- never ran (rc=$$$$rc);" \
	                         "XFAIL covers mismatches only"; \
	                    fail=1; \
	                fi ;; \
	            *) fail=1 ;; \
	            esac; \
	        fi; \
	    done; \
	done; \
	for cfg in $$(NEG_$(1)); do \
	    runs=$$$$((runs + 1)); \
	    if $$(VERIFDIR)/run-tb.sh $(1) $$$$cfg gen >/dev/null 2>&1; then \
	        echo "NEG-FAIL $(1) $$$$cfg -- generated, expected an error"; fail=1; \
	    else \
	        rc=$$$$?; \
	        if [ $$$$rc -eq 3 ]; then \
	            echo "PASS $(1) $$$$cfg -- rejected at generation"; \
	        else \
	            echo "NEG-FAIL $(1) $$$$cfg -- expected rejection at generation (rc=3)," \
	                 "got rc=$$$$rc"; \
	            fail=1; \
	        fi; \
	    fi; \
	done; \
	want=$$$$(( $$(words $$(SWEEP_$(1))) * $$(words $$(TB_SIMS)) + $$(words $$(NEG_$(1))) )); \
	if [ $$$$want -eq 0 ]; then \
	    echo "COUNT-FAIL $(1) -- no SWEEP_$(1) and no NEG_$(1) entries, so nothing ran"; \
	    fail=1; \
	fi; \
	if [ $$$$runs -ne $$$$want ]; then \
	    echo "COUNT-FAIL $(1) -- ran $$$$runs configurations, the tables list $$$$want"; \
	    fail=1; \
	fi; \
	exit $$$$fail
endef

$(foreach f,$(FUNCS),$(eval $(call func_test_rules,$(f))))
$(foreach m,$(MODS),$(eval $(call func_test_rules,$(m))))

# vlint covers the two tops standalone; the 17 functions are include()d and never
# elaborated on their own, so the only place they get linted is inside a testbench. This
# lints a function testbench in every swept configuration with -Wall and builds no
# simulation binary, so the functions stay checked even though the default TB_SIMS is
# iverilog and never runs verilator at all.
#
# The two module testbenches are out of scope: under -Wall they report their own clock
# generator and EXH-only scratch rather than the DUT, and `make vlint` already lints both
# modules standalone with -Wall.
#
# VLINT_TB_SKIP names function testbenches with known warnings, so this target stays a
# gate that passes rather than a report nobody reads. What is left in both is
# UNUSEDSIGNAL on values that are genuinely dead in some configurations: f_logmult's
# zero flag za/zb when ZDET=0, and the high bits of the multipliers' 64-bit reference
# arguments, of which only the table index is read. Removing either means narrowing an
# emitted port or a reference signature; both were tried and both broke the run, because
# a SystemVerilog size cast keeps its operand's signedness and turns the upper half of
# an index range negative. Recorded rather than silently dropped; lift an entry when its
# warnings are fixed.
VLINT_TB_SKIP ?= f_logmult f_slogmult
define func_vlint_rules
.PHONY: vlint-tb-$(1)
vlint-tb-$(1):
	@fail=0; \
	for cfg in $$(or $$(SWEEP_$(1)),default); do \
	    tag=$$$$(echo "$$$$cfg" | tr -d '=' | tr ':' '_'); \
	    if $$(VERIFDIR)/run-tb.sh $(1) $$$$cfg gen >/dev/null 2>&1; then \
	        verilator --lint-only -Wall --top-module tb_$(1) \
	            -f $$(BUILDDIR)/tb_$(1)/$$$$tag/gen/tb.vf || \
	            { echo "LINT-FAIL $(1) $$$$cfg"; fail=1; }; \
	    else \
	        echo "GEN-FAIL $(1) $$$$cfg"; fail=1; \
	    fi; \
	done; \
	exit $$$$fail
endef

$(foreach f,$(FUNCS),$(eval $(call func_vlint_rules,$(f))))

.PHONY: vlint-tb
vlint-tb: $(addprefix vlint-tb-,$(filter-out $(VLINT_TB_SKIP),$(FUNCS)))

# The Q format library, checked without a simulator or a generator. test depends on it, so a
# regression also covers the algebra every derived width comes from. Under -j it runs beside
# the sweeps rather than before them; either way test fails if it fails. The run goes to a
# log and only its last line to the terminal: pytest's progress dots carry no newline, so
# streamed they would land in the middle of another test's result line.
pytest: | $(BUILDDIR)
	@$(PYTHON) -m pytest -q $(LIBDIR)/tests >$(BUILDDIR)/pytest.log 2>&1 \
	    || { cat $(BUILDDIR)/pytest.log; exit 1; }
	@tail -1 $(BUILDDIR)/pytest.log

$(BUILDDIR):
	@mkdir -p $@

test: pytest $(addprefix test-,$(FUNCS) $(MODS))

# The extra regression. 'make test test-extra' covers both simulators.
test-extra:
	@$(MAKE) --no-print-directory test TB_SIMS=verilator

# Breadth instead of depth: every function and module in its default configuration under
# both simulators, where test walks the sweep tables under one. One rule per name, so -j
# runs them at once; the sweeps are what take the time, and smoke has none.
SMOKE_SIMS ?= iverilog verilator

define func_smoke_rules
.PHONY: test-smoke-$(1)
test-smoke-$(1):
	@fail=0; \
	for sim in $$(SMOKE_SIMS); do \
	    $$(VERIFDIR)/run-tb.sh $(1) default $$$$sim || fail=1; \
	done; \
	exit $$$$fail
endef

$(foreach f,$(FUNCS),$(eval $(call func_smoke_rules,$(f))))
$(foreach m,$(MODS),$(eval $(call func_smoke_rules,$(m))))

test-smoke: $(addprefix test-smoke-,$(FUNCS) $(MODS))

# make plot FUNC=f_shright [CFG=IW=8:CW=4] [OUT=shr.png]
# The run is allowed to fail: a mismatching function is exactly the one worth plotting.
plot_tag = $(subst =,,$(subst :,_,$(or $(CFG),default)))

plot:
	@test -n "$(FUNC)" || { echo "usage: make plot FUNC=<name> [CFG=IW=8:CW=4] [OUT=x.png]"; exit 2; }
	-@$(VERIFDIR)/run-tb.sh $(FUNC) $(or $(CFG),default) verilator data
	$(PYTHON) $(VERIFDIR)/plot.py \
	    $(BUILDDIR)/tb_$(FUNC)/$(plot_tag)/verilator/data.csv \
	    $(if $(OUT),--out $(OUT))

cleangen:
	rm -rf $(BUILDDIR)

cleansim:
	rm -rf csrc simv.daidir work
	rm -rf xcelium.d INCA_libs cov_work .simvision *.shm
	rm -f *.vvp simv ucli.key vc_hdrs.h transcript vsim.wlf
	rm -f *.log *.wlf *.vcd *.fst

clean: cleangen cleansim

help:
	@echo "dsp targets:"
	@echo "  gen      - elaborate every top in TOPS (default)"
	@echo "  iir      - elaborate just iir"
	@echo "  intg     - elaborate just intg"
	@echo "  spec_mux - elaborate just spec_mux"
	@echo "  vlint    - lint every top (VERILINT=slang|verilator; default verilator)"
	@echo "  vlint-<top> - lint one top"
	@echo "  pylint   - py_compile the generated Python modules"
	@echo "  lint     - pylint + vlint"
	@echo "  sim      - run SIM_TOP once under SIMULATOR; the checked run is test-<name>"
	@echo "             make sim DUMP=1 writes dump.vcd (worth it for a module)"
	@echo "  pytest   - the Q format library in $(LIBDIR)/tests; no simulator"
	@echo "  test     - pytest, plus every function in functions/ and module in modules/ under $(TB_SIMS) (use -j)"
	@echo "  test-extra - re-run the whole suite under verilator (two-state, the slower build)"
	@echo "  test-smoke - every function and module in its default configuration under $(SMOKE_SIMS)"
	@echo "  test-<f> - unit-test one function or module, e.g. test-f_round, test-intg"
	@echo "  plot     - make plot FUNC=f_shright [CFG=IW=8:CW=4] [OUT=x.png]"
	@echo "  cleangen - remove $(BUILDDIR): elaboration output, test results and logs"
	@echo "  cleansim - remove simulator intermediates"
	@echo "  clean    - cleangen + cleansim"
	@echo ""
	@echo "Generation-time parameters go in EXTRA_FLAGS_<top>:"
	@echo "  make intg EXTRA_FLAGS_intg='-p OW=12 -p IW=6 -p ISYM=1'"
	@echo ""
	@echo "Variables (current values):"
	@echo "  TOPS      = $(TOPS)"
	@echo "  MODS      = $(MODS)"
	@echo "  SRCDIR    = $(SRCDIR)"
	@echo "  INCDIR    = $(INCDIR)"
	@echo "  VERIFDIR  = $(VERIFDIR)"
	@echo "  BUILDDIR  = $(BUILDDIR)"
	@echo "  SIMULATOR = $(SIMULATOR)"
	@echo "  SIM_TOP   = $(SIM_TOP)"
	@echo "  SIM_CFG   = $(SIM_CFG)"
	@echo "  DUMP      = $(DUMP)"
	@echo "  VERILINT  = $(VERILINT)"
