//; # Unit test for spec_mux. The reference is the recursion the module implements, stepped
//; # one symbol at a time over the same speculation tables:
//; #
//; #     sym_i = spec_i[state], state = { state[STATE_W-SYM_W-1:0], sym_i }
//; #
//; # That is what look-ahead composition has to reproduce exactly, whatever LOOKAHEAD is, so the
//; # check is the direct chain against the composed one rather than a tolerance.
//; import textwrap
//; from vexpr import idx, lit
//;
//; # Only what a sweep set is forwarded, so a default here cannot drift from the module's.
//; N_SYM     = parameter('N_SYM',     None)
//; PAM_N     = parameter('PAM_N',     None)
//; N_HIST    = parameter('N_HIST',    None)
//; LOOKAHEAD = parameter('LOOKAHEAD', None)
//; PIPE_LA   = parameter('PIPE_LA',   None)
//; UNROLL    = parameter('UNROLL',    None)
//; RST_STATE = parameter('RST_STATE', None)
//; MAX_NETS  = parameter('MAX_NETS',  None)
//; kw  = dict(N_SYM=N_SYM, PAM_N=PAM_N, N_HIST=N_HIST, LOOKAHEAD=LOOKAHEAD, PIPE_LA=PIPE_LA,
//;     UNROLL=UNROLL, RST_STATE=RST_STATE, MAX_NETS=MAX_NETS)
//; dut = unique_inst('spec_mux', 'dut', **{k: v for k, v in kw.items() if v is not None})
//;
//; # every value the model uses comes back from the instance, never from a default above
//; N_SYM       = dut.get_param('N_SYM')
//; PAM_N       = dut.get_param('PAM_N')
//; N_HIST      = dut.get_param('N_HIST')
//; LOOKAHEAD   = dut.get_param('LOOKAHEAD')
//; PIPE_LA     = dut.get_param('PIPE_LA')
//; UNROLL      = dut.get_param('UNROLL')
//; RST_STATE   = dut.get_param('RST_STATE')
//; MAX_NETS    = dut.get_param('MAX_NETS')
//; SYM_W       = dut.get_param('SYM_W')
//; STATE_W     = dut.get_param('STATE_W')
//; N_SPEC      = dut.get_param('N_SPEC')
//; LATENCY     = dut.get_param('LATENCY')
//; CHAIN_DEPTH = dut.get_param('CHAIN_DEPTH')
//;
//; NRAND = parameter('NRAND', 400)  # blocks of seeded random tables
//; SEED  = parameter('SEED',  1)
//; EXH   = parameter('EXH',   0)    # enumerate every table set a block can take
//;
//; RES_W = N_SYM * SYM_W
//; TBL_W = N_SPEC * SYM_W
//; # tb_check compares in a 64-bit longint, so a block wider than that is compared in
//; # chunks of whole symbols, as many as fit a word. One chunk is the whole block until
//; # N_SYM passes that many symbols, so a narrow block is checked exactly as before.
//; CHUNK_SYM = min(N_SYM, 63 // SYM_W)
//; CHUNK_W   = CHUNK_SYM * SYM_W
//; NCHUNK    = -(-N_SYM // CHUNK_SYM)
//; PAD       = NCHUNK * CHUNK_W - RES_W
//; # The exhaustive sweep walks every table set a block can take, which is only tractable
//; # for the narrowest configurations. The cap is on the sweep, not on the module.
//; EXH_MAX = parameter('EXH_MAX', 200000)  # table sets the exhaustive sweep may enumerate
//; NTBL = PAM_N ** N_SPEC
//; NVEC = NTBL ** N_SYM
//; if EXH and NVEC > EXH_MAX:
//;     error(f"{mname}: EXH would enumerate {NVEC} table sets, over EXH_MAX ({EXH_MAX}); "
//;         f"it needs a small PAM_N ({PAM_N}), N_SPEC ({N_SPEC}) and N_SYM ({N_SYM})")
//; # endif
//;
//; def stim(i):
//;     return idx('stim', i, N_SYM, 2)
//; # enddef
//; SEL_W = len(f"spec[{N_SYM - 1}][{N_SPEC - 1}]")
//; CFG  = f"{mname} N_SYM={N_SYM} PAM_N={PAM_N} N_HIST={N_HIST} LOOKAHEAD={LOOKAHEAD}"
//; CFG += f" PIPE_LA={PIPE_LA} UNROLL={UNROLL} RST_STATE={RST_STATE} MAX_NETS={MAX_NETS}"
//; CFG += f" SYM_W={SYM_W}"
//; CFG += f" STATE_W={STATE_W} N_SPEC={N_SPEC} LATENCY={LATENCY} CHAIN_DEPTH={CHAIN_DEPTH}"
//; CFG += f" EXH={EXH} EXH_MAX={EXH_MAX} NRAND={NRAND} SEED={SEED} NCHUNK={NCHUNK}"
// unit test for spec_mux. The tables reach the DUT through one 2-D unpacked array port, so
// the stimulus is held in a packed variable per symbol and gathered into that array by
// continuous assignment: verilator 5.020 raises no event for a procedural write to an
// unpacked-array element, and a task driving spec directly would be read once, at time zero.
// A table entry is always a symbol below PAM_N: the module reads an entry only at a state it
// can reach, and an entry above PAM_N would drive it to a state the reference never visits.
module `mname`;

