    // enforce 2's complement symmetry - i.e. min=-2^(iwidth-1)+1 == -max
//; from vexpr import lit
//; h         = self.include_params
//; func_name = h.get('func_name', 'f_sym')
//; iwidth    = h.get('iwidth', 8)
//; lifetime  = h.get('lifetime', 'static')
//; min_neg   = -(1 << (iwidth-1))
    function `lifetime` signed [`iwidth-1`:0] `func_name`;
        input signed [`iwidth-1`:0] x;
        `func_name` = (x == `lit(min_neg, iwidth)`) ? `lit(min_neg+1, iwidth)` : x;
    endfunction
