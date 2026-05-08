module CSA__U ( input logic [35:0] a,b,c, output logic[35:0] s, co); assign s = a ^ b ^c; assign co = a&b | b&c | a&c; endmodule
