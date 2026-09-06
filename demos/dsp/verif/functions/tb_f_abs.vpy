//; IW     = parameter('IW',     8)   # input width
//; APPROX = parameter('APPROX', 0)   # absolute value as ~x, one LSB cheap
//; ISYM   = parameter('ISYM',   0)   # caller promises the most negative value never arrives
//; MIN    = -(1 << (IW-1))
//; MAX    =  (1 << (IW-1)) - 1
//; IND    = "    " if ISYM else ""   # the ISYM skip wraps the body in a block
//; CFG    = f"{mname} IW={IW} APPROX={APPROX} ISYM={ISYM}"
// unit test for f_abs
module `mname`;

//; self.include_params = {'func_name': 'dut', 'iwidth': IW, 'approx': APPROX, 'isym': ISYM}
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
//; if ISYM:
            // isym: the caller promises the most negative input never arrives
            if (xs == `MIN`)
                tb_skip();
            else begin
//; # endif
            `IND`y   = dut(x);
            `IND`exp = ref_abs(xs);
            `IND`tb_check(64'(y), exp, $sformatf("x=%0d", xs));
            `IND`tb_data_row($sformatf("%0d,%0d,%0d", xs, y, exp));
//; if ISYM:
            end
//; # endif
        end
        tb_report("`CFG`");
        $finish;
    end
endmodule
