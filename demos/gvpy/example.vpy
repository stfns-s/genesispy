// Demo for bin/gvpy.py running upstream-gvpy templates via genesispy.
// Adapted from gvpy/example.vpy. Exercises literal pass-through, backtick
// expressions, control flow, nested blocks, parameter, pp, and
// generate/instantiate.
//; WIDTH = parameter(name="WIDTH", val=8)
//; DEPTH = parameter(name="DEPTH", val=4)

module `mname()` #(
    parameter WIDTH = `WIDTH`,
    parameter DEPTH = `DEPTH`
) (
    input  wire                  clk,
    input  wire                  rst_n,
    input  wire [`WIDTH-1`:0]    data_in,
    output reg  [`WIDTH-1`:0]    data_out
);

    // Generated register bank
//; for i in range(DEPTH):
    reg [`WIDTH-1`:0] stage_`pp(i)`; // variable i value:`i` prety_printed: `pp(i, '%03d')`
//; # endfor

    // Initial values, conditional on index parity
//; for i in range(DEPTH):
//;     if i % 2 == 0:
    initial stage_`pp(i)` = `WIDTH`'h`pp(0xa0 + i, '%02x')`;
//;     else:
    initial stage_`pp(i)` = `WIDTH`'h`pp(0x50 + i, '%02x')`;
//;     # endif
//; # endfor

    // Pipeline shift
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
//; for i in range(DEPTH):
            stage_`pp(i)` <= '0;
//; # endfor
        end else begin
            stage_`pp(0)` <= data_in;
//; for i in range(1, DEPTH):
            stage_`pp(i)` <= stage_`pp(i-1)`;
//; # endfor
            data_out <= stage_`pp(DEPTH-1)`;
        end
    end


    // Sub-instances via generate + instantiate
    // One submod per pipeline stage; alternating MODE shows kwargs flowing
    // through to the /*PARAMS: ... */ banner that instantiate() emits.
//; subs = []
//; for i in range(DEPTH):
//;     subs.append(generate("submod", f"u_sub_{i}", WIDTH=WIDTH, STAGE=i, MODE=("fast" if i % 2 == 0 else "slow")))
//; # endfor

//; for s in subs:
//;     instantiate(s)
 (
        .clk   (clk),
        .rst_n (rst_n),
        .din   (stage_`pp(s.params['STAGE'])`),
        .dout  ()
    );
//; # endfor

    // Same instance written by hand for contrast: attribute access on the
    // _Inst wrapper (.tname / .iname / .params) instead of instantiate().
//; sub = generate("submod", "u_sub_manual", WIDTH=WIDTH, MODE="fast")
    `sub.tname` /*WIDTH=`sub.params['WIDTH']` MODE=`sub.params['MODE']`*/ `sub.iname` (
        .clk(clk),
        .rst_n(rst_n),
        .din(data_in),
        .dout()
    );

    // Literal backtick passthrough
    // escaped: \`not_an_expr\`

endmodule

// Minimal stub so the generated file elaborates standalone.
module submod #(
    parameter WIDTH = 8,
    parameter STAGE = 0
) (
    input  wire             clk,
    input  wire             rst_n,
    input  wire [WIDTH-1:0] din,
    output wire [WIDTH-1:0] dout
);
    assign dout = din;
endmodule
