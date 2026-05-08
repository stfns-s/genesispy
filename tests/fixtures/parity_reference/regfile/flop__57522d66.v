module flop__U( input logic Clk, input logic [31:0] data_in, input logic Enable, output logic [31:0] data_out ); always @ (posedge Clk) begin if (Enable) data_out <= data_in; end endmodule
