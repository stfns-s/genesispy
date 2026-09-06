//; IW  = parameter('IW',  8)   # input width
//; OW  = parameter('OW', 16)   # output width
//; CFG = f"{mname} IW={IW} OW={OW}"
// unit test for f_sx
module `mname`;

//; self.include_params = {'func_name': 'dut', 'iwidth': IW, 'owidth': OW}
//; include('f_sx.vpy')
//; include('tb_util.vpy')

    logic signed [`IW-1`:0] x;
    logic signed [`OW-1`:0] y;
    longint signed          xs, exp;

    function longint signed ref_sx(input longint signed v);
        ref_sx = v;
    endfunction

    initial begin
        tb_data_open("`CFG`", "x,y,exp");
        for (int i = 0; i < `1 << IW`; i++) begin
            x   = i[`IW-1`:0];
            xs  = longint'(x);
            y   = dut(x);
            exp = ref_sx(xs);
            tb_check(64'(y), exp, $sformatf("x=%0d", xs));
            tb_data_row($sformatf("%0d,%0d,%0d", xs, y, exp));
        end
        tb_report("`CFG`");
        $finish;
    end
endmodule
