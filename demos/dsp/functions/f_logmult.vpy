    // signed log multiplier - antilog(log2(a) + log2(b)), approximating a*b
    //  Each log is one high for a power of two and the sum removes only one of the two
    //  offsets, so the result is about 2*a*b, and exactly that on a power-of-two pair.
//; from vexpr import decl, lit
//; h         = self.include_params
//; func_name = h.get('func_name', 'f_logmult')
//; awidth    = h.get('awidth', 8)
//; bwidth    = h.get('bwidth', 8)
//; isym      = h.get('isym', 0)
//; iapprox   = h.get('iapprox', 1)
//; oapprox   = h.get('oapprox', 0)
//; alfrac    = h.get('alfrac', 0)
//; blfrac    = h.get('blfrac', 0)
//; antilog   = h.get('antilog', 1)
//; zdet      = h.get('zdet', 0)
//; osm       = h.get('osm', 0)
//; sign_only = h.get('sign_only', 0)
//; lifetime  = h.get('lifetime', 'static')
//; if antilog and (alfrac or blfrac):
//;     warning(f"{func_name}: antilog is set, forcing alfrac=blfrac=0")
//;     alfrac = 0
//;     blfrac = 0
//; # endif
//; pwidth    = awidth + bwidth - (1 if isym else 0)
//; a_log     = func_name + '_loga'
//; b_log     = func_name + '_logb'
//; alog_func = func_name + '_antilog'
//; oneg_func = func_name + '_oneg'
//; lneg_func = func_name + '_lneg'
//; pneg_func = func_name + '_pneg'
//; core_func = func_name + '_core'
//; if sign_only:
//;     owidth = 2
    // `func_name`(a[`awidth-1`:0], b[`bwidth-1`:0]) -> the sign of a*b alone, as +1/-1/0
    function `lifetime` `decl(owidth, signed=not osm, pad=False)` `func_name`;
        input signed [`awidth-1`:0] a;
        input signed [`bwidth-1`:0] b;
        reg                         zero;
        begin
            zero = (a == `lit(0, awidth, signed=False)`) || (b == `lit(0, bwidth, signed=False)`);
            case ( { a[`awidth-1`], b[`bwidth-1`] } ) // synthesis full_case parallel_case
                2'b01,
                2'b10:   `func_name` = zero ? 2'b00 : 2'b11;
                default: `func_name` = zero ? 2'b00 : 2'b01;
            endcase
        end
    endfunction
//; else:
//;     logp = {'isym': isym, 'approx': iapprox, 'lifetime': lifetime}
//;     self.include_params = dict(logp, func_name=a_log, iwidth=awidth, lfrac=alfrac)
//;     include('f_log2.vpy')
//;     self.include_params = dict(logp, func_name=b_log, iwidth=bwidth, lfrac=blfrac)
//;     include('f_log2.vpy')
//;     a_log_width = getattr(self, a_log)['owidth'] - 1
//;     b_log_width = getattr(self, b_log)['owidth'] - 1
//;     sum_width   = (a_log_width if a_log_width > b_log_width else b_log_width) + 1
//;     owidth      = pwidth if antilog else sum_width + 1
//;     shift       = alfrac + blfrac + 1
//;     # sum_width is one above the wider log, so both pads are always at least one bit
//;     a_pad       = f"{sum_width - a_log_width}'d0, "
//;     b_pad       = f"{sum_width - b_log_width}'d0, "
//;     # the antilog of a fractional log is a root, not a shift, so it is only offered
//;     # for whole-bit logs, and only where the core leaves the result in the log domain
//;     emit_antilog = not antilog and not alfrac and not blfrac
//;     negp = {'approx': oapprox, 'isym': 1, 'lifetime': lifetime}
//;     # only the two's complement output negates the magnitude, so sign magnitude needs
//;     # neither the negate function nor the magnitude register
//;     if not osm:
//;         self.include_params = dict(negp, func_name=oneg_func, iwidth=owidth)
//;         include('f_negate.vpy')
//;     # endif
//;     if emit_antilog and not osm:
//;         self.include_params = dict(negp, func_name=lneg_func, iwidth=sum_width)
//;         include('f_negate.vpy')
//;     # endif
//;     if emit_antilog:
//;         self.include_params = dict(negp, func_name=pneg_func, iwidth=pwidth)
//;         include('f_negate.vpy')
    // antilog of a `core_func` result, for a caller that took the log-domain output
    function `lifetime` signed [`pwidth-1`:0] `alog_func`;
        input        [`sum_width`:0]   l;   // `"{ sign, log }" if osm else "signed log"`
        reg          [`pwidth-1`:0]    mag;
        reg          [`sum_width-1`:0] l_m;
        reg                            l_s;
        begin
            l_s = l[`sum_width`];
            l_m = l[`sum_width-1`:0];
