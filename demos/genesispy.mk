# Shared Make rules for genesispy demos.
#
# Per-demo layout (mirrors Genesis2/demo/<name>/):
#   <demo>/Makefile          # 3-line shim (TOP, INPUTS, include ../genesispy.mk)
#   <demo>/genesis_src/*.vpy # Verilog-py sources
#   <demo>/config.{json,py}  # optional, demo root (not all demos have these)
#
# A per-demo Makefile sets:
#   TOP         := top
#   INPUTS      := top.vpy ...   # bare names; resolved via --srcpath genesis_src
#   JSON_CONFIG := config.json   # optional
# then `include ../genesispy.mk`.
#
# Legacy XML configs: convert once with `genesispy-xml2json in.xml out.json`.
#
# Optional overrides:
#   OUTPUTDIR     (default: genesis_synth)
#   EXTRA_FLAGS   (passed verbatim to genesispy)
#   SIMULATOR     (xrun | vcs | vlog | verilator | iverilog; default: verilator)
#   SIM_TOP       (default: $(TOP))
#   VERILINT      (slang | verilator; default: verilator)

ifeq ($(strip $(TOP)),)
$(error genesispy.mk: TOP is not set)
endif
ifeq ($(strip $(INPUTS)),)
$(error genesispy.mk: INPUTS is not set)
endif
ifeq ($(wildcard genesis_src/.),)
$(error genesispy.mk: expected sources under ./genesis_src/ -- did you forget to move them?)
endif
ifneq ($(strip $(JSON_CONFIG)),)
CONFIG_FLAG := --json $(JSON_CONFIG)
CONFIG_DEP  := $(JSON_CONFIG)
else
CONFIG_FLAG :=
CONFIG_DEP  :=
endif

# CFG_CONFIG is composable: layered on top of JSON, or used standalone.
ifneq ($(strip $(CFG_CONFIG)),)
CONFIG_FLAG += --cfg $(CFG_CONFIG)
CONFIG_DEP  += $(CFG_CONFIG)
endif

OUTPUTDIR ?= genesis_synth
SIM_TOP   ?= $(TOP)
SIMULATOR ?= verilator
VERILINT  ?= verilator

GENESISPY ?= genesispy
XML2JSON  ?= genesispy-xml2json
PYTHON    ?= python3

GEN_INPUT_FLAGS := $(addprefix --input ,$(INPUTS))
SRC_FILES      := $(addprefix genesis_src/,$(INPUTS))
VLIST          := $(OUTPUTDIR)/$(TOP).vlist
DEPEND         := $(OUTPUTDIR)/$(TOP).depend
CLEAN_SH       := $(OUTPUTDIR)/genesispy_clean.sh
VLOG_VF        := genesis_vlog.vf

.PHONY: gen cleangen cleansim clean pylint vlint lint sim help

# XML -> JSON config conversion. One-way: XML is canonical for demos that
# carry both forms; JSON is regenerated from it. Use `genesispy-json2xml`
# manually if you need the reverse.
%.json: %.xml
	$(XML2JSON) $< $@

gen: $(VLIST) $(VLOG_VF)

$(VLIST): $(SRC_FILES) $(CONFIG_DEP)
	$(GENESISPY) $(GEN_INPUT_FLAGS) --top $(TOP) $(CONFIG_FLAG) \
	    --srcpath genesis_src --outputdir $(OUTPUTDIR) $(EXTRA_FLAGS)

# Genesis2-style product list at demo root (mirrors $(VLIST)).
$(VLOG_VF): $(VLIST)
	cp $(VLIST) $(VLOG_VF)

cleangen:
	rm -rf genesis_raw genesis_synth genesis_verif
	rm -f $(VLIST) $(DEPEND) $(CLEAN_SH) $(VLOG_VF)

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

pylint: gen
	@echo "Compiling generated Python modules..."
	$(PYTHON) -m py_compile genesis_raw/*.py

lint: pylint vlint

vlint: gen
ifeq ($(VERILINT),slang)
	slang --lint-only -Weverything -Wpedantic --top $(SIM_TOP) -f $(VLIST)
else ifeq ($(VERILINT),verilator)
	verilator --lint-only --top-module $(SIM_TOP) -f $(VLIST)
else
	$(error vlint: unknown VERILINT='$(VERILINT)' (slang|verilator))
endif

sim: gen
ifeq ($(SIMULATOR),xrun)
	xrun -sv -access +rwc -64bit +define+SIMULATION -f $(VLIST) -top $(SIM_TOP)
else ifeq ($(SIMULATOR),vcs)
	vcs -sverilog +define+SIMULATION -f $(VLIST) -top $(SIM_TOP) -o simv && ./simv
else ifeq ($(SIMULATOR),vlog)
	vlog -sv +define+SIMULATION -f $(VLIST) && vsim -c -do "run -all; quit" $(SIM_TOP)
else ifeq ($(SIMULATOR),verilator)
	verilator --binary -Wno-fatal --timing -CFLAGS -std=c++20 \
	    +define+SIMULATION --top-module $(SIM_TOP) -f $(VLIST) \
	    -Mdir obj_dir && obj_dir/V$(SIM_TOP)
else ifeq ($(SIMULATOR),iverilog)
	iverilog -g2012 -DSIMULATION -s $(SIM_TOP) -o $(SIM_TOP).vvp -f $(VLIST) && vvp $(SIM_TOP).vvp
else
	$(error sim: unknown SIMULATOR='$(SIMULATOR)' (xrun|vcs|vlog|verilator|iverilog))
endif

# Per-demo Makefiles can set HELP_LOCAL := 1 before the include and provide
# their own `help:` recipe.
ifndef HELP_LOCAL
help:
	@echo "genesispy demo targets:"
	@echo "  gen     - elaborate $(TOP) from genesis_src/$(INPUTS) (default)"
	@echo "  pylint  - py_compile generated Python modules"
	@echo "  vlint   - lint generated Verilog (VERILINT=slang|verilator; default verilator)"
	@echo "  lint    - run pylint + vlint"
	@echo "  sim     - run simulation (SIMULATOR=xrun(cadence)|vcs(synopsys)|vlog(mentor)|verilator|iverilog; default verilator)"
	@echo "  cleangen - remove genesispy elaboration outputs"
	@echo "  cleansim - remove simulator intermediates (all engines)"
	@echo "  clean    - cleangen + cleansim"
	@echo ""
	@echo "Variables (current values):"
	@echo "  TOP         = $(TOP)"
	@echo "  INPUTS      = $(INPUTS)"
	@echo "  JSON_CONFIG = $(JSON_CONFIG)"
	@echo "  OUTPUTDIR   = $(OUTPUTDIR)"
	@echo "  SIMULATOR   = $(SIMULATOR)"
	@echo "  VERILINT    = $(VERILINT)"
endif
