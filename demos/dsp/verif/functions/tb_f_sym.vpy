//; from vexpr import lit
//; IW  = parameter('IW', 8)   # input width
//; MIN = -(1 << (IW-1))
//; CFG = f"{mname} IW={IW}"
//; # The expected values, computed here at generation. f_sym tests the input against the
//; # most negative code and substitutes; this clamps the value into the symmetric range,
//; # so the two agree only if both are right.
//; LO  = MIN + 1
//; HI  = -MIN - 1
//; def _gold(i):
//;     return min(HI, max(LO, i - (1 << IW) if i >= (1 << (IW-1)) else i))
//; # enddef
// unit test for f_sym
module `mname`;

//; self.include_params = {'func_name': 'dut', 'iwidth': IW}
//; include('f_sym.vpy')
//; include('tb_util.vpy')

    logic signed [`IW-1`:0] x, y;
    longint signed          xs, exp;

    // expected output for every input code
    reg signed [`IW-1`:0] gold [0:`(1 << IW) - 1`];

    // called first thing in the initial block, so the table stands before any check reads it
    task gold_load;
        begin
//; for i in range(1 << IW):
            gold[`i`] = `lit(_gold(i), IW)`;
//; # endfor
        end
    endtask

    initial begin
        gold_load;
        tb_data_open("`CFG`", "x,y,exp");
        for (int i = 0; i < `1 << IW`; i++) begin
            x   = i[`IW-1`:0];
            xs  = longint'(x);
            y   = dut(x);
            exp = longint'(gold[i]);
            tb_check(64'(y), exp, $sformatf("x=%0d", xs));
            tb_data_row($sformatf("%0d,%0d,%0d", xs, y, exp));
        end
        tb_report("`CFG`");
        $finish;
    end
endmodule
