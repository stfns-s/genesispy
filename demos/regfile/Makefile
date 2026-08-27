TOP    := top
INPUTS := top.vpy reg_file.vpy flop.vpy cfg_ifc.vpy top_flop_only.vpy

# reg_file compares an N-bit address slice against an (N+1)-bit bound: the bound
# is num_regs, which needs the extra bit when num_regs is a power of two. The
# implicit zero-extension is intended, and matches the Genesis2 reference output.
VERILATOR_FLAGS := -Wno-WIDTHEXPAND

include ../genesispy.mk
