    // shift left and saturate if needed
//; from vexpr import lit, sext
//; h         = self.include_params
//; func_name = h.get('func_name', 'f_shleft')
//; iwidth    = h.get('iwidth', 8)
//; cwidth    = h.get('cwidth', 4)
//; osym      = h.get('osym', 0)
//; lifetime  = h.get('lifetime', 'static')
//; if cwidth < 1:
//;     error(f"{func_name}: cwidth ({cwidth}) must be >= 1")
//; # endif
//; isw       = 2**cwidth - 1 + iwidth
//; shl_max   = (1 << (iwidth-1)) - 1
//; shl_minn  = -(1 << (iwidth-1))
    function `lifetime` signed [`iwidth-1`:0] `func_name`;
        input   signed  [`iwidth-1`:0]  in;
        input           [`cwidth-1`:0]  sh;
        reg     signed  [`isw-1`:0] inx;
        reg                       ovf, udf;
        begin
            inx = `sext('in', iwidth, isw)`;
            inx = inx << sh;

            ovf = ~in[`iwidth-1`] &  (|inx[`isw-1`:`iwidth-1`]);
            udf =  in[`iwidth-1`] & ~(&inx[`isw-1`:`iwidth-1`]);
//; if osym:
            udf =  udf | in[`iwidth-1`] & ( inx[`iwidth-1`:0] == `lit(shl_minn, iwidth)` );
//; # endif

            case ( {ovf, udf} ) // synthesis parallel_case full_case
                2'b10:   `func_name` = `lit(shl_max, iwidth)`;
                2'b01:   `func_name` = `lit(shl_minn, iwidth)`;
                default: `func_name` = inx[`iwidth-1`:0];
            endcase
//; if osym:
            if ( `func_name` == `lit(shl_minn, iwidth)` ) `func_name` = `lit(shl_minn+1, iwidth)`;
//; # endif
        end
    endfunction
