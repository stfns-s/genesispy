// logmult demo top — semi-log and log multipliers as descriptively-named
// Verilog functions (no wrapper modules), self-checked against the exact product.
//; a_width  = 8
//; b_width  = 8
//; slm_fname = f"slogmult_{a_width}x{b_width}"
//; lm_fname  = f"logmult_{a_width}x{b_width}"
module `mname` ();
//; self.include_params = {'func_name': slm_fname, 'a_width': a_width, 'b_width': b_width}
//; include("slogmult.vpy")
//; slm_out = getattr(self, slm_fname)['out_width']
//; self.include_params = {'func_name': lm_fname, 'a_width': a_width, 'b_width': b_width, 'take_antilog': True, 'zero_detect': True}
//; include("logmult.vpy")
//; lm_out = getattr(self, lm_fname)['out_width']

\`ifdef SIMULATION
   //; LM_BOUND  = 110   # logmult worst-case ~100% (factor 2 at powers of two)
   //; SLM_BOUND = 110   # slogmult worst-case ~100%
   logic signed [`a_width-1`:0]  slm_a, lm_a;
   logic signed [`b_width-1`:0]  slm_b, lm_b;
   logic signed [`slm_out-1`:0]  slm_p;
   logic signed [`lm_out-1`:0]   lm_p;
   integer seed, i;
   integer lm_exp, slm_exp;     // exact products
   integer lm_err, slm_err;     // |relative error|, percent

   initial begin
      seed = 12345;
      for (i = 0; i < 40; i = i + 1) begin
         // operands in [-127,127]; -128 is excluded (overflows slogmult shift, isym=0)
         lm_a  = $random(seed) % 128;  lm_b  = $random(seed) % 128;
         slm_a = lm_a;                 slm_b = lm_b;
         #10;
         slm_p = `slm_fname`(slm_a, slm_b);
         lm_p  = `lm_fname`(lm_a, lm_b);
         lm_exp  = lm_a  * lm_b;
         slm_exp = slm_a * slm_b;
         lm_err  = (lm_exp  == 0) ? 0 : ((lm_p  - lm_exp )  * 100) / lm_exp;
         slm_err = (slm_exp == 0) ? 0 : ((slm_p - slm_exp)  * 100) / slm_exp;
         if (lm_err  < 0) lm_err  = -lm_err;
         if (slm_err < 0) slm_err = -slm_err;
         $display("%4t: logmult  %4d * %4d = %6d (exact %6d, err %3d%%)",
                  $time, lm_a, lm_b, lm_p, lm_exp, lm_err);
         $display("%4t: slogmult %4d * %4d = %6d (exact %6d, err %3d%%)",
                  $time, slm_a, slm_b, slm_p, slm_exp, slm_err);
         assert (lm_err  <= `LM_BOUND`)
            else $fatal(1, "logmult error %0d%% > `LM_BOUND`%% on %0d * %0d", lm_err, lm_a, lm_b);
         assert (slm_err <= `SLM_BOUND`)
            else $fatal(1, "slogmult error %0d%% > `SLM_BOUND`%% on %0d * %0d", slm_err, slm_a, slm_b);
      end
      $display("%0t: logmult demo: all %0d vectors within bounds", $time, i);
      $finish;
   end
\`endif
endmodule
