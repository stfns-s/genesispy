module CSA__U9 ( input logic [65:0] a,b,c, output logic[65:0] s, co); assign s = a ^ b ^c; assign co = a&b | b&c | a&c; endmodule
