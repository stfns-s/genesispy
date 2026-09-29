//; IW     = parameter('IW',     8)   # input width
//; if IW < 1:
//;     error(f"{mname}: IW ({IW}) must be >= 1")
//; # endif
//; APPROX = parameter('APPROX', 0)   # absolute value as ~x, one LSB cheap
//; ISYMM  = parameter('ISYMM',  0)   # caller promises the most negative value never arrives
//; MIN    = -(1 << (IW-1))
//; MAX    =  (1 << (IW-1)) - 1
//; IND    = "    " if ISYMM else ""  # the ISYMM skip wraps the body in a block
//; CFG    = f"{mname} IW={IW} APPROX={APPROX} ISYMM={ISYMM}"
// unit test for f_abs
module `mname`;

//; self.include_params = {'func_name': 'dut', 'iwidth': IW, 'approx': APPROX, 'isymm': ISYMM}
//; include('f_abs.vpy')
//; include('tb_util.vpy')

    logic signed [`IW-1`:0] x, y;
    longint signed          xs, exp;

    function longint signed ref_abs(input longint signed v);
//; if APPROX:
        ref_abs = (v < 0) ? -v - 1 : v;
//; else:
        ref_abs = (v == `MIN`) ? `MAX` : ((v < 0) ? -v : v);
//; # endif
    endfunction

    initial begin
        tb_data_open("`CFG`", "x,y,exp");
        for (int i = 0; i < `1 << IW`; i++) begin
            x  = i[`IW-1`:0];
            xs = longint'(x);
//; if ISYMM:
            // isymm: the caller promises the most negative input never arrives
            if (xs == `MIN`)
                tb_skip();
            else begin
//; # endif
            `IND`y   = dut(x);
            `IND`exp = ref_abs(xs);
            `IND`tb_check(64'(y), exp, $sformatf("x=%0d", xs));
            `IND`tb_data_row($sformatf("%0d,%0d,%0d", xs, y, exp));
//; if ISYMM:
            end
//; # endif
        end
        tb_report("`CFG`");
        $finish;
    end
endmodule
