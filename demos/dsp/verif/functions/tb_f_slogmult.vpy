//; AW      = parameter('AW',      8)   # a input width
//; BW      = parameter('BW',      8)   # b input width
//; ISYM    = parameter('ISYM',    0)   # inputs are already symmetric
//; IAPPROX = parameter('IAPPROX', 1)   # approximate the input negate
//; OAPPROX = parameter('OAPPROX', 0)   # approximate the output negate
//; ZDET    = parameter('ZDET',    1)   # force zero when log2(abs b) is zero
//; OW      = AW + BW - (1 if ISYM else 0)
//; MIN_A   = -(1 << (AW-1))
//; MIN_B   = -(1 << (BW-1))
//; CFG     = f"{mname} AW={AW} BW={BW} ISYM={ISYM} IAPPROX={IAPPROX} OAPPROX={OAPPROX}"
//; CFG    += f" ZDET={ZDET}"
// unit test for f_slogmult
module `mname`;

//; PARAMS = {'awidth': AW, 'bwidth': BW, 'isym': ISYM, 'iapprox': IAPPROX}
//; self.include_params = dict(PARAMS, func_name='dut', oapprox=OAPPROX, zdet=ZDET)
//; include('f_slogmult.vpy')
//; self.include_params = {'func_name': 'ref_log2', 'iwidth': BW, 'isym': ISYM, 'approx': IAPPROX, 'lfrac': 0}
//; include('tb_ref_log2.vpy')
//; include('tb_util.vpy')
//; LOG_MSB = getattr(self, 'ref_log2')['owidth'] - 1

    logic signed [`AW-1`:0] a;
    logic signed [`BW-1`:0] b;
    logic signed [`OW-1`:0] y;
    longint signed          as, bs, exp;

    // documented intent: a shifted left by the log of b, negated with b's sign, all in
    // `OW` bits. The shift never overflows `OW`, so the truncation below is a no-op.
    function longint signed ref_slogmult(input longint signed av, bv);
        longint signed l, log2b, res;
        reg [`BW-1`:0] ib;   // unsigned index; a size cast would keep bv's sign
        reg            sb;
        begin
            ib    = bv[`BW-1`:0];
            l     = longint'(ref_log2[ib]);
            sb    = l[`LOG_MSB`];
            log2b = l & `(1 << LOG_MSB) - 1`;
            res   = tb_sext(av << log2b, `OW`);
//; if OAPPROX:
            if (sb) res = tb_sext(~res, `OW`);
//; else:
            if (sb) res = tb_sext(-res, `OW`);
//; # endif
//; if ZDET:
            if (log2b == 0) res = 0;
//; # endif
            ref_slogmult = res;
        end
    endfunction

    initial begin
        ref_log2_load;
        tb_data_open("`CFG`", "a,b,y,exp");
        for (int i = 0; i < `1 << AW`; i++) begin
            a  = i[`AW-1`:0];
            as = longint'(a);
            for (int j = 0; j < `1 << BW`; j++) begin
                b     = j[`BW-1`:0];
                bs    = longint'(b);
//; if ISYM:
                // isym: the caller promises the most negative input never arrives
                if (as == `MIN_A` || bs == `MIN_B`)
                    tb_skip();
                else begin
//; # endif
                y     = dut(a, b);
                exp   = ref_slogmult(as, bs);
                tb_check(64'(y), exp, $sformatf("a=%0d b=%0d", as, bs));
                tb_data_row($sformatf("%0d,%0d,%0d,%0d", as, bs, y, exp));
//; if ISYM:
                end
//; # endif
            end
        end
        tb_report("`CFG`");
        $finish;
    end
endmodule
