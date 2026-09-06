//; IW      = parameter('IW',      8)   # input width
//; OW      = parameter('OW',      8)   # requested output width
//; SM_PLUS = parameter('SM_PLUS', 1)   # sign bit set means positive
// unit test for f_sm2s
module `mname`;

//; self.include_params = {'func_name': 'dut', 'iwidth': IW, 'owidth': OW, 'sm_plus': SM_PLUS}
//; include('f_sm2s.vpy')
//; include('tb_util.vpy')
//; # f_sm2s narrows to the smaller of the two widths, so take the width it published
//; # rather than re-deriving that rule here, where it could drift from the function
//; w       = getattr(self, 'dut')['owidth']
//; OWD     = "" if w == OW else f" (ow={w})"
//; CFG     = f"{mname} IW={IW} OW={OW}{OWD} SM_PLUS={SM_PLUS}"

    logic        [`w-1`:0] x;
    logic signed [`w-1`:0] y;
    longint signed         exp;

    // the input is a pattern, not a number: bit w-1 is the sign flag, bits w-2:0 the magnitude
    function longint signed ref_sm2s(input logic [`w-1`:0] xp);
        longint signed m;
        begin
            m = 64'(xp[`w-2`:0]);
//; if SM_PLUS:
            ref_sm2s = xp[`w-1`] ? m : -m;
//; else:
            ref_sm2s = xp[`w-1`] ? -m : m;
//; # endif
        end
    endfunction

    initial begin
        tb_data_open("`CFG`", "x,y,exp");
        for (int i = 0; i < `1 << w`; i++) begin
            x   = i[`w-1`:0];
            y   = dut(x);
            exp = ref_sm2s(x);
            tb_check(64'(y), exp, $sformatf("x=%0d", x));
            tb_data_row($sformatf("%0d,%0d,%0d", x, y, exp));
        end
        tb_report("`CFG`");
        $finish;
    end
endmodule
