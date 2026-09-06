//; from vexpr import lit
//; IW   = parameter('IW',   8)    # input width
//; OW   = parameter('OW',   8)    # output width
//; MW   = parameter('MW',   4)    # mu width
//; ARST = parameter('ARST', 1)    # asynchronous reset
//; EXH   = parameter('EXH',   0)  # run the exhaustive input sweep
//; # Accumulator states the exhaustive sweep must reach. The count is a property of the
//; # configuration, not of the RTL under test, so it is recorded per sweep entry rather
//; # than derived; 0 asks for no floor. Without it the sweep reports its coverage and
//; # nothing reads the number, so a change that halved it would still pass.
//; EXH_MIN = parameter('EXH_MIN', 0)  # accumulator states the sweep must reach
//; NRAND = parameter('NRAND', 2000)
//; SEED  = parameter('SEED',  1)
//; LSB    = 1 << MW                # fractional bits held below the input's LSB
//; W      = IW + LSB               # full accumulator width
//; OSHIFT = LSB + IW - OW          # accumulator bits dropped to form out
//; dut    = unique_inst('iir', 'dut', IW=IW, OW=OW, MW=MW, ARST=ARST)
//; IMIN   = -(1 << (IW-1))
//; IMAX   =  (1 << (IW-1)) - 1
//; NSTATE = 1 << W
//; MU_MAX = (1 << MW) - 1
//; # The reference walks the accumulator in a 64-bit longint. It has to be exact where the
//; # module's own W bits are not, so it needs a bit more than the module, and every
//; # 64'sd1 << k it builds has to stay positive.
//; if MW > 5:
//;     error(f"{mname}: MW ({MW}) must be <= 5; the reference shifts by mu+2, up to {MU_MAX+2}")
//; # endif
//; if W > 63:
//;     error(f"{mname}: IW+2**MW ({W}) must be <= 63; the 64-bit reference needs a spare bit")
//; # endif
//; OSTEP  = (IMAX * (1 << LSB)) >> OSHIFT   # out for an accumulator holding IMAX
//; MU_LO  = min(1, MU_MAX)                  # directed mu values, clamped to fit MW
//; MU_MID = min(2, MU_MAX)
//; MU_HI  = min(3, MU_MAX)
//; N_MU   = MU_MAX                             # mu is constrained to 1..MU_MAX
//; NVEC   = (1 << IW) * N_MU * 4 * 2           # in, mu, mf, en
//; EXH_HOLD = parameter('EXH_HOLD', 0)        # clocks one vector is held; 0 = derive
//; HOLD   = EXH_HOLD if EXH_HOLD > 0 else (W << MU_MAX)   # settling takes ~0.7*(W-mu)*2**mu
//; if EXH and NVEC * HOLD > 2000000:
//;     error(f"{mname}: EXH=1 needs a smaller configuration or an explicit EXH_HOLD; {NVEC*HOLD} clocks")
//; # endif
//; if EXH and W > 22:
//;     error(f"{mname}: EXH=1 needs a smaller accumulator; {NSTATE} states to track")
//; # endif
//; CFG  = f"{mname} IW={IW} OW={OW} MW={MW} ARST={ARST} W={W}"
//; CFG += f" EXH={EXH} EXH_HOLD={EXH_HOLD} EXH_MIN={EXH_MIN}"
//; CFG += f" NRAND={NRAND} SEED={SEED}"
// unit test for iir. The reference is written from the intended behaviour: the filter
// factor is 2**-mu * (1 + mf[1]/2 + mf[0]/4), each of the six shifted terms floors on its
// own, and the accumulator never wraps. The module constrains mu > 0, so mu=0 is operator
// error and is never driven. Every mu the module allows keeps the factor at or below 1,
// which is what makes the no-wrap claim hold.
module `mname`;

