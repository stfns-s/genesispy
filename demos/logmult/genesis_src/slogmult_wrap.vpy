// Wrapper module exposing f_slogmult as a*b -> p
//; a_width = self.parameter('A_WIDTH', 8)      # multiplicand (a) bit width
//; b_width = self.parameter('B_WIDTH', 8)      # multiplier (b) bit width
//; func_name  = 'f_slogmult'
module `mname` (a, b, p);
//; self.include_params = {'func_name': func_name, 'a_width': a_width, 'b_width': b_width}
//; include("slogmult.vpy")
//; out_width = getattr(self, func_name)['out_width']
   input  signed [`a_width-1`:0] a;
   input  signed [`b_width-1`:0] b;
   output signed [`out_width-1`:0]     p;
   assign p = `func_name`(a, b);
endmodule
