    // absolute - optionally approximate
//; from vexpr import lit
//; h         = self.include_params
//; func_name = h.get('func_name', 'f_abs')
//; iwidth    = h.get('iwidth', 8)
//; approx    = h.get('approx', 0)
//; isym      = h.get('isym', 0)
//; lifetime  = h.get('lifetime', 'static')
//; plus      = "" if approx else " + 1'b1"
//; min_neg   = -(1 << (iwidth-1))
    function `lifetime` signed [`iwidth-1`:0] `func_name`;
        input signed [`iwidth-1`:0] x;
        begin
            if ( x[`iwidth-1`] )
//; # with approx the two arms below are the same expression, so emit one
//; if isym or approx:
                `func_name` = ~x`plus`;
//; else:
                `func_name` = ( x == `lit(min_neg, iwidth)` ) ? ~x : (~x`plus`);
//; # endif
            else
                `func_name` = x;
        end
    endfunction
