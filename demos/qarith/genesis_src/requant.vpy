// Fixed-point requantizer: convert Q_IN -> Q_OUT with rounding + saturation.
//; import re
//; h          = self.include_params
//; func_name  = h.get('func_name', 'f_requant')
//; q_in       = h['q_in']
//; q_out      = h['q_out']
//; round_mode = h.get('round_mode', 'trunc')
//; def _parse_q(s):
//;     mm = re.fullmatch(r'(U?)Q(\d+)\.(\d+)', s.strip())
//;     if not mm:
//;         error(f"{func_name}: bad Q-format {s!r} (want Qm.n or UQm.n)")
//;     return (mm.group(1) == ''), int(mm.group(2)), int(mm.group(3))
//; # enddef
//; if round_mode not in ('trunc', 'half_up', 'half_even'):
//;     error(f"{func_name}: bad round mode {round_mode!r}")
//; # endif
//; s_in,  m_in,  n_in  = _parse_q(q_in)
//; s_out, m_out, n_out = _parse_q(q_out)
//; w_in   = m_in + n_in
//; w_out  = m_out + n_out
//; if w_in < 1 or w_out < 1:
//;     error(f"{func_name}: {q_in} -> {q_out}: a Q format needs at least one bit")
//; # endif
//; if (s_in and m_in < 1) or (s_out and m_out < 1):
//;     error(f"{func_name}: {q_in} -> {q_out}: a signed Q format needs an integer bit for the sign")
//; # endif
//; shift  = n_in - n_out
//; acc_w  = w_in + abs(shift) + 2
//; imax   = (1 << (w_out - 1)) - 1 if s_out else (1 << w_out) - 1
//; osym   = h.get('osym', False)
//; imin   = -((1 << (w_out - 1)) - 1) if (s_out and osym) else (-(1 << (w_out - 1)) if s_out else 0)
//; add_c  = (1 << (shift - 1)) if (shift > 0 and round_mode != 'trunc') else 0
//; tie_mask = (1 << shift) - 1 if shift > 0 else 0
//; tie_val  = (1 << (shift - 1)) if shift > 0 else 0
//; _d = getattr(self, func_name, {}); _d['w_in'] = w_in; _d['w_out'] = w_out; setattr(self, func_name, _d)
// `func_name`: `q_in` -> `q_out`, round=`round_mode`, saturate.
function `"signed " if s_out else ""`[`m_out-1`:`-n_out`] `func_name`;
	input `"signed " if s_in else ""`[`m_in-1`:`-n_in`] x;
	reg signed [`acc_w-1`:0] xs, acc;
	begin
//; if s_in:
		xs = { {`acc_w-w_in`{x[`m_in-1`]}}, x };
//; else:
		xs = { {`acc_w-w_in`{1'b0}}, x };
//; # endif
//; if shift > 0:
		acc = (xs + `add_c`) >>> `shift`;
//;     if round_mode == 'half_even':
		if (((xs & `tie_mask`) == `tie_val`) && acc[0]) acc = acc - 1;
//;     # endif
//; else:
		acc = xs <<< `-shift`;
//; # endif
		if      (acc > `imax`) acc = `imax`;
		else if (acc < `imin`) acc = `imin`;
		`func_name` = acc[`w_out-1`:0];
	end
endfunction
