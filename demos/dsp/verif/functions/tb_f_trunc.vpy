//; IW   = parameter('IW',   8)   # input width
//; OW   = parameter('OW',   6)   # output width
//; OSYM = parameter('OSYM', 0)   # output range excludes the most negative value
//; if OW < 1:
//;     error(f"{mname}: OW ({OW}) must be >= 1")
//; # endif
//; tiw  = IW if OW < IW else OW  # the port widens when OW > IW
//; SH   = 1 << (tiw - OW)
//; MIN = -(1 << (OW-1))
//; MAX = (1 << (OW-1)) - 1
//; CFG  = f"{mname} IW={IW} OW={OW} OSYM={OSYM}"
// unit test for f_trunc
module `mname`;

//; self.include_params = {'func_name': 'dut', 'iwidth': IW, 'owidth': OW, 'osym': OSYM}
//; include('f_trunc.vpy')
//; include('tb_util.vpy')

    logic signed [`tiw-1`:0] x;
    logic signed [`OW-1`:0]  y;
    longint signed           xs, exp;

    initial begin
        tb_data_open("`CFG`", "x,y,exp");
        for (int i = 0; i < `1 << tiw`; i++) begin
            x   = i[`tiw-1`:0];
            xs  = longint'(x);
            y   = dut(x);
            exp = fdiv(xs, `SH`);
//; if OSYM:
            exp = clamp(exp, `MIN+1`, `MAX`);
//; # endif
            tb_check(64'(y), exp, $sformatf("x=%0d", xs));
            tb_data_row($sformatf("%0d,%0d,%0d", xs, y, exp));
        end
        tb_report("`CFG`");
        $finish;
    end
endmodule
