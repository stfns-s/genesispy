//; # Gray-code converter: one Verilog function per include, encoding or decoding.
//; h         = self.include_params
//; func_name = h['func_name']
//; width     = h['width']
//; direction = h.get('direction', 'encode')
//; lifetime  = h.get('lifetime', 'static')
//; if not isinstance(width, int) or width < 1:
//;     error(f"{func_name}: width ({width!r}) must be an integer >= 1")
//; # endif
//; if direction not in ('encode', 'decode'):
//;     error(f"{func_name}: direction {direction!r} must be 'encode' or 'decode'")
//; # endif
//; msb = width - 1
//; src = 'b' if direction == 'encode' else 'g'
//; dst = 'g' if direction == 'encode' else 'b'
//; # The encoder XORs two input bits; the decoder XORs the output bit it just
//; # produced with an input bit, so its chain has to run MSB down.
//; hi  = src if direction == 'encode' else dst
    // `func_name`(`src`[`msb`:0]) -> `dst`[`msb`:0], gray `direction` over `width` bits
    function `lifetime` [`msb`:0] `func_name`;
        input [`msb`:0] `src`;
        reg   [`msb`:0] `dst`;
        begin
            `dst`[`msb`] = `src`[`msb`];
//; for i in range(msb - 1, -1, -1):
            `dst`[`i`] = `hi`[`i+1`] ^ `src`[`i`];
//; # endfor
            `func_name` = `dst`;
        end
    endfunction
//; _d = getattr(self, func_name, {}); _d['owidth'] = width; setattr(self, func_name, _d)
