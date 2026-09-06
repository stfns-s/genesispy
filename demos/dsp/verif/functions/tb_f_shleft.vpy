//; IW   = parameter('IW',   8)   # input width
//; CW   = parameter('CW',   4)   # shift control width
//; OSYM = parameter('OSYM', 0)   # output never takes the most negative value
//; MIN  = -(1 << (IW-1))
//; MAX  =  (1 << (IW-1)) - 1
//; LO   = MIN + 1 if OSYM else MIN
//; CFG  = f"{mname} IW={IW} CW={CW} OSYM={OSYM}"
// unit test for f_shleft
module `mname`;

//; self.include_params = {'func_name': 'dut', 'iwidth': IW, 'cwidth': CW, 'osym': OSYM}
//; include('f_shleft.vpy')
//; include('tb_util.vpy')

    logic signed [`IW-1`:0] x, y;
    logic        [`CW-1`:0] sh;
    longint signed          xs, shs, exp;

    // intent: out = in * 2**sh, saturated to the output range
    function longint signed ref_shleft(input longint signed v, s);
        longint signed m;
        begin
            m = 64'sd1 << s;
            ref_shleft = clamp(v * m, `LO`, `MAX`);
        end
    endfunction

    initial begin
        tb_data_open("`CFG`", "sh,x,y,exp");
        for (int j = 0; j < `1 << CW`; j++) begin
            sh  = j[`CW-1`:0];
            shs = longint'(sh);
            for (int i = 0; i < `1 << IW`; i++) begin
                x   = i[`IW-1`:0];
                xs  = longint'(x);
                y   = dut(x, sh);
                exp = ref_shleft(xs, shs);
                tb_check(64'(y), exp, $sformatf("x=%0d sh=%0d", xs, shs));
                tb_data_row($sformatf("%0d,%0d,%0d,%0d", shs, xs, y, exp));
            end
        end
        tb_report("`CFG`");
        $finish;
    end
endmodule
