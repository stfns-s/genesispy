// Fixed-point negate: -x (or one's complement ~x when approx), then requant to target.
//; import re
//; h         = self.include_params
//; func_name = h['func_name']
//; rq_name   = h['rq_name']
//; approx    = h.get('approx', False)
//; def _pq(s):
//;     mm = re.fullmatch(r'(U?)Q(\d+)\.(\d+)', s.strip())
//;     return (mm.group(1) == ''), int(mm.group(2)), int(mm.group(3))
//; # enddef
//; def _ext(nm, s, m, n, wtot):
//;     pad = wtot - (m + n)
//;     if pad == 0:
//;         return nm
//;     fill = f"{{{pad}{{{nm}[{m - 1}]}}}}" if s else f"{{{pad}{{1'b0}}}}"
//;     return f"{{ {fill}, {nm} }}"
//; # enddef
//; s_a, m_a, n_a = _pq(h['q_a'])
//; s_i, m_i, n_i = _pq(h['q_int'])
//; s_o, m_o, n_o = _pq(h['q_out'])
//; w_i = m_i + n_i
//; op  = '~' if approx else '-'
function `"signed " if s_o else ""`[`m_o-1`:`-n_o`] `func_name`;
	input [`m_a-1`:`-n_a`] x;
	reg signed [`w_i-1`:0] xs;
	begin
		xs = `_ext('x', s_a, m_a, n_a, w_i)`;
		`func_name` = `rq_name`(`op`xs);
	end
endfunction
