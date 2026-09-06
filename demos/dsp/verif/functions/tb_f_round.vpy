//; IW    = parameter('IW',   8)   # input width
//; OW    = parameter('OW',   6)   # requested output width
//; OSYM  = parameter('OSYM', 0)   # output range excludes the most negative value
// unit test for f_round
module `mname`;

//; self.include_params = {'func_name': 'dut', 'iwidth': IW, 'owidth': OW, 'osym': OSYM}
//; include('f_round.vpy')
//; include('tb_util.vpy')
//; # f_round clamps the requested width, so take the width it emitted rather than
//; # re-deriving the clamp here and risking a rule that drifts from the function's
//; ow    = getattr(self, 'dut')['owidth']
//; OWD   = "" if ow == OW else f" (ow={ow})"
//; CFG   = f"{mname} IW={IW} OW={OW}{OWD} OSYM={OSYM}"
//; lsb_w = IW - ow
//; HALF  = 1 << (lsb_w - 1)
//; DIV   = 1 << lsb_w
//; RMIN  = -(1 << (ow-1))
//; RMAX  = (1 << (ow-1)) - 1

    logic signed [`IW-1`:0] x;
    logic signed [`ow-1`:0] y;
    longint signed          xs, exp;

    initial begin
        tb_data_open("`CFG`", "x,y,exp");
        for (int i = 0; i < `1 << IW`; i++) begin
            x   = i[`IW-1`:0];
            xs  = longint'(x);
            y   = dut(x);
            exp = clamp(fdiv(xs + `HALF`, `DIV`), `RMIN`, `RMAX`);
//; if OSYM:
            exp = clamp(exp, `RMIN+1`, `RMAX`);
//; # endif
            tb_check(64'(y), exp, $sformatf("x=%0d", xs));
            tb_data_row($sformatf("%0d,%0d,%0d", xs, y, exp));
        end
        tb_report("`CFG`");
        $finish;
    end
endmodule
