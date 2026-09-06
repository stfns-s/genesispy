//; IW  = parameter('IW', 8)   # width of both operands
//; CFG = f"{mname} IW={IW}"
// unit test for f_umod
module `mname`;

//; self.include_params = {'func_name': 'dut', 'iwidth': IW}
//; include('f_umod.vpy')
//; include('tb_util.vpy')

    logic [`IW-1`:0] a, b, y;
    longint signed   au, bu, exp;

    function longint signed ref_umod(input longint signed n, d);
        ref_umod = (d == 0) ? 0 : n % d;
    endfunction

    initial begin
        tb_data_open("`CFG`", "a,b,y,exp");
        for (int i = 0; i < `1 << IW`; i++) begin
            for (int j = 0; j < `1 << IW`; j++) begin
                a   = i[`IW-1`:0];
                b   = j[`IW-1`:0];
                au  = 64'(a);
                bu  = 64'(b);
                y   = dut(a, b);
                exp = ref_umod(au, bu);
                tb_check(64'(y), exp, $sformatf("a=%0d b=%0d", au, bu));
                tb_data_row($sformatf("%0d,%0d,%0d,%0d", au, bu, y, exp));
            end
        end
        tb_report("`CFG`");
        $finish;
    end
endmodule
