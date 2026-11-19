//; from genesispy.lib.verilog import decl, limit, sext
//; import qfmt
//; h          = self.include_params
//; func_name  = h.get('func_name', 'f_qcvt')
//; q_in       = h.get('q_in',  'Q4.4')
//; q_out      = h.get('q_out', 'Q2.2')
//; round_mode = h.get('round_mode', 'trunc')
//; osymm      = h.get('osymm', 0)
//; lifetime   = h.get('lifetime', 'static')
//; src_lo     = h.get('src_lo', None)      # lowest source code that arrives; None: f_in.min_code
//; src_hi     = h.get('src_hi', None)      # highest; None: f_in.max_code
//; saturate   = h.get('saturate', 1)       # 0: reject a configuration that can saturate
//; def q_or_error(fn, *args):
//;     try:
//;         return fn(*args)
//;     except qfmt.QError as e:
//;         error(f"{func_name}: {e}")
//; # enddef
//; f_in     = q_or_error(qfmt.parse, q_in)
//; f_out    = q_or_error(qfmt.parse, q_out)
//; lo_c     = f_in.min_code if src_lo is None else int(src_lo)
//; hi_c     = f_in.max_code if src_hi is None else int(src_hi)
//; if lo_c < f_in.min_code or hi_c > f_in.max_code or lo_c > hi_c:
//;     error(f"{func_name}: source codes {lo_c} .. {hi_c} do not lie in {f_in} "
//;         f"({f_in.min_code} .. {f_in.max_code})")
//; # endif
//; src      = q_or_error(qfmt.Bounds, lo_c, hi_c, f_in.frac, f_in.signed)
//; rq       = q_or_error(qfmt.requant, src, f_out, round_mode, bool(osymm))
//; # A saturation end is emitted where a source code can reach it. With no source bounds the
//; # range above is the input format's own, so both ends are still exact.
//; sat_lo, sat_hi = rq.sat_lo, rq.sat_hi
//; if not saturate and (sat_lo or sat_hi):
//;     ends = ' and '.join(e for e, hit in (('low', sat_lo), ('high', sat_hi)) if hit)
//;     error(f"{func_name}: {f_in} -> {f_out} under {round_mode} saturates at the {ends} end over "
//;         f"source codes {lo_c} .. {hi_c}, and saturate=0 forbids saturation")
//; # endif
//; emit_lo  = sat_lo
//; emit_hi  = sat_hi
//; iwidth   = f_in.width
//; owidth   = f_out.width
//; shift    = rq.shift
//; # The two spare bits are the rounding carry and the sign that shift needs. With no shift
//; # nothing reads them and verilator reports UNUSEDSIGNAL; an unsigned source still needs
//; # the one bit that keeps it non-negative in a signed xs.
//; margin   = abs(shift) + 2 if shift else (0 if f_in.signed else 1)
//; # An unsigned output needs a sign bit above it only where saturation reads one; with no
//; # saturation nothing reads it.
//; sat_pad  = 1 if (emit_lo or emit_hi) and not f_out.signed else 0
//; acc_w    = max(iwidth + margin, owidth + sat_pad)
//; # With no room to extend into, xs would only repeat qin, and sext refuses a zero widening.
//; scratch  = acc_w > iwidth
//; # Saturation reads the guard bits above the output field, not a comparison with a bound: a
//; # signed output fits when the guard bits repeat its sign bit, an unsigned one when they and
//; # the sign are zero. That holds only while the bounds are the format's ends, or osymm's low
//; # end, whose one excluded code is the field 10..0.
//; top = acc_w - 1
//; ends = (-f_out.max_code if osymm else f_out.min_code, f_out.max_code)
//; if (rq.min_code, rq.max_code) != ends:
//;     error(f"{func_name}: saturation bounds {rq.min_code} .. {rq.max_code} are not the ends "
//;         f"of {f_out}")
//; # endif
//; def field(hi, lo):
//;     if hi < lo:
//;         return None
//;     # endif
//;     return f"acc[{hi}]" if hi == lo else f"acc[{hi}:{lo}]"
//; # enddef
//; guard = field(top - 1, owidth - 1 if f_out.signed else owidth)
//; ovf   = guard and f"~acc[{top}] & |{guard}"
//; low   = field(owidth - 2, 0)
//; if not f_out.signed or (osymm and not low):
//;     udf = f"acc[{top}]"
//; else:
//;     terms = ([f"~&{guard}"] if guard else []) + ([f"~|{low}"] if osymm else [])
//;     udf   = terms and f"acc[{top}] & " + (terms[0] if len(terms) == 1 else
//;         "(" + " | ".join(terms) + ")")
//; # endif
//; if (emit_hi and not ovf) or (emit_lo and not udf):
//;     error(f"{func_name}: {acc_w}-bit acc has no guard bits above {f_out} to saturate from")
//; # endif
//; # With both ends emitted one condition takes them: the sign and guard bits are neither all
//; # zero nor all ones, or, under osymm, the field is 10..0. The sign then selects the end.
//; sat_g = field(top, owidth - 1 if f_out.signed else owidth)
//; if not (emit_hi and emit_lo):
//;     sat = ovf if emit_hi else udf
//; elif not f_out.signed or (osymm and not low):
//;     sat = f"|{sat_g}"
//; elif osymm:
//;     sat = f"|{sat_g} & ~(&{sat_g} & |{low})"
//; else:
//;     sat = f"|{sat_g} & ~&{sat_g}"
//; # endif
//; sat_max = limit("max", owidth, signed=f_out.signed)
//; sat_min = limit("min", owidth, signed=f_out.signed, symm=rq.osymm)
//; if emit_hi and emit_lo:
//;     sat_v = f"acc[{top}] ? {sat_min} : {sat_max}"
//; else:
//;     sat_v = sat_max if emit_hi else sat_min
//; # endif
//; img   = rq.image()
//; def rng(b):
//;     return f"codes {b.lo} .. {b.hi}, values {float(b.lo_val)} .. {float(b.hi_val)}"
//; # enddef
//; satmode = "saturating" if emit_lo or emit_hi else "no saturation"
//; note    = ", output symmetric" if osymm else ""
    // `func_name`: `q_in` -> `q_out`, round=`round_mode`, `satmode``note`
    //     in:  `rng(src)`
    //     out: `rng(img)`
