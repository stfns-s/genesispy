//; # Generate three instances of "pll". First ununique_inst call wins
//; # the bare on-disk name "pll.v"; subsequent calls with the same
//; # resolved params alias to it (only the instance name changes).
//; insts = []
//; for i in range(3):
//;     insts.append(ununique_inst('pll', f'u_pll{i}', M=8))
//; # endfor
module `mname` (input clk_in, output [2:0] clk);
//; for i, u in enumerate(insts):
   `u.instantiate()` (.clk_in(clk_in), .clk_out(clk[`i`]));
//; # endfor
endmodule
