    // drop the low bits of a wider input - optionally maintain output symmetry
    //  The input port is max(iwidth, owidth) wide, so at owidth >= iwidth the port widens
    //  to the output and nothing is dropped; the caller supplies the wider value.
//; from vexpr import lit
//; h         = self.include_params
//; func_name = h.get('func_name', 'f_trunc')
//; iwidth    = h.get('iwidth', 8)
//; owidth    = h.get('owidth', 6)
//; osym      = h.get('osym', 0)
//; lifetime  = h.get('lifetime', 'static')
//; tiw       = iwidth if owidth < iwidth else owidth
//; if owidth < 1:
//;     error(f"{func_name}: owidth ({owidth}) must be >= 1")
//; # endif
//; minn      = -(1 << (owidth-1))
    function `lifetime` signed [`owidth-1`:0] `func_name`;
        input signed [`tiw-1`:0] num;
        // shift and cast rather than part-select: the shift reads the whole word, so the
        // bits the truncation drops are not left unread, which verilator reports as an
        // unused part of num
        localparam TRUNC_OW  = `owidth`;
        localparam TRUNC_LSB = `tiw-owidth`;
        begin
            `func_name` = TRUNC_OW'(num >>> TRUNC_LSB);
//; if osym:
            if ( `func_name` == `lit(minn, owidth)` ) `func_name` = `lit(minn+1, owidth)`;
//; # endif
        end
    endfunction
