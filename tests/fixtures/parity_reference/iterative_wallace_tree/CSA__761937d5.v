module CSA__U ( input logic [8:0] a,b,c, output logic[8:0] s, co); assign s = a ^ b ^c; assign co = a&b | b&c | a&c; endmodule
