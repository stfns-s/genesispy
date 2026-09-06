    // sign extend
//; from vexpr import sext
//; h         = self.include_params
//; func_name = h.get('func_name', 'f_sx')
//; iwidth    = h.get('iwidth', 8)
//; owidth    = h.get('owidth', 16)
//; lifetime  = h.get('lifetime', 'static')
//; if owidth <= iwidth:
//;     error(f"{func_name}: owidth {owidth} does not extend iwidth {iwidth}; narrowing is f_qcvt's job")
//; # endif
    function `lifetime` signed [`owidth-1`:0] `func_name`;
        input [`iwidth-1`:0] x;
        `func_name` = `sext('x', iwidth, owidth)`;
    endfunction
//; _d = getattr(self, func_name, {}); _d['owidth'] = owidth; setattr(self, func_name, _d)
