    // shift left and saturate if needed
//; from genesispy.lib.verilog import limit, sext
//; h         = self.include_params
//; func_name = h.get('func_name', 'f_shleft')
//; iwidth    = h.get('iwidth', 8)
//; cwidth    = h.get('cwidth', 4)
//; osymm     = h.get('osymm', 0)
//; lifetime  = h.get('lifetime', 'static')
//; if cwidth < 1:
//;     error(f"{func_name}: cwidth ({cwidth}) must be >= 1")
//; # endif
//; isw       = 2**cwidth - 1 + iwidth
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
//; if osymm:
            udf =  udf | in[`iwidth-1`] & ( inx[`iwidth-1`:0] == `limit("min", iwidth)` );
//; # endif

            case ( {ovf, udf} ) // synthesis parallel_case full_case
                2'b10:   `func_name` = `limit("max", iwidth)`;
                2'b01:   `func_name` = `limit("min", iwidth)`;
                default: `func_name` = inx[`iwidth-1`:0];
            endcase
//; if osymm:
            if ( `func_name` == `limit("min", iwidth)` ) `func_name` = `limit("min", iwidth, symm=True)`;
//; # endif
        end
    endfunction
