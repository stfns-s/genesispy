# generation_examples demo: five tops, one per pattern from README.md.
# Each example elaborates via a sub-make against ../genesispy.mk with its
# own TOP and a per-example OUTPUTDIR=genesis_synth_ex<N>.

EXAMPLES := ex1_unique ex2_ununique ex3_genwname ex4_synonym ex5_clone
HELP_LOCAL := 1

.PHONY: gen $(EXAMPLES) vlint clean cleangen cleansim help

gen: $(EXAMPLES)

$(EXAMPLES):
	$(MAKE) -f ../genesispy.mk \
	    TOP=$@ \
	    INPUTS="$@.vpy pll.vpy" \
	    OUTPUTDIR=genesis_synth_$(firstword $(subst _, ,$@)) \
	    VLOG_VF=genesis_vlog_$@.vf \
	    gen

vlint: $(addprefix vlint-,$(EXAMPLES))

vlint-%:
	$(MAKE) -f ../genesispy.mk \
	    TOP=$* \
	    INPUTS="$*.vpy pll.vpy" \
	    OUTPUTDIR=genesis_synth_$(firstword $(subst _, ,$*)) \
	    VLOG_VF=genesis_vlog_$*.vf \
	    VERILINT=$(or $(VERILINT),verilator) \
	    vlint

cleangen:
	rm -rf genesis_raw genesis_synth genesis_verif genesis_synth_ex*
	rm -f genesis_vlog_*.vf genesis_vlog_*.vf.flags

cleansim:
	rm -rf obj_dir csrc simv.daidir work
	rm -rf xcelium.d INCA_libs cov_work .simvision *.shm
	rm -f *.vvp simv ucli.key vc_hdrs.h transcript vsim.wlf
	rm -f *.log *.wlf *.vcd *.fst

clean: cleangen cleansim

help:
	@echo "generation_examples demo targets:"
	@echo "  gen              - elaborate all five examples (default)"
	@echo "  ex1_unique       - elaborate just example 1"
	@echo "  ex2_ununique     - elaborate just example 2"
	@echo "  ex3_genwname     - elaborate just example 3"
	@echo "  ex4_synonym      - elaborate just example 4"
	@echo "  ex5_clone        - elaborate just example 5"
	@echo "  vlint            - lint all five (VERILINT=slang|verilator; default verilator)"
	@echo "  vlint-ex<N>_...  - lint a single example"
	@echo "  clean / cleangen / cleansim"
	@echo ""
	@echo "Outputs land under genesis_synth_ex<N>/ -- one dir per example."
	@echo "See README.md for the walkthrough and expected output per example."
