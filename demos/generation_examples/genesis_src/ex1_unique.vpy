//; # Each unique_inst with distinct resolved params produces a distinct
//; # uniquified module on disk (pll_unq1.v, pll_unq2.v, ...).
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
