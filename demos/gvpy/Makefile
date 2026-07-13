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

# Full command lines as variables so the recipe and stamp cannot drift.
# Note: a double-quote inside WIDTH/DEPTH would break the printf quoting below.
GEN_CMD    := $(GVPY) --gvpy-strict --mname $(TOP) \
	    --parameter WIDTH=$(WIDTH) --parameter DEPTH=$(DEPTH) \
	    $(TOP).vpy
GEN_CMD_J2 := $(GVPY) --j2 --gvpy-strict --mname $(TOP) \
	    --parameter WIDTH=$(WIDTH) --parameter DEPTH=$(DEPTH) \
	    $(SRC_J2)

# Stamp files record the last command line used; rewritten only when content
# changes, so mtime advances only on a real parameter change.
FLAGSTAMP    := $(OUT).flags
FLAGSTAMP_J2 := $(OUT_J2).flags

.PHONY: gen gen-j2 cleangen cleansim clean vlint lint sim help FORCE

# Stamp rules precede gen textually; set default goal explicitly.
.DEFAULT_GOAL := gen

$(FLAGSTAMP): FORCE
	@printf '%s\n' "$(GEN_CMD)" | cmp -s - $@ 2>/dev/null || printf '%s\n' "$(GEN_CMD)" > $@

$(FLAGSTAMP_J2): FORCE
	@printf '%s\n' "$(GEN_CMD_J2)" | cmp -s - $@ 2>/dev/null || printf '%s\n' "$(GEN_CMD_J2)" > $@

gen: $(OUT)

$(OUT): $(TOP).vpy $(FLAGSTAMP)
	$(GEN_CMD) > $@

gen-j2: $(OUT_J2)

$(OUT_J2): $(SRC_J2) $(FLAGSTAMP_J2)
	$(GEN_CMD_J2) > $@

cleangen:
	rm -f $(OUT) $(OUT_J2) $(FLAGSTAMP) $(FLAGSTAMP_J2)

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
	slang --lint-only -Weverything -Wpedantic --top $(SIM_TOP) $(OUT)
else ifeq ($(VERILINT),verilator)
	verilator --lint-only --top-module $(SIM_TOP) $(OUT)
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
	verilator --binary -Wno-fatal --timing -CFLAGS -std=c++20 \
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
	@echo "  cleangen - remove $(OUT)"
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
