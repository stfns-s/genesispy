// logmult demo top — semi-log and log multipliers as descriptively-named
// Verilog functions (no wrapper modules), self-checked against the exact product.
//; import random
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
//; # A fractional-log instance and a log-domain instance with its antilog helper.
//; # top only needs logmult_8x8, but both paths ship, so both get checked here.
//; LG_FRAC  = 2
//; lg_fname = f"ilog2_{a_width}_f{LG_FRAC}"
//; nl_fname = f"logmult_{a_width}x{b_width}_nl"
//; self.include_params = {'func_name': lg_fname, 'input_width': a_width, 'log_frac_bits': LG_FRAC}
//; include("ilog2.vpy")
//; lg_out = getattr(self, lg_fname)['out_width']
//; lg_w   = lg_out - 1
//; self.include_params = {'func_name': nl_fname, 'a_width': a_width, 'b_width': b_width, 'take_antilog': False, 'zero_detect': True}
//; include("logmult.vpy")
//; nl_out = getattr(self, nl_fname)['out_width']
//; nl_pw  = getattr(self, nl_fname)['product_width']

\`ifdef SIMULATION
   //; LM_BOUND  = 110   # logmult worst-case ~100% (factor 2 at powers of two)
   //; SLM_BOUND = 110   # slogmult worst-case ~100%
   //; # antilog(core(a,b)) must reproduce the in-core antilog bit for bit: both
   //; # paths compute the same approximation, one inside core, one after it.
   //; # A relative-error bound is far too loose here -- a halved magnitude is
   //; # only -50%, well inside the 110% the log approximation itself needs.
   //; NVEC      = 40
   //; # Vectors are built here rather than by $random(seed) in the testbench:
   //; # verilator 5.020 degenerates that sequence into repeated small powers of
   //; # two as soon as another function call is added to the loop.  Building them
   //; # here also makes every simulator run the same stimulus.
   //; # Operands are in [-127,127]; -128 overflows the slogmult shift at isym=0.
   //; _sdec = lambda v, w: f"{w}'sd{v}" if v >= 0 else f"-{w}'sd{-v}"
   //; _rng  = random.Random(12345)
   //; _vecs = [(_rng.randint(-127, 127), _rng.randint(-127, 127)) for _ in range(NVEC)]
   //; # floor(2**lfrac * log2(2 * trunc)) by integer search, derived independently
   //; # of the emitted table so a repeat of the table's own error cannot agree.
   //; def _lg_golden(x, lfrac):
   //;     lscale = 1 << lfrac
   //;     nb     = x.bit_length()
   //;     keep   = lfrac + 1 if lfrac + 1 < nb else nb
   //;     trunc  = (x >> (nb - keep)) << (nb - keep)
   //;     t      = (2 * trunc) ** lscale
   //;     k      = 0
   //;     while (1 << (k + 1)) <= t:
   //;         k = k + 1
   //;     # endwhile
   //;     return k
   //; # enddef
   logic signed [`a_width-1`:0]  slm_a, lm_a;
   logic signed [`b_width-1`:0]  slm_b, lm_b;
   logic signed [`slm_out-1`:0]  slm_p;
   logic signed [`lm_out-1`:0]   lm_p;
   integer i;
   logic signed [`a_width-1`:0] tb_a [0:`NVEC-1`];
   logic signed [`b_width-1`:0] tb_b [0:`NVEC-1`];
   integer lm_exp, slm_exp;     // exact products
   integer lm_err, slm_err;     // |relative error|, percent
   logic signed [`nl_out-1`:0]  nl_l;
   logic signed [`nl_pw-1`:0]   nl_p;
   integer nl_exp;
   logic [`lg_out-1`:0] lg_res;
   logic [`lg_w-1`:0]   lg_golden [0:`(1 << (a_width - 1)) - 1`];
   integer x;

   initial begin
//; for _n, (_a, _b) in enumerate(_vecs):
      tb_a[`_n`] = `_sdec(_a, a_width)`; tb_b[`_n`] = `_sdec(_b, b_width)`;
//; # endfor
      for (i = 0; i < `NVEC`; i = i + 1) begin
         lm_a  = tb_a[i];  lm_b  = tb_b[i];
         slm_a = lm_a;     slm_b = lm_b;
         #10;
         slm_p = `slm_fname`(slm_a, slm_b);
         lm_p  = `lm_fname`(lm_a, lm_b);
         nl_l  = `nl_fname`(lm_a, lm_b);
         nl_p  = `nl_fname`_antilog(nl_l);
         lm_exp  = lm_a  * lm_b;
         nl_exp  = lm_exp;
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
         assert (nl_p === lm_p)
            else $fatal(1, "antilog mismatch on %0d * %0d: antilog(core)=%0d, in-core=%0d (exact %0d)",
                        lm_a, lm_b, nl_p, lm_p, nl_exp);
      end
      $display("%0t: logmult demo: all %0d vectors within bounds", $time, i);

//; for _x in range(1, 1 << (a_width - 1)):
      lg_golden[`_x`] = `lg_w`'d`_lg_golden(_x, LG_FRAC)`;
//; # endfor
      for (x = 1; x < `1 << (a_width - 1)`; x = x + 1) begin
         lg_res = `lg_fname`(x[`a_width-1`:0]);
         assert (lg_res[`lg_w-1`:0] === lg_golden[x])
            else $fatal(1, "ilog2 log_frac_bits=`LG_FRAC` on x=%0d: got %0d, expected %0d",
                        x, lg_res[`lg_w-1`:0], lg_golden[x]);
      end
      $display("%0t: logmult demo: ilog2 log_frac_bits=`LG_FRAC` exact over %0d magnitudes",
               $time, x - 1);
      $finish;
   end
\`endif
endmodule
