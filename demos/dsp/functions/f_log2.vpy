    // integer log2 - returns { sign, floor(log2(abs x)) + 1 }, one more than the exponent
    //  for a power of two. With lfrac set the value carries that many fractional bits,
    //  floor(2**lfrac * log2(2*m)), m being the magnitude's top lfrac+1 significant bits.
//; from vexpr import lit
//; import math
//; h         = self.include_params
//; func_name = h.get('func_name', 'f_log2')
//; iwidth    = h.get('iwidth', 8)
//; isym      = h.get('isym', 0)
//; approx    = h.get('approx', 1)
//; lfrac     = h.get('lfrac', 0)
//; lifetime  = h.get('lifetime', 'static')
//; if iwidth < 2:
//;     error(f"{func_name}: iwidth ({iwidth}) must be >= 2")
//; # endif
//; in_msb    = iwidth - 1
//; log_msb   = int(math.log(iwidth) / math.log(2) + 1) + lfrac
//; lscale    = 1 << lfrac
//; sym_func  = func_name + '_sym'
//; neg_func  = func_name + '_neg'
//; if not isym:
//;     self.include_params = {'func_name': sym_func, 'iwidth': iwidth, 'lifetime': lifetime}
//;     include('f_sym.vpy')
//; # endif
//; self.include_params = {'func_name': neg_func, 'iwidth': iwidth, 'approx': approx, 'isym': 1, 'lifetime': lifetime}
//; include('f_negate.vpy')
    // `func_name`(x[`in_msb`:0]) -> { sign, log2(abs x)[`log_msb-1`:0] } isym:`isym` lfrac:`lfrac` approx:`approx`
    function `lifetime` [`log_msb`:0] `func_name`;
        input signed [`in_msb`:0] x;
        reg   signed [`in_msb`:0] ix;
        reg                       sign;
        begin
//; if isym:
            ix   = x;
//; else:
            ix   = `sym_func`(x);
//; # endif
            sign = x[`in_msb`];
            // if/else, not a ternary: verilator 5.020 takes an internal fault on a
            // function call inside a ternary when the caller runs in a loop
            if (sign) ix = `neg_func`(ix);

            casez ( ix[`in_msb-1`:0] ) // synthesis full_case
//; for bit in range(in_msb, 0, -1):
//;     nsub = lfrac if lfrac < bit - 1 else bit - 1
//;     for sub in range(1 << nsub):
//;         pat = '0' * (in_msb - bit) + '1' + (format(sub, f'0{nsub}b') if nsub else '') + '?' * (bit - 1 - nsub)
//;         pfx = ((1 << nsub) | sub) << (lfrac - nsub)
//;         val = (pfx ** lscale).bit_length() - 1 + lscale * (bit - lfrac)
                `f"{in_msb}'b{pat}"`: `func_name` = {sign, `lit(val, log_msb, signed=False)`}; // `f"{val / lscale:.{lfrac}f}"`
//;     # endfor
//; # endfor
                `f"{in_msb}'b" + '0' * in_msb`: `func_name` = {sign, `lit(0, log_msb, signed=False)`};
                default: `func_name` = {sign, `lit(0, log_msb, signed=False)`};
            endcase
        end
    endfunction
//; _d = getattr(self, func_name, {}); _d['owidth'] = log_msb + 1; setattr(self, func_name, _d)
