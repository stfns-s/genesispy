// pyinclude_examples demo top: wraps the saturating accumulator in leaf.vpy
// and self-checks it against a golden computed at elaboration time.
//
// The three include mechanisms sit side by side here:
//   pyinclude()  raw .py into THIS module's namespace  (emitters.py, below)
//   unique_inst  a separate module with its own namespace (leaf.vpy)
//   include()    a .vpy snippet with its own namespace  (frag.vpy)
//; # Only emitters.py is pyinclude'd here, so decl_signed and check_eq are
//; # bare names below -- but acc_width is not: leaf.vpy pyincluded that into
//; # its own namespace, and namespaces do not cross.
//; pyinclude("emitters.py")
//; term_w = parameter('TERM_W', 8)
//; nterms = parameter('NTERMS', 16)
//; leaf   = unique_inst('leaf', 'u_acc', TERM_W=term_w, NTERMS=nterms)
//; # The width is read back from the leaf rather than re-derived, so there is
//; # one source of truth even though this module cannot call acc_width.
//; acc_w  = leaf.get_param('ACC_W')
//; # Drive past the design point so the clamp is actually exercised.
//; ndrive   = 2 * nterms
//; max_term = (1 << (term_w - 1)) - 1
//; min_term = -(1 << (term_w - 1))
//; sat_hi   = min((1 << (acc_w - 1)) - 1, ndrive * max_term)
//; sat_lo   = max(-(1 << (acc_w - 1)), ndrive * min_term)
//; seen = [n for n in ('decl_signed', 'check_eq', 'acc_width') if n in globals()]
// `mname`: `nterms` x `term_w`-bit terms, acc `acc_w` bits
// pyinclude'd names visible here: `', '.join(seen)`
module `mname` ();
   reg clk;
   reg reset_b;
   reg add_en;
//; decl_signed(self, 'reg', term_w, 'term')
//; decl_signed(self, 'wire', acc_w, 'acc')

   `leaf.instantiate()`
     (
      .clk(clk),
      .reset_b(reset_b),
      .add_en(add_en),
      .term(term),
      .acc(acc)
      );

//; # frag.vpy pyincludes fixed.py inside its own namespace; nothing it binds
//; # comes back here. Values travel out on self, the include() convention.
//; self.include_params = {'func_name': 'headroom', 'term_w': term_w, 'nterms': nterms}
//; include("frag.vpy")
//; frag_out = getattr(self, 'headroom')
//; leaked = [n for n in ('acc_width', 'sat_bounds', 'clog2') if n in globals()]
// leaked into top from frag.vpy's pyinclude: `', '.join(leaked) or '(none)'`

\`ifdef SIMULATION
   integer i, errors;
//; decl_signed(self, 'reg', acc_w, 'exp_hi', 'exp_lo')

   always #5 clk = ~clk;

   task apply_terms;
      input signed [`term_w-1`:0] value;
      begin
         @(negedge clk);
         reset_b = 1'b0;
         term    = value;
         add_en  = 1'b0;
         @(negedge clk);
         reset_b = 1'b1;
         add_en  = 1'b1;
         for (i = 0; i < `ndrive`; i = i + 1) @(negedge clk);
         add_en = 1'b0;
         @(negedge clk);
      end
   endtask

   initial begin
      clk     = 1'b0;
      errors  = 0;
      exp_hi  = `acc_w`'sd`sat_hi`;
      exp_lo  = -`acc_w`'sd`-sat_lo`;

      // `ndrive` terms of `max_term` must clamp at the positive bound
      apply_terms(`term_w`'sd`max_term`);
//; check_eq(self, 'acc', 'exp_hi', 'positive saturation')

      // and `ndrive` terms of `min_term` at the negative bound
      apply_terms(-`term_w`'sd`-min_term`);
//; check_eq(self, 'acc', 'exp_lo', 'negative saturation')

      // headroom() comes from frag.vpy, whose pyinclude is invisible here
//; check_eq(self, 'headroom(1\'b0)', f"32'sd{frag_out['headroom']}", 'headroom')

      if (errors == 0) $display("pyinclude_examples: all vectors PASS");
      else $fatal(1, "pyinclude_examples: %0d mismatch(es)", errors);
      $finish;
   end
\`endif
endmodule
