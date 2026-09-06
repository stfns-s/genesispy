    // signed semi-log multiplier - sgn(b) * (a << (floor(log2(abs b)) + 1)), approximating a*b
    //  a is shifted as a signed value and carries its own sign; only b's sign is applied
    //  separately. The +1 in the shift makes the result about 2*a*b.
//; from vexpr import lit, sext
//; h         = self.include_params
//; func_name = h.get('func_name', 'f_slogmult')
//; awidth    = h.get('awidth', 8)
//; bwidth    = h.get('bwidth', 8)
//; isym      = h.get('isym', 0)
//; iapprox   = h.get('iapprox', 1)
//; oapprox   = h.get('oapprox', 0)
//; zdet      = h.get('zdet', 1)
//; lifetime  = h.get('lifetime', 'static')
//; owidth    = awidth + bwidth - (1 if isym else 0)
//; log_func  = func_name + '_log'
//; oneg_func = func_name + '_oneg'
//; core_func = func_name + '_core'
//; incp      = {'isym': isym, 'lifetime': lifetime}
//; self.include_params = dict(incp, func_name=log_func, iwidth=bwidth, approx=iapprox)
//; include('f_log2.vpy')
//; log_msb   = getattr(self, log_func)['owidth'] - 1
//; self.include_params = dict(incp, func_name=oneg_func, iwidth=owidth, approx=oapprox, isym=1)
//; include('f_negate.vpy')
    // the core takes the log of b already taken, so one log function can serve several cores
    function `lifetime` signed [`owidth-1`:0] `core_func`;
        input signed [`awidth-1`:0]    a;
        input        [`log_msb`:0]     sb_log2b;   // { sign, log2(abs b) }
        reg   signed [`owidth-1`:0]    res;
        reg          [`log_msb-1`:0]   log2b;
        reg                            sb;
        begin
            { sb, log2b } = sb_log2b;
            // log2b is at most `bwidth-1`, so the shift stays inside `owidth` bits
            res = `sext('a', awidth, owidth)`;
            res = res << log2b;
            if (sb) res = `oneg_func`(res);
//; if zdet:
            if (log2b == `lit(0, log_msb, signed=False)`) res = `lit(0, owidth, signed=False)`;
//; # endif
            `core_func` = res;
        end
    endfunction
    // `func_name`(a[`awidth-1`:0], b[`bwidth-1`:0]) isym:`isym` approx(i:`iapprox`,o:`oapprox`) zdet:`zdet`
    function `lifetime` signed [`owidth-1`:0] `func_name`;
        input signed [`awidth-1`:0] a;
        input signed [`bwidth-1`:0] b;
        `func_name` = `core_func`(a, `log_func`(b));
    endfunction
//; _d = getattr(self, func_name, {}); _d['owidth'] = owidth; setattr(self, func_name, _d)
