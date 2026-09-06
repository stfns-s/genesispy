    // convert 2's complement to sign,magnitude
    //  The most negative input has no magnitude counterpart, so it folds to MIN+1 first.
    //  Both ports are min(iwidth, owidth) wide: this converts, it does not change width.
//; from vexpr import lit
//; h         = self.include_params
//; func_name = h.get('func_name', 'f_s2sm')
//; iwidth    = h.get('iwidth', 8)
//; owidth    = h.get('owidth', 8)
//; sm_plus   = h.get('sm_plus', 1)     # positive is MSB 1 (unconventional)
//; lifetime  = h.get('lifetime', 'static')
//; ow         = owidth if owidth < iwidth else iwidth
//; if ow < 2:
//;     error(f"{func_name}: ow ({ow}) must be >= 2; sign magnitude needs a sign bit and a magnitude bit")
//; # endif
//; minn      = -(1 << (ow-1))
    function `lifetime` unsigned [`ow-1`:0] `func_name`;
        input signed [`ow-1`:0] snum;
        reg signed [`ow-1`:0] t;

        t = (snum == `lit(minn, ow)`) ? `lit(minn+1, ow)` : snum;
        t = t[`ow-1`] ? -t : t;
        `func_name`[`ow-1`]   = `sm_plus` ^ snum[`ow-1`];
        `func_name`[`ow-2`:0] = t[`ow-2`:0];
    endfunction
//; _d = getattr(self, func_name, {}); _d['owidth'] = ow; setattr(self, func_name, _d)