//; # Rounding is a carry into the kept bits, not a constant added before the shift: every
//; # mode is c = a & (b | sticky), where sticky ORs the dropped bits below the half bit.
//; # half_even's b is the kept lsb, so it needs no second pass to step a tie down.
//; # qfmt.OR_MODES add no carry: they OR one bit into the kept lsb, so no carry chain.
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
//; if shift > 0 and round_mode in qfmt.OR_MODES:
//;     # cy is the signed reg described below; an OR of two signed operands stays signed
//;     bit  = f"|xs[{shift-1}:0]" if round_mode == 'to_odd' else "1'b1"
//;     cw   = sext(bit, 1, acc_w, signed=False)
//;     expr = f"(xs >>> {shift}) | cy"
//; elif shift > 0:
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
//;     expr = "xs" if scratch else "qin"
//; # endif
//; direct = not (emit_hi or emit_lo)
//; names  = (['xs'] if scratch else []) + ([] if direct else ['acc']) + (['cy'] if cw else [])
//; regs   = ", ".join(names)
//; # a cast only where it changes width or signedness: slang flags a cast to the same type
//; def cast(w, e):
//;     ew, es = (acc_w, True) if scratch else (iwidth, f_in.signed)
//;     return e if (w, f_out.signed) == (ew, es) else f"{w}'({e})"
//; # enddef
    function `lifetime` `decl(f_out, pad=False)` `func_name`;
        input `decl(f_in, pad=False)` qin;
//; if names:
        reg signed [`acc_w-1`:0] `regs`;
//; # endif
        begin
//; if scratch:
            xs = `sext('qin', iwidth, acc_w, msb=f_in.int_bits-1, signed=f_in.signed)`;
//; # endif
//; if cw:
            cy = `cw`;
//; # endif
//; if direct:
            `func_name` = `cast(owidth, expr)`;
//; else:
            acc = `expr`;
            if ( `sat` )
                `func_name` = `sat_v`;
            else
                `func_name` = acc[`owidth-1`:0];
//; # endif
        end
    endfunction
//; _d = getattr(self, func_name, {}); _d['iwidth'] = iwidth; _d['owidth'] = owidth
//; _d['shift'] = shift
//; setattr(self, func_name, _d)
