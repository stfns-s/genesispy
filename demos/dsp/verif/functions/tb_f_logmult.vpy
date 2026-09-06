//; from vexpr import decl
//; AW        = parameter('AW',        8)   # a input width
//; BW        = parameter('BW',        8)   # b input width
//; ISYM      = parameter('ISYM',      0)   # inputs are already symmetric
//; IAPPROX   = parameter('IAPPROX',   1)   # approximate the input negate
//; OAPPROX   = parameter('OAPPROX',   0)   # approximate the output negate
//; ALFRAC    = parameter('ALFRAC',    0)   # fractional bits in log2(a)
//; BLFRAC    = parameter('BLFRAC',    0)   # fractional bits in log2(b)
//; ANTILOG   = parameter('ANTILOG',   1)   # convert the log sum back to a product
//; ZDET      = parameter('ZDET',      0)   # force zero when either input is zero
//; OSM       = parameter('OSM',       0)   # sign magnitude output
//; SIGN_ONLY = parameter('SIGN_ONLY', 0)   # return only the sign of the product
//; PARAMS = {'awidth': AW, 'bwidth': BW, 'isym': ISYM, 'iapprox': IAPPROX, 'oapprox': OAPPROX}
//; PARAMS.update({'alfrac': ALFRAC, 'blfrac': BLFRAC, 'antilog': ANTILOG, 'zdet': ZDET})
//; PARAMS.update({'osm': OSM, 'sign_only': SIGN_ONLY})
//; CFG    = f"{mname} AW={AW} BW={BW} ISYM={ISYM} IAPPROX={IAPPROX} OAPPROX={OAPPROX}"
//; CFG   += f" ALFRAC={ALFRAC} BLFRAC={BLFRAC} ANTILOG={ANTILOG} ZDET={ZDET} OSM={OSM}"
//; CFG   += f" SIGN_ONLY={SIGN_ONLY}"
// unit test for f_logmult
module `mname`;

//; self.include_params = dict(PARAMS, func_name='dut')
//; include('f_logmult.vpy')
//; # f_logmult forces alfrac and blfrac to zero when it takes the antilog, and exports what
//; # it settled on. The reference follows those; CFG above still echoes what the run asked
//; # for, which is what run-tb.sh matches against its own command line.
//; ALFRAC_EFF = getattr(self, 'dut')['alfrac']
//; BLFRAC_EFF = getattr(self, 'dut')['blfrac']
//; if not SIGN_ONLY:
//;     refp = {'isym': ISYM, 'approx': IAPPROX}
//;     self.include_params = dict(refp, func_name='ref_log2a', iwidth=AW, lfrac=ALFRAC_EFF)
//;     include('tb_ref_log2.vpy')
//;     self.include_params = dict(refp, func_name='ref_log2b', iwidth=BW, lfrac=BLFRAC_EFF)
//;     include('tb_ref_log2.vpy')
//; # endif
//; include('tb_util.vpy')
//; OW      = getattr(self, 'dut')['owidth']
//; PW      = getattr(self, 'dut')['pwidth']
//; ALOG_MSB = 0 if SIGN_ONLY else getattr(self, 'ref_log2a')['owidth'] - 1
//; BLOG_MSB = 0 if SIGN_ONLY else getattr(self, 'ref_log2b')['owidth'] - 1
//; SHIFT    = ALFRAC_EFF + BLFRAC_EFF + 1
//; # the antilog helper exists only where it means something: a whole-bit log, left in
//; # the log domain by the core
//; EMIT_ANTILOG = (not SIGN_ONLY) and (not ANTILOG) and not (ALFRAC_EFF or BLFRAC_EFF)
//; MIN_A   = -(1 << (AW-1))
//; MIN_B   = -(1 << (BW-1))

    logic signed [`AW-1`:0] a;
    logic signed [`BW-1`:0] b;
    logic `decl(OW, signed=not OSM)` y;
    longint signed          as, bs, exp;
//; if EMIT_ANTILOG:
    logic signed [`PW-1`:0] yp;
    longint signed          expp;
//; # endif

//; if SIGN_ONLY:
    // documented intent: the sign of a*b as +1, -1 or 0. The sign rides in the MSB and is
    // turned into two's complement unless the output is asked for in sign magnitude, which
    // is the encoding the wider reference below uses too.
    function longint signed ref_logmult(input longint signed av, bv);
        longint signed mag;
        reg            sgn;
        begin
            mag = (av == 0 || bv == 0) ? 0 : 1;
            sgn = (mag != 0) && ((av < 0) != (bv < 0));
