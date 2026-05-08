module CSA__U ( input logic [67:0] a,b,c, output logic[67:0] s, co); assign s = a ^ b ^c; assign co = a&b | b&c | a&c; endmodule
