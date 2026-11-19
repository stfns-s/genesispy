    // round half_up, to_odd or von_neumann, saturate - optionally maintain output symmetry
//; from genesispy.lib.verilog import limit
//; h         = self.include_params
//; func_name = h.get('func_name', 'f_round')
//; iwidth    = h.get('iwidth', 8)
//; owidth    = h.get('owidth', 6)
//; osymm     = h.get('osymm', 0)
//; lifetime  = h.get('lifetime', 'static')
//; round_mode = h.get('round_mode', 'half_up')
//; if round_mode not in ('half_up', 'to_odd', 'von_neumann'):
//;     error(f"{func_name}: round_mode ({round_mode!r}) must be half_up, to_odd or von_neumann")
//; # endif
//; ow        = owidth if owidth < iwidth else iwidth - 1
//; if ow < 1:
//;     error(f"{func_name}: ow ({ow}) must be >= 1")
//; # endif
//; lsb_w     = iwidth - ow      # LSB width
    function `lifetime` signed [`ow-1`:0] `func_name`;
        input signed [`iwidth-1`:0] num;
        // bounds stay as localparams: given literal bounds instead, verilator
        // reports the low bits of num that rounding discards as unused
        localparam        ROUND_OW   = `ow`;
        localparam        ROUND_IMSB = `iwidth-1`;
        localparam        ROUND_ILSB = `lsb_w`;
        localparam        ROUND_FMSB = `lsb_w-1`;
        localparam string ROUND_MODE = "`round_mode`";
        localparam        ROUND_OR   = (ROUND_MODE != "half_up");
        localparam        ROUND_VN   = (ROUND_MODE == "von_neumann");
        reg                    oflow;
        reg [ROUND_OW-1:0]     num_r_p0;
        reg [ROUND_OW:0]       num_r_p1;
        begin
            num_r_p0 = num[ROUND_IMSB:ROUND_ILSB];
            num_r_p1 = { num[ROUND_IMSB], num[ROUND_IMSB:ROUND_ILSB] } + 1'b1;

            oflow    = (num_r_p1[ROUND_OW:ROUND_OW-1] == 2'b01);

            // to_odd ORs the dropped bits into the kept lsb, von_neumann a 1. At ROUND_OW = 1
            // the only odd code is -1, so +1 saturates to 0 and the truncated code stands.
            if (ROUND_OR)
                `func_name` = (ROUND_OW == 1) ? num_r_p0
                            : num_r_p0 | ROUND_OW'(ROUND_VN | (|num[ROUND_FMSB:0]));
            else
                case ( {num[ROUND_IMSB], num[ROUND_FMSB]} )
                    2'b00:  `func_name` = num_r_p0[ROUND_OW-1:0];
                    2'b01:  `func_name` = oflow ?  `limit("max", ow)` : num_r_p1[ROUND_OW-1:0];
                    2'b10:  `func_name` = num_r_p0[ROUND_OW-1:0];
                    2'b11:  `func_name` = num_r_p1[ROUND_OW-1:0];
                endcase

//; if osymm:
            if ( `func_name` == `limit("min", ow)` ) `func_name` = `limit("min", ow, symm=True)`;
//; # endif
        end
    endfunction
//; _d = getattr(self, func_name, {}); _d['owidth'] = ow; setattr(self, func_name, _d)
