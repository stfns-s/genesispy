//; from vexpr import decl, lit, sext
//; import qfmt
//; h          = self.include_params
//; func_name  = h.get('func_name', 'f_qcvt')
//; q_in       = h.get('q_in',  'Q4.4')
//; q_out      = h.get('q_out', 'Q2.2')
//; round_mode = h.get('round_mode', 'trunc')
//; osym       = h.get('osym', 0)
//; lifetime   = h.get('lifetime', 'static')
//; src_lo     = h.get('src_lo', None)      # lowest source code that arrives; None: f_in.min_code
//; src_hi     = h.get('src_hi', None)      # highest; None: f_in.max_code
//; saturate   = h.get('saturate', 1)       # 0: reject a configuration whose clamp is reachable
//; def q_or_error(fn, *args):
//;     try:
//;         return fn(*args)
//;     except qfmt.QError as e:
//;         error(f"{func_name}: {e}")
//; # enddef
//; f_in     = q_or_error(qfmt.parse, q_in)
//; f_out    = q_or_error(qfmt.parse, q_out)
//; bounded  = src_lo is not None or src_hi is not None
//; lo_c     = f_in.min_code if src_lo is None else int(src_lo)
//; hi_c     = f_in.max_code if src_hi is None else int(src_hi)
//; if lo_c < f_in.min_code or hi_c > f_in.max_code or lo_c > hi_c:
//;     error(f"{func_name}: source codes {lo_c} .. {hi_c} do not lie in {f_in} "
//;         f"({f_in.min_code} .. {f_in.max_code})")
//; # endif
//; src      = q_or_error(qfmt.Bounds, lo_c, hi_c, f_in.frac, f_in.signed)
//; rq       = q_or_error(qfmt.requant, src, f_out, round_mode, bool(osym))
//; # A clamp end is emitted where a source code can reach it. Without source bounds both
//; # are emitted, so a caller that gives none gets the output it always got.
//; sat_lo, sat_hi = rq.sat_lo, rq.sat_hi
//; if not saturate and (sat_lo or sat_hi):
//;     ends = ' and '.join(e for e, hit in (('low', sat_lo), ('high', sat_hi)) if hit)
//;     error(f"{func_name}: {f_in} -> {f_out} under {round_mode} clamps at the {ends} end over "
//;         f"source codes {lo_c} .. {hi_c}, and saturate=0 forbids a clamp")
//; # endif
//; emit_lo  = sat_lo or not bounded
//; emit_hi  = sat_hi or not bounded
//; iwidth   = f_in.width
//; owidth   = f_out.width
//; shift    = rq.shift
//; acc_w    = max(iwidth + abs(shift) + 2, owidth + (0 if f_out.signed else 1))
//; img   = rq.image()
//; def rng(b):
//;     return f"codes {b.lo} .. {b.hi}, values {float(b.lo_val)} .. {float(b.hi_val)}"
//; # enddef
//; clamp = "saturating" if emit_lo or emit_hi else "no clamp"
//; note  = ", output symmetric" if osym else ""
    // `func_name`: `q_in` -> `q_out`, round=`round_mode`, `clamp``note`
    //     in:  `rng(src)`
    //     out: `rng(img)`
//; # Rounding is a carry into the kept bits, not a constant added before the shift: every
//; # mode is c = a & (b | sticky), where sticky ORs the dropped bits below the half bit.
//; # half_even's b is the kept lsb, so it needs no second pass to step a tie down.
//; def carry_expr(mode, s, w, nonneg):
//;     half, kept_lsb, sign = f"xs[{s-1}]", f"xs[{s}]", f"xs[{w-1}]"
//;     if mode == 'trunc' or (mode == 'to_zero' and nonneg):
//;         return None
//;     # endif
//;     if mode == 'half_up' or (mode == 'half_away' and nonneg):
//;         return half
//;     # endif
//;     if mode == 'half_even':
//;         a, b = half, kept_lsb
//;     elif mode == 'half_away':
//;         a, b = half, f"~{sign}"
//;     elif mode == 'to_zero':
//;         a, b = sign, half
//;     else:
//;         error(f"{func_name}: bad round_mode {mode}")
//;     # endif
//;     if s < 2:
//;         return f"{a} & {b}"
//;     # endif
//;     return f"{a} & ({b} | (|xs[{s-2}:0]))"
//; # enddef
//; cw = None
//; if shift > 0:
//;     carry = carry_expr(round_mode, shift, acc_w, rq.src_bounds.lo >= 0)
//;     if carry is None:
//;         expr = f"xs >>> {shift}"
//;     else:
//;         # cy is a declared-signed reg so the sum stays signed without a cast: a shift's
//;         # left operand takes its signedness from the whole expression, and one unsigned
//;         # term would turn >>> into a logical shift. The zero fill is an assignment, so
//;         # cy is non-negative and the extension costs nothing.
//;         cw   = sext(carry, 1, acc_w, signed=False)
//;         expr = f"(xs >>> {shift}) + cy"
//;     # endif
//; elif shift < 0:
//;     expr = f"xs <<< {-shift}"
//; else:
//;     expr = "xs"
//; # endif
//; direct = not (emit_hi or emit_lo)
//; regs   = "xs" + ("" if direct else ", acc") + (", cy" if cw else "")
    function `lifetime` `decl(f_out, pad=False)` `func_name`;
        input `decl(f_in, pad=False)` qin;
        reg signed [`acc_w-1`:0] `regs`;
        begin
            xs = `sext('qin', iwidth, acc_w, msb=f_in.int_bits-1, signed=f_in.signed)`;
//; if cw:
            cy = `cw`;
//; # endif
//; if direct:
            `func_name` = `owidth`'(`expr`);
//; else:
            acc = `expr`;
//;     if emit_hi and emit_lo:
            if      ( acc > `lit(rq.max_code, acc_w)` ) acc = `lit(rq.max_code, acc_w)`;
            else if ( acc < `lit(rq.min_code, acc_w)` ) acc = `lit(rq.min_code, acc_w)`;
            `func_name` = acc[`owidth-1`:0];
//;     else:
//;         if emit_hi:
            if ( acc > `lit(rq.max_code, acc_w)` ) acc = `lit(rq.max_code, acc_w)`;
//;         # endif
//;         if emit_lo:
            if ( acc < `lit(rq.min_code, acc_w)` ) acc = `lit(rq.min_code, acc_w)`;
//;         # endif
            `func_name` = `owidth`'(acc);
//;     # endif
//; # endif
        end
    endfunction
//; _d = getattr(self, func_name, {}); _d['iwidth'] = iwidth; _d['owidth'] = owidth
//; _d['shift'] = shift
//; setattr(self, func_name, _d)
