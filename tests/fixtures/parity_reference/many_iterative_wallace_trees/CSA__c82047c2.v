module CSA__U13 ( input logic [69:0] a,b,c, output logic[69:0] s, co); assign s = a ^ b ^c; assign co = a&b | b&c | a&c; endmodule
