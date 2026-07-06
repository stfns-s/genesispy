// qrequant demo top: fixed-point requantizers as descriptively-named Verilog
// functions, self-checked vs a fixedpoint golden.
//; import re, random
//; from fractions import Fraction
//; from fixedpoint import FixedPoint
//; _RMAP = {'trunc': 'down', 'half_up': 'nearest', 'half_even': 'convergent'}
//; def _parse_q(s):
//;     mm = re.fullmatch(r'(U?)Q(\d+)\.(\d+)', s.strip())
//;     return (mm.group(1) == ''), int(mm.group(2)), int(mm.group(3))
//; # enddef
//; def _fname(q_in, q_out):
//;     return f"{q_in.strip().lower().replace('.', 'd')}_to_{q_out.strip().lower().replace('.', 'd')}"
//; # enddef
//; def _golden(code, q_in, q_out, mode):
//;     s_in, m_in, n_in    = _parse_q(q_in)
//;     s_out, m_out, n_out = _parse_q(q_out)
//;     w_in = m_in + n_in
//;     iv = code - (1 << w_in) if (s_in and (code >> (w_in - 1)) & 1) else code
//;     v = Fraction(iv, 1 << n_in)
//;     if s_out:
//;         lo = Fraction(-(1 << (m_out + n_out - 1)), 1 << n_out)
//;         hi = Fraction((1 << (m_out + n_out - 1)) - 1, 1 << n_out)
//;     else:
//;         lo = Fraction(0)
//;         hi = Fraction((1 << (m_out + n_out)) - 1, 1 << n_out)
//;     v = max(lo, min(hi, v))
//;     fx = FixedPoint(float(v), signed=s_out, m=m_out, n=n_out, overflow='clamp',
//;                     rounding=_RMAP[mode], overflow_alert='ignore',
//;                     implicit_cast_alert='ignore', mismatch_alert='ignore')
//;     return fx.bits
//; # enddef
//; def _vectors(q_in, q_out, mode):
//;     s_in, m_in, n_in = _parse_q(q_in)
//;     w_in = m_in + n_in
//;     if w_in <= 12:
//;         codes = list(range(1 << w_in))
//;     else:
//;         rng = random.Random(0xC0FFEE)
//;         corners = {0, (1 << w_in) - 1, 1 << (w_in - 1)}
//;         codes = sorted(corners | set(rng.sample(range(1 << w_in), 128)))
//;     return [(c, _golden(c, q_in, q_out, mode)) for c in codes]
//; # enddef
//; insts = [
//;     ('Q4.12', 'Q2.6',  'half_even'),
//;     ('UQ8.8', 'UQ4.4', 'half_up'),
//;     ('Q3.5',  'Q3.9',  'trunc'),
//;     ('Q4.4',  'UQ4.4', 'trunc'),
//; ]
//; meta = []
module `mname` ();
//; for q_in, q_out, mode in insts:
//;     s_in, m_in, n_in    = _parse_q(q_in)
//;     s_out, m_out, n_out = _parse_q(q_out)
//;     wi = m_in + n_in; wo = m_out + n_out
//;     fname = _fname(q_in, q_out)
//;     self.include_params = {'func_name': fname, 'q_in': q_in, 'q_out': q_out, 'round_mode': mode}
//;     include("requant.vpy")
//;     meta.append((fname, wi, wo, q_in, q_out, mode, _vectors(q_in, q_out, mode)))
//; # endfor

\`ifdef SIMULATION
   integer i, errors;
//; for fname, wi, wo, q_in, q_out, mode, vecs in meta:
//;     n = len(vecs)
   reg [`wi-1`:0] `fname`_stim [0:`n-1`];
   reg [`wo-1`:0] `fname`_exp  [0:`n-1`];
   reg [`wo-1`:0] `fname`_res;
//; # endfor
   initial begin
      errors = 0;
//; for fname, wi, wo, q_in, q_out, mode, vecs in meta:
//;     for j, (code, exp) in enumerate(vecs):
      `fname`_stim[`j`] = `wi`'d`code`; `fname`_exp[`j`] = `wo`'d`exp`;
//;     # endfor
//; # endfor
//; for fname, wi, wo, q_in, q_out, mode, vecs in meta:
//;     n = len(vecs)
      for (i = 0; i < `n`; i = i + 1) begin
         `fname`_res = `fname`(`fname`_stim[i]);
         if (`fname`_res !== `fname`_exp[i]) begin
            errors = errors + 1;
            $display("FAIL `fname` (`q_in`->`q_out` `mode`) x=%0d y=%0d exp=%0d",
                     `fname`_stim[i], `fname`_res, `fname`_exp[i]);
         end
      end
//; # endfor
      if (errors == 0) $display("qrequant: all vectors PASS");
      else $fatal(1, "qrequant: %0d mismatch(es)", errors);
      $finish;
   end
\`endif
endmodule
