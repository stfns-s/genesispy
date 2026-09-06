//; import math
//; IW   = parameter('IW',   8)   # input width
//; OW   = parameter('OW',   8)   # output width
//; MW   = parameter('MW',   4)   # mu factor width
//; ARST = parameter('ARST', 1)   # asynchronous reset
//; if IW < 2:
//;     error(f"{mname}: IW ({IW}) must be >= 2")
//; # endif
//; if MW < 1:
//;     error(f"{mname}: MW ({MW}) must be >= 1")
//; # endif
//; # out slices the accumulator, which holds IW integer bits and 2**MW below the input LSB
//; if OW < 1 or OW > IW + (1 << MW):
//;     error(f"{mname}: OW ({OW}) must be in 1..{IW + (1 << MW)}")
//; # endif
//; GUARD = f"__{mname.upper()}__"
\`ifndef `GUARD`
\`define `GUARD`
//
// iir filter: iir(n) = iir(n-1)*(1-f) + in*f
//             where f = 2**-mu * (1 + mf[1]/2 + mf[0]/4)
//      H(z) = f / [ 1 - (1-f)*z^-1 ]
//
//      Fclk/F3db ~= pi*(2**(mu+1)/(1 + mf/4) - 1):
//
//; for m in range(1, 1 << MW):
//;     f = 2.0 ** -m
//;     v = math.asin(f / (2.0 * math.sqrt(1.0 - f))) / math.pi
//      mu=`f"{m:02d}"` F3db=`f"{v:.4e}"`*Fclk - Fclk/F3db=`f"{1.0/v:.2f}"`
//; # endfor
module `mname` #(
        parameter       IW=`IW`,   // input width
        parameter       OW=`OW`,   // output width
        parameter       MW=`MW`    // mu factor width
    ) (
        output wire signed [OW-1:0] out,
        input  wire signed [IW-1:0] in,
        input  wire        [MW-1:0] mu, // exp filter factor ff=2**-mu (>0)
        input  wire        [1:0]    mf, // fractional factor: 00: 0.0, 01: 0.25, 10: 0.5, 11: 0.75
        input  wire                 en, clk, reset
    );

    localparam      FRAC_W = 2**MW;
    localparam      MWX = MW+1;

    // align/precondition
    wire            [MWX-1:0]       mu_int  = { 1'd0, mu };
    wire signed     [IW-1:-FRAC_W]     in_sx   = { in, {FRAC_W{1'b0}} };

    // state element
    reg   signed    [IW-1:-FRAC_W]     acc;

    // main factor
    wire            [MWX-1:0]       lm0     = mu_int;
    wire signed     [IW-1:-FRAC_W]     in_sh0  = in_sx >>> lm0;
    wire signed     [IW-1:-FRAC_W]     iir_sh0 = acc >>> lm0;

    // 1st fractional - shift arithmetic broken down to maintain >>> signed properties
    wire            [MWX-1:0]       lm1     = mu_int + 'd1;
    wire signed     [IW-1:-FRAC_W]     _in_sh1  = in_sx >>> lm1;
    wire signed     [IW-1:-FRAC_W]     _iir_sh1 = acc >>> lm1;
    wire signed     [IW-1:-FRAC_W]     in_sh1   = _in_sh1  & { (IW+FRAC_W) { mf[1] } };
    wire signed     [IW-1:-FRAC_W]     iir_sh1  = _iir_sh1 & { (IW+FRAC_W) { mf[1] } };

    // 2nd fractional
    wire            [MWX-1:0]       lm2     = mu_int + 'd2;
    wire signed     [IW-1:-FRAC_W]     _in_sh2  = in_sx >>> lm2;
    wire signed     [IW-1:-FRAC_W]     _iir_sh2 = acc >>> lm2;
    wire signed     [IW-1:-FRAC_W]     in_sh2   = _in_sh2  & { (IW+FRAC_W) { mf[0] } };
    wire signed     [IW-1:-FRAC_W]     iir_sh2  = _iir_sh2 & { (IW+FRAC_W) { mf[0] } };

    // feedback
    wire signed     [IW-1:-FRAC_W]     in_sh   = in_sh0  + in_sh1  + in_sh2;
    wire signed     [IW-1:-FRAC_W]     iir_sh  = iir_sh0 + iir_sh1 + iir_sh2;
    wire signed     [IW-1:-FRAC_W]     iir_res = acc - iir_sh;

//; if ARST:
    always @(posedge clk or posedge reset)
//; else:
    always @(posedge clk)
//; # endif
        if ( reset )
            acc <= 'd0;
        else
            acc <= en ? iir_res + in_sh : acc;

    assign  out = acc[IW-1:IW-OW];

endmodule
\`endif // `GUARD`
