//; from vexpr import lit
//; OW   = parameter('OW', 8)    # output width
//; IW   = parameter('IW', 4)    # input width
//; MW   = parameter('MW', 4)    # mu width
//; dut  = unique_inst('intg', 'dut', OW=OW, IW=IW, MW=MW)
//; AW   = dut.get_param('AW')
//; LW   = dut.get_param('LW')
//; ISYM = dut.get_param('ISYM')
//; NAPX = dut.get_param('NEG_APPROX')
//; DBG  = dut.get_param('DEBUG')
//; IMIN = -(1 << (IW-1))                    # most negative input
//; OMIN = -(1 << (OW-1))                    # most negative output
//; RAIL = -((1 << (OW-1)) - 1)              # output at the accumulator's clamp
//; IMAX = (1 << (IW-1)) - 1                 # most positive input
//; OMAX = (1 << (OW-1)) - 1                 # most positive output
//; LDV  = OMAX // 2                         # a load value well inside the range
//; LIMV = max(1, OMAX // 4)                 # a limit the ramp runs past
//; EXH   = parameter('EXH',   0)            # run the exhaustive input sweep
//; # Accumulator states the exhaustive sweep must reach. The count is a property of the
//; # configuration, not of the RTL under test, so it is recorded per sweep entry rather
//; # than derived; 0 asks for no floor. Without it the sweep reports its coverage and
//; # nothing reads the number, so a change that halved it would still pass.
//; EXH_MIN = parameter('EXH_MIN', 0)        # accumulator states the sweep must reach
//; NRAND = parameter('NRAND', 2000)         # cycles of seeded random stimulus
//; SEED  = parameter('SEED',  1)
//; if MW < 2:
//;     error(f"{mname}: MW ({MW}) must be >= 2; lk_mu > mu > 0 needs two values above zero")
//; # endif
//; MU_MAX = (1 << MW) - 1
//; # The reference walks the accumulator in a 64-bit longint. It has to be exact where the
//; # module's own AW bits are not, so it needs a bit more than the module, and every
//; # 64'sd1 << k it builds has to stay positive.
//; if MW > 5:
//;     error(f"{mname}: MW ({MW}) must be <= 5; the reference shifts by lk_mu, up to {MU_MAX}")
//; # endif
//; if AW > 63:
//;     error(f"{mname}: AW ({AW}) must be <= 63; the 64-bit reference needs a spare bit")
//; # endif
//; MU_LO  = 1                               # smallest legal mu, and the leak shift above it
//; LK_LO  = 2
//; PAIRS  = [(m, l) for m in range(1, MU_MAX) for l in range(m + 1, MU_MAX + 1)]
//; N_PAIR = len(PAIRS)                      # exhaustive field counts
//; N_LIM = 1 << (OW-1)                      # lim is a magnitude, never negative
//; N_LD  = 1 << OW
//; N_F   = 16                               # lk_en, ld, en, neg
//; N_IN  = (1 << IW) - 1 if ISYM else (1 << IW)  # ISYM bars the most negative input
//; NVEC  = N_IN * N_PAIR * N_LIM * N_LD * N_F
//; NSTATE = 1 << AW
//; if EXH and NVEC > 2000000:
//;     error(f"{mname}: EXH=1 needs a smaller configuration; {NVEC} input vectors")
//; # endif
//; if EXH and AW > 22:
//;     error(f"{mname}: EXH=1 needs a smaller AW; {NSTATE} states to track")
//; # endif
//; ASCL = 1 << (AW-OW)                      # accumulator units per output unit
//; AMAX =  ((1 << (OW-1)) - 1) * ASCL
//; AMIN = -((1 << (OW-1)) - 1) * ASCL
//; ACAP =  (1 << (AW-1)) - 1                # largest value AW bits hold
//; AFLR = -(1 << (AW-1))
//; CFG  = f"{mname} OW={OW} IW={IW} MW={MW} AW={AW} LW={LW} ISYM={ISYM}"
//; CFG += f" NEG_APPROX={NAPX} DEBUG={DBG} EXH={EXH} EXH_MIN={EXH_MIN}"
//; CFG += f" NRAND={NRAND} SEED={SEED}"
// unit test for intg. The reference is written from the intended behaviour, not from the
// RTL: load wins over enable, the limit clamps a load, lim is a magnitude and is never
// driven negative, and the accumulator saturates to the symmetric output range. The module
// constrains lk_mu > mu > 0; driving outside that is operator error and is never done here.
module `mname`;

