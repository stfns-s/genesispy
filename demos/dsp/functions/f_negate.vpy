    // negate - optionally approximate with simple inversion
//; from genesispy.lib.verilog import lit
//; h         = self.include_params
//; func_name = h.get('func_name', 'f_negate')
//; iwidth    = h.get('iwidth', 8)
//; approx    = h.get('approx', 0)
//; isymm     = h.get('isymm', 0)
//; lifetime  = h.get('lifetime', 'static')
//; if iwidth < 1:
//;     error(f"{func_name}: iwidth ({iwidth}) must be >= 1")
//; # endif
//; plus      = "" if approx else " + 1'b1"
//; min_neg   = -(1 << (iwidth-1))
    function `lifetime` signed [`iwidth-1`:0] `func_name`;
        input signed [`iwidth-1`:0] x;
//; # with approx the two arms below are the same expression, so emit one
//; if isymm or approx:
        `func_name` = ~x`plus`;
//; else:
        `func_name` = (x == `lit(min_neg, iwidth)`) ? ~x : (~x`plus`);
//; # endif
    endfunction