//; include('tb_util.vpy')

    logic clk   = 1'b0;
    logic reset = 1'b1;
    wire  [`RES_W-1`:0] res;

//; for i in range(N_SYM):
    logic [`TBL_W-1`:0] `stim(i)`;
//; # endfor
    wire  [`SYM_W-1`:0] spec [0:`N_SYM-1`][0:`N_SPEC-1`];
//; for i in range(N_SYM):
//;     for c in range(N_SPEC):
    assign `f"spec[{i}][{c}]".ljust(SEL_W)` = `stim(i)`[`c * SYM_W` +: `SYM_W`];
//;     # endfor
//; # endfor

    always #5 clk = ~clk;

//; conns = ['.res(res)', '.spec(spec)', '.clk(clk)', '.reset(reset)']
    `dut.instantiate()` (
        `textwrap.indent(textwrap.fill(', '.join(conns), 92), ' ' * 8).lstrip()`
    );

    // ------------------------------------------------------------------------- stimulus
    // one packed table per symbol. The drive task copies them into the stimulus variables
    // the gather reads, and never touches spec itself, so the module and the reference read
    // the same numbers by different routes.
    logic [`TBL_W-1`:0] tbl [0:`N_SYM-1`];

    task apply;
        begin
//; for i in range(N_SYM):
            `stim(i)` = tbl[`i`];
//; # endfor
        end
    endtask

    // every entry of every table takes the same symbol
    task fill_flat(input int y);
        begin
            for (int i = 0; i < `N_SYM`; i++)
                for (int c = 0; c < `N_SPEC`; c++)
                    tbl[i][c*`SYM_W` +: `SYM_W`] = `SYM_W`'(y % `PAM_N`);
        end
    endtask

    // entry c takes symbol (c + step) mod PAM_N, so the state walks rather than settling
    task fill_ramp(input int step);
        begin
            for (int i = 0; i < `N_SYM`; i++)
                for (int c = 0; c < `N_SPEC`; c++)
                    tbl[i][c*`SYM_W` +: `SYM_W`] = `SYM_W`'((c + step) % `PAM_N`);
        end
    endtask

    task fill_rand;
        begin
            for (int i = 0; i < `N_SYM`; i++)
                for (int c = 0; c < `N_SPEC`; c++) begin
                    rnd = $random(seed);
                    tbl[i][c*`SYM_W` +: `SYM_W`] = `SYM_W`'(rnd % `PAM_N`);
                end
        end
    endtask

    // -------------------------------------------------------------------- reference model
    logic [`STATE_W-1`:0] ref_state;
    logic [`RES_W-1`:0]   ref_res;
    logic [`RES_W-1`:0]   exp_pipe [0:`LATENCY-1`];
    // the compared copies, widened to a whole number of chunks so the last one is complete
    logic [`NCHUNK * CHUNK_W - 1`:0] res_pad, exp_pad;
    logic [`SYM_W-1`:0]   y;
    int                   k, nblk;
    int unsigned          rnd, seed;
//; if EXH:
    int                   vv, ti;   // the exhaustive sweep's table-set digits
//; # endif

    // one block: N_SYM symbols, each selected by the state the one before it left
    task ref_step;
        begin
            for (int i = 0; i < `N_SYM`; i++) begin
                k = int'(ref_state) * `SYM_W`;
                y = tbl[i][k +: `SYM_W`];
                ref_res[i*`SYM_W` +: `SYM_W`] = y;
//; if N_HIST == 1:
                ref_state = y;
