module flop__U( input logic Clk, input logic [7:0] data_in, output logic [7:0] data_out ); always @ (posedge Clk) begin data_out <= data_in; end endmodule
