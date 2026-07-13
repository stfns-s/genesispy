module CSA__U12 ( input logic [66:0] a,b,c, output logic[66:0] s, co); assign s = a ^ b ^c; assign co = a&b | b&c | a&c; endmodule
