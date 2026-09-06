//; IW  = parameter('IW', 8)   # input width
//; CW  = parameter('CW', 4)   # shift control width, sh is signed
//; MIN = -(1 << (IW-1))
//; MAX =  (1 << (IW-1)) - 1
//; CFG = f"{mname} IW={IW} CW={CW}"
// unit test for f_sh
module `mname`;

//; self.include_params = {'func_name': 'dut', 'iwidth': IW, 'cwidth': CW}
//; include('f_sh.vpy')
//; include('tb_util.vpy')

    logic signed [`IW-1`:0] x, y;
    logic signed [`CW-1`:0] sh;
    logic        [1:0]      frac;
    longint signed          xs, shs, fs, exp;

    // documented intent: out = in * 2**sh * (1 + frac*0.25), truncated once, at the end.
    // sh < 0 shifts right and is not saturated; sh >= 0 shifts left and saturates.
    // the most negative output is replaced by MIN+1 on both paths.
    function longint signed ref_sh(input longint signed v, s, f);
        longint signed num, den;
        begin
            num = v * (4 + f);
            den = 64'sd4;
            if (s >= 0) num = num <<< s;
            else        den = den <<< (-s);
            ref_sh = fdiv(num, den);
            if (s >= 0) ref_sh = clamp(ref_sh, `MIN`, `MAX`);
            if (ref_sh == `MIN`) ref_sh = `MIN+1`;
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
                    exp = ref_sh(xs, shs, fs);
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