//;     if OSM:
            ref_logmult = (longint'(sgn) << `OW-1`) | mag;
//;     else:
            if (sgn) mag = -mag;
            ref_logmult = tb_sext(mag, `OW`);
//;     # endif
        end
    endfunction
//; else:
    // documented intent: the log sum, then a shift back to linear if the core takes the
    // antilog. The sign rides in the MSB, and is turned into two's complement unless the
    // output is asked for in sign magnitude.
    function longint signed ref_logmult(input longint signed av, bv);
        longint signed la, lb, lsum, mag;
        reg [`AW-1`:0] ia;   // unsigned index; a size cast would keep av's sign
        reg [`BW-1`:0] ib;
        reg            sgn;
//;     if ZDET:
        reg            zero;
//;     # endif
        begin
            ia   = av[`AW-1`:0];
            ib   = bv[`BW-1`:0];
            la   = longint'(ref_log2a[ia]);
            lb   = longint'(ref_log2b[ib]);
            sgn  = la[`ALOG_MSB`] ^ lb[`BLOG_MSB`];
            lsum = (la & `(1 << ALOG_MSB) - 1`) + (lb & `(1 << BLOG_MSB) - 1`);
//;     if ZDET:
            zero = (av == 0) || (bv == 0);
//;     # endif
//;     if ANTILOG:
            mag  = (64'd1 << lsum) >> `SHIFT`;
//;     else:
            mag  = lsum;
//;     # endif
            mag  = mag & `(1 << (OW-1)) - 1`;
//;     if ZDET:
            if (zero) begin
                mag = 0;
                sgn = 1'b0;
            end
//;     # endif
//;     if OSM:
            ref_logmult = (longint'(sgn) << `OW-1`) | mag;
//;     else:
//;         if OAPPROX:
            if (sgn) mag = ~mag;
//;         else:
            if (sgn) mag = -mag;
//;         # endif
            ref_logmult = tb_sext(mag, `OW`);
//;     # endif
        end
    endfunction
//; # endif

//; if EMIT_ANTILOG:
    // the antilog helper undoes the core's own negate, so the magnitude comes back as it
    // went in and the product is the same one the ANTILOG=1 core would have produced
    function longint signed ref_antilog(input longint signed av, bv);
        longint signed la, lb, lsum, mag;
        reg [`AW-1`:0] ia;   // unsigned index; a size cast would keep av's sign
        reg [`BW-1`:0] ib;
        reg            sgn;
//;     if ZDET:
        reg            zero;
//;     # endif
        begin
            ia   = av[`AW-1`:0];
            ib   = bv[`BW-1`:0];
            la   = longint'(ref_log2a[ia]);
            lb   = longint'(ref_log2b[ib]);
            sgn  = la[`ALOG_MSB`] ^ lb[`BLOG_MSB`];
            lsum = (la & `(1 << ALOG_MSB) - 1`) + (lb & `(1 << BLOG_MSB) - 1`);
//;     if ZDET:
            zero = (av == 0) || (bv == 0);
//;     # endif
//;     if ZDET:
            if (zero) begin
                lsum = 0;
                sgn  = 1'b0;
            end
//;     # endif
            mag = ((64'd1 << lsum) >> `SHIFT`) & `(1 << PW) - 1`;
//;     if OAPPROX:
            if (sgn) mag = ~mag;
//;     else:
            if (sgn) mag = -mag;
//;     # endif
            ref_antilog = tb_sext(mag, `PW`);
        end
    endfunction
//; # endif

    initial begin
//; if not SIGN_ONLY:
        ref_log2a_load;
        ref_log2b_load;
//; # endif
        tb_data_open("`CFG`", "a,b,y,exp");
        for (int i = 0; i < `1 << AW`; i++) begin
            a  = i[`AW-1`:0];
            as = longint'(a);
            for (int j = 0; j < `1 << BW`; j++) begin
                b  = j[`BW-1`:0];
                bs = longint'(b);
//; if ISYM:
                // isym: the caller promises the most negative input never arrives
                if (as == `MIN_A` || bs == `MIN_B`)
                    tb_skip();
                else begin
//; # endif
                y   = dut(a, b);
                exp = ref_logmult(as, bs);
                tb_check(64'(y), exp, $sformatf("a=%0d b=%0d", as, bs));
                tb_data_row($sformatf("%0d,%0d,%0d,%0d", as, bs, y, exp));
//; if EMIT_ANTILOG:
                yp   = dut_antilog(y);
                expp = ref_antilog(as, bs);
                tb_check(64'(yp), expp, $sformatf("antilog a=%0d b=%0d", as, bs));
//; # endif
//; if ISYM:
                end
//; # endif
            end
        end
        tb_report("`CFG`");
        $finish;
    end
endmodule
