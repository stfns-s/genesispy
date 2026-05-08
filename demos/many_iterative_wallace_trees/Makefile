TOP        := top
INPUTS     := top.vpy wallace.vpy CSA.vpy
HELP_LOCAL := 1
include ../genesispy.mk

help:
	@echo ""
	@echo "many_iterative_wallace_trees — config-driven width sweep"
	@echo ""
	@echo "Default mode (no config):"
	@echo "  make gen"
	@echo "    -> WALLACES_WIDTHS=[4, 8], COND=True, ParamHash={}"
	@echo "    -> 2 unique wallace modules + 2 clones"
	@echo ""
	@echo "JSON config (overrides defaults):"
	@echo "  make gen JSON_CONFIG=config.json"
	@echo "    -> WALLACES_WIDTHS=[2, 5, 16, 32, 64], COND=False,"
	@echo "       ParamHash={Assoc:4, lineSize:256, waySize:4096, wordSize:64}"
	@echo "    -> 5 unique wallace modules + 5 clones"
	@echo ""
	@echo "Legacy XML config (convert first):"
	@echo "  genesispy-xml2json config.xml config.json && make gen JSON_CONFIG=config.json"
	@echo ""
	@echo ".cfg Python config (lowest external priority — JSON and CLI both beat it):"
	@echo "  make gen CFG_CONFIG=config.py"
	@echo "    -> WALLACES_WIDTHS=[3, 7, 11], COND=True,"
	@echo "       ParamHash={tag:cfg-driven, depth:7}"
	@echo "    -> 3 unique wallace modules + 3 clones"
	@echo ""
	@echo "Layered (JSON wins where it sets a value, .cfg fills the rest):"
	@echo "  make gen JSON_CONFIG=config.json CFG_CONFIG=config.py"
	@echo ""
	@echo "Other targets: lint, sim SIMULATOR=verilator|vcs|vlog|iverilog|xrun, clean"
