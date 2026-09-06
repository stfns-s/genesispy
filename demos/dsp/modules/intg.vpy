//; OW         = parameter('OW',         8)          # output width
//; IW         = parameter('IW',         4)          # input width
//; MW         = parameter('MW',         4)          # mu (scaling factor) width
//; AW         = parameter('AW',         IW+(1<<MW)) # accumulator width
//; LW         = parameter('LW',         OW>>1)      # leak feedback width
//; NEG_APPROX = parameter('NEG_APPROX', 0)          # approximate negations (i.e. ~x instead of ~x+1)
//; ISYM       = parameter('ISYM',       0)          # input is symmetric 2's complement
//; DEBUG      = parameter('DEBUG',      0)          # reserved; no debug logic at present
//; if AW < OW:
//;     error(f"{mname}: AW ({AW}) must be >= OW ({OW})")
//; # endif
//; if AW < IW:
//;     error(f"{mname}: AW ({AW}) must be >= IW ({IW})")
//; # endif
//; if AW < LW:
//;     error(f"{mname}: AW ({AW}) must be >= LW ({LW})")
//; # endif
//; if OW < 2:
//;     error(f"{mname}: OW ({OW}) must be >= 2")
//; # endif
//; if LW < 2:
//;     error(f"{mname}: LW ({LW}) must be >= 2")
//; # endif
//; negp       = {'approx': NEG_APPROX, 'lifetime': 'automatic'}
//; GUARD      = f"__{mname.upper()}__"
\`ifndef `GUARD`
\`define `GUARD`
// integrator with exponentially controlled gain.
//  features: leak, clamping, load, freeze, reset
module `mname` #(
        parameter   OW=`OW`,    // output width
        parameter   IW=`IW`,    // input width
        parameter   MW=`MW`,    // mu (scaling factor) width
        parameter   AW=`AW`,    // accumulator width
        parameter   LW=`LW`,    // leak feedback width
        parameter   RSTV = { OW { 1'b0 } } // reset value
    ) (
        output wire signed [OW-1:0] out,        // integrator output
        input  wire signed [IW-1:0] in,         // update input
        input  wire signed [OW-1:0] ld_val,     // load value
        input  wire        [MW-1:0] mu, lk_mu,  // update and leak factors (constrain lk_mu > mu > 0)
        input  wire signed [OW-1:0] lim,        // limit integrator (+/-)
        input  wire                 lk_en,      // leaky integrator enable
        input  wire                 ld,         // load
        input  wire                 en,         // enable updates
        input  wire                 neg,        // negate input
        input  wire                 clk,
        input  wire                 reset
    );

//; if not ISYM:
//;     self.include_params = {'func_name': 'f_i_sym', 'iwidth': IW, 'lifetime': 'automatic'}
//;     include('f_sym.vpy')
//; # endif

//; self.include_params = dict(negp, func_name='f_i_negate', iwidth=IW, isym=1)
//; include('f_negate.vpy')

//; if ISYM:
    wire    signed [IW-1:0] insym = in;
//; else:
    wire    signed [IW-1:0] insym = f_i_sym(in);
//; # endif

    wire    signed [AW-1:0] fb  = { (neg ? f_i_negate(insym) : insym),  {(AW-IW) {1'b0}} };
    wire    signed [AW-1:0] ifb = fb >>> mu;

    reg        [AW-1:0] accum;
    assign          out     = accum[AW-1:AW-OW];

// the underflow clamp puts the most negative value in accum's top LW bits, so the leak
// feedback cannot promise a symmetric input the way the update path can
//; self.include_params = dict(negp, func_name='f_l_negate', iwidth=LW, isym=0)
//; include('f_negate.vpy')

    wire    signed [AW-1:0] lkfb    = lk_en ? { f_l_negate(accum[AW-1:AW-LW]), { AW-LW {1'b0} } } : { AW {1'b0} };
    wire    signed [AW-1:0] ilkfb   = lkfb >>> lk_mu;

    wire    signed [AW:0]   acsum   = {accum[AW-1], accum} + {ifb[AW-1], ifb} + { ilkfb[AW-1], ilkfb };


    // limit next value
    logic signed [AW-1:0] acnxt;
    logic signed [OW-1:0] onxt;

    localparam signed [AW-1:0] AMAX = { 1'b0, { {(OW-2) {1'b1}}, 1'b1 }, {(AW-OW) {1'b0}} };  // max accum
    localparam signed [AW-1:0] AMIN = { 1'b1, { {(OW-2) {1'b0}}, 1'b1 }, {(AW-OW) {1'b0}} };  // min output

    wire            ovf  = (acsum[AW:AW-1] == 2'b01);
    wire            udf  = (acsum[AW:AW-1] == 2'b10);
    logic           liml, limh;

    wire    signed  [AW-1:0]    liml_val, limh_val;

//; if AW == OW:
    assign limh_val =  lim;
    assign liml_val = -lim;
//; else:
    assign limh_val = {  lim, { {(AW-OW) {1'b0}}} };
    assign liml_val = { -lim, { {(AW-OW) {1'b0}}} };
//; # endif

    always @(*) begin // limit on over/underflow and if lim != 0
        if ( ld )
            acnxt = {ld_val, {(AW-OW) {1'b0}}};
        else
            case ({ovf, udf})
            2'b00 : acnxt = acsum[AW-1:0];
            2'b01 : acnxt = AMIN;
            2'b10 : acnxt = AMAX;
            2'b11 : acnxt = acsum[AW-1:0];
            endcase
        onxt  = acnxt[AW-1:AW-OW];
        liml = lim != 'd0 && (onxt < -lim);
        if ( liml ) acnxt = liml_val;
        limh = lim != 'd0 && (onxt >  lim);
        if ( limh ) acnxt = limh_val;
    end

    always @(posedge clk or posedge reset)
        if (reset)
            accum <= { RSTV , { AW-OW {1'b0} } };
        else
            accum <= (ld || en) ? acnxt : accum;

endmodule
\`endif
