module CSA__U8 ( input logic [63:0] a,b,c, output logic[63:0] s, co); assign s = a ^ b ^c; assign co = a&b | b&c | a&c; endmodule