//; else:
                ref_state = { ref_state[`STATE_W-SYM_W-1`:0], y };
//; # endif
            end
        end
    endtask

    // --------------------------------------------------------------------------- cycle
    // tables change after a negedge, so the posedge takes them; #1 lets res settle. A block
    // reaches res `LATENCY` clocks later, so the expected values run through a pipeline of
    // that depth and the first `LATENCY-1` blocks after a reset are not checked.
    task cycle;
        begin
            apply;
            ref_step;
//; for d in reversed(range(1, LATENCY)):
            exp_pipe[`d`] = exp_pipe[`d-1`];
//; # endfor
            exp_pipe[0] = ref_res;
            @(posedge clk);
            #1;
//; if PAD:
            res_pad = {`PAD`'b0, res};
            exp_pad = {`PAD`'b0, exp_pipe[`LATENCY-1`]};
//; else:
            res_pad = res;
            exp_pad = exp_pipe[`LATENCY-1`];
//; # endif
            if (nblk >= `LATENCY-1`)
                for (int w = 0; w < `NCHUNK`; w++)
                    tb_check(64'(res_pad[w*`CHUNK_W` +: `CHUNK_W`]),
                             64'(exp_pad[w*`CHUNK_W` +: `CHUNK_W`]),
                             $sformatf("block %0d symbols %0d..%0d, state in %0d", nblk,
                                       w*`CHUNK_SYM`, w*`CHUNK_SYM` + `CHUNK_SYM-1`, ref_state));
            else
                for (int w = 0; w < `NCHUNK`; w++)
                    tb_skip;
            nblk = nblk + 1;
            @(negedge clk);
        end
    endtask

    task do_reset;
        begin
            fill_flat(0);
            apply;
            reset = 1'b1;
            repeat (2) @(negedge clk);
            reset     = 1'b0;
            ref_state = `lit(RST_STATE, STATE_W, signed=False)`;
            ref_res   = {`RES_W`{1'b0}};
            nblk      = 0;
        end
    endtask

    // The reset is asynchronous, so it must clear res on its own edge rather than at the
    // next posedge. res has to be non-zero first, which a ramp table guarantees.
    task check_async_reset;
        begin
            do_reset;
            fill_ramp(1);
            repeat (`LATENCY + 1`) cycle;
            tb_check(64'(res != 0), 1, "reset setup: res must be non-zero before the pulse");
            #1 reset = 1'b1;
            #1 tb_check(64'(res), 0, "reset must clear res with no clock edge");
            #1 reset = 1'b0;
        end
    endtask

    initial begin
        seed = `SEED`;
        do_reset;
        check_async_reset;

        // a flat table: every symbol decides the same value whatever the history, so the
        // composition must collapse to that value at every look-ahead depth
        for (int v = 0; v < `PAM_N`; v++) begin
            do_reset;
            fill_flat(v);
            repeat (3) cycle;
        end

        // a ramp: the state advances every symbol, so no two positions in the block share
        // a select and the composition is exercised at every level
        for (int v = 0; v < `PAM_N`; v++) begin
            do_reset;
            fill_ramp(v);
            repeat (4) cycle;
        end

        // tables that change every block, with no reset between them: the state carried
        // across the block boundary is the only thing linking one to the next
        do_reset;
        for (int v = 0; v < 8; v++) begin
            fill_ramp(v);
            cycle;
            fill_flat(v);
            cycle;
        end

        // a reset part way through, to show the state restarts at RST_STATE
        fill_rand;
        repeat (3) cycle;
        do_reset;
        fill_rand;
        repeat (3) cycle;

//; if EXH:
        // every table set a block can take, run back to back so the state entering each
        // one is whatever the last one left
        do_reset;
        for (int v = 0; v < `NVEC`; v++) begin
            vv = v;
            for (int i = 0; i < `N_SYM`; i++) begin
                ti = vv % `NTBL`;
                vv = vv / `NTBL`;
                for (int c = 0; c < `N_SPEC`; c++) begin
                    tbl[i][c*`SYM_W` +: `SYM_W`] = `SYM_W`'(ti % `PAM_N`);
                    ti = ti / `PAM_N`;
                end
            end
            cycle;
        end
//; # endif

        // seeded random tables
        do_reset;
        for (int v = 0; v < `NRAND`; v++) begin
            fill_rand;
            cycle;
        end

        tb_report("`CFG`");
        $finish;
    end
endmodule