//; include('tb_util.vpy')

    logic                   clk = 1'b0;
    logic                   reset = 1'b1;
    logic signed [`IW-1`:0] in;
    logic signed [`OW-1`:0] ld_val;
    logic signed [`OW-1`:0] lim;
    logic        [`MW-1`:0] mu;
    logic        [`MW-1`:0] lk_mu;
    logic                   lk_en, ld, en, neg;
    wire  signed [`OW-1`:0] out;

    always #5 clk = ~clk;

    `dut.instantiate()` (
        .out(out), .in(in), .ld_val(ld_val), .mu(mu), .lk_mu(lk_mu), .lim(lim),
        .lk_en(lk_en), .ld(ld), .en(en), .neg(neg), .clk(clk), .reset(reset)
    );

    // ---------------------------------------------------------------- reference model
    longint signed ref_accum;

    // map the most negative value one step up, so the result negates without overflowing
    function longint signed ref_sym(input longint signed x, input integer w);
        if (x == -(64'sd1 << (w-1))) ref_sym = -(64'sd1 << (w-1)) + 1;
        else                         ref_sym = x;
    endfunction

    // negate. isym says the caller promises x is never the most negative value; without
    // that promise the most negative input saturates rather than wrapping. The
    // approximate form drops the +1 and so lands one below the true negation.
    function longint signed ref_negate(input longint signed x, input integer w,
                                       input logic isym);
        longint signed mn;
        begin
            mn = -(64'sd1 << (w-1));
//; if NAPX:
            ref_negate = -x - 1;
//; else:
            if (!isym && x == mn) ref_negate = -(mn + 1);
            else                  ref_negate = -x;
//; # endif
        end
    endfunction

    function longint signed ref_out;
        ref_out = fdiv(ref_accum, `ASCL`);
    endfunction

    // one clock of the intended behaviour. The sum is exact, so an RTL sum too narrow to
    // hold it shows up as a mismatch rather than being reproduced here.
    task ref_step(input longint signed i, ld_v, lim_v, input int m, lm,
                  input logic lke, ldb, enb, negb);
        longint signed insym, v, fb, ifb, top, ilkfb, sum, nxt, onxt;
        begin
//; if ISYM:
            insym = i;
//; else:
            insym = ref_sym(i, `IW`);
//; # endif
            if (negb) v = ref_negate(insym, `IW`, 1'b1);
            else      v = insym;
            fb  = v * `1 << (AW-IW)`;
            ifb = fdiv(fb, 64'sd1 << m);

            top = fdiv(ref_accum, `1 << (AW-LW)`);
            if (lke) ilkfb = fdiv(ref_negate(top, `LW`, 1'b0) * `1 << (AW-LW)`, 64'sd1 << lm);
            else     ilkfb = 0;

            sum = ref_accum + ifb + ilkfb;
            if      (sum > `ACAP`) nxt = `AMAX`;
            else if (sum < `AFLR`) nxt = `AMIN`;
            else                   nxt = sum;

            if (ldb) nxt = ld_v * `ASCL`;

            onxt = fdiv(nxt, `ASCL`);
            if (lim_v != 0 && onxt < -lim_v) nxt = (-lim_v) * `ASCL`;
            if (lim_v != 0 && onxt >  lim_v) nxt = lim_v * `ASCL`;

            if (ldb || enb) ref_accum = nxt;
        end
    endtask

    // ------------------------------------------------------------------ tier scratch
    longint          vec, vfield;
    longint          vin, vpair, vmu, vlk, vlim, vld, vf;
    longint signed   rail_out;
    int              nseen, rnd, seed, sidx, rmu, rlk;
//; if EXH:
    bit              seen [0:`NSTATE-1`];
//; # endif

    // ---------------------------------------------------------------------- stimulus
    // inputs change after a negedge, so the posedge takes them; #1 lets out settle. cycle
    // ends at the following negedge, so it returns where the caller can drive the next
    // vector with no edge wait of its own -- the same convention tb_iir uses.
    task cycle;
        begin
            @(posedge clk);
            #1;
            ref_step(longint'(in), longint'(ld_val), longint'(lim),
                     int'(mu), int'(lk_mu), lk_en, ld, en, neg);
            tb_check(64'(out), ref_out(),
                     $sformatf("in=%0d mu=%0d lk_mu=%0d lk_en=%0b ld=%0b ld_val=%0d en=%0b neg=%0b lim=%0d",
                               in, mu, lk_mu, lk_en, ld, ld_val, en, neg, lim));
            @(negedge clk);
        end
    endtask

    task idle;
        begin
            in = '0; ld_val = '0; lim = '0; mu = `lit(MU_LO, MW, signed=False)`; lk_mu = `lit(LK_LO, MW, signed=False)`;
            lk_en = 1'b0; ld = 1'b0; en = 1'b1; neg = 1'b0;
        end
    endtask

    task do_reset;
        begin
            idle;
            reset = 1'b1;
            repeat (2) @(negedge clk);
            reset = 1'b0;
            ref_accum = 0;
        end
    endtask

    // The reset is asynchronous, so it must clear the output on its own edge. do_reset
    // holds it across two clock edges, which a synchronous reset satisfies just as well;
    // this pulses it between edges and samples before the next posedge, where only an
    // asynchronous reset has taken effect. Needs a non-zero accumulator to see anything,
    // hence the load.
    task check_arst;
        begin
            ld = 1'b1; ld_val = `OMAX`;
            cycle;
            ld = 1'b0;
            tb_check(64'(out != 0), 1, "arst setup: the load must leave out non-zero");
            #1 reset = 1'b1;
            #1 tb_check(64'(out), 0, "arst: reset must clear out with no clock edge");
            #1 reset = 1'b0;
        end
    endtask

    initial begin
        do_reset;
        check_arst;

        // impulse, then coast
        do_reset;
        in = 1;
        cycle;
        in = '0;
        repeat (3) cycle;

        // ramp across the whole input range at a mid shift
        for (int i = `IMIN`; i <= `IMAX`; i++) begin
            in = i[`IW-1`:0]; mu = `lit(2, MW, signed=False)`;
            cycle;
        end

        // en low holds the accumulator
        in = `IMAX`; en = 1'b0;
        repeat (3) cycle;

        // drive into the positive clamp, then out again with neg
        do_reset;
        in = `IMAX`;
        repeat (8) cycle;
        neg = 1'b1;
        repeat (8) cycle;

        // A -- the leak must move the accumulator off the saturated negative state.
        // Where that state sits depends on the widths, so record it rather than assume it.
        do_reset;
        in = `IMIN`;
        repeat (4) cycle;
        rail_out = longint'(out);
        tb_check(64'(rail_out < 0), 1, "A setup: saturated negative");
        in = '0; lk_en = 1'b1;
        cycle;
        tb_check(64'(longint'(out) > rail_out), 1, "A: the leak must move out toward zero");
        repeat (3) cycle;

        // B -- a negative input into a negative accumulator must stay negative
        do_reset;
        ld = 1'b1; ld_val = `OMIN`;
        cycle;
        ld = 1'b0; in = `IMIN`; lk_en = 1'b1;
        cycle;
        tb_check(64'(out < 0), 1, "B: a negative input and leak must not make out positive");

        // load, with and without enable
        do_reset;
        ld = 1'b1; ld_val = `LDV`;
        cycle;
        ld = 1'b1; ld_val = -`LDV`; en = 1'b0;
        cycle;

        // limit holds the output, and clamps a load that jumps past it
        do_reset;
        in = `IMAX`; lim = `LIMV`;
        repeat (6) cycle;
        in = '0; ld = 1'b1; ld_val = `OMAX`;
        cycle;

        // both shifts at their extremes, as far apart as lk_mu > mu allows
        do_reset;
        in = `IMAX`; mu = `lit(MU_MAX - 1, MW, signed=False)`;
        repeat (4) cycle;
        in = '0; lk_en = 1'b1; lk_mu = `lit(MU_MAX, MW, signed=False)`;
        repeat (4) cycle;

//; if EXH:
        // every input vector, against whatever state the walk has reached by then. The
        // reference owns the accumulator, so its value also serves as the state count.
        do_reset;
        for (vec = 0; vec < `NVEC`; vec++) begin
            vfield = vec;
            vf   = vfield % `N_F`;   vfield = vfield / `N_F`;
            vld  = vfield % `N_LD`;  vfield = vfield / `N_LD`;
            vlim = vfield % `N_LIM`; vfield = vfield / `N_LIM`;
            vpair = vfield % `N_PAIR`; vfield = vfield / `N_PAIR`;
            vin  = vfield;
            // the legal (mu, lk_mu) pairs, enumerated at generation
            case (vpair)
//;     for k, (pm, pl) in enumerate(PAIRS):
                `k`: begin vmu = `pm`; vlk = `pl`; end
//;     # endfor
                default: begin vmu = `MU_LO`; vlk = `LK_LO`; end
            endcase
//;     if ISYM:
            // step over the most negative pattern: ISYM promises it is never driven
            if (vin >= `1 << (IW-1)`) vin = vin + 1;
//;     # endif
            in     = vin[`IW-1`:0];
            mu     = vmu[`MW-1`:0];
            lk_mu  = vlk[`MW-1`:0];
            lim    = vlim[`OW-1`:0];
            ld_val = vld[`OW-1`:0];
            lk_en  = vf[0]; ld = vf[1]; en = vf[2]; neg = vf[3];
            cycle;
            sidx = int'(ref_accum & `NSTATE-1`);
            seen[sidx] = 1'b1;
        end
        nseen = 0;
        for (int st = 0; st < `NSTATE`; st++) if (seen[st]) nseen = nseen + 1;
        $display("  exhaustive: %0d vectors, %0d of %0d accumulator states visited",
                 `NVEC`, nseen, `NSTATE`);
        tb_check(64'(nseen >= `EXH_MIN`), 1,
                 $sformatf("exhaustive: %0d accumulator states, need %0d", nseen, `EXH_MIN`));
//; # endif

        // seeded random walk, biased so the accumulator mostly integrates rather than
        // being reloaded or held
        do_reset;
        seed = `SEED`;
        for (int k = 0; k < `NRAND`; k++) begin
            rnd    = $random(seed); in     = rnd[`IW-1`:0];
//; if ISYM:
            if (in == `IMIN`) in = `IMIN + 1`;
//; # endif
            // mu in 1..MU_MAX-1, then lk_mu above it
            rnd    = $random(seed); rmu    = 1 + int'(rnd[`MW-1`:0]) % `MU_MAX - 1`;
            rnd    = $random(seed); rlk    = rmu + 1 + int'(rnd[`MW-1`:0]) % (`MU_MAX` - rmu);
            mu     = rmu[`MW-1`:0];
            lk_mu  = rlk[`MW-1`:0];
            rnd    = $random(seed); lim    = {1'b0, rnd[`OW-2`:0]};
            rnd    = $random(seed); ld_val = rnd[`OW-1`:0];
            rnd    = $random(seed);
            lk_en  = rnd[6];
            neg    = rnd[7];
            ld     = (rnd[2:0] == 3'd0);
            en     = (rnd[5:3] != 3'd0);
            cycle;
        end

        tb_report("`CFG`");
        $finish;
    end
endmodule
