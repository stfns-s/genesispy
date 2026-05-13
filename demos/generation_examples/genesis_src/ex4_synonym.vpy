//; # Register 'my_pll' as a class-level synonym of 'pll' once.
//; # The 2-arg synonym form delegates to Manager.synonym_class.
//; synonym('pll', 'my_pll')
//; # Then instantiate as many times as needed via generate_base
//; # (= ununique_inst), referring to the synonym name.
//; insts = []
//; for i in range(3):
//;     insts.append(generate_base('my_pll', f'u_pll{i}', M=8))
//; # endfor
module `mname` (input clk_in, output [2:0] clk);
//; for i, u in enumerate(insts):
   `u.instantiate()` (.clk_in(clk_in), .clk_out(clk[`i`]));
//; # endfor
endmodule
