//; IW     = parameter('IW',     8)   # input width
//; ISYM   = parameter('ISYM',   0)   # input is already symmetric
//; APPROX = parameter('APPROX', 1)   # negate as ~x instead of ~x+1
//; LFRAC  = parameter('LFRAC',  0)   # fractional bits in the log
//; MIN    = -(1 << (IW-1))
//; CFG    = f"{mname} IW={IW} ISYM={ISYM} APPROX={APPROX} LFRAC={LFRAC}"
// unit test for f_log2
module `mname`;

//; PARAMS = {'iwidth': IW, 'isym': ISYM, 'approx': APPROX, 'lfrac': LFRAC}
//; self.include_params = dict(PARAMS, func_name='dut')
//; include('f_log2.vpy')
//; self.include_params = dict(PARAMS, func_name='ref_log2')
//; include('tb_ref_log2.vpy')
//; include('tb_util.vpy')
//; OW = getattr(self, 'dut')['owidth']

    logic signed [`IW-1`:0] x;
    logic        [`OW-1`:0] y;
    longint signed          xs, exp;

    initial begin
        ref_log2_load;
        tb_data_open("`CFG`", "x,y,exp");
        for (int i = 0; i < `1 << IW`; i++) begin
            x   = i[`IW-1`:0];
            xs  = longint'(x);
//; if ISYM:
            // isym: the caller promises the most negative input never arrives
            if (xs == `MIN`)
                tb_skip();
            else begin
//; # endif
            y   = dut(x);
            exp = longint'(ref_log2[i]);
            tb_check(64'(y), exp, $sformatf("x=%0d", xs));
            tb_data_row($sformatf("%0d,%0d,%0d", xs, y, exp));
//; if ISYM:
            end
//; # endif
        end
        tb_report("`CFG`");
        $finish;
    end
endmodule
