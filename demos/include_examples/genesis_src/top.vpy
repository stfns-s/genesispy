// include_examples demo top: leaves pulled in with include() and emitted as
// Verilog functions directly into this module, self-checked against a golden
// built at elaboration time.
//; # WIDTH is a scalar so `make gen EXTRA_FLAGS='-p WIDTH=1'` can reach it: the
//; # CLI coerces scalars only, so a list-valued parameter would arrive as a string.
//; width  = parameter('WIDTH', 5)
//; # The fixed 3 keeps two codecs in every build, so one leaf is always included
//; # twice under derived names. The set collapses to one when WIDTH is 3.
//; widths = sorted({3, width})
//; GRAY_W     = 4
//; gray_fname = f"gray_enc_w{GRAY_W}"
//; gray_table = [x ^ (x >> 1) for x in range(1 << GRAY_W)]
//; codecs     = []
module `mname` ();
//; for w in widths:
//;     name = f"gray_codec_w{w}"
//;     self.include_params = {'func_name': name, 'width': w}
//;     include("codec.vpy")
//;     codecs.append({'name': name, 'width': w, 'owidth': getattr(self, name)['owidth']})
//; # endfor
//; # gray.vpy also included straight from here, not only through codec.vpy.
//; self.include_params = {'func_name': gray_fname, 'width': GRAY_W, 'direction': 'encode'}
//; include("gray.vpy")
//; gray_ow = getattr(self, gray_fname)['owidth']

\`ifdef SIMULATION
   integer i, errors;
//; for c in codecs:
   reg [`c['owidth']-1`:0] `c['name']`_res;
//; # endfor
   reg [`gray_ow-1`:0] `gray_fname`_res;
   reg [`gray_ow-1`:0] `gray_fname`_exp [0:`(1 << GRAY_W) - 1`];

   initial begin
      errors = 0;
//; for c in codecs:
      // every code must come back unchanged through encode then decode
      for (i = 0; i < `1 << c['width']`; i = i + 1) begin
         `c['name']`_res = `c['name']`(i[`c['width']-1`:0]);
         if (`c['name']`_res !== i[`c['width']-1`:0]) begin
            errors = errors + 1;
            $display("FAIL `c['name']` x=%0d round trip=%0d", i, `c['name']`_res);
         end
      end
//; # endfor
      // the directly included encoder against a table built at elaboration time
//; for x in range(1 << GRAY_W):
      `gray_fname`_exp[`x`] = `gray_ow`'d`gray_table[x]`;
//; # endfor
      for (i = 0; i < `1 << GRAY_W`; i = i + 1) begin
         `gray_fname`_res = `gray_fname`(i[`GRAY_W-1`:0]);
         if (`gray_fname`_res !== `gray_fname`_exp[i]) begin
            errors = errors + 1;
            $display("FAIL `gray_fname` x=%0d res=%0d exp=%0d",
                     i, `gray_fname`_res, `gray_fname`_exp[i]);
         end
      end
      if (errors == 0) $display("include_examples: all vectors PASS");
      else $fatal(1, "include_examples: %0d mismatch(es)", errors);
      $finish;
   end
\`endif
endmodule
