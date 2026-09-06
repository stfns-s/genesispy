    // reduce width and saturate if needed
//; from vexpr import lit
//; h         = self.include_params
//; func_name = h.get('func_name', 'f_sat')
//; iwidth    = h.get('iwidth', 8)
//; owidth    = h.get('owidth', 6)
//; osym      = h.get('osym', 0)
//; lifetime  = h.get('lifetime', 'static')
//; ow        = owidth if iwidth >= owidth else iwidth - 1
//; if iwidth == ow:
//;     error(f"{func_name}: iwidth ({iwidth}) must differ from owidth ({owidth})")
//; # endif
//; if ow < 1:
//;     error(f"{func_name}: ow ({ow}) must be >= 1")
//; # endif
//; omax      = (1 << (ow-1)) - 1
//; ominn     = -(1 << (ow-1))
    function `lifetime` signed [`ow-1`:0] `func_name`;
        input signed [`iwidth-1`:0] x;
        reg                     oflow;
        reg                     uflow;
        begin
            oflow = x[`iwidth-1`] == 1'b0 && x[`iwidth-2`:`ow-1`] != {`iwidth-ow` {1'b0}};
            uflow = x[`iwidth-1`] == 1'b1 && x[`iwidth-2`:`ow-1`] != {`iwidth-ow` {1'b1}};
//; if osym:
            uflow = uflow | x[`iwidth-1`] & ( x[`ow-1`:0] == `lit(ominn, ow)` );
//; # endif

            case ( { oflow, uflow } ) // synthesis parallel_case full_case
//; if osym:
                2'b01:   `func_name` = `lit(ominn+1, ow)`;
//; else:
                2'b01:   `func_name` = `lit(ominn, ow)`;
//; # endif
                2'b10:   `func_name` = `lit(omax, ow)`;
                default: `func_name` = x[`ow-1`:0];
            endcase
        end
    endfunction
//; _d = getattr(self, func_name, {}); _d['owidth'] = ow; setattr(self, func_name, _d)