//; include('tb_util.vpy')

    logic                   clk = 1'b0;
    logic                   reset = 1'b1;
    logic signed [`IW-1`:0] in;
    logic        [`MW-1`:0] mu;
    logic        [1:0]      mf;
    logic                   en;
    wire  signed [`OW-1`:0] out;

    always #5 clk = ~clk;

    `dut.instantiate()` (
        .out(out), .in(in), .mu(mu), .mf(mf), .en(en), .clk(clk), .reset(reset)
    );

    // ---------------------------------------------------------------- reference model
    longint signed ref_acc;

    function longint signed ref_out;
        ref_out = fdiv(ref_acc, 64'sd1 << `OSHIFT`);
    endfunction

    // one clock of the intended behaviour. Both sums are exact, so an accumulator too
    // narrow to hold the result shows up as a mismatch rather than being reproduced here.
    task ref_step(input longint signed i, input int m, input logic [1:0] mfv,
                  input logic enb);
        longint signed iraw, isum, asum;
        begin
            iraw = i * (64'sd1 << `LSB`);
            isum = fdiv(iraw,    64'sd1 << m);
            asum = fdiv(ref_acc, 64'sd1 << m);
            if (mfv[1]) begin
                isum = isum + fdiv(iraw,    64'sd1 << (m + 1));
                asum = asum + fdiv(ref_acc, 64'sd1 << (m + 1));
            end
            if (mfv[0]) begin
                isum = isum + fdiv(iraw,    64'sd1 << (m + 2));
                asum = asum + fdiv(ref_acc, 64'sd1 << (m + 2));
            end
            if (enb) ref_acc = (ref_acc - asum) + isum;
        end
    endtask

    // ------------------------------------------------------------------ tier scratch
    longint          vec, vfield, vin, vmu, vmf, ven;
    longint signed   prev_out;
    int              nseen, rnd, seed, sidx;
//; if EXH:
    bit              seen [0:`NSTATE-1`];
    longint signed   prev_acc;
    int              hold, nheld;
//; # endif

    // ---------------------------------------------------------------------- stimulus
    // One clock. The inputs standing now are taken by the posedge; the reference is then
    // stepped and compared. Ends just after the following negedge so the caller can set
    // the next inputs immediately. Nothing else in this testbench waits on the clock, so
    // no edge can pass without the reference stepping with it.
    task cycle;
        begin
            @(posedge clk);
            #1;
            ref_step(longint'(in), int'(mu), mf, en);
            tb_check(64'(out), ref_out(),
                     $sformatf("in=%0d mu=%0d mf=%0b en=%0b", in, mu, mf, en));
            @(negedge clk);
        end
    endtask

    task do_reset;
        begin
            reset = 1'b1;
            in = '0; mu = '0; mf = '0; en = 1'b1;
            repeat (2) @(negedge clk);
            reset = 1'b0;
            ref_acc = 0;
        end
    endtask

    // do_reset holds reset across two clock edges, where an asynchronous and a synchronous
    // reset reach the same state and are indistinguishable. This pulses it between edges
    // and samples before the next posedge: ARST=1 must have cleared the output by then,
    // ARST=0 must not have touched it. Needs a non-zero accumulator to see anything, hence
    // the run-up first.
    task check_arst;
        longint signed pre;
        begin
            // the most negative input, so out settles on -2**(OW-1) and is non-zero for
            // every output width, down to the one-bit output whose only values are 0 and -1
            in = `IMIN`; mu = `lit(MU_LO, MW, signed=False)`; mf = '0; en = 1'b1;
            repeat (`W + 8`) cycle;
            pre = longint'(out);
            tb_check(64'(pre != 0), 1, "reset-pulse setup: out must be non-zero");
            #1 reset = 1'b1;
//; if ARST:
            #1 tb_check(64'(out), 0, "arst: reset must clear out with no clock edge");
//; else:
            #1 tb_check(64'(out), pre, "sync reset: out must not change between clock edges");
//; # endif
            #1 reset = 1'b0;
        end
    endtask

    initial begin
        do_reset;
        tb_check(64'(out), 0, "reset clears the output");

        // impulse at a mid factor, then coast back toward zero
        in = `IMAX`; mu = `lit(MU_MID, MW, signed=False)`;
        cycle;
        in = '0;
        repeat (12) cycle;

        // step response: from reset, a constant non-negative input drives the output up
        // monotonically and never past the input
        do_reset;
        in = `IMAX`; mu = `lit(MU_HI, MW, signed=False)`;
        prev_out = 0;
        repeat (40) begin
            cycle;
            tb_check(64'(longint'(out) >= prev_out), 1, "step response must not fall");
            tb_check(64'(longint'(out) <= `OSTEP`), 1,
                     "step response must not overshoot the input");
            prev_out = longint'(out);
        end

        // en low holds the output
        in = `IMIN`; en = 1'b0;
        repeat (4) cycle;

        // reset pulsed between clock edges
        do_reset;
        check_arst;

        // every fractional factor at a fixed mu
        do_reset;
        in = `IMAX`; mu = `lit(MU_MID, MW, signed=False)`;
        for (int k = 0; k < 4; k++) begin
            mf = k[1:0];
            repeat (6) cycle;
        end

        // every mu the module allows
        do_reset;
        in = `IMIN`; mf = '0;
        for (int k = 1; k <= `MU_MAX`; k++) begin
            mu = k[`MW-1`:0];
            repeat (4) cycle;
        end

        // reset partway through a run
        in = `IMAX`; mu = `lit(MU_LO, MW, signed=False)`; mf = 2'b11;
        repeat (6) cycle;
        do_reset;
        tb_check(64'(out), 0, "reset clears the output mid-run");

//; if EXH:
        // every input vector, each held until the reference stops moving. The filter
        // converges toward its input, so the states at the two ends of the range are
        // reached only by a vector that stands for the whole transient; one vector per
        // clock, in any order, walks the middle of the range and settles into a cycle.
        // The reference owns the accumulator, so its value also serves as the state count.
        do_reset;
        nheld = 0;
        for (vec = 0; vec < `NVEC`; vec++) begin
            vfield = vec;
            vin    = vfield % `1 << IW`;        vfield = vfield / `1 << IW`;
            ven    = vfield % 2;                vfield = vfield / 2;
            vmf    = vfield % 4;                vfield = vfield / 4;
            vmu    = vfield + 1;                // mu is constrained to 1..MU_MAX
            in = vin[`IW-1`:0];
            mu = vmu[`MW-1`:0];
            mf = vmf[1:0];
            en = ven[0];
            prev_acc = ~ref_acc;                // force the first clock of every vector
            hold     = 0;
            while (ref_acc != prev_acc && hold < `HOLD`) begin
                prev_acc = ref_acc;
                cycle;
                sidx = int'(ref_acc & `NSTATE-1`);
                seen[sidx] = 1'b1;
                hold = hold + 1;
            end
            if (ref_acc != prev_acc) nheld = nheld + 1;
        end
        nseen = 0;
        for (int st = 0; st < `NSTATE`; st++) if (seen[st]) nseen = nseen + 1;
        // an unsettled vector is one the hold bound cut short: coverage below is then a
        // property of the bound, not of the module
        $display("  exhaustive: %0d vectors, %0d of %0d accumulator states visited, %0d unsettled",
                 `NVEC`, nseen, `NSTATE`, nheld);
        tb_check(64'(nheld), 0, "exhaustive: every vector must settle inside the hold bound");
        tb_check(64'(nseen >= `EXH_MIN`), 1,
                 $sformatf("exhaustive: %0d accumulator states, need %0d", nseen, `EXH_MIN`));
//; # endif

        // seeded random walk, biased so the filter mostly runs rather than being held
        do_reset;
        seed = `SEED`;
        for (int k = 0; k < `NRAND`; k++) begin
            rnd = $random(seed); in = rnd[`IW-1`:0];
            rnd = $random(seed); mu = rnd[`MW-1`:0];
            rnd = $random(seed); mf = rnd[1:0];
            if (mu == 0) mu = `lit(MU_LO, MW, signed=False)`;    // mu=0 is operator error, never driven
            rnd = $random(seed); en = (rnd[2:0] != 3'd0);
            cycle;
        end

        tb_report("`CFG`");
        $finish;
    end
endmodule
