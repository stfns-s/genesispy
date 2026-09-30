GVPY      ?= gvpy
TOP       := example
SIM_TOP   ?= $(TOP)
WIDTH     ?= 8
DEPTH     ?= 4
OUT       := example.out.v
OUT_J2    := example.j2.out.v
SRC_J2    := $(TOP).j2.vpy
SIMULATOR ?= verilator
VERILINT  ?= verilator

VERILATOR_FLAGS ?=
SLANG_FLAGS     ?=

# Full command lines as variables so the recipe and stamp cannot drift.
GEN_CMD    := $(GVPY) --gvpy-strict --mname $(TOP) \
	    --parameter WIDTH=$(WIDTH) --parameter DEPTH=$(DEPTH) \
	    $(TOP).vpy
GEN_CMD_J2 := $(GVPY) --j2 --gvpy-strict --mname $(TOP) \
	    --parameter WIDTH=$(WIDTH) --parameter DEPTH=$(DEPTH) \
	    $(SRC_J2)

# Stamp files record the last command line used; rewritten only when content
# changes. A changed command line also removes the product, and both happen
# while make reads this file: make reads a target's mtime before it runs any
# prerequisite's recipe, so a product removed by a stamp recipe would still
# count as up to date whenever the new stamp's coarse mtime ties with it.
# Only goals that build the product do this, and not under make -n.
FLAGSTAMP    := $(OUT).flags
FLAGSTAMP_J2 := $(OUT_J2).flags

GOALS   := $(or $(MAKECMDGOALS),gen)
DRY_RUN := $(findstring n,$(firstword -$(MAKEFLAGS)))

# $(call differ,A,B) is non-empty unless the two strings are equal.
differ = $(subst $(1),,$(2))$(subst $(2),,$(1))

# $(call restamp,STAMP,CMD,PRODUCT,GOALS-THAT-BUILD-IT). $(file) rather than
# the shell, which would strip quotes and expand $VAR in the stamp it writes.
restamp = $(if $(DRY_RUN),,$(if $(filter $(4),$(GOALS)),\
    $(if $(call differ,$(file <$(1)),$(strip $(2))),\
        $(file >$(1),$(strip $(2)))$(shell rm -f $(3)))))

$(call restamp,$(FLAGSTAMP),$(GEN_CMD),$(OUT),gen lint vlint sim $(OUT))
$(call restamp,$(FLAGSTAMP_J2),$(GEN_CMD_J2),$(OUT_J2),gen-j2 $(OUT_J2))

# Lets make -n, which writes no stamp, still plan the build.
$(FLAGSTAMP) $(FLAGSTAMP_J2): ;

.PHONY: gen gen-j2 cleangen cleansim clean vlint lint sim help

# The stamp rule precedes gen textually; set default goal explicitly.
.DEFAULT_GOAL := gen

# A failed run must not leave a truncated, up-to-date output behind.
.DELETE_ON_ERROR:

gen: $(OUT)

$(OUT): $(TOP).vpy $(FLAGSTAMP)
	$(GEN_CMD) > $@.tmp && mv $@.tmp $@

gen-j2: $(OUT_J2)

$(OUT_J2): $(SRC_J2) $(FLAGSTAMP_J2)
	$(GEN_CMD_J2) > $@.tmp && mv $@.tmp $@

cleangen:
	rm -f $(OUT) $(OUT_J2) $(OUT).tmp $(OUT_J2).tmp $(FLAGSTAMP) $(FLAGSTAMP_J2)

cleansim:
	rm -rf obj_dir csrc simv.daidir work
	rm -rf xcelium.d INCA_libs cov_work .simvision *.shm
	rm -rf *.daidir
	rm -f $(SIM_TOP).vvp
	rm -f simv ucli.key vc_hdrs.h transcript vsim.wlf
	rm -f xrun.log xrun.history xrun.key xmsim.key xmverilog.key
	rm -f irun.log irun.history irun.key
	rm -f ncsim.log ncvlog.log ncelab.log
	rm -f *.wlf *.vcd *.fst *.log

clean: cleangen cleansim

lint: vlint

vlint: gen
ifeq ($(VERILINT),slang)
	slang --lint-only -Weverything -Wpedantic $(SLANG_FLAGS) --top $(SIM_TOP) $(OUT)
else ifeq ($(VERILINT),verilator)
	verilator --lint-only $(VERILATOR_FLAGS) --top-module $(SIM_TOP) $(OUT)
else
	$(error vlint: unknown VERILINT='$(VERILINT)' (slang|verilator))
endif

sim: gen
ifeq ($(SIMULATOR),xrun)
	xrun -sv -access +rwc -64bit +define+SIMULATION -top $(SIM_TOP) $(OUT)
else ifeq ($(SIMULATOR),vcs)
	vcs -sverilog +define+SIMULATION -top $(SIM_TOP) $(OUT) -o simv && ./simv
else ifeq ($(SIMULATOR),vlog)
	vlog -sv +define+SIMULATION $(OUT) && vsim -c -do "run -all; quit" $(SIM_TOP)
else ifeq ($(SIMULATOR),verilator)
	verilator --binary -Wno-fatal --timing --assert -CFLAGS -std=c++20 \
	    +define+SIMULATION --top-module $(SIM_TOP) $(OUT) \
	    -Mdir obj_dir && obj_dir/V$(SIM_TOP)
else ifeq ($(SIMULATOR),iverilog)
	iverilog -g2012 -DSIMULATION -s $(SIM_TOP) -o $(SIM_TOP).vvp $(OUT) && vvp $(SIM_TOP).vvp
else
	$(error sim: unknown SIMULATOR='$(SIMULATOR)' (xrun|vcs|vlog|verilator|iverilog))
endif

help:
	@echo "gvpy demo targets:"
	@echo "  gen     - run gvpy on $(TOP).vpy (writes $(OUT))"
	@echo "  gen-j2  - run gvpy --j2 on $(SRC_J2) (writes $(OUT_J2))"
	@echo "  vlint   - lint $(OUT) (VERILINT=slang|verilator; default verilator)"
	@echo "  lint    - alias for vlint"
	@echo "  sim     - run simulation on $(OUT) (SIMULATOR=xrun|vcs|vlog|verilator|iverilog; default verilator)"
	@echo "  cleangen - remove $(OUT), $(OUT_J2) and their .flags stamps"
	@echo "  cleansim - remove simulator intermediates (all engines)"
	@echo "  clean    - cleangen + cleansim"
	@echo ""
	@echo "Variables (current values):"
	@echo "  GVPY        = $(GVPY)"
	@echo "  TOP         = $(TOP)"
	@echo "  SIM_TOP     = $(SIM_TOP)"
	@echo "  WIDTH       = $(WIDTH)"
	@echo "  DEPTH       = $(DEPTH)"
	@echo "  SIMULATOR   = $(SIMULATOR)"
	@echo "  VERILINT    = $(VERILINT)"
	@echo "  VERILATOR_FLAGS = $(VERILATOR_FLAGS)"
	@echo "  SLANG_FLAGS = $(SLANG_FLAGS)"
