//; IW   = parameter('IW',   8)   # input width
//; CW   = parameter('CW',   4)   # shift control width
//; OSYM = parameter('OSYM', 0)   # clamp the low end to MIN+1 rather than MIN
//; MIN  = -(1 << (IW-1))
//; MAX  =  (1 << (IW-1)) - 1
//; LO   = MIN + 1 if OSYM else MIN
//; CFG  = f"{mname} IW={IW} CW={CW} OSYM={OSYM}"
// unit test for f_shright
module `mname`;

//; self.include_params = {'func_name': 'dut', 'iwidth': IW, 'cwidth': CW, 'osym': OSYM}
//; include('f_shright.vpy')
//; include('tb_util.vpy')

    logic signed [`IW-1`:0] x, y;
    logic        [`CW-1`:0] sh;
    logic        [1:0]      frac;
    longint signed          xs, shs, fs, exp;

    // documented intent: out = in / 2**sh * (1 + frac*0.25), truncated once, at the end,
    // then saturated -- the gain reaches 1.75 at sh=0, so the result can leave the range
    function longint signed ref_shright(input longint signed v, s, f);
        longint signed den;
        begin
            den = 64'sd1 << (s + 2);
            ref_shright = clamp(fdiv(v * (4 + f), den), `LO`, `MAX`);
        end
    endfunction

    initial begin
        tb_data_open("`CFG`", "sh,frac,x,y,exp");
        for (int j = 0; j < `1 << CW`; j++) begin
            sh  = j[`CW-1`:0];
            shs = longint'(sh);
            for (int k = 0; k < 4; k++) begin
                frac = k[1:0];
                fs   = longint'(frac);
                for (int i = 0; i < `1 << IW`; i++) begin
                    x   = i[`IW-1`:0];
                    xs  = longint'(x);
                    y   = dut(x, sh, frac);
                    exp = ref_shright(xs, shs, fs);
                    tb_check(64'(y), exp, $sformatf("x=%0d sh=%0d frac=%0d", xs, shs, fs));
                    tb_data_row($sformatf("%0d,%0d,%0d,%0d,%0d", shs, fs, xs, y, exp));
                    tb_diff(64'(y), exp);
                end
            end
        end
        tb_stats("`CFG`");
        tb_report("`CFG`");
        $finish;
    end
endmodule
