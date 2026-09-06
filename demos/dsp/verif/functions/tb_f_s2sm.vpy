//; IW      = parameter('IW',      8)   # input width
//; OW      = parameter('OW',      8)   # requested output width
//; SM_PLUS = parameter('SM_PLUS', 1)   # sign bit set means positive
// unit test for f_s2sm
module `mname`;

//; self.include_params = {'func_name': 'dut', 'iwidth': IW, 'owidth': OW, 'sm_plus': SM_PLUS}
//; include('f_s2sm.vpy')
//; include('tb_util.vpy')
//; # f_s2sm narrows to the smaller of the two widths, so take the width it published
//; # rather than re-deriving that rule here, where it could drift from the function
//; w       = getattr(self, 'dut')['owidth']
//; OWD     = "" if w == OW else f" (ow={w})"
//; CFG     = f"{mname} IW={IW} OW={OW}{OWD} SM_PLUS={SM_PLUS}"
//; MIN     = -(1 << (w-1))
//; SBIT    =  (1 << (w-1))

    logic signed [`w-1`:0] x;
    logic        [`w-1`:0] y;
    longint signed         xs, exp;

    // the result is a pattern, not a number: sign bit set means positive when SM_PLUS,
    // negative otherwise. The most negative input is folded to MIN+1 before the magnitude
    // is taken, so the magnitude always fits in w-1 bits.
    function longint signed ref_s2sm(input longint signed v);
        longint signed m;
        begin
            m = (v == `MIN`) ? `MIN+1` : v;
            if (m < 0) m = -m;
//; if SM_PLUS:
            ref_s2sm = (v < 0) ? m : (m + `SBIT`);
//; else:
            ref_s2sm = (v < 0) ? (m + `SBIT`) : m;
//; # endif
        end
    endfunction

    initial begin
        tb_data_open("`CFG`", "x,y,exp");
        for (int i = 0; i < `1 << w`; i++) begin
            x   = i[`w-1`:0];
            xs  = longint'(x);
            y   = dut(x);
            exp = ref_s2sm(xs);
            tb_check(64'(y), exp, $sformatf("x=%0d", xs));
            tb_data_row($sformatf("%0d,%0d,%0d", xs, y, exp));
        end
        tb_report("`CFG`");
        $finish;
    end
endmodule
