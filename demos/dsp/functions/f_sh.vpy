    // left/right shift by a signed count, with a 2-bit fractional gain
    //  out = in * (4 + frac) / 4 * 2**sh, floored, where sh < 0 shifts right.
    //  A left shift saturates; a right shift cannot leave the range. The most negative
    //  output is always folded to MIN+1, so the result is symmetric whatever sh was.
//; from vexpr import lit, sext
//; h         = self.include_params
//; func_name = h.get('func_name', 'f_sh')
//; iwidth    = h.get('iwidth', 8)
//; cwidth    = h.get('cwidth', 4)
//; lifetime  = h.get('lifetime', 'static')
//; if cwidth < 1:
//;     error(f"{func_name}: cwidth ({cwidth}) must be >= 1")
//; # endif
//; isw       = iwidth + 2**(cwidth-1) + 2   # in*(4+frac) shifted all the way left
//; sh_max    = (1 << (iwidth-1)) - 1
//; sh_minn   = -(1 << (iwidth-1))
    function `lifetime` signed [`iwidth-1`:0] `func_name`;
        input   signed  [`iwidth-1`:0]  in;
        input   signed  [`cwidth-1`:0]  sh;
        input           [1:0]     frac;
        reg     signed  [`isw-1`:0] inx, scaled;
        reg     signed  [`cwidth-1`:0]  psh;
        reg                       ovf, udf;
        begin
            inx = `sext('in', iwidth, isw)`;

            // scale by 4+frac before shifting, so the single >>> 2 below is the only truncation
            case (frac) // synthesis parallel_case full_case
                2'd0: scaled =  inx << 2;
                2'd1: scaled = (inx << 2) + inx;
                2'd2: scaled = (inx << 2) + (inx << 1);
                2'd3: scaled = (inx << 2) + (inx << 1) + inx;
            endcase

            if (sh[`cwidth-1`]) begin
                psh    = -sh;
                scaled = scaled >>> psh;
            end
            else
                scaled = scaled << sh;

            // left:  floor(in*(4+frac)*2**sh / 4)
            // right: floor(floor(in*(4+frac)/2**psh) / 4) == floor(in*(4+frac)/2**(psh+2))
            scaled = scaled >>> 2;

            if (sh[`cwidth-1`] == 1'b0) begin // sh > 0 - check for saturation
                ovf = ~in[`iwidth-1`] &  (|scaled[`isw-1`:`iwidth-1`]);
                udf =  in[`iwidth-1`] & ~(&scaled[`isw-1`:`iwidth-1`]);
                udf =  udf | in[`iwidth-1`] & ( scaled[`iwidth-1`:0] == `lit(sh_minn, iwidth)` );

                case ( {ovf, udf} ) // synthesis parallel_case full_case
                2'b10:   `func_name` = `lit(sh_max, iwidth)`;
                2'b01:   `func_name` = `lit(sh_minn+1, iwidth)`;
                default: `func_name` = scaled[`iwidth-1`:0];
                endcase
            end
            else                              // shifting right, the gain is at most 7/8
                `func_name` = scaled[`iwidth-1`:0];
            if (`func_name` == `lit(sh_minn, iwidth)` ) `func_name` = `lit(sh_minn+1, iwidth)`;
        end
    endfunction
