//; # Each generate_w_name call: registers 'my_pll' as a class-level
//; # synonym of 'pll' (idempotent), then ununique_insts under that
//; # synonym. Disk file gets the synonym name; subsequent calls with
//; # the same resolved params alias to the first.
//; insts = []
//; for i in range(3):
//;     insts.append(generate_w_name('pll', 'my_pll', f'u_pll{i}', M=8))
//; # endfor
module `mname` (input clk_in, output [2:0] clk);
//; for i, u in enumerate(insts):
   `u.instantiate()` (.clk_in(clk_in), .clk_out(clk[`i`]));
//; # endfor
endmodule
