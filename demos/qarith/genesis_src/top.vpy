// qarith demo top: fixed-point requantize + arithmetic (neg/add/sub/mul) as
// descriptively-named Verilog functions, self-checked vs a fixedpoint golden.
//; import re, random
//; from fractions import Fraction
//; from fixedpoint import FixedPoint
//; _RMAP = {'trunc': 'down', 'half_up': 'nearest', 'half_even': 'convergent'}
//; def _parse_q(s):
//;     mm = re.fullmatch(r'(U?)Q(\d+)\.(\d+)', s.strip())
//;     return (mm.group(1) == ''), int(mm.group(2)), int(mm.group(3))
//; # enddef
//; def _tag(q):
//;     return q.strip().lower().replace('.', 'd')
//; # enddef
//; def _decode(code, s, m, n):
//;     w = m + n
//;     iv = code - (1 << w) if (s and (code >> (w - 1)) & 1) else code
//;     return Fraction(iv, 1 << n)
//; # enddef
//; def _round(v, q_out, mode, osym):
//;     s_out, m_out, n_out = _parse_q(q_out)
//;     if s_out:
//;         lo_code = -((1 << (m_out + n_out - 1)) - 1) if osym else -(1 << (m_out + n_out - 1))
//;         lo = Fraction(lo_code, 1 << n_out)
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
//; def _int_fmt(op, fmts):
//;     ps = [_parse_q(f) for f in fmts]
//;     if op == 'neg':
//;         _s, m, n = ps[0]
//;         return f"Q{m + 1}.{n}"
//;     (sa, ma, na), (sb, mb, nb) = ps
//;     if op in ('add', 'sub'):
//;         n_i = max(na, nb)
//;         m_i = max(ma, mb) + 1
//;         signed = (op == 'sub') or sa or sb
//;     else:
//;         n_i = na + nb
//;         m_i = ma + mb
//;         signed = sa or sb
//;     return f"{'' if signed else 'U'}Q{m_i}.{n_i}"
//; # enddef
//; def _opname(op, fmts, q_out, osym, approx):
//;     name = '_'.join([op] + [_tag(f) for f in fmts] + ['to', _tag(q_out)])
//;     if osym:
//;         name += '_sym'
//;     if approx:
//;         name += '_approx'
//;     return name
//; # enddef
//; def _op_result(op, vals, ulp_i, approx):
//;     if op == 'requant':
//;         return vals[0]
//;     if op == 'neg':
//;         return -vals[0] - (ulp_i if approx else 0)
//;     if op == 'add':
//;         return vals[0] + vals[1]
//;     if op == 'sub':
//;         return vals[0] - vals[1] - (ulp_i if approx else 0)
//;     return vals[0] * vals[1]
//; # enddef
//; def _codes(fmts):
//;     ws = [m + n for _s, m, n in [_parse_q(f) for f in fmts]]
//;     if len(ws) == 1:
//;         w = ws[0]
//;         if w <= 12:
//;             return [(c,) for c in range(1 << w)]
//;         rng = random.Random(0xC0FFEE)
//;         corners = {0, (1 << w) - 1, 1 << (w - 1)}
//;         return [(c,) for c in sorted(corners | set(rng.sample(range(1 << w), 128)))]
//;     wa, wb = ws
//;     if wa + wb <= 12:
//;         return [(a, b) for a in range(1 << wa) for b in range(1 << wb)]
//;     rng = random.Random(0xC0FFEE)
//;     ca = {0, (1 << wa) - 1, 1 << (wa - 1)}
//;     cb = {0, (1 << wb) - 1, 1 << (wb - 1)}
//;     corners = {(a, b) for a in ca for b in cb}
//;     sample = {(rng.randrange(1 << wa), rng.randrange(1 << wb)) for _i in range(256)}
//;     return sorted(corners | sample)
//; # enddef
//; def _vectors(op, fmts, q_int, q_out, mode, osym, approx):
//;     ps = [_parse_q(f) for f in fmts]
//;     ulp_i = Fraction(1, 1 << _parse_q(q_int)[2])
//;     rows = []
//;     for codes in _codes(fmts):
//;         vals = [_decode(c, *p) for c, p in zip(codes, ps)]
//;         rows.append(tuple(codes) + (_round(_op_result(op, vals, ulp_i, approx), q_out, mode, osym),))
//;     # endfor
//;     return rows
//; # enddef
//; # A signed result assigned into a wider variable must sign-extend; _sx turns a
//; # raw output code into its signed value, _sd emits it as a sized literal.
//; _sx = lambda v, w: v - (1 << w) if (v >> (w - 1)) & 1 else v
//; _sd = lambda v, w: f"{w}'sd{v}" if v >= 0 else f"-{w}'sd{-v}"
//; WIDE_PAD = 4
//; # requant instances: (q_in, q_out, round_mode)
//; REQUANT = [
//;     ('Q4.12', 'Q2.6',  'half_even'),
//;     ('UQ8.8', 'UQ4.4', 'half_up'),
//;     ('Q3.5',  'Q3.9',  'trunc'),
//;     ('Q4.4',  'UQ4.4', 'trunc'),
//; ]
//; # arithmetic instances: (op, [operand formats], q_out, round_mode, osym, approx)
//; OPS = [
//;     ('neg', ['Q3.2'], 'Q4.2', 'half_even', False, False),
//;     ('neg', ['Q3.2'], 'Q3.2', 'half_even', True,  True ),
//;     ('add', ['Q2.2', 'Q1.3'],   'Q3.3',  'half_even', False, False),
//;     ('add', ['UQ2.2', 'UQ2.2'], 'UQ3.2', 'half_even', False, False),
//;     ('sub', ['Q2.2', 'Q2.2'],   'Q3.2',  'half_even', False, False),
//;     ('sub', ['Q2.2', 'Q2.2'],   'Q2.2',  'half_even', True,  True ),
//;     ('mul', ['Q2.2', 'Q2.2'],   'Q4.4',  'half_even', False, False),
//;     ('mul', ['UQ2.2', 'UQ2.2'], 'UQ4.4', 'half_even', False, False),
//;     ('mul', ['Q2.2', 'UQ2.2'],  'Q4.4',  'half_even', False, False),
//; ]
//; meta = []
module `mname` ();
//; for q_in, q_out, mode in REQUANT:
//;     name = _tag(q_in) + '_to_' + _tag(q_out)
//;     s_in, m_in, n_in = _parse_q(q_in)
//;     s_out, m_out, n_out = _parse_q(q_out)
//;     self.include_params = {'func_name': name, 'q_in': q_in, 'q_out': q_out, 'round_mode': mode, 'osym': False}
//;     include("requant.vpy")
//;     meta.append({'name': name, 'arity': 1, 'ports': [(m_in, n_in)], 'wo': m_out + n_out, 'sgn': s_out, 'label': f"{q_in}->{q_out} {mode}", 'vecs': _vectors('requant', [q_in], q_in, q_out, mode, False, False)})
//; # endfor
//; for op, fmts, q_out, mode, osym, approx in OPS:
//;     name = _opname(op, fmts, q_out, osym, approx)
//;     q_int = _int_fmt(op, fmts)
//;     rq = name + '_rq'
//;     self.include_params = {'func_name': rq, 'q_in': q_int, 'q_out': q_out, 'round_mode': mode, 'osym': osym}
//;     include("requant.vpy")
//;     ip = {'func_name': name, 'q_int': q_int, 'q_out': q_out, 'rq_name': rq, 'approx': approx, 'q_a': fmts[0]}
//;     if len(fmts) > 1:
//;         ip['q_b'] = fmts[1]
//;     self.include_params = ip
//;     include(op + ".vpy")
//;     s_out, m_out, n_out = _parse_q(q_out)
//;     ports = [(_parse_q(f)[1], _parse_q(f)[2]) for f in fmts]
//;     lbl = f"{op} {' '.join(fmts)} -> {q_out}" + (' sym' if osym else '') + (' approx' if approx else '')
//;     meta.append({'name': name, 'arity': len(fmts), 'ports': ports, 'wo': m_out + n_out, 'sgn': s_out, 'label': lbl, 'vecs': _vectors(op, fmts, q_int, q_out, mode, osym, approx)})
//; # endfor

