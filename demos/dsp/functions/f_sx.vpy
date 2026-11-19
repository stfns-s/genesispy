    // sign extend, or zero extend when signed is 0
//; from genesispy.lib.verilog import sext
//; h         = self.include_params
//; func_name = h.get('func_name', 'f_sx')
//; iwidth    = h.get('iwidth', 8)
//; owidth    = h.get('owidth', 16)
//; signed    = h.get('signed', 1)
//; lifetime  = h.get('lifetime', 'static')
//; if owidth <= iwidth:
//;     error(f"{func_name}: owidth {owidth} does not extend iwidth {iwidth}; narrowing is f_qcvt's job")
//; # endif
//; if isinstance(signed, bool) or signed not in (0, 1):
//;     error(f"{func_name}: signed ({signed}) must be 0 or 1")
//; # endif
    function `lifetime` `'signed ' if signed else ''`[`owidth-1`:0] `func_name`;
        input [`iwidth-1`:0] x;
        `func_name` = `sext('x', iwidth, owidth, signed=bool(signed))`;
    endfunction
//; _d = getattr(self, func_name, {}); _d['owidth'] = owidth; setattr(self, func_name, _d)
