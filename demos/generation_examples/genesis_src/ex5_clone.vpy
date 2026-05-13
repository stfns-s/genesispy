//; # Elaborate one unique pll module, then clone it for the other instances.
//; # clone_inst doesn't re-resolve params or re-run the body -- it just
//; # binds a new instance name to the source's already-emitted Verilog.
//; src = unique_inst('pll', 'u_pll0', M=8)
//; insts = [src] + [clone_inst(src, f'u_pll{i}') for i in range(1, 3)]
module `mname` (input clk_in, output [2:0] clk);
//; for i, u in enumerate(insts):
   `u.instantiate()` (.clk_in(clk_in), .clk_out(clk[`i`]));
//; # endfor
endmodule
