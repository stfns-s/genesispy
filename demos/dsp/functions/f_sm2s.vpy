    // convert sign,magnitude to 2's complement
//; h         = self.include_params
//; func_name = h.get('func_name', 'f_sm2s')
//; iwidth    = h.get('iwidth', 8)
//; owidth    = h.get('owidth', 8)
//; sm_plus   = h.get('sm_plus', 1) # MSB 1 maps positive
//; lifetime  = h.get('lifetime', 'static')
//; ow         = owidth if owidth < iwidth else iwidth
//; if ow < 2:
//;     error(f"{func_name}: ow ({ow}) must be >= 2; sign magnitude needs a sign bit and a magnitude bit")
//; # endif
    function `lifetime` signed [`ow-1`:0] `func_name`;
        input signed [`ow-1`:0] unum;

//; if sm_plus:
        `func_name` = unum[`ow-1`] ? {1'b0,  unum[`ow-2`:0]} : -unum;
//; else:
        `func_name` = unum[`ow-1`] ? -{1'b0, unum[`ow-2`:0]} :  unum;
//; # endif
    endfunction
//; _d = getattr(self, func_name, {}); _d['owidth'] = ow; setattr(self, func_name, _d)
