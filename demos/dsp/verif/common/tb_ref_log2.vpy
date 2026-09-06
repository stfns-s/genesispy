    // golden log table for f_log2, for any testbench whose function under test takes a log
//; from vexpr import lit
//; import math
//; h         = self.include_params
//; func_name = h.get('func_name', 'ref_log2')
//; iwidth    = h.get('iwidth', 8)
//; isym      = h.get('isym', 0)
//; approx    = h.get('approx', 1)
//; lfrac     = h.get('lfrac', 0)
//; # Both this table and the function raise a value to the power 2**lfrac, so generation
//; # cost grows as about 4**lfrac. Measured at IW=8: lfrac 12 takes 0.9 s, 16 takes 53 s,
//; # 20 does not finish inside two minutes. The cap is that cost, not an arithmetic limit.
//; if lfrac > 12:
//;     error(f"{func_name}: lfrac ({lfrac}) > 12 costs more to generate than it is worth")
//; # endif
//; min_neg   = -(1 << (iwidth-1))
//; lscale    = 1 << lfrac
//; owidth    = int(math.log(iwidth) / math.log(2) + 1) + lfrac + 1
//; # The expected values, computed here at generation. f_log2 splits the log into a prefix
//; # term and an exponent term and takes the prefix term from a bit_length; this counts the
//; # powers of two that fit under the whole argument instead, so the two agree only if both
//; # are right.
//; def _lg(m):
//;     nsig = sum(1 for k in range(iwidth) if (1 << k) <= m)
//;     drop = max(0, nsig - lfrac - 1)
//;     p    = ((m >> drop) << (drop + 1)) ** lscale
//;     return sum(1 for k in range(1, lscale * iwidth + 1) if (1 << k) <= p)
//; # enddef
//; def _word(i):
//;     v   = i - (1 << iwidth) if i >= (1 << (iwidth-1)) else i
//;     ix  = (min_neg + 1) if (not isym and v == min_neg) else v
//;     ix  = (~ix if approx else -ix) if v < 0 else ix
//;     return ((1 if v < 0 else 0) << (owidth-1)) | _lg(ix & ((1 << (iwidth-1)) - 1))
//; # enddef
    // `func_name`[code] = { sign, floor(`lscale` * log2(2 * m)) }, m being abs(in) truncated
    // to its top `lfrac+1` significant bits. The doubling is the function's own offset: a
    // power of two reports one more than its exponent.
    reg [`owidth-1`:0] `func_name` [0:`(1 << iwidth) - 1`];

    // called first thing in the testbench's initial block, so the table stands before any
    // check reads it
    task `func_name`_load;
        begin
//; for i in range(1 << iwidth):
            `func_name`[`i`] = `lit(_word(i), owidth, signed=False)`;
//; # endfor
        end
    endtask
//; _d = getattr(self, func_name, {}); _d['owidth'] = owidth; setattr(self, func_name, _d)
