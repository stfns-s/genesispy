// Fixed-point subtract: a - b (a + ~b when approx), then requant to target.
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
//; s_b, m_b, n_b = _pq(h['q_b'])
//; s_i, m_i, n_i = _pq(h['q_int'])
//; s_o, m_o, n_o = _pq(h['q_out'])
//; w_i = m_i + n_i
function `"signed " if s_o else ""`[`m_o-1`:`-n_o`] `func_name`;
	input [`m_a-1`:`-n_a`] a;
	input [`m_b-1`:`-n_b`] b;
	reg signed [`w_i-1`:0] as, bs;
	begin
		as = `_ext('a', s_a, m_a, n_a, w_i)` <<< `n_i-n_a`;
		bs = `_ext('b', s_b, m_b, n_b, w_i)` <<< `n_i-n_b`;
//; if approx:
		`func_name` = `rq_name`(as + ~bs);
//; else:
		`func_name` = `rq_name`(as - bs);
//; # endif
	end
endfunction
