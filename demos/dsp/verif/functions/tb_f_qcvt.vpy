//; from genesispy.lib.verilog import decl, lit
//; from fractions import Fraction
//; import qfmt
//; Q_IN       = parameter('Q_IN',       'Q4.4')    # input Q format
//; Q_OUT      = parameter('Q_OUT',      'Q2.2')    # output Q format
//; ROUND_MODE = parameter('ROUND_MODE', 'trunc')   # one of qfmt.ROUND_MODES
//; OSYMM      = parameter('OSYMM',      0)         # output uses a symmetric range
//; SRC_LO     = parameter('SRC_LO',     None)      # lowest input code driven; None: the format's
//; SRC_HI     = parameter('SRC_HI',     None)      # highest input code driven; None: the format's
//; SATURATE   = parameter('SATURATE',   1)         # 0: the function must not saturate
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
//; OMIN  = -((1 << (OW-1)) - 1) if (S_OUT and OSYMM) else (-(1 << (OW-1)) if S_OUT else 0)
//; # the codes driven: the whole input format, or the bounds the function was told about,
//; # which it checks against the format itself
//; LO    = (-(1 << (IW-1)) if S_IN else 0) if SRC_LO is None else int(SRC_LO)
//; HI    = ((1 << (IW-1)) - 1 if S_IN else (1 << IW) - 1) if SRC_HI is None else int(SRC_HI)
//; CFG   = f"{mname} Q_IN={Q_IN} Q_OUT={Q_OUT} ROUND_MODE={ROUND_MODE} OSYMM={OSYMM}"
//; CFG  += f" SRC_LO={SRC_LO} SRC_HI={SRC_HI} SATURATE={SATURATE}"
//; # The expected values, computed here at generation. f_qcvt shifts, with a rounding
//; # constant added first and a tie mask to correct half_even; this holds the exact value
//; # as a Fraction and rounds it, so the two agree only if both are right. A Fraction power
//; # takes a negative exponent, which is what makes a negative m or n fall out.
//; HALF  = Fraction(1, 2)
//; def _round(scaled):
//;     fl  = scaled.numerator // scaled.denominator
//;     rem = scaled - fl
//;     if ROUND_MODE == 'trunc':
//;         up = False
//;     elif ROUND_MODE == 'half_up':
//;         up = rem >= HALF
//;     elif ROUND_MODE == 'half_even':
//;         up = rem > HALF or (rem == HALF and fl % 2 != 0)
//;     elif ROUND_MODE == 'half_away':
//;         up = rem > HALF or (rem == HALF and fl >= 0)
//;     elif ROUND_MODE == 'to_zero':
//;         up = fl < 0 and rem > 0
//;     elif ROUND_MODE == 'to_odd':
//;         return fl | (1 if rem else 0)
//;     elif ROUND_MODE == 'von_neumann':
//;         return fl | (1 if N_OUT < N_IN else 0)
//;     else:
//;         error(f"{mname}: bad ROUND_MODE {ROUND_MODE}")
//;     # endif
//;     return fl + (1 if up else 0)
//; # enddef
//; def _gold(c):
//;     return min(OMAX, max(OMIN, _round(Fraction(c) * Fraction(2) ** (N_OUT - N_IN))))
//; # enddef
// unit test for f_qcvt
module `mname`;

//; incp = {'func_name': 'dut', 'q_in': Q_IN, 'q_out': Q_OUT, 'round_mode': ROUND_MODE}
//; self.include_params = dict(incp, osymm=OSYMM, src_lo=SRC_LO, src_hi=SRC_HI, saturate=SATURATE)
//; include('f_qcvt.vpy')
//; include('tb_util.vpy')

//; COL = [IW, OW]
    logic `decl(IW, signed=S_IN, col=COL)` x;
    logic `decl(OW, signed=S_OUT, col=COL)` y;
    longint signed                                     xs, exp;

    // documented intent: the same real value in the output format, rounded as asked and
    // held inside the output range, for every input code driven
    reg `decl(OW, signed=S_OUT)` gold [0:`HI - LO`];

    // called first thing in the initial block, so the table stands before any check reads it
    task gold_load;
        begin
//; for c in range(LO, HI + 1):
            gold[`c - LO`] = `lit(_gold(c), OW, signed=S_OUT)`;
//; # endfor
        end
    endtask

    initial begin
        gold_load;
        tb_data_open("`CFG`", "x,y,exp");
        for (int c = `LO`; c <= `HI`; c++) begin
            x   = c[`IW-1`:0];
            xs  = longint'(x);
            y   = dut(x);
            exp = longint'(gold[c - (`LO`)]);
            tb_check(64'(y), exp, $sformatf("x=%0d", xs));
            tb_data_row($sformatf("%0d,%0d,%0d", xs, y, exp));
        end
        tb_report("`CFG`");
        $finish;
    end
endmodule
