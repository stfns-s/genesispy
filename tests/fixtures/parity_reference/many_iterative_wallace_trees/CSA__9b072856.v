module CSA__U17 ( input logic [128:0] a,b,c, output logic[128:0] s, co); assign s = a ^ b ^c; assign co = a&b | b&c | a&c; endmodule
