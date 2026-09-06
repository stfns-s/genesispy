//; # Speculative decision multiplexer loop, resolved by look-ahead.
//; #
//; # A slicer array outside this module decides, for every assumed history, the symbol it
//; # would return. This module selects the right one for each of N_SYM symbols per clock,
//; # where the selection for one symbol supplies the history for the next:
//; #
//; #     sym_i   = spec_i[state_{i-1}]
//; #     state_i = { state_{i-1}[STATE_W-SYM_W-1:0], sym_i }
//; #
//; # Written that way a block costs N_SYM selects in series. Look-ahead creates LOOKAHEAD+1
//; # consecutive tables into one indexed by state_{i-LOOKAHEAD-1}, so the recursion is
//; # ceil(N_SYM/(LOOKAHEAD+1)) selects deep instead. The tables are composed newest first, in
//; # Parhi's order: the composition of tables k..i is the composition of k+1..i indexed by the
//; # entry table k holds, so every level is one PAM_N-to-1 select per entry and the overhead is
//; # linear in LOOKAHEAD. The composition reads only module inputs, so it is feed-forward;
//; # PIPE_LA registers it and takes its LOOKAHEAD levels off the path as well.
//; #
//; #   K. K. Parhi, "Pipelining of parallel multiplexer loops and decision feedback
//; #   equalizers," Proc. ICASSP 2004, vol. 5, pp. V-21-V-24.
//; #   K. K. Parhi, "Design of multigigabit multiplexer-loop-based decision feedback
//; #   equalizers," IEEE Trans. VLSI Syst., vol. 13, no. 4, pp. 489-493, Apr. 2005.
//; import qfmt
//; from vexpr import decl, idx, lit
//;
//; # parameters
//; N_SYM     = parameter('N_SYM',     32)     # symbols resolved per clock
//; PAM_N     = parameter('PAM_N',     4)      # symbol levels: 2..16
//; N_HIST    = parameter('N_HIST',    1)      # past symbols the selection is made on
//; LOOKAHEAD = parameter('LOOKAHEAD', 2)      # look-ahead depth; 0 is the plain chain
//; PIPE_LA   = parameter('PIPE_LA',   0)      # register the composed tables: 0/1
//; UNROLL    = parameter('UNROLL',    1)      # 0 rolls the tables into genvar loops: 0/1
//; RST_STATE = parameter('RST_STATE', 0)      # state held out of reset
//; MAX_NETS  = parameter('MAX_NETS',  65536)  # cap on composed table entries
//;
//; # checks: the derived sizes come after the parameters they are derived from are known good
//; if not 2 <= PAM_N <= 16:
//;     error(f"{mname}: PAM_N ({PAM_N}) must be in 2..16")
//; # endif
//; if N_HIST < 1:
//;     error(f"{mname}: N_HIST ({N_HIST}) must be >= 1")
//; # endif
//; if N_SYM < 1:
//;     error(f"{mname}: N_SYM ({N_SYM}) must be >= 1")
//; # endif
//; if not 0 <= LOOKAHEAD <= N_SYM - 1:
//;     error(f"{mname}: LOOKAHEAD ({LOOKAHEAD}) must be in 0..{N_SYM - 1}, one less than "
//;         f"N_SYM ({N_SYM})")
//; # endif
//; SYM_W   = qfmt.clog2(PAM_N)
//; STATE_W = SYM_W * N_HIST
//; N_SPEC  = 1 << STATE_W
//; HI_W    = STATE_W - SYM_W
//; if not 0 <= RST_STATE < N_SPEC:
//;     error(f"{mname}: RST_STATE ({RST_STATE}) must be in 0..{N_SPEC - 1}")
//; # endif
//;
//; # derivation. Symbol i selects from the composition of tables first[i]..i, entered at the
//; # state symbol first[i]-1 left; a symbol no deeper than LOOKAHEAD composes from the state the
//; # block started in, since a longer look-back would leave the block. The composition is built
//; # from the symbol's own table outward, one table range k..i per level, and is not shared
//; # with any other symbol. Range i..i is spec[i] itself and is not emitted.
//; first = [max(0, i - LOOKAHEAD) for i in range(N_SYM)]
//; pairs = [(k, i) for i in range(N_SYM) for k in range(i - 1, first[i] - 1, -1)]
//; N_ENTRIES = len(pairs) * N_SPEC
//; if N_ENTRIES > MAX_NETS:
//;     error(f"{mname}: {N_ENTRIES} composed table entries exceed MAX_NETS ({MAX_NETS}); "
//;         f"raise MAX_NETS, or lower N_SYM ({N_SYM}), LOOKAHEAD ({LOOKAHEAD}) or "
//;         f"N_SPEC ({N_SPEC})")
//; # endif
//; depth = [0] * N_SYM
//; for i in range(N_SYM):
//;     depth[i] = 1 if first[i] == 0 else depth[first[i] - 1] + 1
//; # endfor
//; CHAIN_DEPTH = max(depth)
//; COMP_DEPTH  = 0 if PIPE_LA else LOOKAHEAD
//; LATENCY     = 2 if PIPE_LA else 1
//; # A symbol that enters its table at another symbol's state makes the symbol array refer to
//; # itself through the state wiring. Verilator resolves that at whole-array granularity and
//; # cannot see that element i reads only elements before first[i], so it reports UNOPTFLAT.
//; # The waiver goes on the declaration, and is left out where no symbol looks back inside the
//; # block. The state array refers to itself the same way, each state holding the one before
//; # it shifted, and rolled, so does the table array, one composition level reading the one
//; # before.
//; SELF_REF  = any(f > 0 for f in first)
//; STATE_REF = N_HIST > 1 and N_SYM > 1
//;
//; # helpers: the emitted name families, and the entry a symbol's select reads
//; IDX_W = 2
//; def comp(k, i):
//;     return f"{idx('comp', k, N_SYM, IDX_W)}_{idx('', i, N_SYM, IDX_W)}"
//; # enddef
//; def state(i):
//;     return 'state_prev' if i < 0 else f"state[{i}]"
//; # enddef
//; # the composed table symbol i selects from: spec[i] itself when it composes nothing
//; def composed(i):
//;     return f"spec[{i}]" if first[i] == i else comp(first[i], i)
//; # enddef
//; def table(i):
//;     return f"ptab[{i}]" if PIPE_LA else composed(i)
//; # enddef
//; # the state a symbol reaches: the previous state shifted up, the new symbol below it. The
//; # same shape indexes the next newer table in a composition, with the entry's own index as
//; # the previous state.
//; def nxt(hi, sym):
//;     return sym if N_HIST == 1 else f"{{ {hi}, {sym} }}"
//; # enddef
//;
//; # publish what a parent generator would otherwise derive again
//; parameter('SYM_W',       SYM_W,       force=True)
//; parameter('STATE_W',     STATE_W,     force=True)
//; parameter('N_SPEC',      N_SPEC,      force=True)
//; parameter('LATENCY',     LATENCY,     force=True)
//; parameter('CHAIN_DEPTH', CHAIN_DEPTH, force=True)
//; parameter('COMP_DEPTH',  COMP_DEPTH,  force=True)
//; parameter('N_ENTRIES',   N_ENTRIES,   force=True)
//;
//; # RTL: the column widths are measured before any text is written
//; GUARD      = f"__{mname.upper()}__"
//; RES_W      = N_SYM * SYM_W
//; XDIM       = f"[0:{N_SYM - 1}][0:{N_SPEC - 1}]"
//; port_decls = [decl(RES_W, signed=False), decl(SYM_W, signed=False)]
//; port_w     = max(len(d) for d in port_decls)
//; body_decls = [decl(STATE_W, signed=False), decl(SYM_W, signed=False), decl(RES_W, signed=False)]
//; decl_w     = max(len(d) for d in body_decls)
//; names      = ['state', 'state_prev', 'sym', 'resnxt', 'ptab', 'comp']
//; if UNROLL:
//;     names += [comp(k, i) for k, i in pairs]
//;     # every continuous assignment writes one table entry, so the targets share one column
//;     lhs_w = max(len(n) for n in names) + 2 + len(str(N_SPEC - 1))
//; # endif
//; name_w     = max(len(n) for n in names)
//; regs       = ['res', 'state_prev'] + (['prime'] if PIPE_LA else [])
//; reg_w      = max(len(r) for r in regs)
\`ifndef `GUARD`
\`define `GUARD`
// speculative decision multiplexer loop with look-ahead, after Parhi (ICASSP 2004,
// TVLSI 2005). `N_SYM` symbols per clock, PAM-`PAM_N` at `SYM_W` bits, `N_HIST` history
// symbol`'' if N_HIST == 1 else 's'`, so `N_SPEC` speculations over a `STATE_W`-bit state.
// look-ahead `LOOKAHEAD`: `CHAIN_DEPTH` selects on the recursive path, `COMP_DEPTH` ahead of it,
// `len(pairs)` tables of `N_SPEC` entries, latency `LATENCY`.
module `mname` (
        output reg  `decl(RES_W, signed=False).ljust(port_w)` res,
        input  wire `decl(SYM_W, signed=False).ljust(port_w)` spec `XDIM`,
        input  wire `' ' * port_w` clk,
        input  wire `' ' * port_w` reset
    );

    // the state the block starts in, carried over from the block before it
    reg  `decl(STATE_W, signed=False).ljust(decl_w)` state_prev;
//; if PIPE_LA:
    // a registered composition is one block behind, so the first block out of reset runs on
    // the reset tables. prime holds the state over it, leaving res meaningless for that one
    // cycle and the state at RST_STATE for the first real block.
    reg  `' ' * decl_w` prime;
//; # endif

//; # the compositions, one per table range some symbol's chain passes through. A table is an
//; # array of N_SPEC entries, indexed by the state the composition is entered at, holding the
//; # symbol the newest table returns from there. Rolled, they are one array indexed by [i][d],
//; # tables i-d..i, under genvar loops; unrolled, one array per range and one assignment per
//; # entry. Unrolled keeps the rolled text above it as a comment, so the shape of what follows
//; # is legible without generating the other form. ROLL prefixes it.
//; hi_c = f"c[{HI_W - 1}:0]" if HI_W else ''
//; cdim = f"[0:{N_SYM - 1}][0:{LOOKAHEAD}][0:{N_SPEC - 1}]"
//; ROLL = '// ' if UNROLL else ''
//; if UNROLL:
    // the compositions. UNROLL=0 emits them as the loops commented out here, in place of
    // the arrays and assignments that follow.
//; else:
    // the compositions, comp[i][d] covering tables i-d..i; a level past the block start
    // repeats the one below it
//; # endif
//; if not UNROLL and LOOKAHEAD:
    // verilator lint_off UNOPTFLAT
//; # endif
    `ROLL`wire `decl(SYM_W, signed=False).ljust(decl_w)` `'comp'.ljust(name_w)` `cdim`;
//; if not UNROLL and LOOKAHEAD:
    // verilator lint_on UNOPTFLAT
//; # endif

    `ROLL`generate
    `ROLL`    for (genvar i = 0; i < `N_SYM`; i++) begin : gen_comp
    `ROLL`        for (genvar c = 0; c < `N_SPEC`; c++) begin : gen_entry
    `ROLL`            assign comp[i][0][c] = spec[i][c];
//; if LOOKAHEAD:
    `ROLL`            for (genvar d = 1; d <= `LOOKAHEAD`; d++) begin : gen_level
    `ROLL`                if (d <= i) begin : gen_step
    `ROLL`                    assign comp[i][d][c] = comp[i][d-1][`nxt(hi_c, 'spec[i-d][c]')`];
    `ROLL`                end
    `ROLL`                else begin : gen_alias
    `ROLL`                    assign comp[i][d][c] = comp[i][d-1][c];
    `ROLL`                end
    `ROLL`            end
//; # endif
    `ROLL`        end
    `ROLL`    end
    `ROLL`endgenerate

//; if UNROLL:
//;     for i in range(N_SYM):
//;         if first[i] < i:
    // symbol `i`: tables `first[i]`..`i`, generated from its own table outward
//;             for k in range(i - 1, first[i] - 1, -1):
//;                 src = f"spec[{i}]" if k == i - 1 else comp(k + 1, i)
    wire `decl(SYM_W, signed=False).ljust(decl_w)` `comp(k, i).ljust(name_w)` [0:`N_SPEC-1`];
//;                 for c in range(N_SPEC):
//;                     hi = lit(c % (1 << HI_W), HI_W, signed=False) if HI_W else ''
    assign `f"{comp(k, i)}[{c}]".ljust(lhs_w)` = `src`[`nxt(hi, f"spec[{k}][{c}]")`];
//;                 # endfor
//;             # endfor

//;         # endif
//;     # endfor
//; # endif
//; if PIPE_LA:
    // the tables one block late, so their look-ahead levels leave the path too
    reg  `decl(SYM_W, signed=False).ljust(decl_w)` `'ptab'.ljust(name_w)` `XDIM`;

//; # endif
//; # one select per symbol, the state is the last N_HIST symbols
//; if SELF_REF:
    // verilator lint_off UNOPTFLAT
//; # endif
    wire `decl(SYM_W, signed=False).ljust(decl_w)` `'sym'.ljust(name_w)` [0:`N_SYM-1`];
//; if SELF_REF:
    // verilator lint_on UNOPTFLAT
//; # endif
//; if STATE_REF:
    // verilator lint_off UNOPTFLAT
//; # endif
    wire `decl(STATE_W, signed=False).ljust(decl_w)` `'state'.ljust(name_w)` [0:`N_SYM-1`];
//; if STATE_REF:
    // verilator lint_on UNOPTFLAT
//; # endif
//; head = 'ptab[i]' if PIPE_LA else 'comp[i][i]'
//; roll = f"comp[i][{LOOKAHEAD}]"
//; tail = 'ptab[i]' if PIPE_LA else roll
//; hi_p = f"state_prev[{HI_W - 1}:0]" if HI_W else ''
//; hi_s = f"state[i-1][{HI_W - 1}:0]" if HI_W else ''

    `ROLL`generate
    `ROLL`    for (genvar i = 0; i <= `LOOKAHEAD`; i++) begin : gen_head
    `ROLL`        assign sym[i] = `head`[state_prev];
    `ROLL`    end
//; if SELF_REF:
    `ROLL`    for (genvar i = `LOOKAHEAD + 1`; i < `N_SYM`; i++) begin : gen_tail
    `ROLL`        assign sym[i] = `tail`[state[i-`LOOKAHEAD + 1`]];
    `ROLL`    end
//; # endif
    `ROLL`    assign state[0] = `nxt(hi_p, 'sym[0]')`;
    `ROLL`    for (genvar i = 1; i < `N_SYM`; i++) begin : gen_state
    `ROLL`        assign state[i] = `nxt(hi_s, 'sym[i]')`;
    `ROLL`    end
    `ROLL`endgenerate
//; if UNROLL:

//;     for i in range(N_SYM):
    assign `f"sym[{i}]".ljust(lhs_w)` = `table(i)`[`state(first[i] - 1)`];
//;     # endfor
//;     for i in range(N_SYM):
//;         hi = f"{state(i - 1)}[{HI_W - 1}:0]" if HI_W else ''
    assign `f"state[{i}]".ljust(lhs_w)` = `nxt(hi, f"sym[{i}]")`;
//;     # endfor
//; # endif

    `ROLL`wire `decl(RES_W, signed=False).ljust(decl_w)` resnxt;

    `ROLL`generate
    `ROLL`    for (genvar i = 0; i < `N_SYM`; i++) begin : gen_res
    `ROLL`        assign resnxt[i*`SYM_W` +: `SYM_W`] = sym[i];
    `ROLL`    end
    `ROLL`endgenerate
//; if UNROLL:

    wire `decl(RES_W, signed=False).ljust(decl_w)` `'resnxt'.ljust(name_w)` = {
//;     for i in reversed(range(N_SYM)):
//;         sep = ',' if i else ''
        sym[`i`]`sep`
//;     # endfor
    };
//; # endif

    always @(posedge clk or posedge reset) begin
        if (reset) begin
            `'res'.ljust(reg_w)` <= {`RES_W`{1'b0}};
            `'state_prev'.ljust(reg_w)` <= `lit(RST_STATE, STATE_W, signed=False)`;
//; if PIPE_LA:
            `'prime'.ljust(reg_w)` <= 1'b0;
            for (int i = 0; i < `N_SYM`; i++)
                for (int c = 0; c < `N_SPEC`; c++)
                    ptab[i][c] <= {`SYM_W`{1'b0}};
//; # endif
        end
        else begin
            `'res'.ljust(reg_w)` <= resnxt;
//; if PIPE_LA:
            `'state_prev'.ljust(reg_w)` <= prime ? `state(N_SYM-1)` : state_prev;
            `'prime'.ljust(reg_w)` <= 1'b1;
//; else:
            `'state_prev'.ljust(reg_w)` <= `state(N_SYM-1)`;
//; # endif
//; if PIPE_LA:
            `ROLL`for (int i = 0; i <= `LOOKAHEAD`; i++)
            `ROLL`    for (int c = 0; c < `N_SPEC`; c++) ptab[i][c] <= comp[i][i][c];
//;     if SELF_REF:
            `ROLL`for (int i = `LOOKAHEAD + 1`; i < `N_SYM`; i++)
            `ROLL`    for (int c = 0; c < `N_SPEC`; c++) ptab[i][c] <= `roll`[c];
//;     # endif
//;     if UNROLL:
//;         for i in range(N_SYM):
            for (int c = 0; c < `N_SPEC`; c++) ptab[`i`][c] <= `composed(i)`[c];
//;         # endfor
//;     # endif
//; # endif
        end
    end

endmodule
\`endif // `GUARD`
