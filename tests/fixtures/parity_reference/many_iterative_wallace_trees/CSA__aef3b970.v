module CSA__U21 ( input logic [131:0] a,b,c, output logic[131:0] s, co); assign s = a ^ b ^c; assign co = a&b | b&c | a&c; endmodule
