//; from vexpr import decl, lit
//; from fractions import Fraction
//; import qfmt
//; Q_IN       = parameter('Q_IN',       'Q4.4')    # input Q format
//; Q_OUT      = parameter('Q_OUT',      'Q2.2')    # output Q format
//; ROUND_MODE = parameter('ROUND_MODE', 'trunc')   # trunc, half_up or half_even
//; OSYM       = parameter('OSYM',       0)         # output uses a symmetric range
//; # only the notation comes from the library; the reference arithmetic below is the
//; # testbench's own, so the check stays independent of what the function derives
//; def parse_q(s):
//;     try:
//;         return qfmt.parse(s)
//;     except qfmt.QError as e:
//;         error(f"{mname}: {e}")
//; # enddef
//; F_IN  = parse_q(Q_IN)
//; F_OUT = parse_q(Q_OUT)
//; S_IN,  IW, N_IN  = F_IN.signed,  F_IN.width,  F_IN.frac
//; S_OUT, OW, N_OUT = F_OUT.signed, F_OUT.width, F_OUT.frac
//; OMAX  = (1 << (OW-1)) - 1 if S_OUT else (1 << OW) - 1
//; OMIN  = -((1 << (OW-1)) - 1) if (S_OUT and OSYM) else (-(1 << (OW-1)) if S_OUT else 0)
//; CFG   = f"{mname} Q_IN={Q_IN} Q_OUT={Q_OUT} ROUND_MODE={ROUND_MODE} OSYM={OSYM}"
//; # The expected values, computed here at generation. f_qcvt shifts, with a rounding
//; # constant added first and a tie mask to correct half_even; this holds the exact value
//; # as a Fraction and rounds it, so the two agree only if both are right. A Fraction power
//; # takes a negative exponent, which is what makes a negative m or n fall out.
//; HALF  = Fraction(1, 2)
//; def _round(scaled):
//;     fl  = scaled.numerator // scaled.denominator
//;     rem = scaled - fl
//;     up  = rem > HALF or (rem == HALF and (ROUND_MODE == 'half_up' or fl % 2 != 0))
//;     return fl + (1 if (ROUND_MODE != 'trunc' and up) else 0)
//; # enddef
//; def _gold(i):
//;     v = i - (1 << IW) if (S_IN and i >= (1 << (IW-1))) else i
//;     return min(OMAX, max(OMIN, _round(Fraction(v) * Fraction(2) ** (N_OUT - N_IN))))
//; # enddef
// unit test for f_qcvt
module `mname`;

//; self.include_params = {'func_name': 'dut', 'q_in': Q_IN, 'q_out': Q_OUT, 'round_mode': ROUND_MODE, 'osym': OSYM}
//; include('f_qcvt.vpy')
//; include('tb_util.vpy')

    logic `decl(IW, signed=S_IN)` x;
    logic `decl(OW, signed=S_OUT)` y;
    longint signed                                     xs, exp;

    // documented intent: the same real value in the output format, rounded as asked and
    // held inside the output range, for every input code
    reg `decl(OW, signed=S_OUT)` gold [0:`(1 << IW) - 1`];

    // called first thing in the initial block, so the table stands before any check reads it
    task gold_load;
        begin
//; for i in range(1 << IW):
            gold[`i`] = `lit(_gold(i), OW, signed=S_OUT)`;
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
