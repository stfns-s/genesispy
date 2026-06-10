// Wrapper module exposing f_logmult as a*b -> p
//; a_width  = self.parameter('A_WIDTH', 8)     # multiplicand (a) bit width
//; b_width  = self.parameter('B_WIDTH', 8)     # multiplier (b) bit width
//; take_antilog = self.parameter('TAKE_ANTILOG', True) # True: output the product; False: output log2 of the product
//; zero_detect  = self.parameter('ZERO_DETECT', False) # True: force result to 0 when a or b == 0
//; func_name   = 'f_logmult'
module `mname` (a, b, p);
//; self.include_params = {'func_name': func_name, 'a_width': a_width, 'b_width': b_width, 'take_antilog': take_antilog, 'zero_detect': zero_detect}
//; include("logmult.vpy")
//; out_width = getattr(self, func_name)['out_width']
   input  signed [`a_width-1`:0] a;
   input  signed [`b_width-1`:0] b;
   output signed [`out_width-1`:0]     p;
   assign p = `func_name`(a, b);
endmodule