\`ifdef SIMULATION
   integer i, errors;
//; for e in meta:
//;     nv = len(e['vecs'])
//;     for k, (mk, nk) in enumerate(e['ports']):
   reg [`mk + nk - 1`:0] `e['name']`_in`k` [0:`nv - 1`];
//;     # endfor
   reg [`e['wo'] - 1`:0] `e['name']`_exp [0:`nv - 1`];
   reg [`e['wo'] - 1`:0] `e['name']`_res;
//;     if e['sgn']:
   reg signed [`e['wo'] + WIDE_PAD - 1`:0] `e['name']`_wide;
   reg signed [`e['wo'] + WIDE_PAD - 1`:0] `e['name']`_wexp [0:`nv - 1`];
//;     # endif
//; # endfor
   initial begin
      errors = 0;
//; for e in meta:
//;     for j, vec in enumerate(e['vecs']):
//;         for k in range(e['arity']):
//;             mk, nk = e['ports'][k]
      `e['name']`_in`k`[`j`] = `mk + nk`'d`vec[k]`;
//;         # endfor
      `e['name']`_exp[`j`] = `e['wo']`'d`vec[-1]`;
//;         if e['sgn']:
      `e['name']`_wexp[`j`] = `_sd(_sx(vec[-1], e['wo']), e['wo'] + WIDE_PAD)`;
//;         # endif
//;     # endfor
//; # endfor
//; for e in meta:
//;     nv = len(e['vecs'])
//;     args = ", ".join(f"{e['name']}_in{k}[i]" for k in range(e['arity']))
      for (i = 0; i < `nv`; i = i + 1) begin
         `e['name']`_res = `e['name']`(`args`);
         if (`e['name']`_res !== `e['name']`_exp[i]) begin
            errors = errors + 1;
            $display("FAIL `e['label']` idx=%0d res=%0d exp=%0d",
                     i, `e['name']`_res, `e['name']`_exp[i]);
         end
      end
//; # endfor
//; # A signed function assigned into something wider must sign-extend; an
//; # unsigned declaration would zero-extend and turn negatives positive.
//; for e in meta:
//;     if e['sgn']:
//;         args = ", ".join(f"{e['name']}_in{k}[i]" for k in range(e['arity']))
      for (i = 0; i < `len(e['vecs'])`; i = i + 1) begin
         `e['name']`_wide = `e['name']`(`args`);
         if (`e['name']`_wide !== `e['name']`_wexp[i]) begin
            errors = errors + 1;
            $display("FAIL wide `e['label']` idx=%0d res=%0d exp=%0d",
                     i, `e['name']`_wide, `e['name']`_wexp[i]);
         end
      end
//;     # endif
//; # endfor
      if (errors == 0) $display("qarith: all vectors PASS");
      else $fatal(1, "qarith: %0d mismatch(es)", errors);
      $finish;
   end
\`endif
endmodule
