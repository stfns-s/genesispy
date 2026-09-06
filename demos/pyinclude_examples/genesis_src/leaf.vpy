// pyinclude_examples leaf: a saturating signed accumulator whose widths are
// computed by lib/fixed.py, pyinclude'd into this module's own namespace.
//; pyinclude("fixed.py")
//; term_w = parameter('TERM_W', 8)     # width of one addend
//; nterms = parameter('NTERMS', 16)    # addends the accumulator must hold
//; if not isinstance(term_w, int) or not 2 <= term_w <= 24:
//;     error(f"TERM_W ({term_w!r}) must be an integer in 2..24")
//; # endif
//; if not isinstance(nterms, int) or nterms < 2:
//;     error(f"NTERMS ({nterms!r}) must be an integer >= 2")
//; # endif
//; acc_w = acc_width(term_w, nterms)
//; if acc_w > ACC_W_MAX:
//;     error(f"accumulator width {acc_w} exceeds ACC_W_MAX ({ACC_W_MAX})")
//; # endif
//; lo, hi = sat_bounds(acc_w)
//; sum_w  = acc_w + 1
//; # Published so the parent sizes its port from here rather than re-deriving.
//; parameter('ACC_W', acc_w, force=True)
//; # decl_signed lives in top.vpy's namespace, not this one: pyinclude binds
//; # into the calling module only. This line records what is actually visible.
//; seen = [n for n in ('acc_width', 'sat_bounds', 'decl_signed') if n in globals()]
//; f_term = f"signed [{term_w-1}:0]"
//; f_acc  = f"signed [{acc_w-1}:0]"
//; fw     = max(len(f_term), len(f_acc))
//; def fld(s):
//;     return f"{s:<{fw}}"
//; # enddef
// `mname`: `nterms` x `term_w`-bit terms -> `acc_w`-bit acc, saturating `lo` .. `hi`
// pyinclude'd names visible here: `', '.join(seen)`
module `mname` (
    input  wire `fld('')` clk,
    input  wire `fld('')` reset_b,
    input  wire `fld('')` add_en,
    input  wire `fld(f_term)` term,
    output reg  `fld(f_acc)` acc
);
   // One extra bit so the add cannot wrap before the clamp sees it.
   wire signed [`sum_w-1`:0] term_ext = {{`sum_w-term_w`{term[`term_w-1`]}}, term};
   wire signed [`sum_w-1`:0] sum      = {acc[`acc_w-1`], acc} + term_ext;

   logic signed [`acc_w-1`:0] next_acc;
   always @(*) begin
      next_acc = sum[`acc_w-1`:0];
      if      (sum > `sum_w`'sd`hi`)  next_acc = `acc_w`'sd`hi`;
      else if (sum < -`sum_w`'sd`-lo`) next_acc = -`acc_w`'sd`-lo`;
   end

   always @(posedge clk or negedge reset_b) begin
      if (!reset_b)    acc <= {`acc_w`{1'b0}};
      else if (add_en) acc <= next_acc;
   end
endmodule
