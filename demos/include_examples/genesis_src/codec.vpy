//; # Gray-code round trip: includes gray.vpy twice and calls both halves.
//; # A leaf that itself includes a leaf, the nesting level top.vpy does not reach.
//; h         = self.include_params
//; func_name = h['func_name']
//; width     = h['width']
//; lifetime  = h.get('lifetime', 'static')
//; enc_func  = func_name + '_enc'
//; dec_func  = func_name + '_dec'
//; if width == 1:
//;     warning(f"{func_name}: at width 1 gray coding is the identity, so the round trip proves nothing")
//; # endif
//; self.include_params = {'func_name': enc_func, 'width': width, 'direction': 'encode', 'lifetime': lifetime}
//; include('gray.vpy')
//; self.include_params = {'func_name': dec_func, 'width': width, 'direction': 'decode', 'lifetime': lifetime}
//; include('gray.vpy')
//; # The width comes back from the child rather than being recomputed here.
//; owidth = getattr(self, enc_func)['owidth']
    // `func_name`(x[`width-1`:0]) -> `dec_func`(`enc_func`(x)), which must equal x
    function `lifetime` [`owidth-1`:0] `func_name`;
        input [`width-1`:0] x;
        begin
            `func_name` = `dec_func`(`enc_func`(x));
        end
    endfunction
//; _d = getattr(self, func_name, {})
//; _d['owidth'] = owidth
//; _d['enc'] = enc_func
//; _d['dec'] = dec_func
//; setattr(self, func_name, _d)
