//; IW     = parameter('IW',      8)   # input width
//; OW     = parameter('OW',     16)   # output width
//; SIGNED = parameter('SIGNED',  1)   # 0 extends with zeros
//; CFG = f"{mname} IW={IW} OW={OW} SIGNED={SIGNED}"
//; S = 'signed' if SIGNED else ''
//; FILL = f"x[{IW-1}]" if SIGNED else "1'b0"
// unit test for f_sx
module `mname`;

//; self.include_params = {'func_name': 'dut', 'iwidth': IW, 'owidth': OW, 'signed': SIGNED}
//; include('f_sx.vpy')
//; include('tb_util.vpy')

    logic `S.ljust(6)` [`IW-1`:0] x;
    logic `S.ljust(6)` [`OW-1`:0] y;
    longint signed          xs, exp;

    initial begin
        tb_data_open("`CFG`", "x,y,exp");
        for (int i = 0; i < `1 << IW`; i++) begin
            x   = i[`IW-1`:0];
            xs  = longint'(x);
            y   = dut(x);
            exp = xs;
            tb_check(64'(y), exp, $sformatf("x=%0d", xs));
//; if OW > 64:
            // tb_check takes 64 bits, so the bits above them are checked as the extension
            tb_check(64'(y[`OW-1`:64] != {`OW-64`{`FILL`}}), 0, $sformatf("x=%0d high bits", xs));
//; # endif
            tb_data_row($sformatf("%0d,%0d,%0d", xs, y, exp));
        end
        tb_report("`CFG`");
        $finish;
    end
endmodule
