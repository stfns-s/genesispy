    // shift right - with more accuracy than power of 2
    //  out = in/2^sh*( 1 + frac*0.25 ), truncated once, saturating
//; from vexpr import lit, sext
//; h         = self.include_params
//; func_name = h.get('func_name', 'f_shright')
//; iwidth    = h.get('iwidth', 8)
//; cwidth    = h.get('cwidth', 4)
//; osym      = h.get('osym', 0)
//; lifetime  = h.get('lifetime', 'static')
//; if cwidth < 1:
//;     error(f"{func_name}: cwidth ({cwidth}) must be >= 1")
//; # endif
//; isw       = iwidth + 3      # holds in*(4+frac)
//; shr_max   = (1 << (iwidth-1)) - 1
//; shr_minn  = -(1 << (iwidth-1))
    function `lifetime` signed [`iwidth-1`:0] `func_name`;
        input   signed  [`iwidth-1`:0] in;
        input           [`cwidth-1`:0] sh;
        input           [1:0]    frac;
        reg     signed  [`isw-1`:0] inx, scaled;
        reg                       ovf, udf;
        begin
            inx = `sext('in', iwidth, isw)`;

            // scale by 4+frac up front, so the shift below is the only truncation
            case (frac) // synthesis parallel_case full_case
                2'd0: scaled =  inx << 2;
                2'd1: scaled = (inx << 2) + inx;
                2'd2: scaled = (inx << 2) + (inx << 1);
                2'd3: scaled = (inx << 2) + (inx << 1) + inx;
            endcase

            // floor(floor(x/4)/2**sh) == floor(x/2**(sh+2)), so hoisting the constant shift
            // out keeps this a single truncation, saves a barrel stage, and avoids widening
            // sh, which overflows cwidth bits at sh=max
            scaled = scaled >>> 2;
            scaled = scaled >>> sh;

            // the gain reaches 1.75 at sh=0, so the result can leave the output range
            ovf = ~in[`iwidth-1`] &  (|scaled[`isw-1`:`iwidth-1`]);
            udf =  in[`iwidth-1`] & ~(&scaled[`isw-1`:`iwidth-1`]);
//; if osym:
            udf =  udf | in[`iwidth-1`] & ( scaled[`iwidth-1`:0] == `lit(shr_minn, iwidth)` );
//; # endif

            case ( {ovf, udf} ) // synthesis parallel_case full_case
                2'b10:   `func_name` = `lit(shr_max, iwidth)`;
//; if osym:
                2'b01:   `func_name` = `lit(shr_minn+1, iwidth)`;
//; else:
                2'b01:   `func_name` = `lit(shr_minn, iwidth)`;
//; # endif
                default: `func_name` = scaled[`iwidth-1`:0];
            endcase
        end
    endfunction
