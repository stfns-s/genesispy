    // round - optional produce symmetric output
//; from vexpr import lit
//; h         = self.include_params
//; func_name = h.get('func_name', 'f_round')
//; iwidth    = h.get('iwidth', 8)
//; owidth    = h.get('owidth', 6)
//; osym      = h.get('osym', 0)
//; lifetime  = h.get('lifetime', 'static')
//; ow        = owidth if owidth < iwidth else iwidth - 1
//; if ow < 1:
//;     error(f"{func_name}: ow ({ow}) must be >= 1")
//; # endif
//; lsb_w     = iwidth - ow      # LSB width
//; rmax      = (1 << (ow-1)) - 1
//; rminn     = -(1 << (ow-1))
    function `lifetime` signed [`ow`:1] `func_name`;
        input signed [`iwidth`:1] num;
        // bounds stay as localparams: given literal bounds instead, verilator
        // reports the low bits of num that rounding discards as unused
        localparam ROUND_OW   = `ow`;
        localparam ROUND_IMSB = `iwidth`;   // integer MSB
        localparam ROUND_ILSB = `lsb_w+1`;  // integer LSB
        localparam ROUND_FMSB = `lsb_w`;    // fractional MSB
        reg                    oflow;
        reg [ROUND_OW:1]       num_r_p0;
        reg [ROUND_OW+1:1]     num_r_p1;
        begin
            num_r_p0 = num[ROUND_IMSB:ROUND_ILSB];
            num_r_p1 = { num[ROUND_IMSB], num[ROUND_IMSB:ROUND_ILSB] } + 1'b1;

            oflow    = (num_r_p1[ROUND_OW+1:ROUND_OW] == 2'b01);

            case ( {num[ROUND_IMSB], num[ROUND_FMSB]} ) // synthesis parallel_case full_case
                2'b00:  `func_name` = num_r_p0[ROUND_OW:1];
                2'b01:  `func_name` = oflow ?  `lit(rmax, ow)` : num_r_p1[ROUND_OW:1];
                2'b10:  `func_name` = num_r_p0[ROUND_OW:1];
                2'b11:  `func_name` = num_r_p1[ROUND_OW:1];
            endcase

//; if osym:
            if ( `func_name` == `lit(rminn, ow)` ) `func_name` = `lit(rminn+1, ow)`;
//; # endif
        end
    endfunction
//; _d = getattr(self, func_name, {}); _d['owidth'] = ow; setattr(self, func_name, _d)
