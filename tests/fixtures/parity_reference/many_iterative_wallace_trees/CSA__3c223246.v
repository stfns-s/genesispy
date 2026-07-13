module CSA__U4 ( input logic [33:0] a,b,c, output logic[33:0] s, co); assign s = a ^ b ^c; assign co = a&b | b&c | a&c; endmodule