//;         if not osm:
            // undo the core's own negate, so the magnitude comes back as it went in
            if (l_s) l_m = `lneg_func`(l_m);
//;         # endif
            // one shifter, not up then down: (1 << l_m) >> shift is 2**(l_m - shift)
            if (l_m >= `lit(shift, sum_width, signed=False)`) mag = `lit(1, pwidth, signed=False)` << (l_m - `shift`);
            else                             mag = `lit(0, pwidth, signed=False)`;
            if (l_s) mag = `pneg_func`(mag);
            `alog_func` = mag;
        end
    endfunction
//;     # endif
    // the core takes both logs already taken, so one log function can serve several cores
    function `lifetime` `decl(owidth, signed=not osm, pad=False)` `core_func`;
        input [`a_log_width+1`:0] zslog2a;   // { zero flag, sign, log2(abs a) }
        input [`b_log_width+1`:0] zslog2b;
        reg   [`sum_width-1`:0]   lsum;
//;     if osm:
        reg   [`owidth-1`:0]      res_sm;
//;     else:
        reg   [`owidth-1`:0]      res_sm, mag;
//;     # endif
//;     if antilog:
        reg   [`owidth-2`:0]      alog;
//;     # endif
        reg   [`a_log_width-1`:0] log2a;
        reg   [`b_log_width-1`:0] log2b;
        reg                       sa, sb, za, zb;
        begin
            { za, sa, log2a } = zslog2a;
            { zb, sb, log2b } = zslog2b;
            lsum   = { `a_pad`log2a } + { `b_pad`log2b };
//;     if antilog:
            // one shifter, not up then down: (1 << lsum) >> shift is 2**(lsum - shift)
            if (lsum >= `lit(shift, sum_width, signed=False)`) alog = `lit(1, owidth-1, signed=False)` << (lsum - `shift`);
            else                              alog = `lit(0, owidth-1, signed=False)`;
            res_sm = { sa ^ sb, alog };
//;     else:
            res_sm = { sa ^ sb, lsum };
//;     # endif
//;     if zdet:
            if (za || zb) res_sm = `lit(0, owidth, signed=False)`;
//;     # endif
//;     if osm:
            `core_func` = res_sm;
//;     else:
            mag = { 1'b0, res_sm[`owidth-2`:0] };
            // if/else, not a ternary: verilator 5.020 takes an internal fault on a
            // function call inside a ternary when the caller runs in a loop
            if (res_sm[`owidth-1`]) mag = `oneg_func`(mag);
            `core_func` = mag;
//;     # endif
        end
    endfunction
    // `func_name`(a[`awidth-1`:0], b[`bwidth-1`:0]) lfrac(a:`alfrac`,b:`blfrac`) antilog:`antilog`
    //   isym:`isym` approx(i:`iapprox`,o:`oapprox`) zdet:`zdet` osm:`osm`
    function `lifetime` `decl(owidth, signed=not osm, pad=False)` `func_name`;
        input signed [`awidth-1`:0] a;
        input signed [`bwidth-1`:0] b;
        `func_name` = `core_func`( { a == `lit(0, awidth, signed=False)`, `a_log`(a) }, { b == `lit(0, bwidth, signed=False)`, `b_log`(b) } );
    endfunction
//; # endif
//; # alfrac and blfrac are exported as settled on above, not as asked for, so a caller's
//; # reference can follow the forcing without repeating the rule
//; _d = getattr(self, func_name, {}); _d['owidth'] = owidth; _d['pwidth'] = pwidth
//; _d['alfrac'] = alfrac; _d['blfrac'] = blfrac; setattr(self, func_name, _d)
