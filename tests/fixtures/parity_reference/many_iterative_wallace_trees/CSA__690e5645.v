module CSA__U26 ( input logic [32:0] a,b,c, output logic[32:0] s, co); assign s = a ^ b ^c; assign co = a&b | b&c | a&c; endmodule
